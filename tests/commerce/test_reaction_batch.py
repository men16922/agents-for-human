import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_external_batch import comparison_factory
from test_model_runner import setup as setup

from rehearsal.commerce.learning_budget import BudgetCarryover
from rehearsal.commerce.model_runner import digest
from rehearsal.commerce.observations import ObservationJournal
from rehearsal.commerce.reaction import ReactionSettings
from rehearsal.evaluation import batch, external_batch
from rehearsal.experiments.b3 import BuyerFixture
from rehearsal.experiments.policy import Policy
from rehearsal.world.storage import canonical

ROOT = Path(__file__).parents[2]


def rehash(manifest):
    manifest["id"] = (
        "batch-"
        + hashlib.sha256(
            canonical({k: v for k, v in manifest.items() if k != "id"}).encode()
        ).hexdigest()
    )
    return manifest


def prepare(setup, reactions=ReactionSettings(8), **limits):
    path = setup[1].parent / "reaction-batch"
    training, cases = batch.generated_known_cases(ROOT, 1)
    cases["case-01"]["goal"] = setup[4]["goal"] | {"budget": 500}
    manifest = batch.prepare(
        path,
        training,
        cases,
        1,
        replace(setup[5], **limits),
        500000,
        "offline-scripted-model",
        evaluation_environment="external-medusa",
        external_reactions=reactions,
    )
    return path, manifest


def public_observation_client(setup):
    """SDK wiring fixture. Trade attestation still uses the independent retained raw export."""
    client = setup[6]
    original = client.request
    journal = ObservationJournal(setup[1].parent / "journal", [client.run_id])

    def detailed():
        value = original("GET", "snapshot")
        value["commerce"] = {
            "receipt_status": "OBSERVED",
            "catalog": {"status": "OBSERVED", "source": "medusa-store-sales-channel", "offers": []},
            "orders": {"status": "OBSERVED", "total": 0, "truncated": False, "items": []},
        }
        return value

    def request(method, route, body=None):
        if route == "snapshot?details=true":
            return detailed()
        if route.startswith("observations?"):
            snapshot = detailed()
            journal.record(client.run_id, snapshot, 1000 + snapshot["tick"])
            journal.publish(1000 + snapshot["tick"])
            return journal.read(client.run_id, int(route.split("=")[1]), 1000 + snapshot["tick"])
        return original(method, route, body)

    client.request = request
    return client


@pytest.mark.parametrize("method", ["B1", "B2", "B3"])
def test_reactive_model_arms_execute_from_frozen_settings_and_reuse_learning_ledger(setup, method):
    path, manifest = prepare(setup)
    cell = f"case-01-{method}-r1"
    learned = external_batch.learn(path, cell, comparison_factory)
    historical = copy.deepcopy(learned["total_usage"])
    carry = BudgetCarryover(
        path / "runs" / cell / "learning",
        path / "runs" / cell / "policy.json",
        setup[5],
        "offline-scripted-model",
        method,
    )
    model = BuyerFixture(carry.frozen.policy)
    external_batch.execute(path, cell, model, public_observation_client(setup))
    final = external_batch.settle(path, cell, setup[2])
    selected = next(c for c in final["cells"] if c["id"] == cell)
    assert selected["external_transaction_verified"] and selected["reaction_execution_verified"]
    assert final["planned"] == 4 and final["status_counts"] == {
        "NOT_RUN": 3,
        "EXTERNAL_VERIFIED": 1,
    }
    assert final["external_reactions"] == manifest["external_reactions"]
    assert final["held_micro_usd"] == 0 and not final["model_efficacy_verified"]
    result = json.loads((path / "runs" / cell / "execution/report.json").read_text())
    assert result["reactions"]["settings"] == {"max_replans": 8}
    for key in ("calls", "tool_admissions", "admission_rejections"):
        assert result["usage"][key][: len(historical[key])] == historical[key]
    assert len(result["usage"]["calls"]) == len(historical["calls"]) + model.calls
    assert all(c["role"] == "buyer_evaluation" for c in result["execution_usage"]["calls"])
    assert final["recorded_micro_usd"] == historical["recorded_micro_usd"] + 392
    assert batch.reaction_for(manifest, "B0") is None


def test_b0_keeps_fixed_rules_zero_model_calls_and_no_reaction_in_reactive_roster(setup):
    path, _ = prepare(setup)
    cell = "case-01-B0-r1"
    external_batch.learn(path, cell, lambda *_: pytest.fail("B0 model factory"))
    external_batch.execute(path, cell, None, setup[6])
    report = external_batch.settle(path, cell, setup[2])
    selected = next(c for c in report["cells"] if c["id"] == cell)
    assert selected["reaction_settings"] is None and not selected["reaction_execution_verified"]
    assert selected["external_transaction_verified"] and report["recorded_micro_usd"] == 0
    assert not (path / "runs" / cell / "execution/observations.jsonl").exists()


@pytest.mark.parametrize(
    "damage", ["B0", "mixed", "missing", "extra", "bool", "zero", "oversize", "practice"]
)
def test_invalid_or_unequal_reaction_policy_rejects_even_with_recomputed_manifest_hash(
    setup, damage
):
    path, manifest = prepare(setup)
    policy = manifest["external_reactions"]
    if damage == "B0":
        policy["B0"] = {"max_replans": 8}
    elif damage == "mixed":
        policy["B2"] = None
    elif damage == "missing":
        del policy["B3"]
    elif damage == "extra":
        policy["B1"]["max_model_calls"] = 999
    elif damage == "practice":
        manifest["evaluation_environment"] = "practice"
    else:
        for method in ("B1", "B2", "B3"):
            policy[method] = {"max_replans": {"bool": True, "zero": 0, "oversize": 33}[damage]}
    (path / "manifest.json").write_text(json.dumps(rehash(manifest)))
    with pytest.raises(ValueError):
        external_batch.learn(path, "case-01-B1-r1", lambda *_: pytest.fail("model factory"))
    assert not (path / "runs").exists() and setup[3] == []


