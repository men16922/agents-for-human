import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from test_model_runner import setup as setup

from rehearsal.commerce.learning_budget import B3Carryover
from rehearsal.evaluation import batch, external_batch
from rehearsal.experiments.b2 import SimulationFixture
from rehearsal.experiments.b3 import BuyerFixture, ReviewerFixture
from rehearsal.experiments.policy import Policy

ROOT = Path(__file__).parents[2]
CELL = "case-01-B3-r1"


def factory(kind, policy):
    return ReviewerFixture() if kind == "reviewer" else BuyerFixture(policy)


@pytest.fixture
def roster(setup):
    path = setup[1].parent / "external-batch"
    training, cases = batch.generated_known_cases(ROOT, 2)
    for case in cases.values():
        case["goal"] = setup[4]["goal"] | {"budget": 500}

    def prepare(budget=500000, **limits):
        return batch.prepare(
            path,
            training,
            cases,
            1,
            replace(setup[5], **limits),
            budget,
            "offline-scripted-model",
            evaluation_environment="external-medusa",
        )

    return path, prepare


def run_external(setup, roster, model=None):
    path, _ = roster
    external_batch.learn(path, CELL, factory)
    policy = B3Carryover(
        path / "runs" / CELL / "learning",
        path / "runs" / CELL / "policy.json",
        setup[5],
        "offline-scripted-model",
    ).frozen.policy
    return external_batch.execute(path, CELL, model or BuyerFixture(policy), setup[6])


def test_external_roster_cannot_be_executed_or_reported_as_a_practice_batch(roster):
    path, prepare = roster
    prepare()
    assert external_batch.summarize(path)["status_counts"] == {"NOT_RUN": 8}
    with pytest.raises(ValueError, match="External roster"):
        batch.run_pending(path, lambda *_: pytest.fail("model call"))
    with pytest.raises(ValueError, match="External roster"):
        batch.summarize(path)


def test_entire_cell_budget_is_reserved_before_learning_factory_runs(roster):
    path, prepare = roster
    prepare()

    def inspect(kind, policy):
        report = external_batch.summarize(path)
        assert report["held_micro_usd"] == 100000
        assert report["planned"] == 8
        return factory(kind, policy)

    result = external_batch.learn(path, CELL, inspect)
    assert result["status"] == "WAITING_EXTERNAL"
    report = external_batch.summarize(path)
    assert report["recorded_micro_usd"] == 616
    assert report["held_micro_usd"] == 99384
    assert report["status_counts"] == {"NOT_RUN": 7, "WAITING_EXTERNAL": 1}
    with pytest.raises(ValueError, match="UNRESOLVED_ATTEMPT"):
        external_batch.learn(path, "case-02-B3-r1", lambda *_: pytest.fail("second learner"))


def test_independent_external_settlement_retains_all_arms_and_releases_only_remaining_cap(
    setup,
    roster,
):
    path, prepare = roster
    prepare()
    result = run_external(setup, roster)
    assert result["status"] == "AWAITING_EVIDENCE"
    waiting = external_batch.summarize(path)
    assert waiting["recorded_micro_usd"] == 1008 and waiting["held_micro_usd"] == 98992
    final = external_batch.settle(path, CELL, setup[2])
    assert final["planned"] == 8
    assert final["status_counts"] == {"NOT_RUN": 7, "EXTERNAL_VERIFIED": 1}
    assert final["recorded_micro_usd"] == 1008 and final["held_micro_usd"] == 0
    assert final["methods"]["B3"] == {
        "planned": 2,
        "transaction_verified": 1,
        "condition_verified": 0,
        "reaction_execution_verified": 0,
    }
    assert all(final["methods"][m]["planned"] == 2 for m in ("B0", "B1", "B2", "B3"))
    assert not final["model_efficacy_verified"]
    assert external_batch.summarize(path) == final
    with pytest.raises(ValueError, match="awaiting evidence"):
        external_batch.settle(path, CELL, setup[2])


