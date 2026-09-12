"""Canonical quotes, inventory reservations, orders and virtual deliveries."""

from __future__ import annotations

import json
from pathlib import Path

from .storage import ContractError, Database, Json, canonical, emit, identifier, integer, row
from .supplier_content import supplier_content

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, tick INTEGER NOT NULL DEFAULT 0 CHECK(tick>=0),
    goal TEXT NOT NULL, metadata TEXT NOT NULL, fixture TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (
    run_id TEXT NOT NULL REFERENCES runs(id), id TEXT NOT NULL,
    shipping INTEGER NOT NULL, lead_ticks INTEGER NOT NULL, PRIMARY KEY(run_id,id)
);
CREATE TABLE IF NOT EXISTS offers (
    run_id TEXT NOT NULL, supplier TEXT NOT NULL, item TEXT NOT NULL,
    price INTEGER NOT NULL CHECK(price>0), stock INTEGER NOT NULL CHECK(stock>=0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved>=0), version INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(run_id,supplier,item), CHECK(reserved<=stock),
    FOREIGN KEY(run_id,supplier) REFERENCES suppliers(run_id,id)
);
CREATE TABLE IF NOT EXISTS quotes (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), key TEXT NOT NULL,
    quote_id TEXT NOT NULL, supplier TEXT NOT NULL, recipient TEXT NOT NULL,
    items TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), lead_ticks INTEGER NOT NULL,
    status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
    payment_intent_id TEXT, payment_version INTEGER NOT NULL DEFAULT 0,
    created_tick INTEGER NOT NULL, due_tick INTEGER, delivered_tick INTEGER,
    UNIQUE(run_id,key), UNIQUE(run_id,quote_id),
    CHECK(status IN ('ACCEPTED','PAYMENT_PENDING','PAID','FULFILLING','DELIVERED'))
);
CREATE TABLE IF NOT EXISTS receipts (
    event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, received_tick INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory (
    run_id TEXT NOT NULL REFERENCES runs(id), recipient TEXT NOT NULL, item TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity>=0), PRIMARY KEY(run_id,recipient,item)
);
"""


def decode_order(value: Json) -> Json:
    return value | {"items": json.loads(value["items"])}


class Shop(Database):
    def __init__(self, path: Path):
        super().__init__(path, SCHEMA)

    def create_run(self, run_id: str, fixture: Json, metadata: Json) -> None:
        goal = fixture["goal"]
        integer(goal["budget"])
        integer(goal["deadline_tick"], 1)
        if not run_id or not goal["recipient"] or not goal["items"] or not fixture["suppliers"]:
            raise ContractError("INVALID_SCENARIO")
        for quantity in goal["items"].values():
            integer(quantity, 1)
        with self.transaction() as db:
            old = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if old:
                if old["fixture"] != canonical(fixture) or old["metadata"] != canonical(metadata):
                    raise ContractError("RUN_CONFLICT")
                return
            db.execute(
                "INSERT INTO runs(id,goal,metadata,fixture) VALUES(?,?,?,?)",
                (run_id, canonical(goal), canonical(metadata), canonical(fixture)),
            )
            for supplier, config in fixture["suppliers"].items():
                integer(config["shipping"])
                integer(config["lead_ticks"], 1)
                db.execute(
                    "INSERT INTO suppliers VALUES(?,?,?,?)",
                    (run_id, supplier, config["shipping"], config["lead_ticks"]),
                )
                for item, offer in config["items"].items():
                    integer(offer["price"], 1)
                    integer(offer["stock"])
                    db.execute(
                        "INSERT INTO offers(run_id,supplier,item,price,stock) VALUES(?,?,?,?,?)",
                        (run_id, supplier, item, offer["price"], offer["stock"]),
                    )
            emit(db, run_id, "shop", run_id, 1, 0, "run.created", {"goal": goal, **metadata})

    def run(self, run_id: str) -> Json:
        with self.connect() as db:
            result = row(db, "SELECT * FROM runs WHERE id=?", (run_id,))
        return result | {k: json.loads(result[k]) for k in ("goal", "metadata", "fixture")}

    def quote(self, run_id: str, supplier: str, items: dict[str, int], ttl: int = 5) -> Json:
        integer(ttl, 1)
        if not items:
            raise ContractError("EMPTY_ORDER")
        for quantity in items.values():
            integer(quantity, 1)
        with self.transaction() as db:
            run = row(db, "SELECT * FROM runs WHERE id=?", (run_id,))
            config = row(db, "SELECT * FROM suppliers WHERE run_id=? AND id=?", (run_id, supplier))
            total = config["shipping"]
            versions, prices = {}, {}
            for item, quantity in items.items():
                offer = row(
                    db,
                    "SELECT * FROM offers WHERE run_id=? AND supplier=? AND item=?",
                    (run_id, supplier, item),
                )
                if offer["stock"] - offer["reserved"] < quantity:
                    raise ContractError("INSUFFICIENT_STOCK")
                versions[item], prices[item] = offer["version"], offer["price"]
                total += quantity * offer["price"]
            quote = {
                "id": identifier("quote"),
                "run_id": run_id,
                "supplier": supplier,
                "items": items,
                "unit_prices": prices,
                "quote_version": versions,
                "shipping": config["shipping"],
                "amount": total,
                "based_on_tick": run["tick"],
                "expires_tick": run["tick"] + ttl,
                "lead_ticks": config["lead_ticks"],
                "supplier_content": supplier_content(
                    supplier,
                    {
                        name: json.loads(run["fixture"])["suppliers"][supplier]["items"][name].get(
                            "description"
                        )
                        for name in items
                    },
                ),
            }
            db.execute("INSERT INTO quotes VALUES(?,?,?)", (quote["id"], run_id, canonical(quote)))
            return quote

    def create_order(self, run_id: str, quote_id: str, key: str) -> Json:
        if not key:
            raise ContractError("INVALID_IDEMPOTENCY_KEY")
        with self.transaction() as db:
            prior = db.execute(
                "SELECT * FROM orders WHERE run_id=? AND key=?", (run_id, key)
            ).fetchone()
            if prior:
                if prior["quote_id"] != quote_id:
                    raise ContractError("IDEMPOTENCY_CONFLICT")
                return decode_order(dict(prior))
            if db.execute(
                "SELECT 1 FROM orders WHERE run_id=? AND quote_id=?", (run_id, quote_id)
            ).fetchone():
                raise ContractError("QUOTE_ALREADY_ORDERED")
            run = row(db, "SELECT * FROM runs WHERE id=?", (run_id,))
            quote = json.loads(
                row(db, "SELECT data FROM quotes WHERE run_id=? AND id=?", (run_id, quote_id))[
                    "data"
                ]
            )
            goal = json.loads(run["goal"])
            if run["tick"] >= quote["expires_tick"]:
                raise ContractError("QUOTE_EXPIRED")
            if run["tick"] >= goal["deadline_tick"]:
                raise ContractError("DEADLINE_PASSED")
            for item, quantity in quote["items"].items():
                offer = row(
                    db,
                    "SELECT * FROM offers WHERE run_id=? AND supplier=? AND item=?",
                    (run_id, quote["supplier"], item),
                )
                if offer["version"] != quote["quote_version"][item]:
                    raise ContractError("STALE_QUOTE")
                if offer["stock"] - offer["reserved"] < quantity:
                    raise ContractError("INSUFFICIENT_STOCK")
                db.execute(
                    "UPDATE offers SET reserved=reserved+? "
                    "WHERE run_id=? AND supplier=? AND item=?",
                    (quantity, run_id, quote["supplier"], item),
                )
            oid = identifier("order")
            db.execute(
                "INSERT INTO orders(id,run_id,key,quote_id,supplier,recipient,items,amount,"
                "lead_ticks,status,created_tick) VALUES(?,?,?,?,?,?,?,?,?,'ACCEPTED',?)",
                (
                    oid,
                    run_id,
                    key,
                    quote_id,
                    quote["supplier"],
                    goal["recipient"],
                    canonical(quote["items"]),
                    quote["amount"],
                    quote["lead_ticks"],
                    run["tick"],
                ),
            )
            result = decode_order(row(db, "SELECT * FROM orders WHERE id=?", (oid,)))
            emit(db, run_id, "shop", oid, 1, run["tick"], "order.accepted", result)
            return result

    def order(self, run_id: str, order_id: str) -> Json:
        with self.connect() as db:
            return decode_order(
                row(db, "SELECT * FROM orders WHERE run_id=? AND id=?", (run_id, order_id))
            )

    def apply_payment(self, run_id: str, event: Json) -> None:
        """Internal outbox consumer; caller reads only from the trusted payment DB."""
        if event["run_id"] != run_id or event["source"] != "payments":
            raise ContractError("EVENT_SCOPE_MISMATCH")
        if event["event_type"] not in {"payment.reserved", "payment.settled"}:
            return
        payment = event["payload"]
        with self.transaction() as db:
            run = row(db, "SELECT * FROM runs WHERE id=?", (run_id,))
            if db.execute(
                "SELECT 1 FROM receipts WHERE event_id=?", (event["event_id"],)
            ).fetchone():
                return
            order = row(
                db, "SELECT * FROM orders WHERE run_id=? AND id=?", (run_id, payment["order_id"])
            )
            if (payment["amount"], payment["recipient"]) != (order["amount"], order["supplier"]):
                raise ContractError("PAYMENT_MISMATCH")
            if order["payment_intent_id"] not in (None, payment["id"]):
                raise ContractError("PAYMENT_MISMATCH")
            db.execute(
                "INSERT INTO receipts VALUES(?,?,?)", (event["event_id"], run_id, run["tick"])
            )
            if payment["version"] <= order["payment_version"]:
                return
            db.execute(
                "UPDATE orders SET payment_intent_id=?,payment_version=? WHERE id=?",
                (payment["id"], payment["version"], order["id"]),
            )
            if payment["status"] == "RESERVED":
                db.execute(
                    "UPDATE orders SET status='PAYMENT_PENDING',version=version+1 WHERE id=?",
                    (order["id"],),
                )
                emit(
                    db,
                    run_id,
                    "shop",
                    order["id"],
                    order["version"] + 1,
                    run["tick"],
                    "order.payment_pending",
                    {"payment_intent_id": payment["id"]},
                )
            elif payment["status"] == "SETTLED":
                emit(
                    db,
                    run_id,
                    "shop",
                    order["id"],
                    order["version"] + 1,
                    run["tick"],
                    "order.paid",
                    {"payment_intent_id": payment["id"]},
                )
                # Preparing shipment consumes the reserved physical stock exactly once.
                for item, quantity in json.loads(order["items"]).items():
                    db.execute(
                        "UPDATE offers SET reserved=reserved-?,stock=stock-? "
                        "WHERE run_id=? AND supplier=? AND item=?",
                        (quantity, quantity, run_id, order["supplier"], item),
                    )
                due = run["tick"] + order["lead_ticks"]
                db.execute(
                    "UPDATE orders SET status='FULFILLING',due_tick=?,version=version+2 WHERE id=?",
                    (due, order["id"]),
                )
                emit(
                    db,
                    run_id,
                    "shop",
                    order["id"],
                    order["version"] + 2,
                    run["tick"],
                    "order.fulfilling",
                    {"due_tick": due},
                )

    def advance(self, run_id: str, tick: int) -> None:
        """Admin clock driver. Process due events at their scheduled virtual times."""
        integer(tick)
        with self.transaction() as db:
            run = row(db, "SELECT * FROM runs WHERE id=?", (run_id,))
            if tick < run["tick"]:
                raise ContractError("CLOCK_REVERSED")
            due = db.execute(
                "SELECT * FROM orders WHERE run_id=? AND status='FULFILLING' "
                "AND due_tick<=? ORDER BY due_tick,id",
                (run_id, tick),
            ).fetchall()
            for order in due:
                items = json.loads(order["items"])
                for item, quantity in items.items():
                    db.execute(
                        "INSERT INTO inventory VALUES(?,?,?,?) ON CONFLICT(run_id,recipient,item) "
                        "DO UPDATE SET quantity=quantity+excluded.quantity",
                        (run_id, order["recipient"], item, quantity),
                    )
                db.execute(
                    "UPDATE orders SET status='DELIVERED',delivered_tick=due_tick,"
                    "version=version+1 WHERE id=?",
                    (order["id"],),
                )
                emit(
                    db,
                    run_id,
                    "shop",
                    order["id"],
                    order["version"] + 1,
                    order["due_tick"],
                    "order.delivered",
                    {"recipient": order["recipient"], "items": items},
                )
            if tick != run["tick"]:
                db.execute("UPDATE runs SET tick=? WHERE id=?", (tick, run_id))
                emit(db, run_id, "shop", run_id, tick + 1, tick, "clock.advanced", {"tick": tick})

    def inventory(self, run_id: str) -> dict[str, int]:
        run = self.run(run_id)
        with self.connect() as db:
            values = db.execute(
                "SELECT item,quantity FROM inventory WHERE run_id=? AND recipient=?",
                (run_id, run["goal"]["recipient"]),
            ).fetchall()
        return {v["item"]: v["quantity"] for v in values}

    def change_price(self, run_id: str, supplier: str, item: str, price: int) -> None:
        """Scenario administrator only. Invalidates prior quotes, never accepted orders."""
        integer(price, 1)
        with self.transaction() as db:
            run = row(db, "SELECT * FROM runs WHERE id=?", (run_id,))
            offer = row(
                db,
                "SELECT * FROM offers WHERE run_id=? AND supplier=? AND item=?",
                (run_id, supplier, item),
            )
            db.execute(
                "UPDATE offers SET price=?,version=version+1 "
                "WHERE run_id=? AND supplier=? AND item=?",
                (price, run_id, supplier, item),
            )
            emit(
                db,
                run_id,
                "shop",
                f"{supplier}/{item}",
                offer["version"] + 1,
                run["tick"],
                "offer.price_changed",
                {"supplier": supplier, "item": item, "before": offer["price"], "after": price},
            )

    def offers(self, run_id: str) -> list[Json]:
        with self.connect() as db:
            return [
                dict(v)
                for v in db.execute(
                    "SELECT * FROM offers WHERE run_id=? ORDER BY supplier,item", (run_id,)
                )
            ]
