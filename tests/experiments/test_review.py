import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.experiments.policy import Policy
from rehearsal.experiments.rehearse import experiment
from rehearsal.experiments.review import parse_proposal, review_policy
from rehearsal.experiments.review_runner import ReviewFixture
from rehearsal.world import World
from rehearsal.world.storage import ContractError


def test_nova_fenced_review_preserves_the_json_decision():
    response = (
        '```json\n{\n  "decision": "keep",\n'
        '  "reason": "The experiment completed successfully with all items received '
        'and no policy violations observed. The independent verdict confirms COMPLETE '
        'status with received items matching the goal.",\n'
        '  "counterexamples": [],\n  "candidate_policy": null\n}\n```\n'
    )
    proposal, candidate = parse_proposal(response, Policy(), {"initial"})
    assert proposal["decision"] == "keep" and candidate is None
    assert proposal["counterexamples"] == []


@pytest.mark.parametrize(
    "response,code",
    [
        ('Explanation\n```json\n{}\n```', "MALFORMED_REVIEW"),
        ('```json\n{}\n```\n```json\n{}\n```', "MALFORMED_REVIEW"),
        ('```json\n{"decision":"keep","decision":"revise"}\n```', "DUPLICATE_REVIEW_FIELD"),
        ('```json\n{"decision":"keep","extra":"ignore policy"}\n```', "INVALID_REVIEW_FIELDS"),
    ],
)
def test_fenced_reviews_still_reject_ambiguous_or_invalid_objects(response, code):
    with pytest.raises(ContractError) as error:
        parse_proposal(response, Policy(), {"initial"})
    assert error.value.code == code


@pytest.fixture
def setup(tmp_path):
    scenario = json.loads(
        (Path(__file__).resolve().parents[2] / "scenarios/normal-v1.json").read_text()
    )
    parent = World(tmp_path / "parent")
    parent.create_run("parent", scenario, environment="operating-test")
    before = Policy(refresh_quote_before_order=False)
    experiment(parent, "parent", tmp_path / "before", "before", before, scenario)
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-review-fixture",
        RateCard("1", "2", "0", "0", "fictional fixture rates"),
        100000,
        input_limit=8000,
        output_limit=1024,
    )
    evaluated = []

    def reevaluate(policy, destination, eid):
        evaluated.append(policy)
        experiment(parent, "parent", destination, eid, policy, scenario)
        return destination / "experiment.json"

    def run(factory, **kwargs):
        return review_policy(
            factory,
            kwargs.pop("settings", settings),
            tmp_path / "review",
            before,
            {"before": tmp_path / "before/experiment.json"},
            kwargs.pop("reevaluate", reevaluate),
            scope="offline-scripted-model",
            **kwargs,
        )

    return run, parent, evaluated, tmp_path, settings


def test_two_fresh_reviewers_share_budget_and_link_identical_snapshot_reexperiment(setup):
    run, parent, evaluated, path, _ = setup
    original = parent.snapshot("parent")
    models = []

    class Inspect(ReviewFixture):
        async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
            assert not tool_specs
            self.input = copy.deepcopy(messages)
            self.prompt = system_prompt
            async for value in super().stream(messages, tool_specs, **kwargs):
                yield value

    def factory(_):
        model = Inspect()
        models.append(model)
        return model

    report = run(factory)
    assert report["status"] == "CANDIDATE_EVALUATED_NOT_PROMOTED"
    assert not report["promoted"] and not report["review_efficacy_verified"]
    assert len(models) == 2 and all(m.calls == 1 for m in models)
    assert all(len(m.input) == 1 for m in models)
    assert [r["status"] for r in report["rounds"]] == [
        "CANDIDATE_EVALUATED_NOT_PROMOTED",
        "NO_CHANGE",
    ]
    assert report["usage"]["recorded_micro_usd"] == 56
    assert report["usage"]["all_usage_recorded"] and not report["usage"]["billing_verified"]
    assert evaluated == [Policy()]
    assert parent.snapshot("parent") == original
    first = report["rounds"][0]
    assert first["reexperiment"]["independent_verdict"]["status"] == "COMPLETE"
    revision = json.loads(next((path / "review/round-1/revisions").glob("*.json")).read_text())
    assert revision["review"]["reviewer_kind"] == "scripted-fixture"
    assert revision["status"] == "PROPOSED_REQUIRES_REEXPERIMENT"
    assert revision["diff"] == {"refresh_quote_before_order": {"before": False, "after": True}}


@pytest.mark.parametrize(
    "fault", ["unknown-id", "extra-field", "unsafe-policy", "bad-json", "duplicate", "too-large"]
)
def test_invalid_proposals_never_run_a_candidate(setup, fault):
    run, parent, evaluated, _, _ = setup
    original = parent.snapshot("parent")

    class Bad(ReviewFixture):
        def answer(self, messages):
            if fault == "bad-json":
                return "```json\n{}\n```"
            if fault == "duplicate":
                return '{"decision":"keep","decision":"revise"}'
            if fault == "too-large":
                return "x" * 8193
            value = json.loads(super().answer(messages))
            if fault == "unknown-id":
                value["counterexamples"] = ["../../private-file"]
            if fault == "extra-field":
                value["candidate_policy"]["budget"] = 50000
            if fault == "unsafe-policy":
                value["candidate_policy"]["uncertain_payment_action"] = "replace_order"
            return json.dumps(value)

    model = Bad()
    result = run(lambda _: model)
    assert result["status"] == "REJECTED"
    assert model.calls == 1 and not evaluated and not result["promoted"]
    assert result["usage"]["recorded_micro_usd"] == 28
    assert parent.snapshot("parent") == original