def test_consumed_learning_and_external_cost_reduce_the_next_cell_admission(setup, roster):
    path, prepare = roster
    prepare(budget=100000)
    run_external(setup, roster)
    external_batch.settle(path, CELL, setup[2])
    with pytest.raises(ValueError, match="BATCH_COST_LIMIT"):
        external_batch.learn(path, "case-02-B3-r1", lambda *_: pytest.fail("free budget"))
    assert external_batch.summarize(path)["status_counts"] == {"NOT_RUN": 7, "EXTERNAL_VERIFIED": 1}


def test_process_interruption_keeps_full_reservation_without_retry(roster):
    path, prepare = roster
    prepare()

    def crash(*_):
        raise SystemExit("interrupted after admission")

    with pytest.raises(SystemExit):
        external_batch.learn(path, CELL, crash)
    result = external_batch.summarize(path)
    assert result["status_counts"] == {"NOT_RUN": 7, "LEARNING": 1}
    assert result["held_micro_usd"] == 100000
    with pytest.raises(ValueError, match="UNRESOLVED_ATTEMPT"):
        external_batch.learn(path, CELL, lambda *_: pytest.fail("retry"))


def test_unknown_external_usage_does_not_subtract_learning_cost_twice(setup, roster):
    path, prepare = roster
    prepare()
    external_batch.learn(path, CELL, factory)
    carry = B3Carryover(
        path / "runs" / CELL / "learning",
        path / "runs" / CELL / "policy.json",
        setup[5],
        "offline-scripted-model",
    )

    class Missing(BuyerFixture):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                if "metadata" not in event:
                    yield event

    external_batch.execute(path, CELL, Missing(carry.frozen.policy), setup[6])
    report = external_batch.settle(path, CELL, setup[2])
    assert report["status_counts"] == {"NOT_RUN": 7, "EXTERNAL_INCOMPLETE": 1}
    assert report["recorded_micro_usd"] == 616
    assert report["held_micro_usd"] == 100000 - 616
    with pytest.raises(ValueError, match="UNRESOLVED_USAGE"):
        external_batch.learn(path, "case-02-B3-r1", lambda *_: pytest.fail("unresolved spend"))


@pytest.mark.parametrize(
    "target", ["external-evidence.json", "learning/report.json", "execution/report.json"]
)
def test_changed_external_receipt_retains_cost_denominator_and_blocks_next_admission(
    setup,
    roster,
    target,
):
    path, prepare = roster
    prepare()
    run_external(setup, roster)
    external_batch.settle(path, CELL, setup[2])
    p = path / "runs" / CELL / target
    p.write_text(p.read_text() + " ")
    report = external_batch.summarize(path)
    assert report["status_counts"] == {"NOT_RUN": 7, "INVALID_EVIDENCE": 1}
    assert report["recorded_micro_usd"] == 1008
    with pytest.raises(ValueError, match="Prior external evidence"):
        external_batch.learn(path, "case-02-B3-r1", lambda *_: pytest.fail("invalid evidence"))


def test_another_goal_export_cannot_release_an_external_reservation(setup, roster):
    path, prepare = roster
    prepare()
    run_external(setup, roster)
    chosen = json.loads(setup[2].read_text())
    chosen["expected_goal"]["recipient"] = "other"
    setup[2].write_text(json.dumps(chosen))
    with pytest.raises(ValueError, match="contract mismatch"):
        external_batch.settle(path, CELL, setup[2])
    report = external_batch.summarize(path)
    assert report["held_micro_usd"] == 98992 and report["planned"] == 8


def test_unstarted_or_unknown_arm_cannot_take_a_b3_receipt(setup, roster):
    path, prepare = roster
    prepare()
    with pytest.raises(ValueError, match="explicit comparison"):
        external_batch.learn(path, "case-01-B9-r1", lambda *_: pytest.fail("unknown"))
    with pytest.raises((ValueError, FileNotFoundError)):
        external_batch.settle(path, CELL, setup[2])
    assert external_batch.summarize(path)["status_counts"] == {"NOT_RUN": 8}


def test_mutated_roster_is_rejected_before_model_factory(roster):
    path, prepare = roster
    prepare()
    with sqlite3.connect(path / "batch.sqlite3") as db:
        db.execute("DELETE FROM cells WHERE method='B0'")
    with pytest.raises(ValueError, match="roster was changed"):
        external_batch.learn(path, CELL, lambda *_: pytest.fail("roster mutation"))


