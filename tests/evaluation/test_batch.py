import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.evaluation import batch
from rehearsal.evaluation.frozen_run import EvaluationBuyer, fixture_factory

ROOT = Path(__file__).parents[2]


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "batch"
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-evaluation-fixture",
        RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
        100000,
        max_model_calls=48,
        max_tool_calls=48,
    )
    training, cases = batch.generated_known_cases(ROOT, 2)

    def prepare(repeats=1, budget=500000):
        return batch.prepare(
            path, training, cases, repeats, settings, budget, "offline-scripted-model"
        )

    return path, prepare, training, cases


def test_full_roster_precedes_any_execution_and_keeps_repeat_denominator(setup):
    path, prepare, _, _ = setup
    manifest = prepare(repeats=2)
    report = batch.summarize(path)
    assert manifest["planned"] == report["planned"] == 16
    assert report["status_counts"] == {"NOT_RUN": 16}
    assert report["methods"]["B2"]["planned"] == 4
    assert not report["all_cells_resolved"]
    assert not (path / "runs").exists()
    with pytest.raises(FileExistsError):
        prepare()


def test_fixture_batch_resumes_only_unstarted_cells_and_reaudits_exports(setup):
    path, prepare, _, _ = setup
    prepare()
    first = batch.run_pending(path, fixture_factory, max_cells=2)
    hashes = batch.artifact_hashes(path / "runs")
    assert first["status_counts"] == {"EVALUATED": 2, "NOT_RUN": 6}
    final = batch.run_pending(path, fixture_factory)
    assert final["planned"] == 8 and final["status_counts"] == {"EVALUATED": 8}
    assert final["all_cells_resolved"]
    assert final["recorded_micro_usd"] == 4704
    assert all(batch.artifact_hashes(path / "runs")[k] == v for k, v in hashes.items())
    assert final["methods"]["B2"]["recorded_micro_usd"] == 2016
    assert not final["model_efficacy_verified"] and not final["held_out_evaluation_verified"]
    assert batch.summarize(path) == {k: v for k, v in final.items() if k != "stop_reason"}
    assert batch.run_pending(path, lambda *_: pytest.fail("duplicate invocation")) == final


def test_batch_limit_does_not_multiply_per_cell_budget(setup):
    path, prepare, _, _ = setup
    prepare(budget=100000)
    result = batch.run_pending(path, fixture_factory)
    assert result["stop_reason"] == "BATCH_COST_LIMIT"
    assert result["recorded_micro_usd"] == 364
    assert result["status_counts"] == {"EVALUATED": 2, "NOT_RUN": 6}
    assert result["unresolved_reserved_micro_usd"] == 0
    assert not result["all_cells_resolved"]


def test_missing_usage_holds_remaining_cell_budget_and_stops_batch(setup):
    path, prepare, _, _ = setup
    prepare()

    class Missing(EvaluationBuyer):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                if "metadata" not in event:
                    yield event

    result = batch.run_pending(path, lambda kind, p: Missing(p))
    assert result["stop_reason"] == "UNRESOLVED_USAGE"
    assert result["status_counts"] == {"EVALUATED": 1, "EVALUATION_INCOMPLETE": 1, "NOT_RUN": 6}
    assert result["recorded_micro_usd"] == 0
    assert result["unresolved_reserved_micro_usd"] == 100000
    assert not result["all_cells_resolved"]
    assert batch.run_pending(path, lambda *_: pytest.fail("retry")) == result


def test_runtime_failure_with_recorded_usage_is_kept_in_denominator(setup):
    path, prepare, _, _ = setup
    prepare()

    class Truncated(EvaluationBuyer):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                if event.get("messageStop", {}).get("stopReason") == "end_turn":
                    event = {"messageStop": {"stopReason": "max_tokens"}}
                yield event

    result = batch.run_pending(path, lambda kind, p: Truncated(p), max_cells=2)
    assert result["status_counts"] == {"EVALUATED": 1, "EVALUATION_INCOMPLETE": 1, "NOT_RUN": 6}
    cell = result["cells"][1]
    assert cell["goal_complete"] and cell["spent"] == 380 and cell["usage_resolved"]
    assert result["methods"]["B1"]["planned"] == 2


