"""Controlled stock changes using retained Medusa payloads and an offline HTTP transport.

Failure timing is synthetic. These tests do not demonstrate a live inventory race.
"""

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from rehearsal.commerce.gateway import Binding, MedusaGateway, StoreAPI
from rehearsal.world.storage import ContractError

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def stock_backend(tmp_path):
    evidence = json.loads((ROOT / "evidence/cw05-medusa/evidence.json").read_text())
    contract = json.loads((ROOT / "evidence/cw00/2026-09-07-medusa-contract.json").read_text())
    rejection = next(
        r
        for r in contract["requests"]
        if r["status"] == 400 and r["response"].get("code") == "insufficient_inventory"
    )
    binding = Binding(**evidence["binding"])
    template = copy.deepcopy(evidence["external_orders"][0])
    state = {
        "stock": {"tent": 10, "light": 10},
        "carts": {},
        "orders": [],
        "calls": [],
        "fail_at": None,
        "failure": "http",
        "read_status": None,
    }
    store = StoreAPI("offline-buyer", "offline-key")
    store.http.close()
    gateway = MedusaGateway(tmp_path, binding, store)
    variants = binding.suppliers["A"]["variants"]

    def handle(request):
        method, path = request.method, request.url.path
        body = json.loads(request.content) if request.content else None
        state["calls"].append((method, path, body))
        if method == "GET" and path == "/store/customers/me":
            return httpx.Response(200, json={"customer": {"id": binding.customer_id}})
        if method == "GET" and path == "/store/orders":
            if state["read_status"]:
                return httpx.Response(state["read_status"], json={"message": "private diagnostic"})
            return httpx.Response(
                200, json={"orders": state["orders"], "count": len(state["orders"])}
            )
        if method == "GET" and path.startswith("/store/orders/"):
            order = next(o for o in state["orders"] if o["id"] == path.split("/")[3])
            return httpx.Response(200, json={"order": order})
        if method == "POST" and path == "/store/carts":
            cart = copy.deepcopy(template)
            cart.update(id=f"cart_stock_{len(state['carts'])}", metadata=body["metadata"])
            state["carts"][cart["id"]] = cart
            return httpx.Response(200, json={"cart": cart})
        if path.startswith("/store/carts/") and (
            method == "GET" or path.endswith("/shipping-methods") or "/line-items/" in path
        ):
            cart = state["carts"][path.split("/")[3]]
            if method == "POST" and "/line-items/" in path:
                # Medusa 2.20.1 confirms only the updated variant's inventory.
                line = next(i for i in cart["items"] if i["id"] == path.split("/")[-1])
                name = next(n for n, vid in variants.items() if vid == line["variant_id"])
                assert body["quantity"] == line["quantity"]
                if line["quantity"] > state["stock"][name]:
                    return httpx.Response(rejection["status"], json=rejection["response"])
            return httpx.Response(200, json={"cart": cart})
        stage = (
            "collection"
            if path == "/store/payment-collections"
            else "session"
            if path.endswith("/payment-sessions")
            else "complete"
            if path.endswith("/complete")
            else None
        )
        if method == "POST" and stage:
            # The local budget must already be reserved before any external payment request.
            assert gateway.payments.balance(binding.run_id)["reserved"] == 310
            if state["fail_at"] == stage:
                state["stock"]["tent"] = 0
                if state["failure"] == "timeout":
                    raise httpx.ReadTimeout("synthetic response loss", request=request)
                if state["failure"] == "cart-result":
                    return httpx.Response(
                        200, json={"type": "cart", "error": rejection["response"]}
                    )
                return httpx.Response(rejection["status"], json=rejection["response"])
            if stage == "collection":
                return httpx.Response(200, json={"payment_collection": {"id": "paycol_stock"}})
            if stage == "session":
                return httpx.Response(200, json={"payment_collection": {"id": "paycol_stock"}})
            cart = state["carts"][path.split("/")[3]]
            order = copy.deepcopy(cart)
            order["id"] = f"order_stock_{len(state['orders'])}"
            state["orders"].append(order)
            return httpx.Response(200, json={"type": "order", "order": order})
        raise AssertionError(f"Unexpected replay route: {method} {path}")

    store.http = httpx.Client(
        base_url="http://127.0.0.1:19000", transport=httpx.MockTransport(handle), trust_env=False
    )
    try:
        yield gateway, store, state
    finally:
        store.close()


