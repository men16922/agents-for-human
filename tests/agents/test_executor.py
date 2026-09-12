from __future__ import annotations

import json
from pathlib import Path

import pytest
from strands.models.model import Model

from rehearsal.agents.executor import Limits, build_agent, purchasing_tools
from rehearsal.evaluation.verifier import verify
from rehearsal.world import World
from rehearsal.world.storage import ContractError


class ScriptedModel(Model):
    """Deterministic SDK protocol fixture. This is not a real model success."""

    def __init__(self, repeat=False):
        self.calls = 0
        self.repeat = repeat

    def update_config(self, **kwargs):
        pass

    def get_config(self):
        return {"model_id": "offline-scripted-fixture"}

    async def structured_output(self, *args, **kwargs):
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        index = self.calls
        self.calls += 1
        last = None
        for message in messages:
            for block in message["content"]:
                if "toolResult" in block and not self.repeat:
                    content = block["toolResult"]["content"][0]
                    last = content.get("json") or json.loads(content.get("text", "{}"))
        if self.repeat:
            name, data = "observe_world", {}
        elif index == 0:
            name, data = "observe_world", {}
        elif index == 1:
            name, data = "get_quotes", {"supplier": "A", "items": {"tent": 3, "light": 6}}
        elif index == 2:
            name, data = "create_order", {"quote_id": last["id"], "idempotency_key": "supplies"}
        elif index == 3:
            name, data = "authorize_payment", {"order_id": last["id"], "idempotency_key": "pay"}
        elif index == 4:
            name, data = "wait_for_updates", {"ticks": 10}
        elif index == 5:
            name, data = "get_inventory", {}
        else:
            name, data = "", {}
        yield {"messageStart": {"role": "assistant"}}
        if name:
            yield {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {"toolUse": {"toolUseId": f"call-{index}", "name": name}},
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
                "contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "Fixture done."}}
            }
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "tool_use" if name else "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
                "metrics": {"latencyMs": 1},
            }
        }


@pytest.fixture
def setup(tmp_path):
    scenario = json.loads(
        (Path(__file__).resolve().parents[2] / "scenarios/normal-v1.json").read_text()
    )
    world = World(tmp_path)
    world.create_run("r", scenario)
    return world, scenario, tmp_path


def test_real_strands_loop_with_scripted_model_executes_registered_tools(setup):
    world, scenario, path = setup
    model = ScriptedModel()
    limits = Limits()
    agent = build_agent(model, world, "r", limits)
    result = agent("Complete the event-supplies goal.")
    assert model.calls == limits.model_calls == 7
    assert limits.tool_calls == 6
    assert result.metrics.accumulated_usage["inputTokens"] == 84
    assert result.metrics.accumulated_usage["outputTokens"] == 56
    assert verify(path, "r", scenario).status == "COMPLETE"


def test_sdk_hooks_enforce_model_and_tool_limits(setup):
    world, _, _ = setup
    model = ScriptedModel(repeat=True)
    limits = Limits(max_model_calls=3, max_tool_calls=1)
    agent = build_agent(model, world, "r", limits)
    result = agent("Keep observing.")
    assert model.calls == limits.model_calls == 3
    assert limits.tool_calls == 1
    assert "MODEL_CALL_LIMIT" in str(result)
    assert world.payments.balance("r")["spent"] == 0


def test_tools_do_not_expose_seed_admin_actions_or_run_selection(setup):
    world, scenario, _ = setup
    world.create_run("other", scenario)
    tools = {t.tool_name: t for t in purchasing_tools(world, "r")}
    assert set(tools) == {
        "observe_world",
        "get_quotes",
        "create_order",
        "authorize_payment",
        "get_payment",
        "get_order",
        "get_inventory",
        "wait_for_updates",
    }
    observed = tools["observe_world"]()
    assert "seed" not in json.dumps(observed)
    assert "fixture" not in observed and "metadata" not in observed
    for tool in tools.values():
        assert "run_id" not in tool.tool_spec["inputSchema"]["json"].get("properties", {})
    quote = world.shop.quote("other", "A", {"tent": 1})
    other_order = world.shop.create_order("other", quote["id"], "other-order")
    with pytest.raises(ContractError, match="NOT_FOUND"):
        tools["get_order"](order_id=other_order["id"])
    with pytest.raises(ContractError, match="NOT_FOUND"):
        tools["create_order"](quote_id=quote["id"], idempotency_key="steal")
    with pytest.raises(ContractError, match="WAIT_TOO_LONG"):
        tools["wait_for_updates"](ticks=100)


