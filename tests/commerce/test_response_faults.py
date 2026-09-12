import copy
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from test_observations import auth
from test_observations import http_setup as http_setup

from rehearsal.commerce.response_faults import ResponseFaults
from rehearsal.evaluation.response_conditions import timeout_observed, verify_response_event
from rehearsal.operating.client import OperatingClient
from rehearsal.world.storage import ContractError


def test_response_plan_is_consumed_once_across_instances_and_not_rearmed_after_restart(tmp_path):
    a = ResponseFaults(tmp_path / "faults.db")
    b = ResponseFaults(a.db.path)
    a.arm("one", "loss", 100, 1, 10)
    with pytest.raises(ContractError):
        a.arm("one", "other", 100, 1, 10)
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(lambda journal: journal.consume("one", "order", "SETTLED", 11, 2), (a, b))
        )
    assert sum(r is not None for r in results) == 1
    assert ResponseFaults(a.db.path).consume("one", "again", "SETTLED", 12, 3) is None
    with pytest.raises(ContractError):
        b.arm("one", "loss", 100, 3, 12)
    b.finish("one", "loss", 12, 3)
    with a.db.connect() as db:
        row = dict(db.execute("SELECT * FROM response_faults").fetchone())
    assert row["state"] == "FINISHED" and row["order_id"] == "order" and row["finished_tick"] == 3


def test_interrupt_is_terminal_and_does_not_repeat_consumption(tmp_path):
    journal = ResponseFaults(tmp_path / "faults.db")
    journal.arm("one", "loss", 100, 1, 10)
    journal.consume("one", "order", "UNKNOWN", 11, 2)
    journal.finish("one", "loss", 11.1, 2, interrupted=True)
    journal.finish("one", "loss", 13, 4)
    with journal.db.connect() as db:
        assert db.execute("SELECT state FROM response_faults").fetchone()[0] == "INTERRUPTED"
    assert journal.consume("one", "order", "SETTLED", 14, 5) is None


def test_scheduled_delay_endpoint_preserves_control_role_and_run_scope(http_setup, monkeypatch):
    monkeypatch.setattr("rehearsal.commerce.server.seller_health", lambda _: {"status": "ok"})
    client, observer = http_setup
    backend = observer.backends["one"]
    backend.tick = lambda: 1
    backend.authorize_payment = lambda *_: {"status": "SETTLED"}
    path = "/admin/runs/one/faults/scheduled-payment-response"
    body = {"event_id": "loss", "delay_ms": 1}
    assert client.post(path, json=body).status_code == 401
    for token in ("buyer", "observer", "other"):
        assert client.post(path, json=body, headers=auth(token)).status_code == 403
    for bad in (
        body | {"amount": 1},
        body | {"delay_ms": True},
        body | {"delay_ms": 5001},
        body | {"event_id": "../x"},
    ):
        assert client.post(path, json=bad, headers=auth("control")).status_code == 422
    assert client.post(path, json=body, headers=auth("control")).status_code == 200
    assert client.post(path, json=body, headers=auth("control")).status_code == 409
    assert (
        client.post(
            "/runs/one/payments",
            json={"order_id": "local-order", "idempotency_key": "one"},
            headers=auth("buyer"),
        ).json()["status"]
        == "SETTLED"
    )


@pytest.fixture
def response_case():
    event = {
        "id": "loss",
        "kind": "payment_response_delay",
        "at_tick": 3,
        "max_lateness_ticks": 2,
        "delay_ms": 2000,
    }
    binding = {
        "run_id": "one",
        "goal": {"items": {"tent": 3, "light": 6}, "deadline_tick": 120, "recipient": "venue"},
    }
    snapshot = {
        "run_id": "one",
        "goal": binding["goal"],
        "clock_mode": "operating-one-second-ticks",
        "tick": 3,
    }
    receipt = {
        "event": event,
        "state": "OBSERVED",
        "before": snapshot,
        "after": copy.deepcopy(snapshot),
        "mutation": {
            "method": "POST",
            "path": "/admin/runs/one/faults/scheduled-payment-response",
            "status": 200,
            "request": {"event_id": "loss", "delay_ms": 2000},
            "response": {"armed": True, "event_id": "loss"},
        },
    }
    row = {
        "run_id": "one",
        "event_id": "loss",
        "delay_ms": 2000,
        "armed_tick": 3,
        "armed_at": 1003,
        "state": "FINISHED",
        "order_id": "order",
        "response_status": "SETTLED",
        "consumed_at": 1005,
        "finished_at": 1007,
        "consumed_tick": 5,
        "finished_tick": 7,
    }
    return receipt, event, binding, [row]


def test_arm_plus_consumption_duration_and_client_timeout_are_distinct_evidence(response_case):
    event = verify_response_event(*response_case)
    assert event["end_tick"] == 7
    observed = {
        "run_id": "one",
        "order_id": "order",
        "method": "POST",
        "path": "payments",
        "started_at": 1004.8,
        "finished_at": 1005.5,
        "error_type": "ReadTimeout",
    }
    assert timeout_observed(event, "one", [observed])
    for values in (
        [],
        [observed, observed],
        [observed | {"error_type": "ConnectTimeout"}],
        [observed | {"finished_at": 1008}],
        [observed | {"order_id": "other"}],
    ):
        assert not timeout_observed(event, "one", values)


@pytest.mark.parametrize("state", ["ARMED", "CONSUMED", "INTERRUPTED"])
def test_uncompleted_response_delay_cannot_be_promoted(response_case, state):
    response_case[3][0]["state"] = state
    assert verify_response_event(*response_case) is None


@pytest.mark.parametrize(
    "damage",
    [
        "scope",
        "payload",
        "status",
        "tick",
        "delay",
        "run",
        "id",
        "missing",
        "duplicate",
        "duration",
        "reverse",
        "nan",
    ],
)
def test_response_fault_proof_tampering_is_rejected(response_case, damage):
    receipt, event, _, rows = response_case
    row = rows[0]
    if damage == "scope":
        receipt["mutation"]["path"] += "/other"
    elif damage == "payload":
        receipt["mutation"]["request"]["delay_ms"] = 1
    elif damage == "status":
        receipt["mutation"]["status"] = 201
    elif damage == "tick":
        receipt["after"]["tick"] = 6
    elif damage == "delay":
        row["delay_ms"] = 1
    elif damage == "run":
        row["run_id"] = "other"
    elif damage == "id":
        row["event_id"] = "other"
    elif damage == "missing":
        rows.clear()
    elif damage == "duplicate":
        rows.append(dict(row))
    elif damage == "duration":
        row["finished_at"] = 1006
    elif damage == "reverse":
        row["finished_tick"] = 2
    elif damage == "nan":
        row["consumed_at"] = float("nan")
    with pytest.raises(ValueError):
        verify_response_event(*response_case)


def test_payment_timeout_records_only_bounded_transport_metadata():
    client = OperatingClient("http://127.0.0.1:18001", "run", "private-token")
    client.http.close()

    def timeout(request):
        raise httpx.ReadTimeout("private diagnostic", request=request)

    client.http = httpx.Client(
        base_url="http://127.0.0.1:18001", transport=httpx.MockTransport(timeout)
    )
    try:
        assert client.authorize_payment("order", "key").status == "UNKNOWN"
        record = client.transport_events[0]
        assert record["error_type"] == "ReadTimeout" and record["order_id"] == "order"
        assert record["started_at"] <= record["finished_at"]
        assert "private" not in json.dumps(record) and "key" not in record
    finally:
        client.close()
