"""Real SDK loops with explicit fixture providers; no paid model calls."""

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from rehearsal.agents.metering import RateCard, UsageLedger
from rehearsal.agents.runner import ModelSettings
from rehearsal.experiments.b3 import BuyerFixture, ReviewerFixture, run_b3
from rehearsal.experiments.model_experiment import validate_shared_ledger, verify_attribution
from rehearsal.world.storage import ContractError


@pytest.fixture
def setup(tmp_path):
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-b3-fixture",
        RateCard("1", "2", "0", "0", "fictional fixture rates"),
        100000,
        max_model_calls=32,
    )
    scenario = json.loads((Path(__file__).parents[2] / "scenarios/normal-v1.json").read_text())
    models = []

    def run(buyer=BuyerFixture, reviewer=ReviewerFixture, **overrides):
        def factory(kind, arg=None):
            model = kind(arg) if arg is not None else kind()
            models.append(model)
            return model

        return run_b3(
            lambda p: factory(buyer, p),
            lambda _: factory(reviewer),
            replace(settings, **overrides),
            tmp_path / "b3",
            scenario,
            "offline-scripted-model",
        )

    return run, models, tmp_path / "b3", settings


def test_three_roles_share_usage_and_independent_same_snapshot_evidence(setup):
    run, models, path, _ = setup
    result = run()
    assert result["status"] == "CANDIDATE_EVALUATED_NOT_PROMOTED"
    assert result["parent_unchanged"] and not result["promoted"]
    assert not result["efficacy_verified"] and not result["held_out_evaluation_verified"]
    assert [m.calls for m in models] == [6, 1, 14, 1]
    usage = result["usage"]
    assert len(usage["calls"]) == 22 and usage["recorded_micro_usd"] == 616
    assert usage["all_usage_recorded"] and not usage["billing_verified"]
    assert usage["unresolved_reserved_micro_usd"] == 0
    assert usage["admission_rejections"] == []
    for role, count in {"buyer_initial": 6, "reviewer": 2, "buyer_candidate": 14}.items():
        attribution = usage["role_usage"][role]
        assert attribution["scope"] == "offline-scripted-model"
        assert attribution["model_calls"] == attribution["status_counts"]["RECORDED"] == count
        assert attribution["recorded_tokens"]["inputTokens"] == 12 * count
        assert attribution["recorded_tokens"]["outputTokens"] == 8 * count
    initial = json.loads((path / "initial/experiment.json").read_text())
    candidate = json.loads((path / "review/round-1/reexperiment/experiment.json").read_text())
    assert initial["snapshot_sha256"] == candidate["snapshot_sha256"]
    assert not initial["policy"]["refresh_quote_before_order"]
    assert initial["verdict"]["status"] == "INCOMPLETE"
    assert candidate["verdict"]["status"] == "COMPLETE"
    assert candidate["verdict"]["spent"] == 380
    assert len(candidate["accounting"]["call_ids"]) == 14
    for name, digest in result["source_hashes"].items():
        assert hashlib.sha256((Path(__file__).parents[2] / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize(
    "limit,counts,role",
    [
        (6, [6], "reviewer"),
        (7, [6, 1, 0], "buyer_candidate"),
        (10, [6, 1, 3], "buyer_candidate"),
        (21, [6, 1, 14], "reviewer"),
    ],
)
def test_shared_call_cap_stops_at_role_transitions_and_mid_candidate(setup, limit, counts, role):
    run, models, _, _ = setup
    result = run(max_model_calls=limit)
    assert result["status"] == "REJECTED" and result["error"] == "MODEL_CALL_LIMIT"
    assert [m.calls for m in models] == counts
    assert len(result["usage"]["calls"]) == limit
    assert result["usage"]["admission_rejections"][-1]["role"] == role
    assert not result["promoted"] and result["parent_unchanged"]


@pytest.mark.parametrize(
    "paid_calls,role",
    [(0, "buyer_initial"), (6, "reviewer"), (7, "buyer_candidate"), (10, "buyer_candidate")],
)
def test_shared_cost_guard_includes_prior_roles_and_retains_denial(setup, paid_calls, role):
    run, models, _, _ = setup
    # Full per-call reservation 10048 plus 28 per completed fixture call.
    budget = 10047 if paid_calls == 0 else 10048 + (paid_calls - 1) * 28
    result = run(budget_micro_usd=budget)
    assert result["status"] in {"REJECTED", "ERROR"}
    assert sum(m.calls for m in models) == paid_calls
    usage = result["usage"]
    assert usage["recorded_micro_usd"] == paid_calls * 28
    assert usage["admission_rejections"][-1]["reason"] == "ESTIMATED_COST_LIMIT"
    assert usage["admission_rejections"][-1]["role"] == role
    assert usage["role_usage"][role]["admission_rejections"] == 1
    assert not result["promoted"]


@pytest.mark.parametrize("role", ["buyer_initial", "reviewer", "buyer_candidate"])
@pytest.mark.parametrize("failure", ["missing", "partial", "exception"])
def test_unresolved_provider_usage_preserves_reservation_and_blocks_later_roles(
    setup, role, failure
):
    run, models, path, _ = setup

    class BrokenBuyer(BuyerFixture):
        async def stream(self, *args, **kwargs):
            targeted = self.policy.refresh_quote_before_order == (role == "buyer_candidate")
            async for chunk in faulty_stream(self, super().stream, targeted, args, kwargs):
                yield chunk

    class BrokenReviewer(ReviewerFixture):
        async def stream(self, *args, **kwargs):
            async for chunk in faulty_stream(self, super().stream, True, args, kwargs):
                yield chunk

    async def faulty_stream(model, stream, targeted, args, kwargs):
        if targeted and failure == "exception":
            model.calls += 1
            raise RuntimeError("synthetic provider failure")
        async for chunk in stream(*args, **kwargs):
            if targeted and "metadata" in chunk:
                if failure == "missing":
                    continue
                chunk = copy.deepcopy(chunk)
                del chunk["metadata"]["usage"]["outputTokens"]
            yield chunk

    result = run(
        buyer=BrokenBuyer if role != "reviewer" else BuyerFixture,
        reviewer=BrokenReviewer if role == "reviewer" else ReviewerFixture,
    )
    assert result["status"] in {"REJECTED", "ERROR"}
    assert [m.calls for m in models] == {
        "buyer_initial": [1],
        "reviewer": [6, 1],
        "buyer_candidate": [6, 1, 1],
    }[role]
    usage = result["usage"]
    assert not usage["all_usage_recorded"]
    assert usage["unresolved_reserved_micro_usd"] == 10048
    assert usage["calls"][-1]["role"] == role
    assert usage["calls"][-1]["status"] == ("ERROR" if failure == "exception" else "USAGE_UNKNOWN")
    assert usage["role_usage"][role]["unresolved_reserved_micro_usd"] == 10048
    assert result["parent_unchanged"] and not result["promoted"]
    if role == "buyer_candidate":
        assert len(list((path / "review/round-1/revisions").glob("*.json"))) == 1


def test_usage_attribution_cannot_be_reassigned_or_forged_and_limit_survives_reopen(setup):
    run, _, path, settings = setup
    run()
    ledger = UsageLedger(
        path / "usage.sqlite3",
        "b3-session",
        settings.model_id,
        settings.rates,
        settings.budget_micro_usd,
        settings.input_limit,
        settings.output_limit,
        "offline-scripted-model",
        max_calls=32,
        max_total_tokens=settings.max_total_tokens,
        max_tool_calls=settings.max_tool_calls,
    )
    artifact = json.loads((path / "initial/experiment.json").read_text())
    verify_attribution(artifact, ledger, "buyer_initial")
    for field, value in [("call_ids", []), ("scope", "live-model"), ("calls_sha256", "0" * 64)]:
        bad = copy.deepcopy(artifact)
        bad["accounting"][field] = value
        with pytest.raises(ContractError, match="EXPERIMENT_USAGE_MISMATCH"):
            verify_attribution(bad, ledger, "buyer_initial")
    with pytest.raises(ContractError, match="EXPERIMENT_USAGE_MISMATCH"):
        verify_attribution(artifact, ledger, "buyer_candidate")
    with pytest.raises(ContractError, match="SHARED_USAGE_CONFIG_MISMATCH"):
        validate_shared_ledger(
            ledger, replace(settings, max_model_calls=33), "offline-scripted-model"
        )
    with pytest.raises(ValueError, match="call limit cannot change"):
        UsageLedger(
            path / "usage.sqlite3",
            "b3-session",
            settings.model_id,
            settings.rates,
            settings.budget_micro_usd,
            settings.input_limit,
            settings.output_limit,
            "offline-scripted-model",
            max_calls=33,
        )


@pytest.mark.parametrize(
    "calls,role", [(0, "buyer_initial"), (6, "reviewer"), (7, "buyer_candidate"), (21, "reviewer")]
)
def test_shared_total_token_admission_includes_every_role(setup, calls, role):
    run, models, _, _ = setup
    cap = 9023 if calls == 0 else 9024 + (calls - 1) * 20
    result = run(max_total_tokens=cap)
    assert sum(m.calls for m in models) == calls
    usage = result["usage"]
    assert usage["recorded_total_tokens"] == calls * 20
    assert usage["admission_rejections"][-1]["reason"] == "TOTAL_TOKEN_LIMIT"
    assert usage["admission_rejections"][-1]["role"] == role
    assert usage["max_total_tokens"] == cap
    assert not result["promoted"]


@pytest.mark.parametrize("cap", [5, 6, 17])
def test_tool_budget_does_not_reset_for_candidate_and_cannot_promote_limited_run(setup, cap):
    run, _, path, _ = setup
    result = run(max_tool_calls=cap)
    usage = result["usage"]
    assert result["error"] == "SHARED_TOOL_CALL_LIMIT"
    assert usage["admitted_tool_calls"] == cap
    assert usage["role_usage"]["buyer_initial"]["admitted_tool_calls"] == 5
    assert usage["role_usage"]["buyer_candidate"]["admitted_tool_calls"] == cap - 5
    assert usage["tool_admissions"][-1]["status"] == "REJECTED"
    assert usage["tool_admissions"][-1]["role"] == "buyer_candidate"
    candidate = json.loads((path / "review/round-1/reexperiment/experiment.json").read_text())
    assert candidate["runtime_status"] == "LIMITED"
    assert not result["promoted"]
    if cap == 17:
        # Goods can arrive before a later observation hits its cap. Keep both facts.
        assert candidate["verdict"]["status"] == "COMPLETE"


def test_full_run_counts_failed_tool_attempt_and_all_tokens(setup):
    run, _, _, _ = setup
    result = run()
    usage = result["usage"]
    assert usage["recorded_total_tokens"] == 440
    assert usage["admitted_tool_calls"] == 18
    assert usage["unresolved_reserved_tokens"] == 0
    assert not usage["estimated_token_budget_exceeded"]
    assert usage["role_usage"]["buyer_initial"]["admitted_tool_calls"] == 5
    assert usage["role_usage"]["buyer_candidate"]["admitted_tool_calls"] == 13
