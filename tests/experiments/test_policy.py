from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from rehearsal.experiments.policy import Policy, record_revision
from rehearsal.world.storage import ContractError


def test_policy_hash_is_content_based_and_unknown_fields_rejected():
    policy = Policy()
    assert Policy.parse(asdict(policy)).version == policy.version
    assert Policy(wait_ticks=10).version != policy.version
    with pytest.raises(ContractError, match="POLICY_FIELDS_MISMATCH"):
        Policy.parse(asdict(policy) | {"python_code": "unsafe"})
    with pytest.raises(ContractError, match="UNSAFE_UNKNOWN_PAYMENT_POLICY"):
        Policy(uncertain_payment_action="new_payment")


def test_revision_links_actual_artifact_hash_and_requires_new_experiment(tmp_path):
    before = Policy(refresh_quote_before_order=False)
    after = Policy(refresh_quote_before_order=True)
    experiment = tmp_path / "experiment.json"
    experiment.write_text(json.dumps({"experiment_id": "exp1", "policy_version": before.version}))
    review = {
        "review_id": "review1",
        "round": 1,
        "reviewer_kind": "scripted-fixture",
        "counterexamples": ["exp1"],
        "reason": "Stale quote rejection requires refresh.",
    }
    path = record_revision(tmp_path / "revisions", before, after, review, {"exp1": experiment})
    result = json.loads(path.read_text())
    assert result["diff"] == {"refresh_quote_before_order": {"before": False, "after": True}}
    assert result["status"] == "PROPOSED_REQUIRES_REEXPERIMENT"
    assert len(result["experiments"][0]["sha256"]) == 64
    with pytest.raises(FileExistsError):
        record_revision(tmp_path / "revisions", before, after, review, {"exp1": experiment})
    with pytest.raises(ContractError, match="UNKNOWN_EXPERIMENT"):
        record_revision(tmp_path / "other", before, after, review, {})


def test_review_cannot_cite_an_experiment_for_another_policy(tmp_path):
    before, after = Policy(refresh_quote_before_order=False), Policy()
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"experiment_id": "exp", "policy_version": after.version}))
    review = {
        "review_id": "r",
        "round": 1,
        "reviewer_kind": "human",
        "counterexamples": ["exp"],
        "reason": "wrong policy",
    }
    with pytest.raises(ContractError, match="EXPERIMENT_POLICY_MISMATCH"):
        record_revision(tmp_path / "revisions", before, after, review, {"exp": path})


def test_known_price_counterexample_reexperiment_uses_identical_forks(tmp_path):
    from pathlib import Path

    from rehearsal.experiments.rehearse import experiment
    from rehearsal.world import World

    scenario = json.loads(
        (Path(__file__).resolve().parents[2] / "scenarios/normal-v1.json").read_text()
    )
    parent = World(tmp_path / "parent")
    parent.create_run("parent", scenario, environment="operating-test")
    initial = parent.snapshot("parent")
    before = experiment(
        parent,
        "parent",
        tmp_path / "before",
        "before",
        Policy(refresh_quote_before_order=False),
        scenario,
    )
    after = experiment(parent, "parent", tmp_path / "after", "after", Policy(), scenario)
    assert before["snapshot_sha256"] == after["snapshot_sha256"]
    assert before["rejection"] == "STALE_QUOTE"
    assert before["verdict"]["status"] == "FAILED"
    assert before["verdict"]["spent"] == 0
    assert after["verdict"]["status"] == "COMPLETE"
    assert after["verdict"]["spent"] == 380
    assert parent.snapshot("parent") == initial