def test_sdk_hooks_persist_each_usage_without_counting_canceled_calls(setup):
    from rehearsal.agents.metering import MeterHooks, RateCard, UsageLedger

    world, _, path = setup
    ledger = UsageLedger(
        path / "usage.sqlite3",
        "r",
        "scripted",
        RateCard("1", "2", "0", "1", "fictional offline test rates"),
        1_000_000,
        10_000,
        100,
        scope="offline-scripted-model",
    )
    meter = MeterHooks(ledger)
    model = ScriptedModel(repeat=True)
    agent = build_agent(model, world, "r", Limits(max_model_calls=2), meter)
    agent("Observe until the call limit.")
    report = ledger.report()
    assert len(report["calls"]) == model.calls == 2
    assert report["recorded_micro_usd"] == 56
    assert report["all_usage_recorded"]


def test_sdk_meter_stops_before_provider_when_budget_is_insufficient(setup):
    from rehearsal.agents.metering import MeterHooks, RateCard, UsageLedger

    world, _, path = setup
    ledger = UsageLedger(
        path / "usage.sqlite3",
        "r",
        "scripted",
        RateCard("1", "2", "0", "1", "fictional offline test rates"),
        1,
        10_000,
        100,
        scope="offline-scripted-model",
    )
    meter = MeterHooks(ledger)
    model = ScriptedModel(repeat=True)
    result = build_agent(model, world, "r", Limits(), meter)("Observe.")
    assert model.calls == 0
    assert ledger.report()["calls"] == []
    assert "ESTIMATED_COST_LIMIT" in str(result)


@pytest.mark.parametrize("missing", ["all-metadata", "usage", "outputTokens"])
def test_sdk_default_zero_usage_does_not_erase_missing_provider_accounting(setup, missing):
    from rehearsal.agents.metering import MeterHooks, RateCard, UsageLedger

    world, _, path = setup
    ledger = UsageLedger(
        path / "raw-usage.sqlite3",
        "r",
        "scripted",
        RateCard("1", "2", "0", "0", "fictional offline rates"),
        100000,
        10000,
        100,
        scope="offline-scripted-model",
    )

    class Missing(ScriptedModel):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                if "metadata" in event:
                    if missing == "all-metadata":
                        continue
                    if missing == "usage":
                        event["metadata"].pop("usage")
                    else:
                        event["metadata"]["usage"].pop("outputTokens")
                yield event

    model = Missing(repeat=True)
    build_agent(model, world, "r", Limits(), MeterHooks(ledger))("Observe repeatedly.")
    report = ledger.report()
    assert model.calls == len(report["calls"]) == 1
    assert report["calls"][0]["status"] == "USAGE_UNKNOWN"
    assert not report["all_usage_recorded"]
    assert report["unresolved_reserved_micro_usd"] == 10200


def runner_settings():
    from rehearsal.agents.metering import RateCard
    from rehearsal.agents.runner import ModelSettings

    return ModelSettings(
        "offline",
        "offline",
        "offline-scripted-fixture",
        RateCard("1", "2", "0", "1", "fictional offline test rates"),
        1_000_000,
        input_limit=10_000,
    )


def test_runner_exports_durable_usage_tool_trace_and_independent_verdict(setup):
    from rehearsal.agents.runner import execute

    _, scenario, path = setup
    destination = path / "invocation"
    report = execute(
        ScriptedModel(), runner_settings(), destination, scenario, "new", "offline-scripted-model"
    )
    assert report["success"]
    assert report["scope"] == "offline-scripted-model"
    assert report["verdict"]["status"] == "COMPLETE"
    assert report["usage"]["recorded_micro_usd"] == 196
    assert report["tool_calls"] == 6
    assert len((destination / "tools.jsonl").read_text().splitlines()) == 6
    saved = json.loads((destination / "report.json").read_text())
    assert saved == report
    with pytest.raises(FileExistsError):
        execute(
            ScriptedModel(),
            runner_settings(),
            destination,
            scenario,
            "new",
            "offline-scripted-model",
        )


def test_runner_records_failed_model_attempt_as_unknown_usage(setup):
    from rehearsal.agents.runner import execute

    class FailedModel(ScriptedModel):
        async def stream(self, *args, **kwargs):
            self.calls += 1
            raise TimeoutError("simulated lost model response")
            yield

    _, scenario, path = setup
    model = FailedModel()
    report = execute(
        model, runner_settings(), path / "failure", scenario, "failed", "offline-scripted-model"
    )
    assert not report["success"]
    assert report["runtime_status"] == "ERROR"
    assert model.calls == 1
    assert report["usage"]["calls"][0]["status"] == "ERROR"
    assert not report["usage"]["all_usage_recorded"]
    assert report["usage"]["unresolved_reserved_micro_usd"] > 0
    assert report["verdict"]["status"] == "INCOMPLETE"