def test_crash_leaves_unresolved_attempt_without_automatic_retry(setup, monkeypatch):
    path, prepare, _, _ = setup
    prepare()
    batch.run_pending(path, fixture_factory, max_cells=1)

    def crash(*args, **kwargs):
        raise SystemExit("synthetic interruption")

    monkeypatch.setattr(batch, "run_cell", crash)
    with pytest.raises(SystemExit):
        batch.run_pending(path, fixture_factory)
    monkeypatch.setattr(batch, "run_cell", lambda *a: pytest.fail("retry"))
    result = batch.run_pending(path, fixture_factory)
    assert result["stop_reason"] == "UNRESOLVED_ATTEMPT"
    assert result["status_counts"] == {"EVALUATED": 1, "RUNNING": 1, "NOT_RUN": 6}
    assert result["unresolved_reserved_micro_usd"] == 100000


def test_unhandled_runner_error_is_not_assumed_free(setup, monkeypatch):
    path, prepare, _, _ = setup
    prepare()
    batch.run_pending(path, fixture_factory, max_cells=1)

    def error(*args, **kwargs):
        raise RuntimeError("synthetic lost usage")

    monkeypatch.setattr(batch, "run_cell", error)
    result = batch.run_pending(path, fixture_factory)
    assert result["status_counts"] == {"EVALUATED": 1, "ERROR": 1, "NOT_RUN": 6}
    assert result["stop_reason"] == "UNRESOLVED_USAGE"
    assert result["unresolved_reserved_micro_usd"] == 100000


def test_two_claimers_cannot_admit_the_same_attempt(setup):
    path, prepare, _, _ = setup
    manifest = prepare()
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: batch.claim(path, manifest), range(2)))
    assert sum(cell is not None for cell, _ in results) == 1
    assert [reason for _, reason in results].count("UNRESOLVED_ATTEMPT") == 1
    assert batch.summarize(path)["status_counts"] == {"RUNNING": 1, "NOT_RUN": 7}


@pytest.mark.parametrize("damage", ["delete", "edit"])
def test_artifact_damage_retains_cost_denominator_and_blocks_resume(setup, damage):
    path, prepare, _, _ = setup
    prepare()
    batch.run_pending(path, fixture_factory, max_cells=2)
    evidence = path / "runs/case-01-B1-r1/evaluation/evidence.json"
    if damage == "delete":
        evidence.unlink()
    else:
        evidence.write_text("{}")
    report = batch.summarize(path)
    assert report["status_counts"] == {"EVALUATED": 1, "INVALID_EVIDENCE": 1, "NOT_RUN": 6}
    assert report["planned"] == 8 and report["recorded_micro_usd"] == 364
    with pytest.raises(ValueError, match="Prior batch evidence"):
        batch.run_pending(path, lambda *_: pytest.fail("invalid resume"))


def test_roster_deletion_cannot_reduce_denominator(setup):
    path, prepare, _, _ = setup
    prepare()
    with sqlite3.connect(path / "batch.sqlite3") as db:
        db.execute("DELETE FROM cells WHERE method='B3'")
    with pytest.raises(ValueError, match="roster"):
        batch.summarize(path)


def test_negative_durable_cost_is_rejected(setup):
    path, prepare, _, _ = setup
    prepare()
    with sqlite3.connect(path / "batch.sqlite3") as db:
        db.execute("UPDATE cells SET recorded=-1 WHERE method='B3'")
    with pytest.raises(ValueError, match="durable batch cost"):
        batch.run_pending(path, fixture_factory)


def test_source_change_blocks_execution_before_any_provider(setup, monkeypatch):
    path, prepare, _, _ = setup
    prepare()
    original = batch.digest
    monkeypatch.setattr(
        batch, "digest", lambda p: "changed" if p.name == "batch.py" else original(p)
    )
    with pytest.raises(ValueError, match="source changed"):
        batch.run_pending(path, lambda *_: pytest.fail("provider"))
    assert not (path / "runs").exists()


@pytest.mark.parametrize("fault", ["repeat", "budget", "case_id", "condition"])
def test_invalid_manifest_inputs_do_not_create_batch(setup, fault):
    path, prepare, training, cases = setup
    if fault == "case_id":
        cases["../escape"] = cases.pop("case-01")
    if fault == "condition":
        cases["case-01"] = copy.deepcopy(training)
        cases["case-01"].update(seed=900, scenario_version="renamed")
    with pytest.raises(ValueError):
        prepare(repeats=0 if fault == "repeat" else 1, budget=0 if fault == "budget" else 100000)
    assert not path.exists()


def test_manifest_modification_is_rejected(setup):
    path, prepare, _, _ = setup
    prepare()
    value = json.loads((path / "manifest.json").read_text())
    value["batch_budget_micro_usd"] += 1
    batch.write(path / "manifest.json", value)
    with pytest.raises(ValueError, match="integrity"):
        batch.run_pending(path, fixture_factory)
