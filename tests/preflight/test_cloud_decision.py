"""DynamoDB transaction behavior with a controlled race, no cloud calls."""

import copy
import json

import pytest
from botocore.exceptions import ClientError

from rehearsal.preflight.cloud import decision
from rehearsal.preflight.contracts import catalog, plan_for, snapshot
from rehearsal.preflight.report import build_report
from rehearsal.preflight.simulation import measure_all
from rehearsal.serverless.control import Control
from rehearsal.serverless.domain import Rejected, canonical, digest


class Database:
    def __init__(self):
        self.source = catalog()
        self.saved = None
        self.race = False
        self.writes = 0

    def get_item(self, **kw):
        if kw["Key"]["pk"]["S"].startswith("SOURCE#"):
            return {
                "Item": {
                    "body": {"S": canonical(self.source)},
                    "digest": {"S": digest(self.source)},
                    "revision": {"N": str(self.source["revision"])},
                }
            }
        return {"Item": self.saved} if self.saved else {}

    def transact_write_items(self, **kw):
        check, finalized, put = kw["TransactItems"]
        assert finalized["ConditionCheck"]["ConditionExpression"] == "finalized = :yes"
        if self.race:
            self.source["revision"] += 1
        values = check["ConditionCheck"]["ExpressionAttributeValues"]
        if values[":hash"]["S"] != digest(self.source) or self.saved:
            raise ClientError({"Error": {"Code": "TransactionCanceledException"}}, "Transact")
        self.saved = put["Put"]["Item"]
        self.writes += 1


@pytest.fixture
def setup():
    db = Database()
    frozen = snapshot(db.source, 1000)
    report = build_report(
        "preview-test",
        frozen,
        measure_all("preview-test", frozen, [plan_for(frozen, s) for s in "ABC"]),
        proposed_supplier="A",
        generated_at=1100,
    )
    body = {
        "action": "accept",
        "report_sha256": report["report_sha256"],
        "plan_sha256": report["plans"][1]["plan"]["plan_sha256"],
    }
    return db, Control(db, "control"), report, body


def test_atomic_accept_retry_and_conflicting_decision(setup):
    db, control, report, body = setup
    first = decision(control, report, "family-camping", body, 1200)
    # Historical replay does not refresh expiry or validation time.
    again = decision(control, report, "family-camping", body, 9000)
    assert first == again and first["revalidated_at"] == 1200
    assert first["external_orders_created"] == 0 and db.writes == 1
    with pytest.raises(Rejected, match="DECISION_ALREADY_RECORDED"):
        decision(control, report, "family-camping", body | {"action": "decline"}, 1201)


def test_source_change_between_read_and_commit_rejects_handoff(setup):
    db, control, report, body = setup
    db.race = True
    with pytest.raises(Rejected, match="SOURCE_OR_DECISION_CHANGED"):
        decision(control, report, "family-camping", body, 1200)
    assert db.saved is None and db.writes == 0


@pytest.mark.parametrize("change", ["expiry", "source", "plan", "report"])
def test_invalid_accept_has_no_durable_side_effect(setup, change):
    db, control, report, body = setup
    now = 1200
    if change == "expiry":
        now = 1900
    elif change == "source":
        db.source["suppliers"]["B"]["items"]["tent"]["price"] += 1
    elif change == "plan":
        body["plan_sha256"] = report["plans"][0]["plan"]["plan_sha256"]
    else:
        body["report_sha256"] = "forged"
    with pytest.raises(Rejected):
        decision(control, report, "family-camping", body, now)
    assert db.saved is None and db.writes == 0


def test_declining_an_expired_report_never_issues_execution_brief(setup):
    db, control, report, body = setup
    result = decision(control, report, "family-camping", body | {"action": "decline"}, 9999)
    assert result["decision"] == "DECLINED"
    assert "plan" not in result and db.writes == 1
    assert json.loads(db.saved["body"]["S"]) == result
    assert report == copy.deepcopy(report)