def test_sealed_runtime_can_be_settled_after_controller_dies_without_reinvocation(
    setup,
    roster,
    monkeypatch,
):
    path, prepare = roster
    prepare()
    external_batch.learn(path, CELL, factory)
    carry = B3Carryover(
        path / "runs" / CELL / "learning",
        path / "runs" / CELL / "policy.json",
        setup[5],
        "offline-scripted-model",
    )
    model = BuyerFixture(carry.frozen.policy)

    def crash(*_):
        raise SystemExit("after HTTP seal, before controller accounting")

    monkeypatch.setattr(external_batch, "refresh_reservation", crash)
    with pytest.raises(SystemExit):
        external_batch.execute(path, CELL, model, setup[6])
    before = external_batch.summarize(path)
    assert before["status_counts"] == {"NOT_RUN": 7, "EXTERNAL_RUNNING": 1}
    assert before["recorded_micro_usd"] + before["held_micro_usd"] == 100000
    calls = len(setup[3])
    final = external_batch.settle(path, CELL, setup[2])
    assert final["recorded_micro_usd"] == 1008 and final["held_micro_usd"] == 0
    assert final["methods"]["B3"]["transaction_verified"] == 1
    assert len(setup[3]) == calls and model.calls == 14


def test_a_phase_label_without_sealed_runtime_cannot_release_budget(setup, roster):
    path, prepare = roster
    prepare()
    external_batch.learn(path, CELL, factory)
    p = path / "runs" / CELL / "report.json"
    value = json.loads(p.read_text())
    value["status"] = "EXTERNAL_RUNNING"
    p.write_text(json.dumps(value))
    with pytest.raises(FileNotFoundError):
        external_batch.settle(path, CELL, setup[2])
    report = external_batch.summarize(path)
    assert report["recorded_micro_usd"] + report["held_micro_usd"] == 100000


def test_unknown_reservation_cannot_be_cleared_by_durable_status_tampering(setup, roster):
    path, prepare = roster
    prepare()
    run_external(setup, roster)
    external_batch.settle(path, CELL, setup[2])
    with sqlite3.connect(path / "batch.sqlite3") as db:
        db.execute("UPDATE cells SET reserved=1 WHERE id=?", (CELL,))
    report = external_batch.summarize(path)
    assert report["status_counts"] == {"NOT_RUN": 7, "INVALID_EVIDENCE": 1}
    assert report["recorded_micro_usd"] == 1008 and report["held_micro_usd"] == 1


def test_invalid_selection_or_raw_export_cannot_be_sealed_as_an_ordinary_failure(setup, roster):
    path, prepare = roster
    prepare()
    run_external(setup, roster)
    chosen = json.loads(setup[2].read_text())
    chosen["sha256"] = "0" * 64
    setup[2].write_text(json.dumps(chosen))
    with pytest.raises(ValueError, match="evidence is not verified"):
        external_batch.settle(path, CELL, setup[2])
    report = external_batch.summarize(path)
    assert report["status_counts"] == {"NOT_RUN": 7, "AWAITING_EVIDENCE": 1}
    assert report["held_micro_usd"] == 98992
    assert not (path / "runs" / CELL / "selection.json").exists()


class SingleAgentFixture(SimulationFixture):
    def get_config(self):
        return {"model_id": "offline-b3-fixture"}


def comparison_factory(kind, policy):
    if kind == "simulation":
        return SingleAgentFixture()
    return factory(kind, policy)