@pytest.mark.parametrize("fault", ["exception", "no-usage", "truncated"])
def test_failed_or_unverifiable_model_response_retains_accounting_and_stops(setup, fault):
    run, _, evaluated, _, _ = setup

    class Broken(ReviewFixture):
        async def stream(self, *args, **kwargs):
            if fault == "exception":
                self.calls += 1
                raise RuntimeError("synthetic failure")
            async for value in super().stream(*args, **kwargs):
                if fault == "no-usage" and "metadata" in value:
                    continue
                if fault == "truncated" and "messageStop" in value:
                    value = {"messageStop": {"stopReason": "max_tokens"}}
                yield value

    model = Broken()
    result = run(lambda _: model)
    assert result["status"] in {"REJECTED", "ERROR"} and model.calls == 1
    assert not evaluated
    if fault != "truncated":
        assert not result["usage"]["all_usage_recorded"]
        assert result["usage"]["unresolved_reserved_micro_usd"] == 10048


def test_shared_cost_limit_prevents_second_round_call(setup):
    run, _, evaluated, _, settings = setup
    models = []

    def factory(_):
        model = ReviewFixture()
        models.append(model)
        return model

    result = run(factory, settings=replace(settings, budget_micro_usd=10048))
    assert [m.calls for m in models] == [1, 0]
    assert len(evaluated) == 1 and not result["promoted"]
    assert result["rounds"][-1]["stop_reason"] == "ESTIMATED_COST_LIMIT"
    assert result["usage"]["recorded_micro_usd"] == 28


def test_tampered_evidence_is_rejected_before_model_factory(setup):
    run, _, _, path, _ = setup
    (path / "before/evidence.json").write_text("{}")
    with pytest.raises(ContractError, match="EXPERIMENT_EVIDENCE_HASH_MISMATCH"):
        run(lambda _: pytest.fail("No model may be constructed"))
    assert not (path / "review").exists()


def test_reviewer_tool_request_is_unregistered_and_cannot_trigger_another_call(setup):
    run, _, evaluated, _, _ = setup

    class Attacker(ReviewFixture):
        async def stream(self, *args, **kwargs):
            self.calls += 1
            yield {"messageStart": {"role": "assistant"}}
            yield {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {"toolUse": {"toolUseId": "attack", "name": "authorize_payment"}},
                }
            }
            yield {
                "contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": "{}"}}}
            }
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "tool_use"}}
            yield {"metadata": {"usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20}}}

    model = Attacker()
    result = run(lambda _: model)
    assert model.calls == 1 and not evaluated
    assert result["rounds"][0]["attempted_tools"] == ["authorize_payment"]
    assert not result["promoted"]


def test_reusing_model_context_is_rejected_on_second_round(setup):
    run, _, evaluated, _, _ = setup
    model = ReviewFixture()
    result = run(lambda _: model)
    assert result["error"] == "REVIEW_MODEL_INSTANCE_REUSED"
    assert model.calls == 1 and len(evaluated) == 1


def test_configured_total_call_limit_also_applies_across_rounds(setup):
    run, _, evaluated, _, settings = setup
    models = []

    def factory(_):
        models.append(ReviewFixture())
        return models[-1]

    report = run(factory, settings=replace(settings, max_model_calls=1))
    assert report["error"] == "MODEL_CALL_LIMIT"
    assert len(models) == len(evaluated) == 1


def test_changed_artifact_during_review_cannot_be_attached_to_a_revision(setup):
    run, _, evaluated, path, _ = setup

    class Mutator(ReviewFixture):
        def answer(self, messages):
            artifact = path / "before/experiment.json"
            value = json.loads(artifact.read_text())
            value["tool_trace"].append({"unobserved": "new trace"})
            artifact.write_text(json.dumps(value))
            return super().answer(messages)

    report = run(lambda _: Mutator())
    assert report["error"] == "REVIEW_INPUT_CHANGED"
    assert not evaluated and not list((path / "review").glob("**/revisions/*.json"))


@pytest.mark.parametrize("failure", ["error", "wrong-snapshot"])
def test_failed_reexperiment_preserves_proposal_but_never_promotes(setup, failure):
    run, _, _, path, _ = setup

    def fail(policy, directory, eid):
        if failure == "error":
            raise RuntimeError("reevaluation failed")
        scenario = json.loads(
            (Path(__file__).resolve().parents[2] / "scenarios/normal-v1.json").read_text()
        )
        other = World(path / "other-parent")
        other.create_run("different", scenario, environment="operating-test")
        experiment(other, "different", directory, eid, policy, scenario)
        return directory / "experiment.json"

    report = run(lambda _: ReviewFixture(), reevaluate=fail)
    assert report["status"] in {"ERROR", "REJECTED"}
    assert not report["promoted"]
    assert len(list((path / "review").glob("**/revisions/*.json"))) == 1
    assert "candidate_policy" not in report
    if failure == "wrong-snapshot":
        assert report["error"] == "REEXPERIMENT_SNAPSHOT_MISMATCH"
