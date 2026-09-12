"""Independent synthetic Medusa seller process. No purchasing/model tool imports.

Reads submitted, budget-reserved intents. Every admin mutation is journaled before
HTTP. After interruption, actual remote state can resolve a pending action; an
unobserved action is never blindly repeated. Only this process has the admin token.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import sqlite3
import threading
import time
from pathlib import Path

import httpx

from rehearsal.world.storage import ContractError, Database, Json, canonical

ORDER_FIELDS = (
    "+customer_id,+currency_code,*payment_collections.payments.captures,*fulfillments,*items"
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules (
    order_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, first_seen REAL NOT NULL, due_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    order_id TEXT NOT NULL, action TEXT NOT NULL, body_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('STARTED','DONE','OBSERVED')),
    started_at REAL NOT NULL, finished_at REAL,
    PRIMARY KEY(order_id,action)
);
"""


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ContractError("INVALID_SELLER_ID")
    return value


def read_rows(path: Path, table: str) -> list[Json]:
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute(f"SELECT * FROM {table}")]


class AdminAPI:
    def __init__(self, token: str):
        self.http = httpx.Client(
            base_url="http://127.0.0.1:19000",
            timeout=15,
            trust_env=False,
            headers={"Authorization": f"Bearer {token}"},
        )

    def call(self, method: str, path: str, body: Json | None = None) -> Json:
        if method not in {"GET", "POST"} or not path.startswith("/admin/"):
            raise ContractError("ADMIN_ROUTE_REQUIRED")
        response = self.http.request(method, path, json=body)
        if response.status_code >= 400:
            raise ContractError(f"MEDUSA_SELLER_HTTP_{response.status_code}")
        result: Json = response.json()
        return result

    def close(self) -> None:
        self.http.close()


