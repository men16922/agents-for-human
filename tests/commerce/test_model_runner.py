import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.commerce.model_runner import attest, configuration, digest, execute_http
from rehearsal.experiments.b3 import BuyerFixture
from rehearsal.experiments.frozen import freeze
from rehearsal.experiments.policy import Policy
from rehearsal.operating.client import OperatingClient

ROOT = Path(__file__).parents[2]
RETAINED = ROOT / "evidence/cw05-b0-rerun/revised-price-loss/medusa"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    recorded = json.loads((RETAINED / "report.json").read_text())
    evidence = json.loads((RETAINED / "evidence.json").read_text())
    binding = evidence["binding"]
    trace = recorded["executor"]["trace"]
    initial = copy.deepcopy(trace[0]["result"])
    final = recorded["executor"]["snapshot"]
    quotes = {t["result"]["supplier"]: t["result"] for t in trace if t["tool"] == "get_quotes"}
    order = next(t["result"] for t in trace if t["tool"] == "create_order")
    calls = []
    paid = False

    def handler(request):
        nonlocal paid
        calls.append((request.method, request.url.path))
        assert request.headers["Authorization"] == "Bearer local-buyer-fixture-only"
        path = request.url.path
        if request.method == "GET" and path.endswith("/snapshot"):
            value = final if paid else initial
        elif request.method == "GET" and "/payments/" in path:
            value = next(t["result"] for t in reversed(trace) if t["tool"] == "get_payment")
        elif request.method == "GET" and "/orders/" in path:
            value = next(t["result"] for t in reversed(trace) if t["tool"] == "get_order")
        elif path.endswith("/quotes"):
            value = quotes[json.loads(request.content)["supplier"]]
        elif path.endswith("/orders"):
            value = order
        elif path.endswith("/payments"):
            paid = True
            raise httpx.ReadTimeout("Retained payment response loss", request=request)
        else:
            pytest.fail(f"Unexpected HTTP: {request.method} {path}")
        return httpx.Response(200, json=copy.deepcopy(value))

    client = OperatingClient(
        "http://127.0.0.1:18001", binding["run_id"], "local-buyer-fixture-only"
    )
    client.http.close()
    client.http = httpx.Client(
        base_url="http://127.0.0.1:18001",
        headers={"Authorization": "Bearer local-buyer-fixture-only"},
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr("rehearsal.operating.tools.time.sleep", lambda _: None)
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-b3-fixture",
        RateCard("1", "2", "0", "0", "fictional SDK rates"),
        100000,
        max_model_calls=48,
        max_tool_calls=48,
    )
    frozen = freeze(Policy(), tmp_path / "policy.json", ROOT)
    directory = tmp_path / "execution"
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "run_id": binding["run_id"],
                "expected_goal": binding["goal"],
                "expected_budget": binding["budget"],
                "artifact_path": str(RETAINED / "evidence.json"),
                "sha256": digest(RETAINED / "evidence.json"),
            }
        )
    )

    def run(model=None, **limits):
        return execute_http(
            model or BuyerFixture(Policy()),
            replace(settings, **limits),
            client,
            directory,
            copy.deepcopy(binding["goal"]),
            binding["budget"],
            frozen,
            "offline-scripted-model",
        )

    yield run, directory, selection, calls, initial, settings, client, frozen
    client.close()


def test_http_runtime_completion_requires_separate_independent_transaction_evidence(setup):
    run, directory, selection, calls, _, _, _, _ = setup
    result = run()
    assert result["runtime_status"] == "COMPLETED" and result["runtime_accounted"]
    assert result["transaction_status"] == "NOT_VERIFIED" and not result["success"]
    assert result["scope_check_reads"] == 8
    assert all("/admin/" not in p for _, p in calls)
    assert sum(m == "POST" and p.endswith("/payments") for m, p in calls) == 1
    assert result["usage"]["recorded_micro_usd"] == 392
    assert all(c["role"] == "executor" for c in result["usage"]["calls"])
    verdict = attest(directory, selection)
    assert verdict["success"] and verdict["orders_match_execution"]
    assert verdict["evidence_review"]["verdict"]["spent"] == 380
    assert not verdict["model_efficacy_verified"]
    assert "local-buyer-fixture-only" not in "".join(
        p.read_text() for p in directory.glob("*.json*")
    )
    assert not (directory / "shop.sqlite3").exists()
    count = len(calls)
    with pytest.raises(FileExistsError):
        run()
    assert len(calls) == count


