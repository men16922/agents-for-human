"""Real retained Store catalog + order responses through customer-only observation."""

import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from rehearsal.commerce.details import catalog, public_details
from rehearsal.commerce.gateway import Binding, MedusaGateway, StoreAPI
from rehearsal.commerce.observations import ObservationJournal, Projection
from rehearsal.world.storage import ContractError

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def evidence():
    return json.loads((ROOT / "tests/fixtures/commerce/observer-detail.json").read_text())


class ReadStore(StoreAPI):
    def __init__(self, evidence):
        self.customer = evidence["binding"]["customer_id"]
        self.orders = copy.deepcopy(evidence["external_orders"])
        self.products = json.loads(
            (ROOT / "tests/fixtures/commerce/products.json").read_text()
        )
        self.calls = []
        self.fail_catalog = False
        self.fail_orders = False

    def call(self, method, path, body=None):
        assert method == "GET" and body is None, "Observation must never issue a POST"
        self.calls.append((method, path))
        route = urlsplit(path).path
        if route == "/store/products":
            if self.fail_catalog:
                raise httpx.ReadTimeout("secret-catalog-token")
            return copy.deepcopy(self.products)
        if route == "/store/customers/me":
            return {"customer": {"id": self.customer}}
        if self.fail_orders:
            raise httpx.ReadTimeout("secret-order-token")
        if route == "/store/orders":
            return {"orders": self.orders, "count": len(self.orders)}
        if route.startswith("/store/orders/"):
            return {"order": next(o for o in self.orders if o["id"] == route.split("/")[-1])}
        raise AssertionError(route)


@pytest.fixture
def prepared(tmp_path, evidence):
    store = ReadStore(evidence)
    gateway = MedusaGateway(tmp_path, Binding(**evidence["binding"]), store)
    for database, tables in (
        (gateway.db, ("quotes", "purchases")),
        (gateway.payments, ("accounts", "intents")),
    ):
        with database.transaction() as db:
            for table in tables:
                db.execute(f"DELETE FROM {table}")
                for row in evidence["tables"][table]:
                    columns = ",".join(row)
                    db.execute(
                        f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in row)})",
                        tuple(row.values()),
                    )
    return gateway, store


def test_read_only_catalog_scope_and_price_are_separate_from_quotes(evidence):
    store = ReadStore(evidence)
    result = catalog(Binding(**evidence["binding"]), store)
    assert result["status"] == "OBSERVED"
    offers = {(o["supplier"], o["item"]): o for o in result["offers"]}
    assert offers["A", "tent"]["stock"] == 0
    assert offers["B", "tent"]["stock"] == 7
    assert offers["B", "light"]["unit_price"] == 25
    query = parse_qs(urlsplit(store.calls[0][1]).query)
    wanted = {
        v
        for supplier in evidence["binding"]["suppliers"].values()
        for v in supplier["variants"].values()
    }
    assert set(query["variants[id][]"]) == wanted
    assert query["region_id"] == [evidence["binding"]["region_id"]]
    assert "cart_id" not in query
    assert all(
        "variant_id" not in offer and "calculated_price" not in offer for offer in offers.values()
    )


def test_catalog_and_order_journal_projection_without_transaction_commands(prepared, tmp_path):
    gateway, store = prepared
    snapshot = gateway.observe_world(include_details=True)
    assert snapshot["inventory"] == {"tent": 3, "light": 6}
    assert snapshot["balance"]["spent"] == 380
    order = snapshot["commerce"]["orders"]["items"][0]
    assert (order["supplier"], order["status"], order["payment_status"]) == (
        "B",
        "DELIVERED",
        "SETTLED",
    )
    journal = ObservationJournal(tmp_path / "journal.db", [gateway.binding.run_id])
    raw = copy.deepcopy(snapshot)
    raw["commerce"]["orders"]["items"][0]["private_token"] = "hidden"
    event = journal.record(gateway.binding.run_id, raw, 100)
    assert "private_token" not in json.dumps(event)
    assert "quote_id" not in json.dumps(event["snapshot"]["commerce"])
    journal.publish(100)
    p = Projection(gateway.binding.run_id)
    p.apply(journal.read(gateway.binding.run_id, 0, 101)["events"][0])
    assert p.snapshot["commerce"]["catalog"]["status"] == "OBSERVED"
    assert p.snapshot["commerce"]["orders"]["items"][0]["status"] == "DELIVERED"
    assert all(m == "GET" for m, _ in store.calls)


def test_unavailable_catalog_does_not_fabricate_zero_stock_or_hide_orders(prepared):
    gateway, store = prepared
    store.fail_catalog = True
    result = gateway.observe_world(include_details=True)
    assert result["commerce"]["catalog"]["status"] == "UNAVAILABLE"
    assert result["commerce"]["catalog"]["offers"] == []
    assert result["commerce"]["orders"]["items"][0]["status"] == "DELIVERED"
    assert "secret" not in json.dumps(result)


def test_unavailable_order_is_unknown_not_reused_delivered(prepared):
    gateway, store = prepared
    store.fail_orders = True
    result = gateway.observe_world(include_details=True)
    order = result["commerce"]["orders"]["items"][0]
    assert order["status"] == order["payment_status"] == "UNKNOWN"
    assert result["commerce"]["orders"]["status"] == "PARTIAL"
    assert result["commerce"]["receipt_status"] == "UNAVAILABLE"
    assert "secret" not in json.dumps(result)


