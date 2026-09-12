"""Replay actual split Medusa delivery reads without relaxing settled-state guards."""

import copy
import json
from pathlib import Path

import pytest
from test_gateway import prepared as prepared

from rehearsal.world.storage import ContractError

ROOT = Path(__file__).parents[2]
CAPTURE = ROOT / "evidence/cw05-delivery-transition/capture"


@pytest.fixture
def evidence():
    return json.loads((CAPTURE / "evidence.json").read_text())


@pytest.fixture
def transition(prepared):
    gateway, store, oid = prepared
    gateway.tick = lambda: 20
    snapshots = json.loads((CAPTURE / "capture.json").read_text())["samples"]
    split = next(s["order"] for s in snapshots if s["state"] == "split-delivered")
    final = next(s["order"] for s in snapshots if s["state"] == "consistent-delivered")
    with gateway.db.transaction() as db:
        db.execute("UPDATE purchases SET received_tick=NULL WHERE id=?", (oid,))
    with gateway.payments.transaction() as db:
        db.execute("UPDATE intents SET status='RESERVED',settled_tick=NULL,version=1")
        db.execute("UPDATE accounts SET spent=0,reserved=310")
    store.orders = [copy.deepcopy(split)]
    return gateway, store, oid, copy.deepcopy(final)


@pytest.mark.parametrize("surface", ["payment", "order", "snapshot"])
def test_captured_delivery_transition_is_unknown_without_consuming_or_releasing_reservation(
    transition, surface
):
    gateway, store, oid, final = transition
    if surface == "payment":
        result = gateway.get_payment(oid)
        assert result == {"status": "UNKNOWN", "reason": "EXTERNAL_DELIVERY_PENDING"}
    elif surface == "order":
        result = gateway.get_order(oid)
        assert result["status"] == "UNKNOWN" and result["reason"] == "EXTERNAL_DELIVERY_PENDING"
    else:
        result = gateway.observe_world()
        assert result["inventory"] == {"tent": 0, "light": 0}
    assert gateway._purchase(oid)["received_tick"] is None
    assert gateway.payments.balance(gateway.binding.run_id)["reserved"] == 310
    assert gateway.payments.balance(gateway.binding.run_id)["spent"] == 0
    store.orders = [final]
    for _ in range(3):
        assert gateway.get_payment(oid)["status"] == "SETTLED"
        assert gateway.get_order(oid)["status"] == "DELIVERED"
        snapshot = gateway.observe_world()
        assert snapshot["inventory"] == {"tent": 3, "light": 6}
        assert snapshot["balance"]["spent"] == 310 and snapshot["balance"]["reserved"] == 0
    assert all(method == "GET" for method, _, _ in store.calls)


def test_temporary_unknown_does_not_erase_previous_payment_settlement(transition):
    gateway, store, oid, _ = transition
    intent = gateway.payments.for_order(gateway.binding.run_id, oid)
    gateway.payments.settle(gateway.binding.run_id, intent["id"], gateway.tick())
    assert gateway.get_payment(oid)["status"] == "UNKNOWN"
    assert gateway.payments.balance(gateway.binding.run_id)["spent"] == 310
    assert gateway.payments.for_order(gateway.binding.run_id, oid)["status"] == "SETTLED"


@pytest.mark.parametrize(
    "damage",
    [
        "received",
        "canceled",
        "missing-time",
        "not-shipped",
        "excess",
        "negative",
        "amount",
        "customer",
    ],
)
def test_split_delivery_does_not_mask_confirmed_receipt_or_contract_contradictions(
    transition, damage
):
    gateway, store, oid, _ = transition
    o = store.orders[0]
    if damage == "received":
        with gateway.db.transaction() as db:
            db.execute("UPDATE purchases SET received_tick=1 WHERE id=?", (oid,))
    elif damage == "canceled":
        o["fulfillments"][0]["canceled_at"] = "2026-09-09T00:00:00Z"
    elif damage == "missing-time":
        o["fulfillments"][0]["delivered_at"] = None
    elif damage == "not-shipped":
        o["items"][0]["detail"]["shipped_quantity"] = 0
    elif damage == "excess":
        o["items"][0]["detail"]["delivered_quantity"] = 4
    elif damage == "negative":
        o["items"][0]["detail"]["delivered_quantity"] = -1
    elif damage == "amount":
        o["total"] += 1
    elif damage == "customer":
        o["customer_id"] = "other"
    with pytest.raises(ContractError):
        gateway.get_payment(oid)
    assert gateway.payments.balance(gateway.binding.run_id)["reserved"] == 310
    assert all(method == "GET" for method, _, _ in store.calls)