@pytest.mark.parametrize("method,calls,cost", [("B0", 0, 0), ("B1", 14, 392), ("B2", 37, 1036)])
def test_all_external_arms_keep_their_own_learning_roles_cost_and_independent_receipt(
    setup,
    roster,
    method,
    calls,
    cost,
):
    from rehearsal.commerce.learning_budget import BudgetCarryover

    path, prepare = roster
    prepare()
    cell = f"case-01-{method}-r1"
    seen = []

    def build(kind, policy):
        seen.append(kind)
        return comparison_factory(kind, policy)

    learning = external_batch.learn(path, cell, build)
    assert learning["status"] == "WAITING_EXTERNAL"
    if method in {"B0", "B1"}:
        assert seen == [] and learning["learning_status"] == "NOT_REQUIRED"
    else:
        assert seen == ["simulation"]
        assert learning["total_usage"]["recorded_micro_usd"] == 644
        assert {c["role"] for c in learning["total_usage"]["calls"]} == {"simulation_agent"}
    carry = BudgetCarryover(
        path / "runs" / cell / "learning",
        path / "runs" / cell / "policy.json",
        setup[5],
        "offline-scripted-model",
        method,
    )
    external_batch.execute(
        path,
        cell,
        None if method == "B0" else BuyerFixture(carry.frozen.policy),
        setup[6],
    )
    final = external_batch.settle(path, cell, setup[2])
    assert final["status_counts"] == {"NOT_RUN": 7, "EXTERNAL_VERIFIED": 1}
    assert final["methods"][method]["transaction_verified"] == 1
    assert final["methods"][method]["condition_verified"] == 0
    assert final["recorded_micro_usd"] == cost and final["held_micro_usd"] == 0
    runtime = json.loads((path / "runs" / cell / "execution/report.json").read_text())
    assert len(runtime["usage"]["calls"]) == calls
    assert runtime["usage"]["admitted_tool_calls"] > 0
    assert runtime["learning_budget"]["method"] == method
    if method == "B0":
        assert runtime["baseline"]["status"] == "GOAL_OBSERVED"
        assert runtime["usage"]["recorded_total_tokens"] == 0
        assert runtime["tool_calls"] == runtime["usage"]["admitted_tool_calls"] == 12
    assert not runtime["model_efficacy_verified"]


@pytest.mark.parametrize("method", ["B0", "B1", "B2", "B3"])
def test_fixed_and_model_modes_cannot_be_swapped_within_a_reserved_arm(setup, roster, method):
    path, prepare = roster
    prepare()
    cell = f"case-01-{method}-r1"
    external_batch.learn(path, cell, comparison_factory)
    with pytest.raises(ValueError, match="B0 has no model"):
        external_batch.execute(
            path, cell, BuyerFixture(Policy()) if method == "B0" else None, setup[6]
        )
    assert setup[3] == []
    assert external_batch.summarize(path)["status_counts"] == {"NOT_RUN": 7, "WAITING_EXTERNAL": 1}


def test_b0_obeys_shared_tool_limit_and_keeps_zero_model_reservation(setup):
    from dataclasses import replace

    path = setup[1].parent / "bounded-b0"
    training, cases = batch.generated_known_cases(ROOT, 1)
    cases["case-01"]["goal"] = setup[4]["goal"] | {"budget": 500}
    batch.prepare(
        path,
        training,
        cases,
        1,
        replace(setup[5], max_tool_calls=2),
        100000,
        "offline-scripted-model",
        evaluation_environment="external-medusa",
    )
    external_batch.learn(path, "case-01-B0-r1", lambda *_: pytest.fail("B0 model factory"))
    result = external_batch.execute(path, "case-01-B0-r1", None, setup[6])
    assert result["runtime_status"] == "LIMITED"
    assert result["total_usage"]["admitted_tool_calls"] == 2
    assert result["total_usage"]["calls"] == []
    assert not any(m == "POST" and p.endswith("/orders") for m, p in setup[3])
    final = external_batch.settle(path, "case-01-B0-r1", setup[2])
    assert final["status_counts"] == {"EXTERNAL_INCOMPLETE": 1, "NOT_RUN": 3}
    assert final["held_micro_usd"] == final["recorded_micro_usd"] == 0


