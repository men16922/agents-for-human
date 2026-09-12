from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rehearsal.evaluation.verifier import verify, verify_export
from rehearsal.world import World
from rehearsal.world.client import observe_payment
from rehearsal.world.storage import ContractError


@pytest.fixture
def setup(tmp_path):
    scenario = json.loads(
        (Path(__file__).resolve().parents[2] / "scenarios/normal-v1.json").read_text()
    )
    world = World(tmp_path)
    world.create_run("r", scenario)
    return world, scenario, tmp_path


def purchase(world, supplier="A"):
    quote = world.shop.quote("r", supplier, {"tent": 3, "light": 6})
    return world.shop.create_order("r", quote["id"], "supplies")


def finish(world):
    order = purchase(world)
    payment = world.authorize_payment("r", order["id"], "payment")
    world.settle_payment("r", payment["id"])
    world.advance("r", 10)
    return order, payment


def test_independent_complete_and_pending(setup):
    world, scenario, path = setup
    assert verify(path, "r", scenario).status == "INCOMPLETE"
    order = purchase(world)
    payment = world.authorize_payment("r", order["id"], "payment")
    result = verify(path, "r", scenario)
    assert (result.status, result.spent, result.reserved) == ("INCOMPLETE", 0, 310)
    world.settle_payment("r", payment["id"])
    assert verify(path, "r", scenario).status == "INCOMPLETE"
    world.advance("r", 10)
    result = verify(path, "r", scenario)
    assert (result.status, result.spent, result.reserved) == ("COMPLETE", 310, 0)
    assert result.received == {"light": 6, "tent": 3}


def test_f01_price_change_requotes_and_alternative_purchase(setup):
    world, scenario, path = setup
    quote = world.shop.quote("r", "A", {"tent": 3, "light": 6})
    world.shop.change_price("r", "A", "tent", 100)
    with pytest.raises(ContractError, match="STALE_QUOTE"):
        world.shop.create_order("r", quote["id"], "supplies")
    assert world.payments.balance("r")["spent"] == 0
    a = world.shop.quote("r", "A", {"tent": 3, "light": 6})
    b = world.shop.quote("r", "B", {"tent": 3, "light": 6})
    assert a["amount"] == 430 and b["amount"] == 380
    order = world.shop.create_order("r", b["id"], "supplies")
    payment = world.authorize_payment("r", order["id"], "payment")
    world.settle_payment("r", payment["id"])
    world.advance("r", 15)
    assert verify(path, "r", scenario).status == "COMPLETE"


def test_f02_settlement_response_loss_is_unknown_and_explicitly_reconciled(setup):
    world, scenario, path = setup
    order = purchase(world)

    def response_lost_after_commit():
        payment = world.authorize_payment("r", order["id"], "stable-intent")
        world.settle_payment("r", payment["id"])
        raise TimeoutError("synthetic response dropped after durable commit")

    observation = observe_payment(response_lost_after_commit)
    assert observation.status == "UNKNOWN" and observation.payment is None
    # No invented failure, new intent, compensating refund or duplicate purchase.
    result = verify(path, "r", scenario)
    assert result.status == "INCOMPLETE" and result.spent == 310 and result.reserved == 0
    observation = observe_payment(lambda: world.payments.for_order("r", order["id"]))
    assert observation.status == "SETTLED"
    assert (
        world.authorize_payment("r", order["id"], "stable-intent")["id"]
        == observation.payment["id"]
    )
    world.advance("r", 10)
    assert verify(path, "r", scenario).status == "COMPLETE"
    assert len([e for e in world.payments.events("r") if e["event_type"] == "payment.settled"]) == 1


def test_f06_impossible_stock_spends_nothing(setup):
    _, scenario, path = setup
    for supplier in scenario["suppliers"].values():
        supplier["items"]["tent"]["stock"] = 0
    world = World(path / "impossible")
    world.create_run("r", scenario)
    for supplier in scenario["suppliers"]:
        with pytest.raises(ContractError, match="INSUFFICIENT_STOCK"):
            purchase(world, supplier)
    assert world.payments.balance("r")["spent"] == 0
    world.advance("r", 60)
    result = verify(path / "impossible", "r", scenario)
    assert result.status == "FAILED" and result.reasons == ["DEADLINE_MISSED"]
    assert result.spent == result.reserved == 0