class Seller:
    def __init__(self, config: Json, api: AdminAPI):
        self.config, self.api = config, api
        self.directory = Path(config["directory"])
        self.db = Database(self.directory / "seller.sqlite3", SCHEMA)
        self.clock_epoch, self.clock_start = time.time(), time.monotonic()
        self.cycles = 0
        self.errors: dict[str, str] = {}

    def now(self) -> float:
        return self.clock_epoch + time.monotonic() - self.clock_start

    def _order(self, order_id: str) -> Json:
        value: Json = self.api.call(
            "GET", f"/admin/orders/{safe_id(order_id)}?fields={ORDER_FIELDS}"
        )["order"]
        return value

    def _discover(self, binding: Json, quote_id: str, mapped_id: str | None) -> Json | None:
        if mapped_id:
            return self._order(mapped_id)
        offset = 0
        matches: list[Json] = []
        while True:
            page = self.api.call(
                "GET",
                "/admin/orders?limit=50&offset="
                + str(offset)
                + "&customer_id="
                + safe_id(binding["customer_id"]),
            )
            matches.extend(
                o
                for o in page["orders"]
                if (o.get("metadata") or {}).get("rehearsal_quote") == quote_id
            )
            offset += len(page["orders"])
            if offset >= page["count"]:
                break
            if not page["orders"]:
                raise ContractError("SELLER_INCOMPLETE_LIST")
        if len(matches) > 1:
            raise ContractError("SELLER_DUPLICATE_ORDER")
        return self._order(matches[0]["id"]) if matches else None

    def _validate(
        self, binding: Json, quote: Json, intent: Json, order: Json, location_id: str
    ) -> None:
        supplier = binding["suppliers"][quote["supplier"]]
        items = {supplier["variants"][n]: q for n, q in quote["items"].items()}
        lines = order["items"]
        if (
            order["customer_id"] != binding["customer_id"]
            or order["region_id"] != binding["region_id"]
            or order["currency_code"] != "usd"
            or order["metadata"]
            != {"rehearsal_run": binding["run_id"], "rehearsal_quote": quote["id"]}
            or intent["run_id"] != binding["run_id"]
            or intent["recipient"] != quote["supplier"]
            or intent["status"] not in {"RESERVED", "SETTLED"}
            or intent["amount"] != quote["amount"]
            or order["total"] != intent["amount"]
            or order["tax_total"]
            or order["discount_total"]
            or len(lines) != len(items)
            or {i["variant_id"]: i["quantity"] for i in lines} != items
            or order["shipping_total"] != quote["shipping"]
            or order["total"]
            != order["shipping_total"] + sum(i["unit_price"] * i["quantity"] for i in lines)
            or len(order["shipping_methods"]) != 1
            or order["shipping_methods"][0]["shipping_option_id"] != supplier["shipping_option_id"]
        ):
            raise ContractError("SELLER_ORDER_CONTRACT_MISMATCH")
        for name, price in quote["unit_prices"].items():
            if (
                next(
                    i["unit_price"] for i in lines if i["variant_id"] == supplier["variants"][name]
                )
                != price
            ):
                raise ContractError("SELLER_PRICE_MISMATCH")
        collections = order["payment_collections"]
        if len(collections) != 1:
            raise ContractError("SELLER_PAYMENT_COUNT")
        collection = collections[0]
        if (
            collection["amount"] != intent["amount"]
            or collection["currency_code"] != "usd"
            or collection.get("refunded_amount", 0)
            or len(collection["payments"]) != 1
            or collection["payments"][0]["provider_id"] != "pp_system_default"
        ):
            raise ContractError("SELLER_PAYMENT_MISMATCH")
        if order["payment_status"] == "captured":
            captures = collection["payments"][0]["captures"]
            if (
                collection["captured_amount"] != intent["amount"]
                or sum(c["amount"] for c in captures) != intent["amount"]
                or len({c["id"] for c in captures}) != len(captures)
            ):
                raise ContractError("SELLER_CAPTURE_MISMATCH")
        elif order["payment_status"] != "authorized":
            raise ContractError("SELLER_UNSUPPORTED_PAYMENT_STATE")
        elif intent["status"] == "SETTLED":
            raise ContractError("SELLER_PAYMENT_REGRESSION")
        fulfillments = order["fulfillments"]
        if len(fulfillments) > 1 or any(f["canceled_at"] for f in fulfillments):
            raise ContractError("SELLER_UNSUPPORTED_FULFILLMENT")
        if any(
            f["location_id"] != location_id
            or f["shipping_option_id"] != supplier["shipping_option_id"]
            for f in fulfillments
        ):
            raise ContractError("SELLER_FULFILLMENT_SCOPE_MISMATCH")
        expected_count = {"not_fulfilled": 0, "fulfilled": 1, "shipped": 1, "delivered": 1}
        if len(fulfillments) != expected_count.get(order["fulfillment_status"]):
            raise ContractError("SELLER_UNSUPPORTED_FULFILLMENT_STATE")
        if order["fulfillment_status"] == "delivered" and (
            not fulfillments
            or not fulfillments[0]["delivered_at"]
            or any(i["detail"]["delivered_quantity"] != i["quantity"] for i in lines)
        ):
            raise ContractError("SELLER_DELIVERY_MISMATCH")

    def _observed(self, oid: str, action: str) -> None:
        with self.db.transaction() as db:
            db.execute(
                "UPDATE actions SET status='OBSERVED',finished_at=COALESCE(finished_at,?) "
                "WHERE order_id=? AND action=?",
                (self.now(), oid, action),
            )

    def _mutate(self, oid: str, action: str, path: str, body: Json) -> None:
        digest = hashlib.sha256(canonical(body).encode()).hexdigest()
        with self.db.transaction() as db:
            prior = db.execute(
                "SELECT * FROM actions WHERE order_id=? AND action=?", (oid, action)
            ).fetchone()
            if prior:
                # Remote GET did not show this action's effect; a replay is not safe evidence.
                raise ContractError("SELLER_ACTION_UNCERTAIN_OR_REGRESSED")
            db.execute(
                "INSERT INTO actions VALUES(?,?,?,'STARTED',?,NULL)",
                (oid, action, digest, self.now()),
            )
        self.api.call("POST", path, body)
        with self.db.transaction() as db:
            db.execute(
                "UPDATE actions SET status='DONE',finished_at=? WHERE order_id=? AND action=?",
                (self.now(), oid, action),
            )

    def process(self, run: Json, purchase: Json, quote: Json, intent: Json) -> None:
        binding = run["binding"]
        order = self._discover(binding, quote["id"], purchase["external_id"])
        if order is None:
            return  # Buyer may still be completing the cart; never initiate checkout here.
        self._validate(binding, quote, intent, order, run["locations"][quote["supplier"]])
        oid = safe_id(order["id"])
        now = self.now()
        with self.db.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO schedules VALUES(?,?,?,?)",
                (oid, binding["run_id"], now, now + quote["lead_ticks"]),
            )
            due = db.execute("SELECT due_at FROM schedules WHERE order_id=?", (oid,)).fetchone()[0]
        if order["payment_status"] == "authorized":
            pid = safe_id(order["payment_collections"][0]["payments"][0]["id"])
            self._mutate(oid, "capture", f"/admin/payments/{pid}/capture", {})
            order = self._order(oid)
            self._validate(binding, quote, intent, order, run["locations"][quote["supplier"]])
        if order["payment_status"] != "captured":
            return
        self._observed(oid, "capture")
        items = [{"id": i["id"], "quantity": i["quantity"]} for i in order["items"]]
        if not order["fulfillments"]:
            self._mutate(
                oid,
                "fulfill",
                f"/admin/orders/{oid}/fulfillments",
                {
                    "items": items,
                    "location_id": run["locations"][quote["supplier"]],
                    "shipping_option_id": binding["suppliers"][quote["supplier"]][
                        "shipping_option_id"
                    ],
                    "no_notification": True,
                },
            )
            order = self._order(oid)
            self._validate(binding, quote, intent, order, run["locations"][quote["supplier"]])
        self._observed(oid, "fulfill")
        fulfillment = order["fulfillments"][0]
        fid = safe_id(fulfillment["id"])
        if not fulfillment["shipped_at"]:
            self._mutate(
                oid,
                "ship",
                f"/admin/orders/{oid}/fulfillments/{fid}/shipments",
                {"items": items, "labels": [], "no_notification": True},
            )
            order = self._order(oid)
            self._validate(binding, quote, intent, order, run["locations"][quote["supplier"]])
            fulfillment = order["fulfillments"][0]
        self._observed(oid, "ship")
        if not fulfillment["delivered_at"] and self.now() >= due:
            self._mutate(
                oid,
                "deliver",
                f"/admin/orders/{oid}/fulfillments/{fid}/mark-as-delivered",
                {"no_notification": True},
            )
            order = self._order(oid)
            self._validate(binding, quote, intent, order, run["locations"][quote["supplier"]])
        if order["fulfillment_status"] == "delivered":
            self._observed(oid, "deliver")

    def step(self) -> None:
        errors = {}
        for run_id, run in self.config["runs"].items():
            directory = Path(run["directory"])
            purchases = read_rows(directory / "medusa.sqlite3", "purchases")
            quotes = {
                q["id"]: json.loads(q["data"])
                for q in read_rows(directory / "medusa.sqlite3", "quotes")
            }
            intents = {
                i["order_id"]: i for i in read_rows(directory / "payments.sqlite3", "intents")
            }
            for purchase in purchases:
                if purchase["stage"] == "ACCEPTED":
                    continue
                try:
                    self.process(
                        run, purchase, quotes[purchase["quote_id"]], intents[purchase["id"]]
                    )
                except Exception as exc:
                    errors[f"{run_id}:{purchase['id']}"] = (
                        exc.code if isinstance(exc, ContractError) else type(exc).__name__
                    )
        self.errors = errors
        self.cycles += 1

    def status(self, state: str = "running") -> None:
        value = {
            "state": state,
            "pid": os.getpid(),
            "updated_at": time.time(),
            "worker_cycles": self.cycles,
            "errors": self.errors,
        }
        temporary = self.directory / "seller-status.tmp"
        temporary.write_text(canonical(value) + "\n")
        temporary.replace(self.directory / "seller-status.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads(args.config.read_text())
    api = AdminAPI(config["admin_token"])
    seller = Seller(config, api)
    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    with (seller.directory / "seller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            while not stopping.is_set():
                seller.step()
                seller.status()
                stopping.wait(0.2)
        finally:
            seller.status("stopped")
            api.close()


if __name__ == "__main__":
    main()