@pytest.mark.parametrize(
    "limits",
    [
        {"max_model_calls": 23},
        {"max_tool_calls": 22},
        {"max_total_tokens": 9464},
        {"budget_micro_usd": 10664},
    ],
)
def test_b2_learning_consumes_each_shared_limit_before_external_execution(setup, roster, limits):
    path, prepare = roster
    prepare(**limits)
    cell = "case-01-B2-r1"
    learning = external_batch.learn(path, cell, comparison_factory)
    assert learning["status"] == "WAITING_EXTERNAL"
    assert learning["total_usage"]["recorded_micro_usd"] == 644
    result = external_batch.execute(path, cell, BuyerFixture(Policy()), setup[6])
    assert result["runtime_status"] == "LIMITED"
    assert result["total_usage"]["admitted_tool_calls"] == 22
    assert not any(m == "POST" for m, _ in setup[3])
    final = external_batch.settle(path, cell, setup[2])
    assert final["status_counts"] == {"NOT_RUN": 7, "EXTERNAL_INCOMPLETE": 1}
    assert final["methods"]["B2"]["transaction_verified"] == 0


def test_b0_rechecks_server_scope_before_following_write_without_a_model(setup, roster):
    path, prepare = roster
    prepare()
    cell = "case-01-B0-r1"
    external_batch.learn(path, cell, lambda *_: pytest.fail("B0 model"))
    client = setup[6]
    original = client.request

    def changed(method, route, body=None):
        response = original(method, route, body)
        if method == "POST" and route == "quotes":
            setup[4]["goal"]["recipient"] = "changed-venue"
        return response

    client.request = changed
    result = external_batch.execute(path, cell, None, client)
    assert result["runtime_status"] == "LIMITED"
    runtime = json.loads((path / "runs" / cell / "execution/report.json").read_text())
    assert runtime["stop_reason"] == "HTTP_RUN_CONTRACT_CHANGED"
    assert runtime["usage"]["calls"] == []
    assert not any(m == "POST" and p.endswith("/orders") for m, p in setup[3])


def declared_fixture(setup, events=None):
    from test_conditions import artifact_for

    path = setup[1].parent / "declared-external"
    training, cases = batch.generated_known_cases(ROOT, 1)
    chosen = json.loads(setup[2].read_text())
    raw = json.loads(Path(chosen["artifact_path"]).read_text())
    case = cases["case-01"]
    case["goal"] = chosen["expected_goal"] | {"budget": chosen["expected_budget"]}
    for name in case["suppliers"]:
        case["suppliers"][name]["lead_ticks"] = raw["binding"]["suppliers"][name]["lead_ticks"]
    if events is not None:
        case["events"] = events
    batch.prepare(
        path,
        training,
        cases,
        1,
        setup[5],
        500000,
        "offline-scripted-model",
        evaluation_environment="external-medusa",
    )
    artifact = artifact_for(case, raw, setup[4])
    conditions = path / "operator-conditions.json"
    conditions.write_text(json.dumps(artifact))
    external_batch.learn(path, CELL, factory)
    return path, conditions, artifact


def test_verified_initial_conditions_are_pinned_and_recomputed_at_external_settlement(setup):
    path, conditions, _ = declared_fixture(setup)
    result = external_batch.execute(
        path, CELL, BuyerFixture(Policy()), setup[6], condition_path=conditions
    )
    assert result["status"] == "AWAITING_EVIDENCE"
    final = external_batch.settle(path, CELL, setup[2])
    assert final["methods"]["B3"]["condition_verified"] == 1
    assert final["methods"]["B3"]["transaction_verified"] == 1
    assert final["planned"] == 4
    pinned = path / "runs" / CELL / "conditions.json"
    assert pinned.read_bytes() == conditions.read_bytes()
    pinned.write_text(pinned.read_text() + " ")
    broken = external_batch.summarize(path)
    assert broken["methods"]["B3"]["condition_verified"] == 0
    assert broken["status_counts"] == {"NOT_RUN": 3, "INVALID_EVIDENCE": 1}


def test_mismatched_provider_condition_rejects_before_any_http_or_model(setup):
    path, conditions, raw = declared_fixture(setup)
    raw["catalog_get"]["response"]["products"][0]["variants"][0]["inventory_quantity"] += 1
    conditions.write_text(json.dumps(raw))
    model = BuyerFixture(Policy())
    with pytest.raises(ValueError, match="Store GET"):
        external_batch.execute(path, CELL, model, setup[6], condition_path=conditions)
    assert model.calls == 0 and setup[3] == []
    assert external_batch.summarize(path)["status_counts"] == {"NOT_RUN": 3, "WAITING_EXTERNAL": 1}


