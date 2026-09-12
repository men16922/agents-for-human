from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest

from rehearsal.world import OperatingClock, World
from rehearsal.world.storage import ContractError

FIXTURE = Path(__file__).resolve().parents[2] / "scenarios/normal-v1.json"


@pytest.fixture
def fixture():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def world(tmp_path, fixture):
    result = World(tmp_path)
    result.create_run("r1", fixture)
    return result


def order(world, supplier="A", key="purchase-1", items=None, run="r1"):
    quote = world.shop.quote(run, supplier, items or {"tent": 3, "light": 6})
    return world.shop.create_order(run, quote["id"], key)


def test_normal_purchase_hand_calculated(world):
    purchase = order(world)
    assert purchase["amount"] == 310
    assert purchase["recipient"] == "event-venue"
    payment = world.authorize_payment("r1", purchase["id"], "intent-1")
    assert payment["amount"] == 310 and payment["recipient"] == "A"
    assert world.snapshot("r1")["balance"]["reserved"] == 310
    assert world.snapshot("r1")["balance"]["spent"] == 0
    assert world.shop.order("r1", purchase["id"])["status"] == "PAYMENT_PENDING"
    world.advance("r1", 3)
    world.settle_payment("r1", payment["id"])
    assert world.shop.order("r1", purchase["id"])["status"] == "FULFILLING"
    assert world.snapshot("r1")["inventory"] == {}
    world.advance("r1", 12)
    assert world.snapshot("r1")["inventory"] == {}
    world.advance("r1", 13)
    assert world.snapshot("r1")["inventory"] == {"tent": 3, "light": 6}
    balance = world.snapshot("r1")["balance"]
    assert (balance["spent"], balance["reserved"], balance["available"]) == (310, 0, 190)
    offers = {v["item"]: v for v in world.shop.offers("r1") if v["supplier"] == "A"}
    assert (offers["tent"]["stock"], offers["light"]["stock"]) == (7, 4)
    assert all(v["reserved"] == 0 for v in offers.values())
    assert world.shop.order("r1", purchase["id"])["delivered_tick"] == 13


def test_retries_conflicts_and_single_order_intent(world):
    quote = world.shop.quote("r1", "A", {"tent": 1})
    purchase = world.shop.create_order("r1", quote["id"], "same")
    assert world.shop.create_order("r1", quote["id"], "same")["id"] == purchase["id"]
    newer = world.shop.quote("r1", "A", {"tent": 1})
    with pytest.raises(ContractError, match="IDEMPOTENCY_CONFLICT"):
        world.shop.create_order("r1", newer["id"], "same")
    with pytest.raises(ContractError, match="QUOTE_ALREADY_ORDERED"):
        world.shop.create_order("r1", quote["id"], "new-key")
    payment = world.authorize_payment("r1", purchase["id"], "pay")
    for _ in range(3):
        assert world.authorize_payment("r1", purchase["id"], "pay")["id"] == payment["id"]
        world.settle_payment("r1", payment["id"])
        world.synchronize("r1")
    with pytest.raises(ContractError, match="ORDER_ALREADY_HAS_INTENT"):
        world.authorize_payment("r1", purchase["id"], "new-pay")
    second = world.shop.create_order("r1", newer["id"], "second")
    with pytest.raises(ContractError, match="IDEMPOTENCY_CONFLICT"):
        world.authorize_payment("r1", second["id"], "pay")
    world.advance("r1", 20)
    world.advance("r1", 20)
    assert world.shop.inventory("r1") == {"tent": 1}
    assert world.payments.balance("r1")["spent"] == 70
    settled = [e for e in world.payments.events("r1") if e["event_type"] == "payment.settled"]
    delivered = [e for e in world.shop.events("r1") if e["event_type"] == "order.delivered"]
    assert len(settled) == len(delivered) == 1


@pytest.mark.parametrize("budget,success", [(310, True), (309, False)])
def test_budget_exact_boundary(tmp_path, fixture, budget, success):
    fixture["goal"]["budget"] = budget
    world = World(tmp_path)
    world.create_run("r1", fixture)
    purchase = order(world)
    if success:
        world.authorize_payment("r1", purchase["id"], "pay")
        assert world.payments.balance("r1")["available"] == 0
    else:
        before = world.payments.events("r1")
        with pytest.raises(ContractError, match="BUDGET_EXCEEDED"):
            world.authorize_payment("r1", purchase["id"], "pay")
        assert world.payments.balance("r1")["reserved"] == 0
        assert world.payments.events("r1") == before


def test_concurrent_budget_reservations_are_atomic(world):
    purchases = [order(world, "A", "a"), order(world, "B", "b")]
    barrier = Barrier(2)

    def reserve(index):
        barrier.wait(timeout=3)
        try:
            return world.authorize_payment("r1", purchases[index]["id"], str(index))["amount"]
        except ContractError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    assert results.count("BUDGET_EXCEEDED") == 1
    amount = next(r for r in results if isinstance(r, int))
    assert amount in (310, 380)
    assert world.payments.balance("r1")["reserved"] == amount


