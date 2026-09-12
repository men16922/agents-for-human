import json
import sqlite3
from pathlib import Path

import pytest

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.evaluation import batch, metrics
from rehearsal.evaluation.frozen_run import EvaluationBuyer, fixture_factory

ROOT = Path(__file__).parents[2]


@pytest.fixture
def prepared(tmp_path):
    directory = tmp_path / "batch"
    training, cases = batch.generated_known_cases(ROOT, 2)
    settings = ModelSettings(
        "offline", "offline", "offline-evaluation-fixture",
        RateCard("1", "2", "0", "0", "fixture"), 100000,
        max_model_calls=48, max_tool_calls=48,
    )
    batch.prepare(directory, training, cases, 1, settings, 500000, "offline-scripted-model")
    return directory


def reseal(directory, cell):
    with sqlite3.connect(directory / "batch.sqlite3") as db:
        db.execute(
            "UPDATE cells SET artifact_hashes=? WHERE id=?",
            (json.dumps(batch.artifact_hashes(directory / "runs" / cell)), cell),
        )


def test_no_execution_has_no_token_tool_or_duration_measurements(prepared):
    before = {str(p): p.read_bytes() for p in prepared.rglob("*") if p.is_file()}
    value = metrics.report(prepared)
    assert value["planned"] == 8 and value["status_counts"] == {"NOT_RUN": 8}
    for row in value["methods"].values():
        assert row["tokens"]["cells_with_records"] == 0
        assert row["tokens"]["complete_usage_cells"] == 0
        assert row["tool_calls"]["unavailable_cells"] == 2
        assert row["duration"]["median_seconds"] is None
        assert row["duration"]["p95_seconds"] is None
    assert "unavailable" in metrics.markdown(value)
    assert before == {str(p): p.read_bytes() for p in prepared.rglob("*") if p.is_file()}


def test_partial_roster_uses_real_monotonic_intervals_and_raw_tokens(prepared, monkeypatch):
    # Control only the batch timer; SDK internals continue using their own clock.
    class Timer:
        values = iter((1_000_000_000, 3_000_000_000, 10_000_000_000, 15_000_000_000))

        @classmethod
        def perf_counter_ns(cls):
            return next(cls.values)

    monkeypatch.setattr(batch, "time", Timer)
    batch.run_pending(prepared, fixture_factory, max_cells=2)
    value = metrics.report(prepared)
    b0, b1 = value["methods"]["B0"], value["methods"]["B1"]
    assert b0["tokens"] == {
        "recorded": 0, "cells_with_records": 1,
        "unavailable_cells": 1, "complete_usage_cells": 1,
    }
    assert b1["tokens"]["recorded"] == 260  # 13 calls * (12 input + 8 output).
    assert b1["model_calls"]["recorded"] == 13
    assert b0["duration"]["median_seconds"] == 2
    assert b1["duration"]["p95_seconds"] == 5
    assert b1["duration"]["samples"] == 1
    assert b1["duration"]["unavailable_cells"] == 1
    assert value["status_counts"] == {"EVALUATED": 2, "NOT_RUN": 6}


def test_training_and_evaluation_tokens_share_the_report_denominator(prepared, monkeypatch):
    class Timer:
        values = iter(
            n for i, duration in enumerate((2, 3, 4, 5, 8, 9, 10, 11))
            for n in (i * 100_000_000_000, (i * 100 + duration) * 1_000_000_000)
        )

        @classmethod
        def perf_counter_ns(cls):
            return next(cls.values)

    monkeypatch.setattr(batch, "time", Timer)
    batch.run_pending(prepared, fixture_factory)
    value = metrics.report(prepared)
    assert value["methods"]["B2"]["tokens"]["recorded"] == 1440
    for method in ("B1", "B2", "B3"):
        row = value["methods"][method]
        assert row["tokens"]["complete_usage_cells"] == row["planned"] == 2
        assert row["tokens"]["recorded"] == row["model_calls"]["recorded"] * 20
        assert row["duration"]["samples"] == 2
    assert not value["model_efficacy_verified"]
    assert value["methods"]["B0"]["duration"]["median_seconds"] == 5
    assert value["methods"]["B0"]["duration"]["p95_seconds"] == 8