def test_other_customer_fails_before_catalog_or_order_read(prepared):
    gateway, store = prepared
    store.customer = "other-customer"
    with pytest.raises(ContractError, match="CUSTOMER_SCOPE_MISMATCH"):
        gateway.observe_world(include_details=True)
    assert all(path == "/store/customers/me" for _, path in store.calls)


@pytest.mark.parametrize("change", ["missing", "price", "currency", "stock", "flags"])
def test_missing_or_invalid_offer_is_unavailable_not_zero(evidence, change):
    store = ReadStore(evidence)
    if change == "missing":
        store.products["products"].pop(0)
    else:
        variant = store.products["products"][0]["variants"][0]
        if change == "price":
            variant["calculated_price"]["calculated_amount"] = True
        elif change == "currency":
            variant["calculated_price"]["currency_code"] = "krw"
        elif change == "stock":
            variant["inventory_quantity"] = -1
        elif change == "flags":
            variant["allow_backorder"] = 0
    result = catalog(Binding(**evidence["binding"]), store)
    assert result["status"] == "PARTIAL"
    first = next(o for o in result["offers"] if o["supplier"] == "A" and o["item"] == "tent")
    assert first["status"] == "UNAVAILABLE" and first["stock"] is None


def test_unmanaged_inventory_is_not_infinite_or_zero(evidence):
    store = ReadStore(evidence)
    variant = store.products["products"][0]["variants"][0]
    variant["manage_inventory"] = False
    del variant["inventory_quantity"]
    result = catalog(Binding(**evidence["binding"]), store)
    offer = result["offers"][0]
    assert offer["status"] == "OBSERVED" and offer["stock"] is None
    assert offer["inventory_managed"] is False


@pytest.mark.parametrize("change", ["run", "duplicate", "supplier", "total", "amount"])
def test_journal_rejects_conflicting_order_details(prepared, change):
    gateway, _ = prepared
    snapshot = gateway.observe_world(include_details=True)
    details = snapshot["commerce"]
    order = details["orders"]["items"][0]
    if change == "run":
        order["run_id"] = "other"
    elif change == "duplicate":
        details["orders"]["items"].append(copy.deepcopy(order))
    elif change == "supplier":
        order["supplier"] = "not-bound"
    elif change == "total":
        details["orders"]["total"] = 0
    elif change == "amount":
        order["amount"] = True
    with pytest.raises(ContractError, match="INVALID_COMMERCE_OBSERVATION"):
        public_details(details, snapshot)


def test_accepted_order_with_committed_reservation_does_not_look_unpaid(prepared):
    gateway, store = prepared
    with gateway.db.transaction() as db:
        db.execute("UPDATE purchases SET stage='ACCEPTED',external_id=NULL,received_tick=NULL")
    with gateway.payments.transaction() as db:
        db.execute("UPDATE intents SET status='RESERVED',settled_tick=NULL")
        db.execute("UPDATE accounts SET spent=0,reserved=380")
    result = gateway.observe_world(include_details=True)
    order = result["commerce"]["orders"]["items"][0]
    assert order["status"] == "ACCEPTED" and order["payment_status"] == "RESERVED"
    assert result["balance"]["reserved"] == 380
    assert all(
        path.startswith(("/store/customers/me", "/store/products?")) for _, path in store.calls
    )


def test_unpaid_accepted_order_is_explicit_and_does_not_read_external_orders(prepared):
    gateway, store = prepared
    with gateway.db.transaction() as db:
        db.execute("UPDATE purchases SET stage='ACCEPTED',external_id=NULL,received_tick=NULL")
    with gateway.payments.transaction() as db:
        db.execute("DELETE FROM intents")
        db.execute("UPDATE accounts SET spent=0,reserved=0")
    result = gateway.observe_world(include_details=True)
    assert result["commerce"]["orders"]["items"][0]["payment_status"] == "NOT_STARTED"
    assert all(
        path.startswith(("/store/customers/me", "/store/products?")) for _, path in store.calls
    )


def test_order_observation_bounds_rows_and_reports_total(prepared):
    gateway, _ = prepared
    with gateway.db.transaction() as db:
        base_quote = dict(db.execute("SELECT * FROM quotes LIMIT 1").fetchone())
        db.execute("DELETE FROM purchases")
        for n in range(51):
            qid = f"quote-{n}"
            quote = json.loads(base_quote["data"])
            quote["id"] = qid
            db.execute("INSERT INTO quotes VALUES(?,?,?)", (qid, f"cart-{n}", json.dumps(quote)))
            db.execute(
                "INSERT INTO purchases VALUES(?,?,?,'ACCEPTED',NULL,NULL,?)",
                (f"order-{n}", f"key-{n}", qid, n),
            )
    with gateway.payments.transaction() as db:
        db.execute("DELETE FROM intents")
        db.execute("UPDATE accounts SET spent=0,reserved=0")
    result = gateway.observe_world(include_details=True)
    orders = result["commerce"]["orders"]
    assert orders["total"] == 51 and len(orders["items"]) == 50 and orders["truncated"]
    assert orders["items"][0]["id"] == "order-50"
    assert "order-0" not in {o["id"] for o in orders["items"]}
