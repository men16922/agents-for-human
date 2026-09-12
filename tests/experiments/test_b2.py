import copy
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from rehearsal.agents.metering import MeterHooks, RateCard, UsageLedger
from rehearsal.agents.runner import ModelSettings
from rehearsal.experiments.b2 import SimulationFixture, Simulations, run_b2
from rehearsal.experiments.policy import Policy
from rehearsal.world import World
from rehearsal.world.storage import ContractError

ROOT = Path(__file__).parents[2]


@pytest.fixture
def setup(tmp_path):
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-b2-fixture",
        RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
        100000,
        max_model_calls=32,
    )
    scenario = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    directory = tmp_path / "b2"

    def run(model=None, **kwargs):
        return run_b2(
            model or SimulationFixture(),
            replace(settings, **kwargs),
            directory,
            scenario,
            "offline-scripted-model",
        )

    return run, directory, settings, scenario


def test_one_agent_retains_dialog_and_tests_revision_without_peer(setup):
    run, directory, _, _ = setup

    class Inspect(SimulationFixture):
        histories = []

        async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
            self.histories.append(copy.deepcopy(messages))
            assert {t["name"] for t in tool_specs} == {
                "begin_experiment",
                "finish_experiment",
                "observe_world",
                "get_quotes",
                "create_order",
                "authorize_payment",
                "get_payment",
                "get_order",
                "get_inventory",
                "wait_for_updates",
            }
            assert "There is no peer reviewer" in system_prompt
            assert all("seed" not in str(m) for m in messages)
            async for event in super().stream(messages, tool_specs, system_prompt, **kwargs):
                yield event

    model = Inspect()
    report = run(model)
    assert report["status"] == "CANDIDATE_EVALUATED_NOT_PROMOTED"
    assert report["single_agent"] and report["peer_reviewer_calls"] == 0
    assert model.calls == 23
    assert len(model.histories[-1]) > len(model.histories[0])
    assert model.histories[-1][: len(model.histories[0])] == model.histories[0]
    assert "simulation-1" in str(model.histories[-1]) and "simulation-2" in str(model.histories[-1])
    assert report["parent_unchanged"] and not report["promoted"]
    assert not report["model_efficacy_verified"] and not report["held_out_evaluation_verified"]
    before, after = report["experiments"]
    assert before["snapshot_sha256"] == after["snapshot_sha256"]
    assert before["verdict"]["status"] == "INCOMPLETE" and before["verdict"]["spent"] == 0
    assert after["verdict"]["status"] == "COMPLETE" and after["verdict"]["spent"] == 380
    assert report["initial_policy"]["refresh_quote_before_order"] is False
    usage = report["usage"]
    assert usage["recorded_micro_usd"] == 644 and usage["recorded_total_tokens"] == 460
    assert usage["admitted_tool_calls"] == 22 and len(usage["calls"]) == 23
    assert set(usage["role_usage"]) == {"simulation_agent"}
    assert {c["execution_id"] for c in usage["calls"]} == {
        "simulation-controller",
        "simulation-1",
        "simulation-2",
    }
    revision = json.loads(next((directory / "revisions").glob("*.json")).read_text())
    assert revision["review"]["review_id"] == "self-reflection"
    assert revision["review"]["counterexamples"] == ["simulation-1"]


@pytest.mark.parametrize(
    "decision,citations,expected",
    [
        ("keep", ["simulation-1", "simulation-2"], "NO_CHANGE"),
        ("keep", ["simulation-1", "invented"], "REJECTED"),
        ("revise", ["simulation-1", "simulation-2"], "REJECTED"),
    ],
)
def test_keep_can_compare_both_verified_experiments_but_revision_cites_initial_policy(
    setup, decision, citations, expected
):
    run, _, _, _ = setup

    class Compare(SimulationFixture):
        def action(self, messages):
            name, data = super().action(messages)
            if not name:
                data.update(
                    decision=decision,
                    reason="Compare the supplied initial and revised experiments.",
                    counterexamples=citations,
                    candidate_policy=None if decision == "keep" else asdict(Policy()),
                )
            return name, data

    report = run(Compare())
    assert len(report["experiments"]) == 2
    assert report["status"] == expected
    if expected == "REJECTED":
        assert report["error"] == "INVALID_REVIEW_COUNTEREXAMPLES"
    else:
        assert report["proposal"]["counterexamples"] == citations
        assert report["proposal"]["candidate_policy"] is None
    assert report["parent_unchanged"] and not report["promoted"]