def buy_intent(gateway):
    quote = gateway.get_quotes("A", {"tent": 3, "light": 6})
    assert quote["amount"] == 310
    return gateway.create_order(quote["id"], "stock-buy")


@pytest.mark.parametrize("point", ["before-order", "before-payment"])
@pytest.mark.parametrize("item", ["tent", "light"])
def test_stock_rejection_before_submission_creates_no_payment_and_can_retry(
    stock_backend, point, item
):
    gateway, store, state = stock_backend
    quote = gateway.get_quotes("A", {"tent": 3, "light": 6})
    order = None
    if point == "before-payment":
        order = gateway.create_order(quote["id"], "stock-buy")
    state["stock"][item] = 0
    with pytest.raises(ContractError, match="^MEDUSA_HTTP_400$"):
        if order:
            gateway.authorize_payment(order["id"], "stock-pay")
        else:
            gateway.create_order(quote["id"], "stock-buy")
    balance = gateway.payments.balance(gateway.binding.run_id)
    assert (balance["spent"], balance["reserved"], balance["available"]) == (0, 0, 500)
    with gateway.payments.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 0
    with gateway.db.connect() as db:
        rows = list(db.execute("SELECT stage FROM purchases"))
        assert [r[0] for r in rows] == (["ACCEPTED"] if order else [])
    assert not any("payment-collections" in path for _, path, _ in state["calls"])
    state["stock"][item] = 10
    reopened = MedusaGateway(gateway.directory, gateway.binding, store)
    order = reopened.create_order(quote["id"], "stock-buy")
    assert reopened.authorize_payment(order["id"], "stock-pay")["status"] == "SETTLED"
    assert reopened.payments.balance(gateway.binding.run_id)["spent"] == 310


@pytest.mark.parametrize(
    "stage,failure",
    [
        ("collection", "http"),
        ("session", "http"),
        ("complete", "http"),
        ("complete", "timeout"),
        ("complete", "cart-result"),
    ],
)
def test_failure_after_submission_stays_unknown_reserved_and_never_resubmits(
    stock_backend, stage, failure
):
    gateway, store, state = stock_backend
    order = buy_intent(gateway)
    state.update(fail_at=stage, failure=failure)
    result = gateway.authorize_payment(order["id"], "stock-pay")
    assert result["status"] == "UNKNOWN"
    if failure == "http":
        assert result["reason"] == "MEDUSA_HTTP_400"
        assert "Some variant" not in json.dumps(result)
    assert gateway._purchase(order["id"])["stage"] == "SUBMITTED"
    balance = gateway.payments.balance(gateway.binding.run_id)
    assert (balance["spent"], balance["reserved"], balance["available"]) == (0, 310, 190)
    assert not state["orders"]
    state.update(fail_at=None)
    state["stock"]["tent"] = 10
    reopened = MedusaGateway(gateway.directory, gateway.binding, store)
    state["calls"].clear()
    assert reopened.authorize_payment(order["id"], "stock-pay")["status"] == "UNKNOWN"
    assert reopened.get_payment(order["id"])["status"] == "UNKNOWN"
    assert reopened.get_order(order["id"])["status"] == "UNKNOWN"
    with pytest.raises(ContractError, match="ORDER_ALREADY_HAS_INTENT"):
        reopened.authorize_payment(order["id"], "replacement")
    assert all(method == "GET" for method, _, _ in state["calls"])
    assert reopened.payments.balance(gateway.binding.run_id)["reserved"] == 310
    assert reopened.observe_world()["inventory"] == {"tent": 0, "light": 0}
    # A replacement order cannot reuse funds locked by the uncertain first submission.
    quote = reopened.get_quotes("A", {"tent": 3, "light": 6})
    replacement = reopened.create_order(quote["id"], "replacement-buy")
    state["calls"].clear()
    with pytest.raises(ContractError, match="BUDGET_EXCEEDED"):
        reopened.authorize_payment(replacement["id"], "replacement-pay")
    assert not any(
        "payment-collections" in path or path.endswith("/complete") for _, path, _ in state["calls"]
    )
    assert reopened.payments.balance(gateway.binding.run_id)["reserved"] == 310


