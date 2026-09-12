from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from rehearsal.agents.metering import RateCard, UsageLedger

RATES = RateCard("1", "2", "0.1", "1.25", "fictional offline test rates")


def ledger(path: Path, budget=1000):
    return UsageLedger(
        path / "usage.sqlite3",
        "run",
        "scripted",
        RATES,
        budget,
        100,
        10,
        scope="offline-scripted-model",
    )


def test_usage_separates_input_output_cache_and_rounds_up():
    assert (
        RATES.micro_usd(
            {
                "inputTokens": 10,
                "outputTokens": 5,
                "cacheReadInputTokens": 1,
                "cacheWriteInputTokens": 1,
            }
        )
        == 22
    )
    with pytest.raises(ValueError):
        RATES.micro_usd({"inputTokens": True})


def test_reservation_recording_and_reopen(tmp_path):
    meter = ledger(tmp_path)
    call, reason = meter.reserve(50)
    assert reason is None
    assert meter.report()["unresolved_reserved_micro_usd"] == 145
    meter.finish(call, {"inputTokens": 12, "outputTokens": 8})
    reopened = ledger(tmp_path)
    assert reopened.report()["recorded_micro_usd"] == 28
    assert reopened.report()["unresolved_reserved_micro_usd"] == 0
    assert reopened.report()["all_usage_recorded"]
    with pytest.raises(ValueError, match="already finalized"):
        meter.finish(call, {"inputTokens": 12, "outputTokens": 8})


@pytest.mark.parametrize("outcome", ["missing", "error", "partial", "invalid", "crash"])
def test_unresolved_usage_is_never_free_and_blocks_next_call(tmp_path, outcome):
    meter = ledger(tmp_path)
    call, _ = meter.reserve(50)
    if outcome == "missing":
        meter.finish(call, None)
    elif outcome == "error":
        meter.finish(call, None, "TimeoutError")
    elif outcome == "partial":
        meter.finish(call, {"inputTokens": 12})
    elif outcome == "invalid":
        meter.finish(call, {"inputTokens": -1, "outputTokens": 8})
    reopened = ledger(tmp_path)
    report = reopened.report()
    assert not report["all_usage_recorded"]
    assert report["unresolved_reserved_micro_usd"] == 145
    assert reopened.reserve(50) == (None, "PRIOR_USAGE_UNRESOLVED")


def test_cost_admission_and_underestimated_input_record_actual_overrun(tmp_path):
    meter = ledger(tmp_path, budget=145)
    call, _ = meter.reserve(100)
    # An estimate can be wrong: retain the measured usage rather than truncate it.
    meter.finish(call, {"inputTokens": 200, "outputTokens": 10})
    report = meter.report()
    assert report["estimated_budget_exceeded"]
    assert report["recorded_micro_usd"] == 220
    assert meter.reserve(1) == (None, "ESTIMATED_COST_LIMIT")
    assert not report["billing_verified"]


def test_exact_budget_and_unknown_input_admission(tmp_path):
    meter = ledger(tmp_path, budget=144)
    assert meter.reserve(50) == (None, "ESTIMATED_COST_LIMIT")
    assert meter.reserve(None) == (None, "INPUT_ESTIMATE_UNAVAILABLE")
    assert meter.reserve(101) == (None, "INPUT_TOKEN_LIMIT")
    assert meter.report()["calls"] == []


def test_concurrent_admission_cannot_double_reserve(tmp_path):
    meter = ledger(tmp_path, budget=145)
    barrier = Barrier(2)

    def admit(_):
        barrier.wait(timeout=3)
        return meter.reserve(50)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(admit, range(2)))
    assert sum(call is not None for call, _ in results) == 1
    assert meter.report()["unresolved_reserved_micro_usd"] == 145


def constrained(path, tokens=200, tools=1):
    return UsageLedger(
        path / "constraints.sqlite3",
        "run",
        "scripted",
        RATES,
        10000,
        100,
        10,
        scope="offline-scripted-model",
        max_calls=3,
        max_total_tokens=tokens,
        max_tool_calls=tools,
    )


def test_shared_token_actual_overrun_and_unknown_reservation_survive_reopen(tmp_path):
    meter = constrained(tmp_path)
    call, _ = meter.reserve(10, role="buyer_initial", execution_id="initial")
    meter.finish(call, {"inputTokens": 210, "outputTokens": 10, "cacheReadInputTokens": 5})
    reopened = constrained(tmp_path)
    assert reopened.report()["recorded_total_tokens"] == 225
    assert reopened.report()["estimated_token_budget_exceeded"]
    assert reopened.reserve(1, role="reviewer", execution_id="review") == (
        None,
        "TOTAL_TOKEN_LIMIT",
    )
    with pytest.raises(ValueError, match="session constraints cannot change"):
        constrained(tmp_path, tokens=201)


def test_unknown_token_reservation_is_not_zero(tmp_path):
    meter = constrained(tmp_path)
    call, _ = meter.reserve(1)
    meter.finish(call, None)
    reopened = constrained(tmp_path)
    assert reopened.report()["recorded_total_tokens"] == 0
    assert reopened.report()["unresolved_reserved_tokens"] == 110
    assert reopened.reserve(1) == (None, "PRIOR_USAGE_UNRESOLVED")


def test_two_roles_cannot_admit_tools_past_one_shared_slot(tmp_path):
    meter = constrained(tmp_path)
    barrier = Barrier(2)

    def attempt(role):
        barrier.wait(timeout=3)
        return meter.admit_tool(role, role, "observe_world")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["buyer_initial", "buyer_candidate"]))
    assert results.count(None) == results.count("SHARED_TOOL_CALL_LIMIT") == 1
    reopened = constrained(tmp_path)
    assert reopened.report()["admitted_tool_calls"] == 1
    assert len(reopened.report()["tool_admissions"]) == 2
    assert (
        reopened.admit_tool("reviewer", "review", "authorize_payment", "REVIEW_TOOLS_FORBIDDEN")
        == "REVIEW_TOOLS_FORBIDDEN"
    )
    assert reopened.report()["admitted_tool_calls"] == 1