def test_late_delivery_cannot_satisfy_goal(setup):
    world, scenario, path = setup
    order = purchase(world)
    world.advance("r", 55)
    payment = world.authorize_payment("r", order["id"], "pay")
    world.settle_payment("r", payment["id"])
    world.advance("r", 65)
    assert world.shop.inventory("r") == {"tent": 3, "light": 6}
    result = verify(path, "r", scenario)
    assert result.status == "FAILED" and result.reasons == ["DEADLINE_MISSED"]


@pytest.mark.parametrize(
    "database,sql,reason",
    [
        ("payments", "UPDATE accounts SET spent=300", "BALANCE_MISMATCH"),
        ("shop", "UPDATE inventory SET quantity=7 WHERE item='light'", "INVENTORY_MISMATCH"),
        ("shop", "UPDATE orders SET recipient='attacker'", "RECIPIENT_VIOLATION"),
        (
            "shop",
            "UPDATE offers SET stock=stock+1 WHERE supplier='A'",
            "STOCK_CONSERVATION_VIOLATION",
        ),
        (
            "shop",
            "DELETE FROM events WHERE event_type='order.delivered'",
            "DELIVERY_EVENT_MISMATCH",
        ),
        (
            "payments",
            "DELETE FROM events WHERE event_type='payment.settled'",
            "PAYMENT_EVENT_MISMATCH",
        ),
        ("shop", "UPDATE orders SET amount=1", "ORDER_AMOUNT_MISMATCH"),
    ],
)
def test_verifier_rejects_corrupted_evidence(setup, database, sql, reason):
    world, scenario, path = setup
    finish(world)
    with sqlite3.connect(path / f"{database}.sqlite3") as db:
        db.execute(sql)
    result = verify(path, "r", scenario)
    assert result.status == "FAILED" and reason in result.reasons


def test_missing_evidence_never_looks_complete(setup):
    _, scenario, path = setup
    assert verify(path / "missing", "r", scenario).status == "UNKNOWN"
    assert not (path / "missing").exists()
    assert verify(path, "nonexistent-run", scenario).status == "UNKNOWN"


def test_export_recomputed_without_trusting_saved_verdict(setup):
    world, scenario, path = setup
    finish(world)
    artifact = path / "export.json"
    result = verify(path, "r", scenario, export_to=artifact)
    assert verify_export(artifact) == result
    data = json.loads(artifact.read_text())
    data["tables"]["inventory"][0]["quantity"] += 1
    data["verdict"]["status"] = "COMPLETE"
    artifact.write_text(json.dumps(data))
    assert verify_export(artifact).status == "FAILED"


def test_verifier_detects_consistently_wrong_quote_and_payment(setup):
    world, scenario, path = setup
    finish(world)
    artifact = path / "export.json"
    verify(path, "r", scenario, export_to=artifact)
    data = json.loads(artifact.read_text())
    # A server could compute the same wrong price across every derived record.
    # Independent fixture prices must still reject that internally consistent trace.
    quote = json.loads(data["tables"]["quotes"][0]["data"])
    quote["unit_prices"]["tent"] = 1
    quote["amount"] = 133
    data["tables"]["quotes"][0]["data"] = json.dumps(quote)
    data["tables"]["orders"][0]["amount"] = 133
    data["tables"]["intents"][0]["amount"] = 133
    data["tables"]["accounts"][0]["spent"] = 133
    for event in data["tables"]["payment_events"]:
        if event["event_type"].startswith("payment."):
            payload = json.loads(event["payload"])
            payload["amount"] = 133
            event["payload"] = json.dumps(payload)
    artifact.write_text(json.dumps(data))
    result = verify_export(artifact)
    assert result.status == "FAILED" and "QUOTE_PRICE_MISMATCH" in result.reasons


@pytest.mark.parametrize(
    "tamper,reason",
    [
        ("scope", "RUN_SCOPE_MISMATCH"),
        ("duplicate", "DUPLICATE_EVIDENCE_ROW"),
    ],
)
def test_export_enforces_scope_and_unique_evidence_rows(setup, tamper, reason):
    world, scenario, path = setup
    finish(world)
    artifact = path / "export.json"
    verify(path, "r", scenario, export_to=artifact)
    data = json.loads(artifact.read_text())
    if tamper == "scope":
        data["tables"]["intents"][0]["run_id"] = "other"
    else:
        data["tables"]["inventory"].append(data["tables"]["inventory"][0])
    artifact.write_text(json.dumps(data))
    result = verify_export(artifact)
    assert result.status == "FAILED" and reason in result.reasons