def test_unknown_checkout_later_reconciles_existing_order_without_resubmission(stock_backend):
    gateway, store, state = stock_backend
    order = buy_intent(gateway)
    state.update(fail_at="complete", failure="http")
    assert gateway.authorize_payment(order["id"], "stock-pay")["status"] == "UNKNOWN"
    # A later independent observation is inserted by the fixture, never by the buyer.
    external = copy.deepcopy(next(iter(state["carts"].values())))
    external["id"] = "order_later_observed"
    state["orders"].append(external)
    reopened = MedusaGateway(gateway.directory, gateway.binding, store)
    state["calls"].clear()
    for _ in range(2):
        assert reopened.get_payment(order["id"])["status"] == "SETTLED"
        assert reopened.authorize_payment(order["id"], "stock-pay")["status"] == "SETTLED"
        assert reopened.observe_world()["inventory"] == {"tent": 3, "light": 6}
    assert all(method == "GET" for method, _, _ in state["calls"])
    balance = reopened.payments.balance(gateway.binding.run_id)
    assert (balance["spent"], balance["reserved"]) == (310, 0)
    with reopened.payments.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 1
        assert (
            db.execute("SELECT COUNT(*) FROM events WHERE event_type='payment.settled'").fetchone()[
                0
            ]
            == 1
        )


def test_http_failure_during_reconciliation_keeps_reservation_and_hides_diagnostics(stock_backend):
    gateway, _, state = stock_backend
    order = buy_intent(gateway)
    state.update(fail_at="complete", failure="cart-result")
    assert gateway.authorize_payment(order["id"], "stock-pay")["status"] == "UNKNOWN"
    state["read_status"] = 503
    state["calls"].clear()
    for result in (
        gateway.get_payment(order["id"]),
        gateway.authorize_payment(order["id"], "stock-pay"),
    ):
        assert result == {"status": "UNKNOWN", "reason": "MEDUSA_HTTP_503"}
    assert all(method == "GET" for method, _, _ in state["calls"])
    assert gateway.payments.balance(gateway.binding.run_id)["reserved"] == 310


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("customer_id", "other-customer", "CUSTOMER_SCOPE_MISMATCH"),
        ("total", 1, "UNSUPPORTED_EXTERNAL_TOTAL"),
    ],
)
def test_local_evidence_contradictions_are_not_masked_as_http_uncertainty(
    stock_backend, field, value, reason
):
    gateway, _, state = stock_backend
    order = buy_intent(gateway)
    state.update(fail_at="complete", failure="http")
    assert gateway.authorize_payment(order["id"], "stock-pay")["status"] == "UNKNOWN"
    external = copy.deepcopy(next(iter(state["carts"].values())))
    external.update(id="order_wrong", **{field: value})
    state["orders"].append(external)
    with pytest.raises(ContractError, match=reason):
        gateway.get_payment(order["id"])
    assert gateway.payments.balance(gateway.binding.run_id)["reserved"] == 310


def test_separate_gateway_instances_serialize_same_key_without_duplicate_checkout(stock_backend):
    gateway, store, state = stock_backend
    order = buy_intent(gateway)
    copies = [MedusaGateway(gateway.directory, gateway.binding, store) for _ in range(4)]
    barrier = threading.Barrier(4)

    def pay(backend):
        barrier.wait(timeout=5)
        return backend.authorize_payment(order["id"], "same-concurrent-key")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(pay, copies))
    assert all(value["status"] == "SETTLED" for value in results)
    assert len(state["orders"]) == 1
    assert sum(path.endswith("/complete") for _, path, _ in state["calls"]) == 1
    with gateway.payments.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 1
        assert (
            db.execute("SELECT COUNT(*) FROM events WHERE event_type='payment.settled'").fetchone()[
                0
            ]
            == 1
        )


def test_concurrent_distinct_orders_cannot_spend_the_same_run_budget_twice(stock_backend):
    gateway, store, state = stock_backend
    first = buy_intent(gateway)
    second_quote = gateway.get_quotes("A", {"tent": 3, "light": 6})
    second = gateway.create_order(second_quote["id"], "second-concurrent-order")
    copies = [MedusaGateway(gateway.directory, gateway.binding, store) for _ in range(2)]
    barrier = threading.Barrier(2)

    def pay(index):
        barrier.wait(timeout=5)
        try:
            return copies[index].authorize_payment(
                [first, second][index]["id"], f"concurrent-pay-{index}"
            )["status"]
        except ContractError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pay, range(2)))
    assert sorted(results) == ["BUDGET_EXCEEDED", "SETTLED"]
    assert len(state["orders"]) == 1
    assert sum(path.endswith("/complete") for _, path, _ in state["calls"]) == 1
    balance = gateway.payments.balance(gateway.binding.run_id)
    assert (balance["spent"], balance["reserved"], balance["available"]) == (310, 0, 190)