def test_learning_contract_cannot_switch_reaction_limit_before_http(setup):
    path, _ = prepare(setup)
    cell = "case-01-B1-r1"
    external_batch.learn(path, cell, comparison_factory)
    cp = path / "runs" / cell
    spec = json.loads((cp / "batch-spec.json").read_text())
    spec["reaction_settings"]["max_replans"] = 1
    (cp / "batch-spec.json").write_text(json.dumps(spec))
    report = json.loads((cp / "report.json").read_text())
    report["batch_spec_sha256"] = digest(cp / "batch-spec.json")
    (cp / "report.json").write_text(json.dumps(report))
    model = BuyerFixture(Policy())
    with pytest.raises(ValueError, match="cell contract changed"):
        external_batch.execute(path, cell, model, setup[6])
    assert model.calls == 0 and setup[3] == []


@pytest.mark.parametrize("target", ["spec", "runtime", "missing_observations"])
def test_changed_reaction_runtime_cannot_settle_or_release_reserved_budget(setup, target):
    path, _ = prepare(setup)
    cell = "case-01-B1-r1"
    external_batch.learn(path, cell, comparison_factory)
    carry = BudgetCarryover(
        path / "runs" / cell / "learning",
        path / "runs" / cell / "policy.json",
        setup[5],
        "offline-scripted-model",
        "B1",
    )
    external_batch.execute(
        path, cell, BuyerFixture(carry.frozen.policy), public_observation_client(setup)
    )
    cp = path / "runs" / cell / "execution"
    if target == "spec":
        spec = json.loads((cp / "spec.json").read_text())
        spec["reaction_settings"] = None
        (cp / "spec.json").write_text(json.dumps(spec))
    elif target == "runtime":
        runtime = json.loads((cp / "report.json").read_text())
        runtime["reactions"]["settings"] = {"max_replans": 1}
        (cp / "report.json").write_text(json.dumps(runtime))
    else:
        (cp / "observations.jsonl").unlink()
    before = external_batch.summarize(path)
    with pytest.raises((ValueError, FileNotFoundError)):
        external_batch.settle(path, cell, setup[2])
    after = external_batch.summarize(path)
    assert after["held_micro_usd"] == before["held_micro_usd"] > 0
    assert after["planned"] == 4


def test_historical_nonreactive_manifest_and_retained_results_are_unchanged():
    path = ROOT / "tests/fixtures/notifications-batch"
    manifest = batch.load(path)
    assert "external_reactions" not in manifest
    assert all(batch.reaction_for(manifest, m) is None for m in ("B0", "B1", "B2", "B3"))
    assert external_batch.summarize(path) == json.loads((path / "report.json").read_text())


@pytest.mark.parametrize("mode", ["--learn", "--execute", "--settle", "--report"])
def test_cli_reaction_override_is_rejected_before_settings_or_model(mode, monkeypatch):
    monkeypatch.setattr("sys.argv", ["external-batch", mode, "unused", "--max-replans", "8"])
    monkeypatch.setattr(external_batch, "read_settings", lambda *_: pytest.fail("settings"))
    with pytest.raises(SystemExit) as exc:
        external_batch.main()
    assert exc.value.code == 2


def test_reaction_settings_are_rejected_by_practice_prepare_without_creating_files(setup):
    training, cases = batch.generated_known_cases(ROOT, 1)
    path = setup[1].parent / "invalid-practice"
    with pytest.raises(ValueError, match="external Medusa"):
        batch.prepare(
            path,
            training,
            cases,
            1,
            setup[5],
            500000,
            "offline-scripted-model",
            external_reactions=ReactionSettings(8),
        )
    assert not path.exists()


def test_reactive_b3_cannot_reset_the_call_limit_already_used_by_learning(setup):
    path, _ = prepare(setup, max_model_calls=23)
    cell = "case-01-B3-r1"
    learned = external_batch.learn(path, cell, comparison_factory)
    assert len(learned["total_usage"]["calls"]) == 22
    model = BuyerFixture(Policy())
    result = external_batch.execute(path, cell, model, public_observation_client(setup))
    assert result["runtime_status"] == "LIMITED" and model.calls == 1
    assert len(result["total_usage"]["calls"]) == 23
    assert not any(m == "POST" for m, _ in setup[3])
    final = external_batch.settle(path, cell, setup[2])
    assert final["status_counts"] == {"NOT_RUN": 3, "EXTERNAL_INCOMPLETE": 1}
    assert final["recorded_micro_usd"] == 644 and final["held_micro_usd"] == 0
    assert final["methods"]["B3"]["reaction_execution_verified"] == 0


def test_reactive_b3_missing_usage_keeps_batch_reservation_and_denominator(setup):
    path, _ = prepare(setup)
    cell = "case-01-B3-r1"
    external_batch.learn(path, cell, comparison_factory)

    class Missing(BuyerFixture):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                if "metadata" not in event:
                    yield event

    model = Missing(Policy())
    external_batch.execute(path, cell, model, public_observation_client(setup))
    assert model.calls == 1
    final = external_batch.settle(path, cell, setup[2])
    assert final["status_counts"] == {"NOT_RUN": 3, "EXTERNAL_INCOMPLETE": 1}
    assert final["recorded_micro_usd"] == 616 and final["held_micro_usd"] == 100000 - 616
    with pytest.raises(ValueError, match="UNRESOLVED_USAGE"):
        external_batch.learn(path, "case-01-B1-r1", lambda *_: pytest.fail("unresolved spend"))
