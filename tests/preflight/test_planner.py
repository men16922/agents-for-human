"""Scripted SDK plumbing: selection, full denominator and metered failures, not efficacy."""

import asyncio
import json

import pytest

from rehearsal.agents.metering import RateCard, UsageLedger
from rehearsal.experiments.review_runner import ReviewFixture
from rehearsal.preflight.contracts import catalog, snapshot
from rehearsal.preflight.planner import plan_and_measure
from rehearsal.preflight.report import build_report


class PlannerFixture(ReviewFixture):
    def __init__(self, missing=False, fail=False):
        super().__init__()
        self.missing, self.fail = missing, fail

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        names = {t["name"] for t in tool_specs}
        assert names == {"inspect_snapshot", "propose_plan", "rehearse_plan"}
        steps = [
            ("inspect_snapshot", {}),
            ("propose_plan", {"supplier": "A"}),
            ("rehearse_plan", {"supplier": "A", "condition": "stock-disappears"}),
        ]
        index = self.calls
        self.calls += 1
        if self.fail and index == 1:
            raise TimeoutError("Injected ambiguous provider failure")
        yield {"messageStart": {"role": "assistant"}}
        if index < len(steps):
            name, data = steps[index]
            yield {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {"toolUse": {"toolUseId": f"c-{index}", "name": name}},
                }
            }
            yield {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"toolUse": {"input": json.dumps(data)}},
                }
            }
        else:
            yield {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"text": "Fixture; independent verifier decides."},
                }
            }
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "tool_use" if index < len(steps) else "end_turn"}}
        if not self.missing:
            yield {
                "metadata": {
                    "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
                    "metrics": {"latencyMs": 1},
                }
            }


def ledger(tmp_path):
    return UsageLedger(
        tmp_path / "usage.sqlite3",
        "preview-test",
        "fixture",
        RateCard("1", "2", "0", "0", "offline fictional"),
        500000,
        24000,
        1024,
        "offline-scripted-model",
        max_calls=18,
        max_tool_calls=24,
        max_total_tokens=300000,
    )


def test_agent_proposal_does_not_control_report_or_test_denominator(tmp_path):
    usage = ledger(tmp_path)
    frozen = snapshot(catalog(), 1000)
    result = asyncio.run(plan_and_measure(PlannerFixture(), usage, "preview-test", frozen))
    assert result["runtime_status"] == "COMPLETED"
    assert result["proposed_supplier"] == "A"
    assert len(result["artifacts"]) == 12  # Agent called just one test.
    report = build_report(
        "preview-test",
        frozen,
        result["artifacts"],
        proposed_supplier=result["proposed_supplier"],
        generated_at=1100,
    )
    assert report["recommended_supplier"] == "B"
    assert len(usage.report()["calls"]) == 4
    assert usage.report()["role_usage"]["preflight_planner"]["model_calls"] == 4
    assert usage.report()["recorded_micro_usd"] == 112
    assert result["external_orders_created"] == 0


@pytest.mark.parametrize("missing,fail", [(True, False), (False, True)])
def test_unknown_model_usage_does_not_produce_complete_evidence(tmp_path, missing, fail):
    usage = ledger(tmp_path)
    result = asyncio.run(
        plan_and_measure(
            PlannerFixture(missing, fail), usage, "preview-test", snapshot(catalog(), 1000)
        )
    )
    assert result["runtime_status"] == "ERROR"
    assert not usage.report()["all_usage_recorded"]
    assert usage.report()["unresolved_reserved_micro_usd"] > 0
    assert len(result["artifacts"]) < 12
