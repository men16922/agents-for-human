"""Existing practice controllers retain an injected run-wide usage ledger."""

import json
from pathlib import Path

import pytest

from rehearsal.agents.metering import RateCard, UsageLedger
from rehearsal.agents.runner import ModelSettings
from rehearsal.experiments.b2 import SimulationFixture, run_b2
from rehearsal.experiments.b3 import BuyerFixture, ReviewerFixture, run_b3


@pytest.mark.parametrize("method,learning_calls", [("B2", 23), ("B3", 22)])
def test_practice_includes_prior_calls_and_shares_remaining_admission(
    tmp_path, method, learning_calls
):
    settings = ModelSettings(
        "offline",
        "offline",
        f"offline-{method.lower()}-fixture",
        RateCard("1", "2", "0", "0", "fictional fixture rates"),
        100000,
        max_model_calls=32,
    )
    ledger = UsageLedger(
        tmp_path / "usage.sqlite3",
        "entire-cloud-run",
        settings.model_id,
        settings.rates,
        settings.budget_micro_usd,
        settings.input_limit,
        settings.output_limit,
        "offline-scripted-model",
        max_calls=settings.max_model_calls,
        max_total_tokens=settings.max_total_tokens,
        max_tool_calls=settings.max_tool_calls,
    )
    call, reason = ledger.reserve(100, role="executor", execution_id="prior")
    assert reason is None
    ledger.finish(call, {"inputTokens": 12, "outputTokens": 8})
    scenario = json.loads(Path("scenarios/normal-v1.json").read_text())
    if method == "B2":
        result = run_b2(
            SimulationFixture(),
            settings,
            tmp_path / "learning",
            scenario,
            "offline-scripted-model",
            shared_ledger=ledger,
        )
    else:
        result = run_b3(
            lambda p: BuyerFixture(p),
            lambda _: ReviewerFixture(),
            settings,
            tmp_path / "learning",
            scenario,
            "offline-scripted-model",
            shared_ledger=ledger,
        )
    assert result["status"] == "CANDIDATE_EVALUATED_NOT_PROMOTED"
    assert len(ledger.report()["calls"]) == learning_calls + 1
    assert result["usage"]["recorded_micro_usd"] == (learning_calls + 1) * 28
    assert result["usage"]["role_usage"]["executor"]["model_calls"] == 1
    assert not (tmp_path / "learning/usage.sqlite3").exists()
    call, reason = ledger.reserve(100, role="buyer_evaluation", execution_id="cloud-evaluation")
    assert reason is None
    ledger.finish(call, {"inputTokens": 12, "outputTokens": 8})
    assert len(ledger.report()["calls"]) == learning_calls + 2
    assert ledger.report()["unresolved_reserved_micro_usd"] == 0
