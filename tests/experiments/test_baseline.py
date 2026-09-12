"""Frozen inputs and B0 behavior, with independent world evidence."""

import json
import runpy
from dataclasses import asdict
from pathlib import Path

import pytest

from rehearsal.agents.executor import SYSTEM_PROMPT, Limits, agent_for_tools, purchasing_tools
from rehearsal.evaluation.verifier import verify
from rehearsal.experiments.baseline import ToolPort, run_baseline
from rehearsal.experiments.frozen import SOURCES, FrozenPolicy, freeze
from rehearsal.experiments.policy import Policy, policy_prompt
from rehearsal.world import World
from rehearsal.world.storage import ContractError

ROOT = Path(__file__).resolve().parents[2]


def setup_world(tmp_path, partial=False):
    scenario = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    if partial:
        scenario["suppliers"]["A"]["items"]["light"]["stock"] = 0
        scenario["suppliers"]["B"]["items"]["tent"]["stock"] = 0
        for value in scenario["suppliers"]["C"]["items"].values():
            value["stock"] = 0
    world = World(tmp_path)
    world.create_run("r", scenario)
    return world, scenario


def test_frozen_policy_is_content_addressed_immutable_and_detects_source_change(tmp_path):
    snapshot = tmp_path / "source"
    for name in SOURCES:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    path = tmp_path / "policy.json"
    frozen = freeze(Policy(), path, snapshot)
    assert FrozenPolicy.load(path, snapshot) == frozen
    with pytest.raises(FileExistsError):
        freeze(Policy(), path, snapshot)
    changed = snapshot / SOURCES[0]
    changed.write_text(changed.read_text() + "\n# changed\n")
    with pytest.raises(ContractError, match="FROZEN_EXECUTION_SOURCE_CHANGED"):
        frozen.check()
    value = json.loads(path.read_text())
    value["policy"]["wait_ticks"] = 2
    path.write_text(json.dumps(value))
    with pytest.raises(ContractError, match="FROZEN_MANIFEST_MISMATCH"):
        FrozenPolicy.load(path, snapshot)


@pytest.mark.parametrize("partial,amount,count", [(False, 310, 1), (True, 360, 2)])
def test_baseline_buys_only_remaining_items_from_visible_quotes(tmp_path, partial, amount, count):
    world, scenario = setup_world(tmp_path / "world", partial)
    frozen = freeze(Policy(), tmp_path / "policy.json", ROOT)
    port = ToolPort(purchasing_tools(world, "r"))
    report = run_baseline(frozen, port, "b0")
    assert report["status"] == "GOAL_OBSERVED", report
    assert len(report["orders"]) == count
    verdict = verify(tmp_path / "world", "r", scenario)
    assert verdict.status == "COMPLETE" and verdict.spent == amount
    if partial:
        accepted = [r["result"]["items"] for r in report["trace"] if r["tool"] == "create_order"]
        assert accepted == [{"light": 6}, {"tent": 3}]


def test_unknown_authorization_queries_same_order_and_never_replaces_it(tmp_path):
    world, scenario = setup_world(tmp_path / "world")
    frozen = freeze(Policy(), tmp_path / "policy.json", ROOT)
    port = ToolPort(purchasing_tools(world, "r"))
    original = port.tools["authorize_payment"]
    port.tools["authorize_payment"] = lambda **args: (original(**args), {"status": "UNKNOWN"})[1]
    report = run_baseline(frozen, port, "b0")
    assert report["status"] == "GOAL_OBSERVED"
    assert [r["tool"] for r in port.trace].count("authorize_payment") == 1
    queries = [r["arguments"]["order_id"] for r in port.trace if r["tool"] == "get_payment"]
    assert set(queries) == set(report["orders"]) and len(report["orders"]) == 1
    assert verify(tmp_path / "world", "r", scenario).status == "COMPLETE"


def test_existing_unknown_reservation_stops_new_spending(tmp_path):
    world, _ = setup_world(tmp_path / "world")
    quote = world.shop.quote("r", "A", {"tent": 1})
    order = world.shop.create_order("r", quote["id"], "previous")
    world.authorize_payment("r", order["id"], "previous")
    frozen = freeze(Policy(), tmp_path / "policy.json", ROOT)
    port = ToolPort(purchasing_tools(world, "r"))
    result = run_baseline(frozen, port, "resume")
    assert result["status"] == "UNKNOWN" and result["reason"] == "EXISTING_RESERVATION"
    assert [t["tool"] for t in port.trace] == ["observe_world"]


