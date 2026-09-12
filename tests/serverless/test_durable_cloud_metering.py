"""Paid-call admission is durable before execution; storage errors fail closed."""

import sqlite3

import pytest

from rehearsal.agents.metering import RateCard
from rehearsal.serverless.metering import DurableLedger


class Storage:
    def __init__(self):
        self.objects = []
        self.fail = False

    def put_object(self, **kwargs):
        if self.fail:
            raise TimeoutError("Injected S3 response failure")
        self.objects.append(kwargs["Body"])


class Control:
    def __init__(self):
        self.reports = []

    def publish(self, run_id, name, body):
        self.reports.append(body["usage"])


def ledger(tmp_path):
    meter = DurableLedger(
        tmp_path / "usage.sqlite3",
        "cloud-test",
        "scripted",
        RateCard("1", "2", "0.1", "1.25", "offline test rates"),
        1000,
        100,
        10,
        scope="offline-scripted-model",
    )
    s3, control = Storage(), Control()
    meter.bind(control, s3, "test-bucket", "cloud-test")
    return meter, s3, control


def test_reservation_and_provider_usage_are_exported_before_return(tmp_path):
    meter, s3, control = ledger(tmp_path)
    call, reason = meter.reserve(50, role="buyer_evaluation", execution_id="cloud")
    assert reason is None and call is not None
    assert control.reports[-1]["unresolved_reserved_micro_usd"] == 145
    exported = tmp_path / "exported.sqlite3"
    exported.write_bytes(s3.objects[-1])
    with sqlite3.connect(exported) as db:
        assert db.execute("pragma integrity_check").fetchone() == ("ok",)
    meter.finish(call, {"inputTokens": 12, "outputTokens": 8})
    assert control.reports[-1]["recorded_micro_usd"] == 28
    assert control.reports[-1]["unresolved_reserved_micro_usd"] == 0
    assert len(s3.objects) == 3


def test_failed_durable_admission_cannot_allow_a_paid_call(tmp_path):
    meter, s3, control = ledger(tmp_path)
    s3.fail = True
    with pytest.raises(TimeoutError):
        meter.reserve(50)
    assert meter.report()["unresolved_reserved_micro_usd"] == 145
    s3.fail = False
    assert meter.reserve(50) == (None, "PRIOR_USAGE_UNRESOLVED")
    assert control.reports[-1]["unresolved_reserved_micro_usd"] == 145