@pytest.mark.parametrize("field", ["goal", "run", "budget", "reserved", "received", "deadline"])
def test_wrong_or_used_external_run_is_rejected_before_model_call(setup, field):
    run, path, _, calls, initial, _, _, _ = setup
    if field == "goal":
        initial["goal"]["recipient"] = "elsewhere"
    elif field == "run":
        initial["run_id"] = "other"
    elif field == "budget":
        initial["balance"]["budget"] += 1
    elif field == "reserved":
        initial["balance"]["reserved"] = 10
    elif field == "received":
        initial["inventory"]["tent"] = 1
    else:
        initial["tick"] = initial["goal"]["deadline_tick"]
    model = BuyerFixture(Policy())
    result = run(model)
    assert model.calls == 0 and not result["runtime_accounted"]
    assert len(calls) == 1 and result["transaction_status"] == "NOT_VERIFIED"
    assert (path / "report.json").exists()


def test_changed_scope_before_write_stops_model_and_sends_no_mutation(setup):
    run, _, _, calls, initial, _, _, _ = setup

    class Change(BuyerFixture):
        async def stream(self, *args, **kwargs):
            if self.calls == 1:
                initial["goal"]["recipient"] = "elsewhere"
            async for event in super().stream(*args, **kwargs):
                yield event

    model = Change(Policy())
    result = run(model)
    assert result["stop_reason"] == "HTTP_RUN_CONTRACT_CHANGED"
    assert model.calls == 2 and not any(m == "POST" for m, _ in calls)


def test_missing_raw_usage_retains_reservation_and_never_proves_success(setup):
    run, path, selection, calls, _, _, _, _ = setup

    class Missing(BuyerFixture):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                if "metadata" not in event:
                    yield event

    result = run(Missing(Policy()))
    assert not result["usage"]["all_usage_recorded"]
    assert result["usage"]["unresolved_reserved_micro_usd"] > 0
    assert not result["runtime_accounted"]
    assert not any(m == "POST" for m, _ in calls)
    assert not attest(path, selection)["success"]


@pytest.mark.parametrize("limit", [{"max_model_calls": 1}, {"max_tool_calls": 1}])
def test_common_limits_stop_http_execution_without_reset(setup, limit):
    run, _, _, calls, _, _, _, _ = setup
    result = run(**limit)
    assert result["runtime_status"] == "LIMITED"
    assert not result["runtime_accounted"] and not any(m == "POST" for m, _ in calls)


@pytest.mark.parametrize("file", ["report.json", "spec.json", "tools.jsonl"])
def test_evidence_review_rejects_mutated_execution_artifact(setup, file):
    run, path, selection, _, _, _, _, _ = setup
    run()
    (path / file).write_text((path / file).read_text() + " ")
    with pytest.raises(ValueError):
        attest(path, selection)


def test_other_goal_evidence_selection_is_rejected(setup):
    run, path, selection, _, _, _, _, _ = setup
    run()
    value = json.loads(selection.read_text())
    value["expected_goal"]["recipient"] = "elsewhere"
    selection.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="contract mismatch"):
        attest(path, selection)


def test_buyer_config_rejects_admin_credentials_and_duplicate_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"run_id":"one", "run_id":"two"}')
    with pytest.raises(ValueError, match="Duplicate"):
        configuration(path)
    path.write_text(json.dumps({"admin_token": "never-accepted"}))
    with pytest.raises(ValueError, match="Only buyer"):
        configuration(path)


