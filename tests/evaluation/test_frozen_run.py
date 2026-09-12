import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.evaluation.frozen_run import (
    EvaluationBuyer,
    fixture_factory,
    known_pair,
    run_cell,
)
from rehearsal.experiments.policy import Policy
from rehearsal.world.storage import ContractError

ROOT = Path(__file__).parents[2]


@pytest.fixture
def setup(tmp_path):
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-evaluation-fixture",
        RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
        100000,
        max_model_calls=48,
        max_tool_calls=48,
    )
    training, evaluation = known_pair(ROOT)
    directory = tmp_path / "cell"
    models = []

    def run(method="B3", factory=fixture_factory, **limits):
        def track(kind, policy):
            model = factory(kind, policy)
            models.append((kind, model))
            return model

        return run_cell(
            method,
            track,
            replace(settings, **limits),
            directory,
            training,
            evaluation,
            "offline-scripted-model",
        )

    return run, directory, models, settings, training, evaluation


@pytest.mark.parametrize(
    "method,calls,tokens,cost,tools",
    [
        ("B0", 0, 0, 0, 24),
        ("B1", 14, 280, 392, 13),
        ("B2", 37, 740, 1036, 35),
        ("B3", 36, 720, 1008, 31),
    ],
)
def test_known_evaluation_keeps_training_and_execution_in_one_budget(
    setup, method, calls, tokens, cost, tools
):
    run, path, models, _, _, _ = setup
    result = run(method)
    assert result["status"] == "EVALUATED"
    assert result["verdict"]["status"] == "COMPLETE" and result["verdict"]["spent"] == 380
    assert len(result["total_usage"]["calls"]) == calls
    assert result["total_usage"]["recorded_total_tokens"] == tokens
    assert result["total_usage"]["recorded_micro_usd"] == cost
    assert result["total_tool_calls"] == tools
    assert sum(m.calls for _, m in models) == calls
    assert (
        result["learning_usage"]["recorded_micro_usd"]
        + result["evaluation_usage"]["recorded_micro_usd"]
        == cost
    )
    assert not result["promoted"] and not result["model_efficacy_verified"]
    assert not result["held_out_evaluation_verified"]
    policy = json.loads((path / "policy.json").read_text())
    assert policy["learning_evidence"] == result["learning_artifact_hashes"]
    evaluation = json.loads((path / "evaluation/evidence.json").read_text())
    assert evaluation["run_id"] == "evaluation"
    assert evaluation["tables"]["runs"][0]["id"] == "evaluation"
    assert (
        json.loads(evaluation["tables"]["runs"][0]["metadata"])["policy_version"]
        == result["frozen_id"]
    )
    with pytest.raises(FileExistsError):
        run(method)


def test_evaluation_agent_receives_only_frozen_policy_and_fresh_dialog(setup):
    run, _, _, _, _, _ = setup
    observed = []

    class Inspect(EvaluationBuyer):
        async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
            if not self.calls:
                observed.append(copy.deepcopy(messages))
                assert len(messages) == 1
                assert "simulation-" not in str(messages) and "Known stale" not in str(messages)
                assert "Frozen purchasing policy" in system_prompt
            async for chunk in super().stream(messages, tool_specs, system_prompt, **kwargs):
                yield chunk

    result = run(
        "B2",
        factory=lambda kind, p: Inspect(p) if kind == "evaluation" else fixture_factory(kind, p),
    )
    assert result["status"] == "EVALUATED" and len(observed) == 1


@pytest.mark.parametrize("method,training_calls", [("B2", 23), ("B3", 22)])
@pytest.mark.parametrize("limit", ["calls", "tokens", "cost", "tools"])
def test_training_budget_cannot_reset_before_evaluation(setup, method, training_calls, limit):
    run, path, models, _, _, _ = setup
    limits = {
        "calls": {"max_model_calls": training_calls},
        "tokens": {"max_total_tokens": 9024 + (training_calls - 1) * 20},
        "cost": {"budget_micro_usd": 10048 + (training_calls - 1) * 28},
        "tools": {"max_tool_calls": 22 if method == "B2" else 18},
    }[limit]
    result = run(method, **limits)
    assert result["status"] == "EVALUATION_INCOMPLETE"
    assert result["learning_status"] == "CANDIDATE_EVALUATED_NOT_PROMOTED"
    assert result["evaluation_status"] == "LIMITED"
    evaluation = json.loads((path / "evaluation/report.json").read_text())
    assert (
        evaluation["stop_reason"]
        == {
            "calls": "MODEL_CALL_LIMIT",
            "tokens": "TOTAL_TOKEN_LIMIT",
            "cost": "ESTIMATED_COST_LIMIT",
            "tools": "SHARED_TOOL_CALL_LIMIT",
        }[limit]
    )
    assert not evaluation["success"]
    assert result["total_usage"]["recorded_micro_usd"] >= training_calls * 28
    assert not result["promoted"]
    assert sum(m.calls for _, m in models) == training_calls + (1 if limit == "tools" else 0)


