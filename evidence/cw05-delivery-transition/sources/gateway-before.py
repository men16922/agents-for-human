"""Durable customer-only Medusa adapter, separate from seller credentials/operations.

Accepted orders are local purchase intents until Medusa completes their cart. A
submitted checkout is never automatically repeated. Read-only reconciliation uses
that authenticated customer's order list, then validates the persisted mapping.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from rehearsal.commerce.details import catalog
from rehearsal.world.payments import PaymentLedger
from rehearsal.world.storage import (
    ContractError,
    Database,
    Json,
    canonical,
    identifier,
    integer,
    row,
)
from rehearsal.world.supplier_content import supplier_content

SCHEMA = """
CREATE TABLE IF NOT EXISTS binding (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quotes (id TEXT PRIMARY KEY, cart_id TEXT UNIQUE, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS purchases (
    id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, quote_id TEXT UNIQUE NOT NULL,
    stage TEXT NOT NULL CHECK(stage IN ('ACCEPTED','SUBMITTED','MAPPED')),
    external_id TEXT UNIQUE, received_tick INTEGER, created_tick INTEGER NOT NULL
);
"""
ORDER_FIELDS = "+customer_id,+metadata,*fulfillments"


def external_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ContractError("INVALID_EXTERNAL_ID")
    return value


def units(value: object) -> int:
    # Medusa may serialize exact integral monetary values as either int or float.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("UNSUPPORTED_EXTERNAL_AMOUNT")
    if value < 0 or int(value) != value:
        raise ContractError("UNSUPPORTED_EXTERNAL_AMOUNT")
    return int(value)


class MedusaHTTPError(ContractError):
    """An external HTTP rejection, distinct from a local ledger/ownership violation."""

    def __init__(self, status_code: int):
        super().__init__(f"MEDUSA_HTTP_{status_code}")


class StoreAPI:
    """Fixed local origin and Store routes only; never a general-purpose HTTP tool."""

    def __init__(self, token: str, publishable_key: str):
        self.http = httpx.Client(
            base_url="http://127.0.0.1:19000",
            timeout=15,
            trust_env=False,
            headers={"Authorization": f"Bearer {token}", "x-publishable-api-key": publishable_key},
        )

    def call(self, method: str, path: str, body: Json | None = None) -> Json:
        if method not in {"GET", "POST"} or not path.startswith("/store/"):
            raise ContractError("STORE_ROUTE_REQUIRED")
        response = self.http.request(method, path, json=body)
        if response.status_code >= 400:
            # Do not forward external diagnostics, addresses, or hidden fields to the model.
            raise MedusaHTTPError(response.status_code)
        value: Json = response.json()
        return value

    def close(self) -> None:
        self.http.close()


@dataclass(frozen=True)
class Binding:
    run_id: str
    customer_id: str
    region_id: str
    suppliers: Json
    goal: Json
    budget: int = 500
    quote_ttl: int = 30


class MedusaGateway:
    def __init__(self, directory: Path, binding: Binding, store: StoreAPI):
        external_id(binding.run_id)
        external_id(binding.customer_id)
        integer(binding.budget)
        integer(binding.quote_ttl, 1)
        self.directory, self.binding, self.store = directory, binding, store
        self.db = Database(directory / "medusa.sqlite3", SCHEMA)
        self.payments = PaymentLedger(directory / "payments.sqlite3")
        self._mutex = threading.RLock()
        with self.db.transaction() as db:
            existing = db.execute("SELECT data FROM binding WHERE id=1").fetchone()
            if existing:
                persisted = json.loads(existing[0])
                if persisted["config"] != asdict(binding):
                    raise ContractError("BINDING_CONFLICT")
            else:
                persisted = {"config": asdict(binding), "started_at": time.time()}
                db.execute("INSERT INTO binding VALUES(1,?)", (canonical(persisted),))
        self.started_at = float(persisted["started_at"])
        self.payments.create_account(binding.run_id, binding.budget, {"backend": "medusa"})

    @contextmanager
    def locked(self) -> Iterator[None]:
        # Cross-process serialization spans short durable DB writes and external IO.
        # Never hold an uncommitted intent across a financial HTTP call.
        with self._mutex, (self.directory / "gateway.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def tick(self) -> int:
        return int(max(0, time.time() - self.started_at))

    def _identity(self) -> None:
        customer = self.store.call("GET", "/store/customers/me")["customer"]
        if customer["id"] != self.binding.customer_id:
            raise ContractError("CUSTOMER_SCOPE_MISMATCH")

    def _quote(self, qid: str) -> tuple[Json, str]:
        with self.db.connect() as db:
            value = row(db, "SELECT * FROM quotes WHERE id=?", (qid,))
        return json.loads(value["data"]), value["cart_id"]

    def _purchase(self, oid: str) -> Json:
        # Resolve only our local ID before any external request. External IDs are not handles.
        with self.db.connect() as db:
            return row(db, "SELECT * FROM purchases WHERE id=?", (oid,))

    def _terms(self, cart: Json, supplier: str, items: dict[str, int]) -> Json:
        config = self.binding.suppliers[supplier]
        wanted = {config["variants"][name]: quantity for name, quantity in items.items()}
        actual = {i["variant_id"]: units(i["quantity"]) for i in cart["items"]}
        if len(actual) != len(cart["items"]) or actual != wanted:
            raise ContractError("EXTERNAL_ITEMS_MISMATCH")
        if cart.get("customer_id") != self.binding.customer_id:
            raise ContractError("CUSTOMER_SCOPE_MISMATCH")
        if cart["currency_code"] != "usd" or cart.get("region_id") != self.binding.region_id:
            raise ContractError("EXTERNAL_CURRENCY_OR_REGION_MISMATCH")
        prices = {
            name: units(next(i["unit_price"] for i in cart["items"] if i["variant_id"] == vid))
            for name, vid in config["variants"].items()
            if name in items
        }
        shipping, amount = units(cart["shipping_total"]), units(cart["total"])
        if amount != shipping + sum(prices[n] * q for n, q in items.items()) or amount == 0:
            raise ContractError("UNSUPPORTED_EXTERNAL_TOTAL")
        if cart.get("tax_total", 0) or cart.get("discount_total", 0):
            raise ContractError("UNSUPPORTED_EXTERNAL_ADJUSTMENT")
        methods = cart["shipping_methods"]
        if len(methods) != 1 or methods[0]["shipping_option_id"] != config["shipping_option_id"]:
            raise ContractError("EXTERNAL_SHIPPING_MISMATCH")
        return {"unit_prices": prices, "shipping": shipping, "amount": amount}

    def get_quotes(self, supplier: str, items: dict[str, int]) -> Json:
        if supplier not in self.binding.suppliers or not items:
            raise ContractError("INVALID_SUPPLIER_OR_ITEMS")
        config = self.binding.suppliers[supplier]
        for name, quantity in items.items():
            integer(quantity, 1)
            if name not in config["variants"]:
                raise ContractError("NOT_FOUND")
        with self.locked():
            self._identity()
            qid = identifier("quote")
            cart = self.store.call(
                "POST",
                "/store/carts",
                {
                    "region_id": self.binding.region_id,
                    "shipping_address": {
                        "first_name": "Test",
                        "last_name": "Buyer",
                        "address_1": "Synthetic venue",
                        "city": "Test",
                        "country_code": "us",
                        "postal_code": "10001",
                    },
                    "metadata": {"rehearsal_run": self.binding.run_id, "rehearsal_quote": qid},
                    "items": [
                        {"variant_id": config["variants"][n], "quantity": q}
                        for n, q in items.items()
                    ],
                },
            )["cart"]
            cid = external_id(cart["id"])
            cart = self.store.call(
                "POST",
                f"/store/carts/{cid}/shipping-methods",
                {
                    "option_id": config["shipping_option_id"],
                },
            )["cart"]
            terms = self._terms(cart, supplier, items)
            tick = self.tick()
            quote = {
                "id": qid,
                "run_id": self.binding.run_id,
                "supplier": supplier,
                "items": items,
                **terms,
                "quote_version": hashlib.sha256(canonical(terms).encode()).hexdigest(),
                "based_on_tick": tick,
                "expires_tick": tick + self.binding.quote_ttl,
                "lead_ticks": config["lead_ticks"],
                "supplier_content": supplier_content(
                    supplier,
                    {
                        name: next(
                            i for i in cart["items"] if i["variant_id"] == config["variants"][name]
                        ).get("product_description")
                        for name in items
                    },
                ),
            }
            with self.db.transaction() as db:
                db.execute("INSERT INTO quotes VALUES(?,?,?)", (qid, cid, canonical(quote)))
            return quote

    def _refresh(self, quote: Json, cid: str) -> None:
        cart = self.store.call("GET", f"/store/carts/{external_id(cid)}")["cart"]
        # Each update validates only that variant's inventory in Medusa 2.20.1.
        # Check every quoted line; this is still not an atomic stock reservation.
        for line in cart["items"]:
            cart = self.store.call(
                "POST",
                f"/store/carts/{cid}/line-items/{external_id(line['id'])}",
                {"quantity": line["quantity"]},
            )["cart"]
        terms = self._terms(cart, quote["supplier"], quote["items"])
        if any(terms[k] != quote[k] for k in terms):
            raise ContractError("STALE_QUOTE")

    def create_order(self, quote_id: str, idempotency_key: str) -> Json:
        if not idempotency_key:
            raise ContractError("INVALID_IDEMPOTENCY_KEY")
        with self.locked():
            with self.db.connect() as db:
                prior = db.execute(
                    "SELECT * FROM purchases WHERE key=?", (idempotency_key,)
                ).fetchone()
                if prior:
                    if prior["quote_id"] != quote_id:
                        raise ContractError("IDEMPOTENCY_CONFLICT")
                    return self._public(dict(prior))
                if db.execute("SELECT 1 FROM purchases WHERE quote_id=?", (quote_id,)).fetchone():
                    raise ContractError("QUOTE_ALREADY_ORDERED")
            quote, cid = self._quote(quote_id)
            if self.tick() >= quote["expires_tick"]:
                raise ContractError("QUOTE_EXPIRED")
            if self.tick() >= self.binding.goal["deadline_tick"]:
                raise ContractError("DEADLINE_PASSED")
            self._identity()
            self._refresh(quote, cid)
            oid = identifier("order")
            with self.db.transaction() as db:
                db.execute(
                    "INSERT INTO purchases VALUES(?,?,?,'ACCEPTED',NULL,NULL,?)",
                    (oid, idempotency_key, quote_id, self.tick()),
                )
            return self._public(self._purchase(oid))

    def _public(self, purchase: Json, external: Json | None = None) -> Json:
        quote, _ = self._quote(purchase["quote_id"])
        status = "ACCEPTED"
        if external:
            status = {
                "delivered": "DELIVERED",
                "shipped": "FULFILLING",
                "fulfilled": "FULFILLING",
            }.get(external["fulfillment_status"], "ACCEPTED")
            if status == "ACCEPTED" and external["payment_status"] == "captured":
                status = "PAID"
        return {
            "id": purchase["id"],
            "run_id": self.binding.run_id,
            "quote_id": quote["id"],
            "supplier": quote["supplier"],
            "items": quote["items"],
            "amount": quote["amount"],
            "status": status,
            "created_tick": purchase["created_tick"],
        }

    def _validate_order(self, purchase: Json, order: Json) -> None:
        quote, _ = self._quote(purchase["quote_id"])
        metadata = order.get("metadata") or {}
        if (metadata.get("rehearsal_run"), metadata.get("rehearsal_quote")) != (
            self.binding.run_id,
            quote["id"],
        ):
            raise ContractError("EXTERNAL_MAPPING_MISMATCH")
        terms = self._terms(order, quote["supplier"], quote["items"])
        if any(terms[k] != quote[k] for k in terms):
            raise ContractError("EXTERNAL_AMOUNT_MISMATCH")

    def _external(self, purchase: Json) -> Json | None:
        self._identity()
        oid = purchase["external_id"]
        if not oid:
            # Only read the authenticated customer's paginated list. No complete retry here.
            offset = 0
            matches: list[Json] = []
            while True:
                page = self.store.call("GET", f"/store/orders?limit=50&offset={offset}")
                matches.extend(
                    o
                    for o in page["orders"]
                    if (o.get("metadata") or {}).get("rehearsal_quote") == purchase["quote_id"]
                )
                offset += len(page["orders"])
                if offset >= page["count"]:
                    break
                if not page["orders"]:
                    raise ContractError("INCOMPLETE_EXTERNAL_LIST")
            if len(matches) > 1:
                raise ContractError("DUPLICATE_EXTERNAL_ORDER")
            if not matches:
                return None
            oid = matches[0]["id"]
        order: Json = self.store.call(
            "GET", f"/store/orders/{external_id(oid)}?fields={ORDER_FIELDS}"
        )["order"]
        self._validate_order(purchase, order)
        if order["id"] != oid:
            raise ContractError("EXTERNAL_MAPPING_MISMATCH")
        if order["fulfillment_status"] == "delivered":
            if (
                not order["fulfillments"]
                or any(not f["delivered_at"] or f["canceled_at"] for f in order["fulfillments"])
                or any(i["detail"]["delivered_quantity"] != i["quantity"] for i in order["items"])
            ):
                raise ContractError("EXTERNAL_DELIVERY_MISMATCH")
        elif purchase["received_tick"] is not None:
            raise ContractError("EXTERNAL_DELIVERY_REGRESSION")
        with self.db.transaction() as db:
            db.execute(
                "UPDATE purchases SET stage='MAPPED',external_id=? WHERE id=?",
                (oid, purchase["id"]),
            )
            if order["fulfillment_status"] == "delivered":
                db.execute(
                    "UPDATE purchases SET received_tick=COALESCE(received_tick,?) WHERE id=?",
                    (self.tick(), purchase["id"]),
                )
        return order

    def _payment(self, purchase: Json) -> Json:
        intent = self.payments.for_order(self.binding.run_id, purchase["id"])
        if purchase["stage"] == "ACCEPTED":
            return intent
        order = self._external(purchase)
        if order is None:
            return {"status": "UNKNOWN"}
        collections = order["payment_collections"]
        if len(collections) != 1 or units(collections[0]["amount"]) != intent["amount"]:
            raise ContractError("EXTERNAL_PAYMENT_MISMATCH")
        collection = collections[0]
        if units(collection.get("refunded_amount", 0)):
            raise ContractError("UNSUPPORTED_EXTERNAL_REFUND")
        if order["payment_status"] == "captured":
            if units(collection["captured_amount"]) != intent["amount"]:
                raise ContractError("EXTERNAL_PAYMENT_MISMATCH")
            return self.payments.settle(self.binding.run_id, intent["id"], self.tick())
        if order["payment_status"] != "authorized":
            raise ContractError("UNSUPPORTED_EXTERNAL_PAYMENT_STATE")
        if intent["status"] == "SETTLED":
            raise ContractError("EXTERNAL_PAYMENT_REGRESSION")
        return intent

    def authorize_payment(self, order_id: str, idempotency_key: str) -> Json:
        with self.locked():
            purchase = self._purchase(order_id)
            quote, cid = self._quote(purchase["quote_id"])
            if purchase["stage"] == "ACCEPTED":
                if self.tick() >= self.binding.goal["deadline_tick"]:
                    raise ContractError("DEADLINE_PASSED")
                self._identity()
                self._refresh(quote, cid)
            intent = self.payments.reserve(
                self.binding.run_id,
                order_id,
                idempotency_key,
                quote["supplier"],
                quote["amount"],
                self.tick(),
            )
            if purchase["stage"] != "ACCEPTED":
                return self._safe_payment(purchase)
            # Persist submission BEFORE the first payment request; errors never release budget.
            with self.db.transaction() as db:
                db.execute("UPDATE purchases SET stage='SUBMITTED' WHERE id=?", (order_id,))
            try:
                collection = self.store.call(
                    "POST", "/store/payment-collections", {"cart_id": cid}
                )["payment_collection"]
                self.store.call(
                    "POST",
                    f"/store/payment-collections/{external_id(collection['id'])}/payment-sessions",
                    {"provider_id": "pp_system_default"},
                )
                result = self.store.call("POST", f"/store/carts/{cid}/complete", {})
                if result.get("type") != "order":
                    return {"status": "UNKNOWN"}
                # Reconcile using customer list, not an unverified checkout response ID.
                return self._safe_payment(self._purchase(order_id))
            except MedusaHTTPError as exc:
                # Submission may already have created a session/order. An HTTP status
                # alone cannot prove rollback of the multi-request checkout sequence.
                return {"status": "UNKNOWN", "id": intent["id"], "reason": exc.code}
            except httpx.TransportError:
                return {"status": "UNKNOWN", "id": intent["id"]}

    def _safe_payment(self, purchase: Json) -> Json:
        try:
            return self._payment(purchase)
        except MedusaHTTPError as exc:
            return {"status": "UNKNOWN", "reason": exc.code}
        except httpx.TransportError:
            return {"status": "UNKNOWN"}

    def get_payment(self, order_id: str) -> Json:
        with self.locked():
            return self._safe_payment(self._purchase(order_id))

    def get_order(self, order_id: str) -> Json:
        with self.locked():
            purchase = self._purchase(order_id)
            external = self._external(purchase) if purchase["stage"] != "ACCEPTED" else None
            result = self._public(purchase, external)
            if purchase["stage"] == "SUBMITTED" and external is None:
                result["status"] = "UNKNOWN"
            return result

    def _observe_details(self) -> Json:
        # Caller holds the gateway lock; only GETs are sent to Medusa.
        self._identity()
        try:
            offers = catalog(self.binding, self.store)
        except (ContractError, httpx.TransportError, KeyError, TypeError, ValueError):
            offers = {"status": "UNAVAILABLE", "source": "medusa-store-sales-channel", "offers": []}
        with self.db.connect() as db:
            total = db.execute("SELECT COUNT(*) FROM purchases").fetchone()[0]
            purchases = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM purchases ORDER BY created_tick DESC,id LIMIT 50"
                )
            ]
        orders = []
        for purchase in purchases:
            result = self._public(purchase)
            result["payment_status"] = "NOT_STARTED"
            if purchase["stage"] == "ACCEPTED":
                try:
                    result["payment_status"] = self.payments.for_order(
                        self.binding.run_id, purchase["id"]
                    )["status"]
                except ContractError as exc:
                    if exc.code != "NOT_FOUND":
                        raise
            else:
                try:
                    payment = self._safe_payment(purchase)
                    external = self._external(purchase)
                    result = self._public(purchase, external)
                    if external is None:
                        result["status"] = "UNKNOWN"
                    result["payment_status"] = payment["status"]
                except (ContractError, httpx.TransportError):
                    result.update(status="UNKNOWN", payment_status="UNKNOWN")
            orders.append(result)
        return {
            "catalog": offers,
            "orders": {
                "status": "PARTIAL"
                if any(o["status"] == "UNKNOWN" or o["payment_status"] == "UNKNOWN" for o in orders)
                else "OBSERVED",
                "total": total,
                "truncated": total > len(orders),
                "items": orders,
            },
        }

    def observe_world(self, *, include_details: bool = False) -> Json:
        with self.locked():
            received = dict.fromkeys(self.binding.goal["items"], 0)
            with self.db.connect() as db:
                purchases = [
                    dict(r) for r in db.execute("SELECT * FROM purchases WHERE stage!='ACCEPTED'")
                ]
            receipt_known = True
            for purchase in purchases:
                payment = self._safe_payment(purchase)
                receipt_known = receipt_known and payment["status"] != "UNKNOWN"
                if payment["status"] == "SETTLED":
                    purchase = self._purchase(purchase["id"])
                    if purchase["received_tick"] is not None:
                        quote, _ = self._quote(purchase["quote_id"])
                        for name, quantity in quote["items"].items():
                            received[name] = received.get(name, 0) + quantity
            balance = self.payments.balance(self.binding.run_id)
            result: Json = {
                "run_id": self.binding.run_id,
                "goal": self.binding.goal,
                "tick": self.tick(),
                "clock_mode": "operating-one-second-ticks",
                "inventory": received,
                "balance": {k: balance[k] for k in ("budget", "spent", "reserved", "available")},
                "suppliers": sorted(self.binding.suppliers),
            }
            if include_details:
                result["commerce"] = self._observe_details()
                result["commerce"]["receipt_status"] = (
                    "OBSERVED"
                    if receipt_known and result["commerce"]["orders"]["status"] == "OBSERVED"
                    else "UNAVAILABLE"
                )
            return result