def test_truncated_model_response_cannot_be_promoted_by_complete_medusa_evidence(setup):
    run, path, selection, _, _, _, _, _ = setup

    class Truncated(BuyerFixture):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                if event.get("messageStop", {}).get("stopReason") == "end_turn":
                    event = {"messageStop": {"stopReason": "max_tokens"}}
                yield event

    result = run(Truncated(Policy()))
    assert result["runtime_status"] == "ERROR" and result["usage"]["all_usage_recorded"]
    reviewed = attest(path, selection)
    assert reviewed["transaction_verified"] and reviewed["orders_match_execution"]
    assert not reviewed["success"]


def test_complete_evidence_for_same_run_cannot_claim_an_unobserved_purchase(setup, monkeypatch):
    run, path, selection, _, _, _, _, _ = setup
    run()
    # A changed but internally consistent export renames the local purchase/intent link.
    evidence = json.loads((RETAINED / "evidence.json").read_text())
    previous = evidence["tables"]["purchases"][0]["id"]
    evidence["tables"]["purchases"][0]["id"] = "different-execution-order"
    for intent in evidence["tables"]["intents"]:
        if intent["order_id"] == previous:
            intent["order_id"] = "different-execution-order"
    altered = path.parent / "different.json"
    altered.write_text(json.dumps(evidence))
    chosen = json.loads(selection.read_text())
    chosen.update(artifact_path=str(altered), sha256=digest(altered))
    selection.write_text(json.dumps(chosen))
    result = attest(path, selection)
    assert result["transaction_verified"]
    assert not result["orders_match_execution"] and not result["success"]


@pytest.mark.parametrize("damage", ["delete", "edit"])
def test_spec_change_during_execution_retains_error_report(setup, damage):
    run, path, _, _, _, _, _, _ = setup

    class Change(BuyerFixture):
        async def stream(self, *args, **kwargs):
            if not self.calls:
                if damage == "delete":
                    (path / "spec.json").unlink()
                else:
                    (path / "spec.json").write_text("{}")
            async for event in super().stream(*args, **kwargs):
                yield event

    result = run(Change(Policy()))
    assert result["error_code"] == "EXECUTION_INPUT_CHANGED"
    assert not result["runtime_accounted"]
    assert json.loads((path / "report.json").read_text()) == result


def test_cli_preflight_constructs_neither_http_nor_aws_client(setup, monkeypatch, capsys):
    from rehearsal.commerce import model_runner

    _, directory, selection, _, _, settings, _, _ = setup
    chosen = json.loads(selection.read_text())
    config = directory.parent / "config.json"
    config.write_text(
        json.dumps(
            {
                "run_id": chosen["run_id"],
                "buyer_token": "local-buyer-fixture-only",
                "expected_goal": chosen["expected_goal"],
                "expected_budget": chosen["expected_budget"],
                "policy_path": "policy.json",
            }
        )
    )
    monkeypatch.setattr(model_runner, "read_settings", lambda _: settings)
    monkeypatch.setattr(model_runner, "OperatingClient", lambda *a: pytest.fail("HTTP client"))
    monkeypatch.setattr(model_runner, "bedrock_model", lambda *a: pytest.fail("AWS client"))
    monkeypatch.setattr("sys.argv", ["model_runner", "--config", str(config)])
    assert model_runner.main() == 0
    assert "local-buyer-fixture-only" not in capsys.readouterr().out
    assert not directory.exists()


def learning_handoff(setup, **limits):
    from rehearsal.commerce.learning_budget import B3Carryover, prepare
    from rehearsal.experiments.b3 import ReviewerFixture, run_b3

    _, directory, selection, _, _, settings, client, _ = setup
    settings = replace(settings, **limits)
    learning = directory.parent / "learning"
    scenario = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    result = run_b3(
        BuyerFixture,
        lambda _: ReviewerFixture(),
        settings,
        learning,
        scenario,
        "offline-scripted-model",
    )
    assert result["status"] == "CANDIDATE_EVALUATED_NOT_PROMOTED", result.get("error")
    frozen_path = directory.parent / "learned-policy.json"
    frozen = prepare(learning, frozen_path, settings, "offline-scripted-model")
    carry = B3Carryover(learning, frozen_path, settings, "offline-scripted-model")
    chosen = json.loads(selection.read_text())

    def run(model=None):
        return execute_http(
            model or BuyerFixture(frozen.policy),
            settings,
            client,
            directory,
            chosen["expected_goal"],
            chosen["expected_budget"],
            frozen,
            "offline-scripted-model",
            carryover=carry,
        )

    return carry, run, settings