def test_unknown_usage_is_partial_and_not_a_zero_cost_completed_sample(prepared):
    class Missing(EvaluationBuyer):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                if "metadata" not in event:
                    yield event

    batch.run_pending(prepared, lambda kind, p: Missing(p))
    row = metrics.report(prepared)["methods"]["B1"]
    assert row["tokens"]["recorded"] == 0
    assert row["tokens"]["complete_usage_cells"] == 0
    assert row["unresolved_reserved_micro_usd"] == 100000
    assert row["duration"]["samples"] == 1  # Failed attempts still take time.
    assert row["status_counts"] == {"EVALUATION_INCOMPLETE": 1, "NOT_RUN": 1}


def test_legacy_artifacts_do_not_invent_time_from_wall_clock_timestamps(prepared):
    batch.run_pending(prepared, fixture_factory, max_cells=1)
    cell = "case-01-B0-r1"
    (prepared / "runs" / cell / "timing.json").unlink()
    reseal(prepared, cell)
    row = metrics.report(prepared)["methods"]["B0"]
    assert row["goal_complete"] == 1 and row["tokens"]["complete_usage_cells"] == 1
    assert row["duration"]["samples"] == 0
    assert row["duration"]["median_seconds"] is None


def test_crash_is_an_unfinished_attempt_without_fabricated_elapsed_time(prepared, monkeypatch):
    def crash(*args, **kwargs):
        raise SystemExit("interrupted")

    monkeypatch.setattr(batch, "run_cell", crash)
    with pytest.raises(SystemExit):
        batch.run_pending(prepared, fixture_factory)
    row = metrics.report(prepared)["methods"]["B0"]
    assert row["status_counts"] == {"RUNNING": 1, "NOT_RUN": 1}
    assert row["duration"]["samples"] == 0
    assert row["tokens"]["cells_with_records"] == 0


def test_caught_error_keeps_elapsed_time_and_unknown_token_count(prepared, monkeypatch):
    def error(*args, **kwargs):
        raise RuntimeError("unrecorded failure")

    monkeypatch.setattr(batch, "run_cell", error)
    batch.run_pending(prepared, fixture_factory)
    row = metrics.report(prepared)["methods"]["B0"]
    assert row["status_counts"] == {"ERROR": 1, "NOT_RUN": 1}
    assert row["duration"]["samples"] == 1
    assert row["tokens"]["cells_with_records"] == 0


@pytest.mark.parametrize("damage", ["hash", "negative", "boolean", "difference", "token-total"])
def test_invalid_evidence_cannot_contribute_measurements(prepared, damage):
    batch.run_pending(prepared, fixture_factory, max_cells=2)
    cell = "case-01-B1-r1"
    path = prepared / "runs" / cell
    if damage == "token-total":
        target = path / "report.json"
        value = json.loads(target.read_text())
        value["total_usage"]["recorded_total_tokens"] += 1
    else:
        target = path / "timing.json"
        value = json.loads(target.read_text())
        value["duration_ns"] = {"negative": -1, "boolean": True}.get(damage, 9)
    batch.write(target, value)
    if damage != "hash":
        reseal(prepared, cell)  # Independently validate contents even if hashes are refreshed.
    row = metrics.report(prepared)["methods"]["B1"]
    assert row["status_counts"] == {"INVALID_EVIDENCE": 1, "NOT_RUN": 1}
    assert row["tokens"]["cells_with_records"] == 0
    assert row["tool_calls"]["cells_with_records"] == 0
    assert row["duration"]["samples"] == 0
    assert row["recorded_micro_usd"] == 364  # Invalid artifacts do not erase durable cost.