def test_stale_capture_can_be_refreshed_before_an_external_attempt_is_claimed(setup):
    path, conditions, raw = declared_fixture(setup)
    setup[4]["tick"] += 10
    model = BuyerFixture(Policy())
    with pytest.raises(ValueError, match="too old"):
        external_batch.execute(path, CELL, model, setup[6], condition_path=conditions)
    assert model.calls == 0 and not (path / "runs" / CELL / "execution").exists()
    assert not (path / "runs" / CELL / "conditions.json").exists()
    raw["before"]["tick"] = raw["after"]["tick"] = setup[4]["tick"]
    raw["initial_evidence"]["captured_at_tick"] = setup[4]["tick"]
    conditions.write_text(json.dumps(raw))
    assert (
        external_batch.execute(path, CELL, model, setup[6], condition_path=conditions)[
            "runtime_status"
        ]
        == "COMPLETED"
    )


def test_unsupported_events_reject_before_learning_or_an_external_admission(setup, roster):
    path, prepare = roster
    manifest = prepare()
    manifest["cases"]["case-01"]["events"] = []
    # Rebuild a valid content-addressed manifest containing an unsupported case.
    import hashlib

    from rehearsal.world.storage import canonical

    manifest["id"] = (
        "batch-"
        + hashlib.sha256(
            canonical({k: v for k, v in manifest.items() if k != "id"}).encode()
        ).hexdigest()
    )
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="explicit timed events required"):
        external_batch.learn(path, CELL, lambda *_: pytest.fail("model"))
    assert not (path / "runs").exists()


@pytest.mark.parametrize("state", ["NOT_RUN", "UNKNOWN"])
def test_unfulfilled_declared_events_do_not_become_condition_success_or_hold_resolved_cost(
    setup, state
):
    from rehearsal.commerce.model_runner import digest
    from rehearsal.evaluation.conditions import fingerprint

    events = [
        {
            "id": "stockA",
            "at_tick": 50,
            "max_lateness_ticks": 3,
            "kind": "stock",
            "supplier": "A",
            "item": "tent",
            "value": 0,
        }
    ]
    path, conditions, _ = declared_fixture(setup, events)
    external_batch.execute(path, CELL, BuyerFixture(Policy()), setup[6], condition_path=conditions)
    selected = json.loads(setup[2].read_text())
    raw = json.loads(Path(selected["artifact_path"]).read_text())
    case = json.loads((path / "manifest.json").read_text())["cases"]["case-01"]
    raw["condition_events"] = {
        "schema": "rehearsal-timed-condition-events-v1",
        "case_sha256": fingerprint(case),
        "run_id": raw["binding"]["run_id"],
        "receipts": {"stockA": {"event": events[0], "state": state}},
    }
    artifact = path / "operator-final.json"
    artifact.write_text(json.dumps(raw))
    selected.update(artifact_path=str(artifact), sha256=digest(artifact))
    setup[2].write_text(json.dumps(selected))
    final = external_batch.settle(path, CELL, setup[2])
    assert final["methods"]["B3"]["transaction_verified"] == 1
    assert final["methods"]["B3"]["condition_verified"] == 0
    assert final["held_micro_usd"] == 0 and final["planned"] == 4
    # The retained event proof participates in the durable artifact hash set.
    proof = path / "runs" / CELL / "external-evidence.json"
    proof.write_text(proof.read_text() + " ")
    assert external_batch.summarize(path)["status_counts"] == {"NOT_RUN": 3, "INVALID_EVIDENCE": 1}


def test_timed_case_requires_initial_proof_before_model_or_attempt(setup):
    events = [
        {
            "id": "stockA",
            "at_tick": 50,
            "max_lateness_ticks": 3,
            "kind": "stock",
            "supplier": "A",
            "item": "tent",
            "value": 0,
        }
    ]
    path, _, _ = declared_fixture(setup, events)
    model = BuyerFixture(Policy())
    with pytest.raises(ValueError, match="require initial condition evidence"):
        external_batch.execute(path, CELL, model, setup[6])
    assert model.calls == 0 and not (path / "runs" / CELL / "execution").exists()