def test_baseline_enforces_tool_limit_before_side_effect(tmp_path):
    world, _ = setup_world(tmp_path / "world")
    frozen = freeze(Policy(), tmp_path / "policy.json", ROOT)
    result = run_baseline(frozen, ToolPort(purchasing_tools(world, "r"), max_calls=2), "limited")
    assert result["status"] == "LIMITED" and not result["orders"]
    assert world.payments.balance("r")["reserved"] == 0


def test_real_sdk_receives_policy_prompt_without_changing_tool_authority(tmp_path):
    world, scenario = setup_world(tmp_path / "world")
    Scripted = runpy.run_path(str(ROOT / "tests/agents/test_executor.py"))["ScriptedModel"]
    observed = []

    class Recorder(Scripted):
        async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
            observed.append(system_prompt)
            async for event in super().stream(messages, tool_specs, system_prompt, **kwargs):
                yield event

    policy = Policy(supplier_preference="shortest_lead")
    frozen = freeze(policy, tmp_path / "policy.json", ROOT)
    frozen.check()
    agent_for_tools(Recorder(), purchasing_tools(world, "r"), Limits(), policy=frozen.policy)(
        "Buy supplies"
    )
    assert observed and all(prompt == policy_prompt(SYSTEM_PROMPT, policy) for prompt in observed)
    assert asdict(policy) == asdict(frozen.policy)
    assert verify(tmp_path / "world", "r", scenario).status == "COMPLETE"


@pytest.mark.parametrize("refresh,spent", [(False, 0), (True, 380)])
def test_refresh_policy_changes_decision_after_actual_world_price_update(tmp_path, refresh, spent):
    world, scenario = setup_world(tmp_path / "world")
    frozen = freeze(Policy(refresh_quote_before_order=refresh), tmp_path / "policy.json", ROOT)

    class PriceChangePort(ToolPort):
        changed = False

        def call(self, name, **arguments):
            result = super().call(name, **arguments)
            if name == "get_quotes" and arguments["supplier"] == "A" and not self.changed:
                world.shop.change_price("r", "A", "tent", 100)
                self.changed = True
            return result

    report = run_baseline(frozen, PriceChangePort(purchasing_tools(world, "r")), "b0")
    verdict = verify(tmp_path / "world", "r", scenario)
    assert verdict.spent == spent
    if refresh:
        assert report["status"] == "GOAL_OBSERVED" and verdict.status == "COMPLETE"
    else:
        assert report["reason"] == "STALE_QUOTE" and report["orders"] == []


def test_metered_sdk_runner_records_frozen_id_and_actual_prompt_hash(tmp_path):
    from rehearsal.agents.runner import ModelSettings, execute
    from rehearsal.experiments.frozen import digest

    Scripted = runpy.run_path(str(ROOT / "tests/agents/test_executor.py"))["ScriptedModel"]
    values = runpy.run_path(str(ROOT / "tests/agents/test_runner_settings.py"))["configured"]()
    values["REHEARSAL_MODEL_ID"] = "offline-scripted-fixture"
    settings = ModelSettings.from_values(values)
    scenario = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    frozen = freeze(Policy(), tmp_path / "policy.json", ROOT)
    report = execute(
        Scripted(),
        settings,
        tmp_path / "run",
        scenario,
        "frozen-test",
        "offline-scripted-model",
        frozen,
    )
    assert report["success"] and report["verdict"]["status"] == "COMPLETE"
    assert report["frozen_id"] == frozen.identifier
    assert report["prompt_sha256"] == frozen.prompt_sha256
    assert report["prompt_sha256"] == digest(policy_prompt(SYSTEM_PROMPT, frozen.policy).encode())
    assert report["usage"]["all_usage_recorded"]


def test_missing_required_item_blocks_spending_on_available_subset(tmp_path):
    from rehearsal.evaluation.pilot import known_cases

    scenario = known_cases(ROOT)["impossible"]
    world = World(tmp_path / "world")
    world.create_run("r", scenario)
    frozen = freeze(Policy(), tmp_path / "policy.json", ROOT)
    port = ToolPort(purchasing_tools(world, "r"))
    result = run_baseline(frozen, port, "impossible")
    assert result["reason"] == "NO_EXECUTABLE_QUOTE"
    assert result["orders"] == []
    assert all(row["tool"] in {"observe_world", "get_quotes"} for row in port.trace)
    verdict = verify(tmp_path / "world", "r", scenario)
    assert verdict.status == "INCOMPLETE" and verdict.spent == verdict.reserved == 0
    assert any(row.get("result", {}).get("items") == {"light": 6} for row in port.trace)