@pytest.mark.parametrize("fault", ["missing", "partial", "exception"])
def test_evaluation_usage_failure_retains_all_training_cost_and_unknown_reservation(setup, fault):
    run, _, _, _, _, _ = setup

    class Broken(EvaluationBuyer):
        async def stream(self, *args, **kwargs):
            if fault == "exception":
                self.calls += 1
                raise RuntimeError("synthetic evaluation failure")
            async for event in super().stream(*args, **kwargs):
                if "metadata" in event:
                    if fault == "missing":
                        continue
                    event = copy.deepcopy(event)
                    del event["metadata"]["usage"]["outputTokens"]
                yield event

    result = run(factory=lambda k, p: Broken(p) if k == "evaluation" else fixture_factory(k, p))
    assert result["status"] == "EVALUATION_INCOMPLETE"
    assert result["learning_usage"]["recorded_micro_usd"] == 616
    assert result["total_usage"]["recorded_micro_usd"] == 616
    assert result["evaluation_usage"]["unresolved_reserved_micro_usd"] == 10048
    assert result["total_usage"]["unresolved_reserved_tokens"] == 9024
    assert result["evaluation_usage"]["calls"][-1]["role"] == "buyer_evaluation"


def test_failed_learning_leaves_evaluation_unexecuted_instead_of_falling_back(setup):
    run, _, models, _, _, _ = setup
    result = run("B3", max_model_calls=3)
    assert result["status"] == "REJECTED" and result["error"] == "LEARNING_NOT_READY"
    assert result["evaluation_status"] == "NOT_RUN"
    assert not any(k == "evaluation" for k, _ in models)
    assert result["total_usage"]["recorded_micro_usd"] == 84
    assert "frozen_id" not in result


@pytest.mark.parametrize("damage", ["edit", "delete"])
def test_policy_file_mutation_before_evaluation_blocks_provider_call(setup, damage):
    run, path, models, _, _, _ = setup

    def factory(kind, policy):
        if kind == "evaluation":
            if damage == "delete":
                (path / "policy.json").unlink()
            else:
                (path / "policy.json").write_text("{}")
        return fixture_factory(kind, policy)

    result = run("B2", factory=factory)
    assert result["error"] == "FROZEN_POLICY_FILE_CHANGED"
    assert models[-1][0] == "evaluation" and models[-1][1].calls == 0
    assert not (path / "evaluation").exists()


def test_learning_artifact_changed_during_evaluation_is_rejected(setup):
    run, path, _, _, _, _ = setup

    class Mutator(EvaluationBuyer):
        async def stream(self, *args, **kwargs):
            if not self.calls:
                (path / "learning/response.txt").write_text("replaced history")
            async for chunk in super().stream(*args, **kwargs):
                yield chunk

    result = run(
        "B2", factory=lambda k, p: Mutator(p) if k == "evaluation" else fixture_factory(k, p)
    )
    assert result["status"] == "REJECTED" and result["error"] == "LEARNING_ARTIFACT_CHANGED"
    assert result["evaluation_status"] == "COMPLETED"
    assert not result["promoted"]


def test_reused_provider_context_is_rejected_across_learning_and_evaluation(setup):
    run, _, _, _, _, _ = setup
    shared = EvaluationBuyer(Policy(refresh_quote_before_order=False))

    def factory(kind, policy):
        if kind == "evaluation" or (kind == "buyer" and not policy.refresh_quote_before_order):
            return shared
        return fixture_factory(kind, policy)

    result = run(factory=factory)
    assert result["error"] == "EVALUATION_MODEL_CONTEXT_REUSED"
    assert result["evaluation_status"] == "NOT_RUN"


def test_renaming_or_reseeding_training_does_not_make_a_new_condition(setup):
    _, path, _, settings, training, _ = setup
    evaluation = copy.deepcopy(training)
    evaluation.update(scenario_version="supposedly-new", seed=999)
    with pytest.raises(ContractError, match="EVALUATION_CONDITION_REUSED"):
        run_cell(
            "B1", fixture_factory, settings, path, training, evaluation, "offline-scripted-model"
        )
    assert not path.exists()


def test_truncated_final_response_is_not_a_success_even_after_delivery(setup):
    run, path, _, _, _, _ = setup

    class Truncated(EvaluationBuyer):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                if event.get("messageStop", {}).get("stopReason") == "end_turn":
                    event = {"messageStop": {"stopReason": "max_tokens"}}
                yield event

    result = run("B1", factory=lambda kind, policy: Truncated(policy))
    assert result["verdict"]["status"] == "COMPLETE"
    assert result["evaluation_status"] == "ERROR"
    assert (
        json.loads((path / "evaluation/report.json").read_text())["error_type"]
        == "MaxTokensReachedException"
    )
    assert result["status"] == "EVALUATION_INCOMPLETE"
    assert result["total_usage"]["all_usage_recorded"]