@pytest.mark.parametrize("fault", ["missing", "partial", "exception"])
@pytest.mark.parametrize("call", [1, 8, 23])
def test_unknown_or_failed_usage_blocks_proposal_and_preserves_reservation(setup, fault, call):
    run, _, _, _ = setup

    class Broken(SimulationFixture):
        async def stream(self, *args, **kwargs):
            target = self.calls + 1 == call
            if target and fault == "exception":
                self.calls += 1
                raise RuntimeError("synthetic provider failure")
            async for chunk in super().stream(*args, **kwargs):
                if target and "metadata" in chunk:
                    if fault == "missing":
                        continue
                    chunk = copy.deepcopy(chunk)
                    del chunk["metadata"]["usage"]["outputTokens"]
                yield chunk

    model = Broken()
    report = run(model)
    assert model.calls == call
    assert report["status"] in {"REJECTED", "ERROR"} and not report["promoted"]
    assert report["usage"]["unresolved_reserved_micro_usd"] == 10048
    assert report["usage"]["unresolved_reserved_tokens"] == 9024
    assert report["usage"]["calls"][-1]["status"] == (
        "ERROR" if fault == "exception" else "USAGE_UNKNOWN"
    )
    assert report["parent_unchanged"]
    assert "candidate_policy" not in report


@pytest.mark.parametrize(
    "limits,expected",
    [
        ({"max_model_calls": 7}, "MODEL_CALL_LIMIT"),
        ({"max_total_tokens": 9024}, "TOTAL_TOKEN_LIMIT"),
        ({"budget_micro_usd": 10048}, "ESTIMATED_COST_LIMIT"),
        ({"max_tool_calls": 8}, "TOOL_CALL_LIMIT"),
    ],
)
def test_limits_span_simulations_and_leave_interrupted_evidence(setup, limits, expected):
    run, path, _, _ = setup
    report = run(**limits)
    assert report["error"] == expected
    assert not report["promoted"] and report["parent_unchanged"]
    assert report["experiments"]
    for experiment in report["experiments"]:
        assert (path / experiment["experiment_id"] / "evidence.json").exists()
    assert report["usage"]["all_usage_recorded"]


@pytest.mark.parametrize("fault", ["unknown-citation", "unsafe-policy", "untested", "tamper"])
def test_policy_proposal_requires_valid_matching_experiment_evidence(setup, fault):
    run, directory, _, _ = setup

    class Bad(SimulationFixture):
        def action(self, messages):
            name, value = super().action(messages)
            if fault == "untested" and self.calls == 8:
                return "", {
                    "decision": "revise",
                    "reason": "untried",
                    "counterexamples": ["simulation-1"],
                    "candidate_policy": asdict(Policy()),
                }
            if not name:
                if fault == "unknown-citation":
                    value["counterexamples"] = ["not-an-experiment"]
                elif fault == "unsafe-policy":
                    value["candidate_policy"]["uncertain_payment_action"] = "replace_order"
                elif fault == "tamper":
                    path = directory / "simulation-1/experiment.json"
                    artifact = json.loads(path.read_text())
                    artifact["tool_trace"] = []
                    path.write_text(json.dumps(artifact))
            return name, value

    report = run(Bad())
    assert report["status"] == "REJECTED"
    assert (
        report["error"]
        == {
            "unknown-citation": "INVALID_REVIEW_COUNTEREXAMPLES",
            "unsafe-policy": "UNSAFE_UNKNOWN_PAYMENT_POLICY",
            "untested": "CANDIDATE_NOT_EVALUATED",
            "tamper": "SIMULATION_ARTIFACT_CHANGED",
        }[fault]
    )
    assert not (directory / "revisions").exists()
    assert not report["promoted"] and report["parent_unchanged"]


def test_simulation_lifecycle_is_bounded_and_never_exposes_parent_tools(setup, tmp_path):
    _, _, settings, scenario = setup
    parent = World(tmp_path / "parent")
    parent.create_run("parent", scenario, environment="operating-test")
    original = parent.snapshot("parent")
    meter = MeterHooks(
        UsageLedger(
            tmp_path / "usage.sqlite3",
            "b2",
            settings.model_id,
            settings.rates,
            100000,
            8000,
            1024,
            "offline-scripted-model",
        )
    )
    simulations = Simulations(parent, scenario, tmp_path / "simulations", meter)
    with pytest.raises(ContractError, match="NO_ACTIVE_EXPERIMENT"):
        simulations.call("observe_world")
    with pytest.raises(ContractError, match="INITIAL_POLICY_REQUIRED"):
        simulations.begin(asdict(Policy()))
    with pytest.raises(ContractError, match="POLICY_FIELDS_MISMATCH"):
        simulations.begin(asdict(Policy()) | {"budget": 50000})
    simulations.begin(asdict(Policy(refresh_quote_before_order=False)))
    with pytest.raises(ContractError, match="EXPERIMENT_ALREADY_ACTIVE"):
        simulations.begin(asdict(Policy()))
    quote = simulations.call("get_quotes", supplier="A", items={"tent": 3})
    simulations.finish()
    simulations.begin(asdict(Policy()))
    with pytest.raises(ContractError):
        simulations.call("create_order", quote_id=quote["id"], idempotency_key="cross-experiment")
    simulations.finish()
    with pytest.raises(ContractError, match="SIMULATION_LIMIT"):
        simulations.begin(asdict(Policy()))
    assert parent.snapshot("parent") == original
