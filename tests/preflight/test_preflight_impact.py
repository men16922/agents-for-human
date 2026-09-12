from __future__ import annotations

import copy
import json

import pytest

from rehearsal.preflight.contracts import (
    CONDITIONS,
    REPORT_TTL,
    catalog,
    expected_decision,
    plan_for,
    snapshot,
)
from rehearsal.preflight.report import build_report
from rehearsal.preflight.simulation import measure, measure_all
from rehearsal.serverless.domain import Rejected, digest


@pytest.fixture
def batch():
    frozen = snapshot(catalog(), 1000)
    plans = [plan_for(frozen, sid) for sid in "ABC"]
    artifacts = measure_all("preview-test", frozen, plans)
    return frozen, artifacts


def report_for(batch):
    frozen, artifacts = batch
    return build_report("preview-test", frozen, artifacts, proposed_supplier="A", generated_at=1010)


def test_preflight_reports_actual_fork_outcomes_without_mutating_source(batch):
    frozen, artifacts = batch
    assert frozen == snapshot(catalog(), 1000)
    assert len({a["run_id"] for a in artifacts}) == 12
    report = report_for(batch)
    assert report["status"] == "REPORT_READY"
    assert report["coverage"]["verified"] == report["coverage"]["planned"] == 12
    assert report["recommended_supplier"] == "B"
    a, b, c = report["plans"]
    assert (a["goals_met"], b["goals_met"], c["goals_met"]) == (2, 4, 0)
    assert [p["normal_spend"] for p in report["plans"]] == [149, 179, 129]
    assert [p["normal_arrival_minute"] for p in report["plans"]] == [1442, 2522, 7202]
    assert [p["eligible_for_handoff"] for p in report["plans"]] == [False, True, False]
    assert all(a["summary"]["external_orders_created"] == 0 for a in artifacts)
    # Changing one fork does not affect the frozen source or any other fork.
    artifacts[0]["state"]["suppliers"]["A"]["items"]["tent"]["stock"] = 999
    assert artifacts[1]["state"]["suppliers"]["A"]["items"]["tent"]["stock"] == 0
    assert frozen["source"]["suppliers"]["A"]["items"]["tent"]["stock"] == 10


def test_response_loss_commits_once_and_queries_the_same_order(batch):
    _, artifacts = batch
    for artifact in [a for a in artifacts if a["condition"] == "payment-response-lost"]:
        trace = artifact["trace"]
        auth = [t for t in trace if t["action"] == "authorize_payment"]
        query = [t for t in trace if t["action"] == "get_payment"]
        unknown = next(t for t in trace if t["action"] == "payment_knowledge")
        assert len(auth) == len(query) == 1
        assert auth[0]["args"]["order_id"] == query[0]["args"]["order_id"]
        assert unknown["reservation_retained"] > 0 and unknown["status"] == "UNKNOWN"
        assert artifact["summary"]["reserved"] == 0
        assert artifact["summary"]["duplicate_payments"] == 0


def test_unavailable_goal_never_buys_only_lanterns():
    frozen = snapshot(catalog("no-tents"), 1000)
    artifacts = measure_all("preview-empty", frozen, [plan_for(frozen, sid) for sid in "ABC"])
    report = build_report(
        "preview-empty", frozen, artifacts, proposed_supplier=None, generated_at=1010
    )
    assert report["decision"] == "DO_NOT_EXECUTE"
    assert report["recommended_supplier"] is None
    assert all(a["state"]["spent"] == 0 and not a["state"]["orders"] for a in artifacts)


@pytest.mark.parametrize(
    "damage",
    ["missing", "duplicate", "fake_summary", "fake_journal", "fake_recovery", "different_plan"],
)
def test_incomplete_or_forged_evidence_never_becomes_execution_basis(batch, damage):
    frozen, artifacts = copy.deepcopy(batch)
    if damage == "missing":
        artifacts.pop()
    elif damage == "duplicate":
        artifacts.append(copy.deepcopy(artifacts[0]))
    else:
        a = artifacts[3]
        if damage == "fake_summary":
            a["summary"]["spent"] = 0
        elif damage == "fake_journal":
            a["state"]["spent"] = 0
        elif damage == "fake_recovery":
            a["trace"] = [t for t in a["trace"] if t["action"] != "get_payment"]
        elif damage == "different_plan":
            a["plan"] = plan_for(frozen, "B")
        a["artifact_sha256"] = digest({k: v for k, v in a.items() if k != "artifact_sha256"})
    report = build_report(
        "preview-test", frozen, artifacts, proposed_supplier="A", generated_at=1010
    )
    assert not report["evidence_complete"] and report["status"] == "REVIEW_REQUIRED"
    assert not any(p["eligible_for_handoff"] for p in report["plans"])
    with pytest.raises(Rejected, match="REPORT_NOT_READY"):
        expected_decision(report, plan_for(frozen, "B")["plan_sha256"], frozen["source"], 1100)


def test_report_decision_binds_plan_snapshot_freshness_and_evidence(batch):
    frozen, _ = batch
    report = report_for(batch)
    plan = report["plans"][1]["plan"]
    handoff = expected_decision(report, plan["plan_sha256"], frozen["source"], 1100)
    assert handoff["report_sha256"] == report["report_sha256"]
    assert handoff["plan"] == plan and handoff["external_orders_created"] == 0
    with pytest.raises(Rejected, match="PLAN_NOT_ELIGIBLE"):
        expected_decision(report, report["plans"][0]["plan"]["plan_sha256"], frozen["source"], 1100)
    with pytest.raises(Rejected, match="REPORT_EXPIRED"):
        expected_decision(report, plan["plan_sha256"], frozen["source"], 1000 + REPORT_TTL)
    changed = copy.deepcopy(frozen["source"])
    changed["suppliers"]["B"]["items"]["tent"]["price"] += 1
    with pytest.raises(Rejected, match="SOURCE_CHANGED"):
        expected_decision(report, plan["plan_sha256"], changed, 1100)
    report["plans"][0]["eligible_for_handoff"] = True
    with pytest.raises(Rejected, match="REPORT_HASH_MISMATCH"):
        expected_decision(report, plan["plan_sha256"], frozen["source"], 1100)


@pytest.mark.parametrize(
    "field,value",
    [
        ("supplier", "unknown"),
        ("partial_purchase", True),
        ("items", {"light": 2}),
        ("payment_recovery", "retry_new_order"),
    ],
)
def test_plan_authority_cannot_be_rewritten(batch, field, value):
    frozen, _ = batch
    plan = plan_for(frozen, "A")
    plan[field] = value
    with pytest.raises(Rejected):
        measure("preview-test", frozen, plan, CONDITIONS[0])


def test_a_serialized_report_rechecks_identically(batch):
    report = report_for(batch)
    wire = json.loads(json.dumps(report))
    assert (
        expected_decision(
            wire, wire["plans"][1]["plan"]["plan_sha256"], wire["snapshot"]["source"], 1100
        )["decision"]
        == "ACCEPTED_FOR_EXECUTION_REVIEW"
    )