def test_concurrent_stock_reservations_are_atomic(world):
    quotes = [world.shop.quote("r1", "A", {"light": 6}) for _ in range(2)]
    barrier = Barrier(2)

    def accept(index):
        barrier.wait(timeout=3)
        try:
            return world.shop.create_order("r1", quotes[index]["id"], str(index))["status"]
        except ContractError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, range(2)))
    assert sorted(results) == ["ACCEPTED", "INSUFFICIENT_STOCK"]
    lights = next(
        v for v in world.shop.offers("r1") if v["supplier"] == "A" and v["item"] == "light"
    )
    assert lights["reserved"] == 6 and lights["stock"] == 10


def test_stock_failure_rolls_back_earlier_items(world):
    stale = world.shop.quote("r1", "A", {"tent": 3, "light": 6})
    order(world, items={"tent": 8})
    before = world.shop.offers("r1")
    with pytest.raises(ContractError, match="INSUFFICIENT_STOCK"):
        world.shop.create_order("r1", stale["id"], "conflicting")
    assert world.shop.offers("r1") == before


def test_persisted_outbox_recovers_interrupted_projection(world, tmp_path):
    purchase = order(world)
    with patch.object(world, "synchronize", side_effect=RuntimeError("process stopped")):
        with pytest.raises(RuntimeError):
            world.authorize_payment("r1", purchase["id"], "intent")
    assert world.payments.balance("r1")["reserved"] == 310
    assert world.shop.order("r1", purchase["id"])["status"] == "ACCEPTED"
    resumed = World(tmp_path)
    payment = resumed.authorize_payment("r1", purchase["id"], "intent")
    assert resumed.shop.order("r1", purchase["id"])["status"] == "PAYMENT_PENDING"
    with patch.object(resumed, "synchronize", side_effect=RuntimeError("process stopped")):
        with pytest.raises(RuntimeError):
            resumed.settle_payment("r1", payment["id"])
    restarted = World(tmp_path)
    restarted.synchronize("r1")
    restarted.advance("r1", 10)
    assert restarted.shop.inventory("r1") == {"tent": 3, "light": 6}
    assert restarted.payments.balance("r1")["spent"] == 310


def test_reversed_payment_events_do_not_regress_or_duplicate(world):
    purchase = order(world)
    payment = world.payments.reserve("r1", purchase["id"], "pay", "A", 310, 0)
    world.payments.settle("r1", payment["id"], 0)
    for event in reversed(world.payments.events("r1")):
        world.shop.apply_payment("r1", event)
    world.synchronize("r1")
    assert world.shop.order("r1", purchase["id"])["status"] == "FULFILLING"
    world.advance("r1", 10)
    assert world.shop.inventory("r1") == {"tent": 3, "light": 6}


def test_run_isolation_and_reinitialization(world, fixture):
    world.create_run("r1", fixture)
    world.create_run("r2", fixture)
    purchase = order(world)
    payment = world.authorize_payment("r1", purchase["id"], "pay")
    with pytest.raises(ContractError, match="NOT_FOUND"):
        world.shop.order("r2", purchase["id"])
    with pytest.raises(ContractError, match="NOT_FOUND"):
        world.payments.get("r2", payment["id"])
    with pytest.raises(ContractError, match="EVENT_SCOPE_MISMATCH"):
        world.shop.apply_payment("r2", world.payments.events("r1")[-1])
    assert world.payments.balance("r2")["reserved"] == 0
    assert world.shop.inventory("r2") == {}
    changed = deepcopy(fixture)
    changed["goal"]["budget"] = 100
    with pytest.raises(ContractError, match="RUN_CONFLICT"):
        world.create_run("r1", changed)


def test_quote_expiry_and_monotonic_clock(world):
    quote = world.shop.quote("r1", "A", {"tent": 1}, ttl=5)
    world.advance("r1", 5)
    with pytest.raises(ContractError, match="QUOTE_EXPIRED"):
        world.shop.create_order("r1", quote["id"], "late")
    with pytest.raises(ContractError, match="CLOCK_REVERSED"):
        world.advance("r1", 4)
    assert world.shop.run("r1")["tick"] == 5


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5])
def test_quantities_are_positive_integers(world, quantity):
    with pytest.raises(ContractError, match="INVALID_INTEGER"):
        world.shop.quote("r1", "A", {"tent": quantity})


def test_operating_clock_does_not_depend_on_world_steps():
    with patch("rehearsal.world.time.monotonic", side_effect=[100.0, 100.9, 103.4]):
        clock = OperatingClock(initial_tick=7)
        assert clock.now() == 7
        assert clock.now() == 10