def test_b3_learning_and_http_share_original_cost_tokens_tools_and_one_slot(setup):
    carry, run, _ = learning_handoff(setup)
    initial = carry.accounting()
    assert initial["planned_external_runs"] == 1 and initial["attempted_external_runs"] == 0
    assert initial["external_state"]["state"] == "NOT_RUN"
    result = run()
    assert result["runtime_accounted"]
    assert result["usage"]["recorded_micro_usd"] == 1008
    assert result["usage"]["recorded_total_tokens"] == 720
    assert result["usage"]["admitted_tool_calls"] == 31
    assert result["execution_usage"]["recorded_micro_usd"] == 392
    assert result["execution_usage"]["recorded_total_tokens"] == 280
    assert len(result["execution_usage"]["calls"]) == 14
    assert all(c["role"] == "buyer_evaluation" for c in result["execution_usage"]["calls"])
    assert result["learning_budget"]["learning_usage"] == initial["learning_usage"]
    assert result["usage"]["calls"][:22] == initial["learning_usage"]["calls"]
    assert result["learning_budget"]["external_state"]["state"] == "COMPLETED"
    assert not (setup[1] / "usage.sqlite3").exists()
    assert attest(setup[1], setup[2])["success"]
    assert not result["model_efficacy_verified"]


@pytest.mark.parametrize(
    "limits",
    [
        {"max_model_calls": 22},
        {"max_tool_calls": 18},
        {"budget_micro_usd": 10636},
        {"max_total_tokens": 9444},
    ],
)
def test_b3_consumed_limits_are_not_reset_by_http_start(setup, limits):
    carry, run, _ = learning_handoff(setup, **limits)
    result = run()
    assert not result["runtime_accounted"]
    assert result["runtime_status"] == "LIMITED"
    assert not any(m == "POST" for m, _ in setup[3])
    assert result["usage"]["admitted_tool_calls"] == 18
    if "max_model_calls" in limits:
        assert result["execution_usage"]["calls"] == []
        assert result["usage"]["recorded_micro_usd"] == 616
    assert carry.accounting()["attempted_external_runs"] == 1


def test_b3_zero_model_attempt_is_retained_and_cannot_be_retried(setup):
    from rehearsal.world.storage import ContractError

    carry, run, _ = learning_handoff(setup)
    setup[4]["balance"]["reserved"] = 1
    result = run()
    assert result["execution_usage"]["calls"] == []
    assert not result["runtime_accounted"]
    assert carry.accounting()["external_state"]["state"] == "ERROR"
    with pytest.raises(ContractError, match="ALREADY_RETAINED"):
        carry.claim("another-run", setup[1].parent / "another-execution")
    assert carry.accounting()["attempted_external_runs"] == 1


@pytest.mark.parametrize("target", ["policy", "artifact", "ledger", "missing-ledger"])
def test_b3_handoff_rejects_changed_or_missing_history_before_http(setup, target):
    import sqlite3

    from rehearsal.commerce.learning_budget import B3Carryover
    from rehearsal.world.storage import ContractError

    carry, _, settings = learning_handoff(setup)
    if target == "policy":
        carry.policy_path.write_text(carry.policy_path.read_text() + " ")
        with pytest.raises(ContractError, match="ARTIFACT_CHANGED"):
            carry.check()
    else:
        if target == "artifact":
            path = carry.directory / "initial/experiment.json"
            path.write_text(path.read_text() + " ")
        elif target == "ledger":
            with carry.ledger.connect() as db:
                db.execute("UPDATE model_calls SET estimated_micro_usd=0 WHERE id=1")
        else:
            carry.ledger.path.unlink()
        with pytest.raises((ContractError, sqlite3.OperationalError)):
            B3Carryover(carry.directory, carry.policy_path, settings, "offline-scripted-model")
        if target == "missing-ledger":
            assert not carry.ledger.path.exists()
    assert setup[3] == []


@pytest.mark.parametrize(
    "change",
    [
        {"max_model_calls": 49},
        {"max_tool_calls": 49},
        {"max_total_tokens": 99999},
        {"budget_micro_usd": 100001},
    ],
)
def test_b3_budget_settings_cannot_be_increased_or_replaced_on_resume(setup, change):
    from rehearsal.commerce.learning_budget import B3Carryover

    carry, _, settings = learning_handoff(setup)
    with pytest.raises(ValueError):
        B3Carryover(
            carry.directory,
            carry.policy_path,
            replace(settings, **change),
            "offline-scripted-model",
        )
    assert setup[3] == []


def test_b3_mid_execution_learning_change_stops_tools_and_next_model_call(setup):
    carry, run, _ = learning_handoff(setup)

    class Change(BuyerFixture):
        async def stream(self, *args, **kwargs):
            if not self.calls:
                path = carry.directory / "initial/experiment.json"
                path.write_text(path.read_text() + " ")
            async for event in super().stream(*args, **kwargs):
                yield event

    model = Change(carry.frozen.policy)
    result = run(model)
    assert model.calls == 1
    assert not result["runtime_accounted"]
    assert not any(m == "POST" for m, _ in setup[3])
    assert result["error_code"] == "B3_LEARNING_ARTIFACT_CHANGED"


def test_b3_unknown_external_usage_keeps_original_reservation_and_failed_slot(setup):
    carry, run, _ = learning_handoff(setup)

    class Missing(BuyerFixture):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                if "metadata" not in event:
                    yield event

    result = run(Missing(carry.frozen.policy))
    assert result["usage"]["recorded_micro_usd"] == 616
    assert result["usage"]["unresolved_reserved_micro_usd"] > 0
    assert result["error_code"] == "B3_USAGE_UNRESOLVED"
    assert result["learning_budget"]["attempted_external_runs"] == 1
    assert not result["runtime_accounted"]


def test_learned_policy_cannot_silently_start_with_a_new_budget(setup, monkeypatch):
    from rehearsal.commerce import model_runner
    from rehearsal.world.storage import ContractError

    carry, _, settings = learning_handoff(setup)
    chosen = json.loads(setup[2].read_text())
    config = setup[1].parent / "buyer-config.json"
    config.write_text(
        json.dumps(
            {
                "run_id": chosen["run_id"],
                "buyer_token": "local-buyer-fixture-only",
                "expected_goal": chosen["expected_goal"],
                "expected_budget": chosen["expected_budget"],
                "policy_path": str(carry.policy_path),
            }
        )
    )
    with pytest.raises(ContractError, match="LEARNING_BUDGET_REQUIRED"):
        execute_http(
            BuyerFixture(carry.frozen.policy),
            settings,
            setup[6],
            setup[1],
            chosen["expected_goal"],
            chosen["expected_budget"],
            carry.frozen,
            "offline-scripted-model",
        )
    monkeypatch.setattr("sys.argv", ["model_runner", "--config", str(config), "--execute"])
    monkeypatch.setattr(model_runner, "bedrock_model", lambda *a: pytest.fail("AWS client"))
    with pytest.raises(ContractError, match="LEARNING_BUDGET_REQUIRED"):
        model_runner.main()
    assert setup[3] == [] and not setup[1].exists()


def test_reopened_zero_call_attempt_still_cannot_be_started(setup):
    from rehearsal.commerce.learning_budget import B3Carryover
    from rehearsal.world.storage import ContractError

    carry, _, settings = learning_handoff(setup)
    carry.claim("interrupted-before-first-call", setup[1])
    assert carry.accounting()["external_state"]["state"] == "STARTED"
    with pytest.raises(ContractError, match="ALREADY_RETAINED"):
        B3Carryover(carry.directory, carry.policy_path, settings, "offline-scripted-model")
    assert carry.accounting()["total_usage"] == carry.baseline
