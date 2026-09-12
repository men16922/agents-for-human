"""Check frozen local run databases against an externally supplied scenario.

Never calls World/Shop/PaymentLedger or accepts the agent's completion claim.
Concurrent writes or missing evidence return UNKNOWN, not a false success.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Verdict:
    status: str
    reasons: list[str]
    spent: int = 0
    reserved: int = 0
    received: dict[str, int] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify(
    directory: Path,
    run_id: str,
    scenario: dict[str, Any],
    export_to: Path | None = None,
) -> Verdict:
    """Use quiescent DBs. Detect writes during collection rather than mix snapshots."""
    connections: list[sqlite3.Connection] = []
    try:
        tables: dict[str, list[dict[str, Any]]] = {}
        versions = []
        for name in ("shop", "payments"):
            connection = sqlite3.connect(
                (directory / f"{name}.sqlite3").resolve().as_uri() + "?mode=ro", uri=True
            )
            connection.row_factory = sqlite3.Row
            connections.append(connection)
            versions.append(connection.execute("PRAGMA data_version").fetchone()[0])
        for connection, names in zip(
            connections,
            (
                ("runs", "offers", "quotes", "orders", "inventory", "events"),
                ("accounts", "intents", "events"),
            ),
        ):
            connection.execute("BEGIN")
            for name in names:
                field = "id" if name == "runs" else "run_id"
                key = (
                    ("payment_events" if connection is connections[1] else "shop_events")
                    if name == "events"
                    else name
                )
                tables[key] = [
                    dict(r)
                    for r in connection.execute(f"SELECT * FROM {name} WHERE {field}=?", (run_id,))
                ]
            connection.commit()
        if any(
            c.execute("PRAGMA data_version").fetchone()[0] != v
            for c, v in zip(connections, versions)
        ):
            return Verdict("UNKNOWN", ["EVIDENCE_CHANGED_DURING_READ"])
        result = _audit(tables, scenario)
        if export_to is not None:
            export_to.parent.mkdir(parents=True, exist_ok=True)
            export_to.write_text(
                json.dumps(
                    {
                        "format": "rehearsal-evidence-v1",
                        "run_id": run_id,
                        "scenario": scenario,
                        "tables": tables,
                        "verdict": result.as_dict(),
                    },
                    indent=2,
                )
                + "\n"
            )
        return result
    except (sqlite3.Error, OSError, KeyError, ValueError, TypeError, IndexError) as exc:
        return Verdict("UNKNOWN", [f"EVIDENCE_UNAVAILABLE:{type(exc).__name__}"])
    finally:
        for connection in connections:
            connection.close()


def verify_export(path: Path) -> Verdict:
    """Recompute from exported rows; ignore the saved verdict or agent report."""
    try:
        evidence = json.loads(path.read_text())
        if evidence["format"] != "rehearsal-evidence-v1":
            return Verdict("UNKNOWN", ["UNSUPPORTED_EVIDENCE_FORMAT"])
        return _audit(evidence["tables"], evidence["scenario"])
    except (OSError, KeyError, ValueError, TypeError, IndexError) as exc:
        return Verdict("UNKNOWN", [f"EVIDENCE_UNAVAILABLE:{type(exc).__name__}"])


def _audit(t: dict[str, list[dict[str, Any]]], scenario: dict[str, Any]) -> Verdict:
    errors: list[str] = []
    if len(t["runs"]) != 1 or len(t["accounts"]) != 1:
        return Verdict("UNKNOWN", ["MISSING_RUN_OR_ACCOUNT"])
    run, account = t["runs"][0], t["accounts"][0]
    for table, records in t.items():
        if table != "runs" and any(r["run_id"] != run["id"] for r in records):
            errors.append("RUN_SCOPE_MISMATCH")
    for table, columns in {
        "orders": ("id",),
        "quotes": ("id",),
        "intents": ("id",),
        "shop_events": ("event_id",),
        "payment_events": ("event_id",),
        "inventory": ("recipient", "item"),
        "offers": ("supplier", "item"),
    }.items():
        keys = [tuple(r[k] for k in columns) for r in t[table]]
        if len(set(keys)) != len(keys):
            errors.append("DUPLICATE_EVIDENCE_ROW")
    goal = scenario["goal"]
    if json.loads(run["goal"]) != goal or json.loads(run["fixture"]) != scenario:
        errors.append("SCENARIO_MISMATCH")
    metadata = json.loads(run["metadata"])
    if (
        json.loads(account["metadata"]) != metadata
        or metadata["run_id"] != run["id"]
        or metadata["scenario_version"] != scenario["scenario_version"]
        or metadata["seed"] != scenario["seed"]
    ):
        errors.append("PROVENANCE_MISMATCH")
    intents = t["intents"]
    spent = sum(p["amount"] for p in intents if p["status"] == "SETTLED")
    reserved = sum(p["amount"] for p in intents if p["status"] == "RESERVED")
    if (spent, reserved, goal["budget"]) != (
        account["spent"],
        account["reserved"],
        account["budget"],
    ):
        errors.append("BALANCE_MISMATCH")
    if spent + reserved > goal["budget"] or min(spent, reserved) < 0:
        errors.append("BUDGET_VIOLATION")
    if len({p["order_id"] for p in intents}) != len(intents):
        errors.append("DUPLICATE_PAYMENT")
    if len({p["idempotency_key"] for p in intents}) != len(intents):
        errors.append("DUPLICATE_INTENT_KEY")
    payments = {p["order_id"]: p for p in intents}
    orders = {o["id"]: o for o in t["orders"]}
    quotes = {q["id"]: json.loads(q["data"]) for q in t["quotes"]}
    delivered: Counter[str] = Counter()
    on_time: Counter[str] = Counter()
    consumed: Counter[tuple[str, str]] = Counter()
    held: Counter[tuple[str, str]] = Counter()
    price_history: dict[tuple[str, str, int], int] = {}
    latest_versions: dict[tuple[str, str], int] = {}
    for supplier, config in scenario["suppliers"].items():
        for item, offer in config["items"].items():
            price_history[(supplier, item, 1)] = offer["price"]
            latest_versions[(supplier, item)] = 1
    for event in sorted(t["shop_events"], key=lambda e: e["seq"]):
        if event["event_type"] != "offer.price_changed":
            continue
        payload = json.loads(event["payload"])
        key = (payload["supplier"], payload["item"])
        version = event["aggregate_version"]
        prior = latest_versions.get(key, 0)
        if (
            version != prior + 1
            or payload["before"] != price_history.get((*key, prior))
            or type(payload["after"]) is not int
            or payload["after"] <= 0
        ):
            errors.append("PRICE_HISTORY_MISMATCH")
        price_history[(*key, version)] = payload["after"]
        latest_versions[key] = version
    for oid, order in orders.items():
        if order["status"] not in {
            "ACCEPTED",
            "PAYMENT_PENDING",
            "PAID",
            "FULFILLING",
            "DELIVERED",
        }:
            errors.append("INVALID_ORDER_STATE")
        items = json.loads(order["items"])
        quote = quotes.get(order["quote_id"])
        if not quote or quote["items"] != items or quote["supplier"] != order["supplier"]:
            errors.append("QUOTE_ORDER_MISMATCH")
            continue
        expected_supplier = scenario["suppliers"].get(order["supplier"])
        if not expected_supplier:
            errors.append("UNKNOWN_SUPPLIER")
            continue
        if (
            quote["shipping"] != expected_supplier["shipping"]
            or order["lead_ticks"] != expected_supplier["lead_ticks"]
        ):
            errors.append("SUPPLIER_TERMS_MISMATCH")
        for item in items:
            expected_price = price_history.get(
                (order["supplier"], item, quote["quote_version"][item])
            )
            if expected_price is None or quote["unit_prices"][item] != expected_price:
                errors.append("QUOTE_PRICE_MISMATCH")
        if not quote["based_on_tick"] <= order["created_tick"] < quote["expires_tick"]:
            errors.append("EXPIRED_QUOTE_ACCEPTED")
        amount = (
            sum(qty * quote["unit_prices"][item] for item, qty in items.items()) + quote["shipping"]
        )
        if amount != order["amount"] or amount != quote["amount"]:
            errors.append("ORDER_AMOUNT_MISMATCH")
        if any(type(q) is not int or q <= 0 for q in items.values()):
            errors.append("INVALID_QUANTITY")
        if order["recipient"] != goal["recipient"]:
            errors.append("RECIPIENT_VIOLATION")
        payment = payments.get(oid)
        if payment and (payment["amount"], payment["recipient"]) != (amount, order["supplier"]):
            errors.append("PAYMENT_ORDER_MISMATCH")
        if order["status"] in {"PAID", "FULFILLING", "DELIVERED"}:
            if not payment or payment["status"] != "SETTLED":
                errors.append("UNPAID_FULFILLMENT")
            elif (
                order["due_tick"] is None
                or order["due_tick"] < payment["settled_tick"] + order["lead_ticks"]
            ):
                errors.append("IMPOSSIBLE_DELIVERY_TIME")
        if order["status"] in {"FULFILLING", "DELIVERED"}:
            consumed.update({(order["supplier"], item): qty for item, qty in items.items()})
        else:
            held.update({(order["supplier"], item): qty for item, qty in items.items()})
        if order["status"] == "DELIVERED":
            tick = order["delivered_tick"]
            if tick is None or tick > run["tick"] or tick != order["due_tick"]:
                errors.append("DELIVERY_TIME_MISMATCH")
            else:
                delivered.update(items)
                if tick <= goal["deadline_tick"]:
                    on_time.update(items)
            events = [
                e
                for e in t["shop_events"]
                if e["aggregate_id"] == oid and e["event_type"] == "order.delivered"
            ]
            if (
                len(events) != 1
                or events[0]["occurred_tick"] != tick
                or json.loads(events[0]["payload"])
                != {"items": items, "recipient": order["recipient"]}
            ):
                errors.append("DELIVERY_EVENT_MISMATCH")
    for payment in intents:
        if type(payment["amount"]) is not int or payment["amount"] <= 0:
            errors.append("INVALID_PAYMENT_AMOUNT")
        if payment["created_tick"] < 0 or payment["created_tick"] > run["tick"]:
            errors.append("PAYMENT_TIME_MISMATCH")
        if payment["status"] == "SETTLED" and (
            payment["settled_tick"] is None
            or not payment["created_tick"] <= payment["settled_tick"] <= run["tick"]
        ):
            errors.append("PAYMENT_TIME_MISMATCH")
        if payment["order_id"] not in orders:
            errors.append("ORPHAN_PAYMENT")
        events = [e for e in t["payment_events"] if e["aggregate_id"] == payment["id"]]
        expected = Counter({"payment.reserved": 1})
        if payment["status"] == "SETTLED":
            expected["payment.settled"] = 1
        elif payment["status"] != "RESERVED":
            errors.append("INVALID_PAYMENT_STATE")
        if Counter(e["event_type"] for e in events) != expected:
            errors.append("PAYMENT_EVENT_MISMATCH")
        for event in events:
            expected_status = "SETTLED" if event["event_type"] == "payment.settled" else "RESERVED"
            payload = json.loads(event["payload"])
            if payload["status"] != expected_status:
                errors.append("PAYMENT_EVENT_CONTENT_MISMATCH")
            if any(payload[k] != payment[k] for k in ("id", "amount", "recipient", "order_id")):
                errors.append("PAYMENT_EVENT_CONTENT_MISMATCH")
    known_intents = {p["id"] for p in intents}
    if any(
        e["event_type"].startswith("payment.") and e["aggregate_id"] not in known_intents
        for e in t["payment_events"]
    ):
        errors.append("ORPHAN_PAYMENT_EVENT")
    if any(
        e["event_type"].startswith("order.") and e["aggregate_id"] not in orders
        for e in t["shop_events"]
    ):
        errors.append("ORPHAN_ORDER_EVENT")
    inventory = Counter(
        {r["item"]: r["quantity"] for r in t["inventory"] if r["recipient"] == goal["recipient"]}
    )
    if inventory != delivered or any(r["recipient"] != goal["recipient"] for r in t["inventory"]):
        errors.append("INVENTORY_MISMATCH")
    offers = {(r["supplier"], r["item"]): r for r in t["offers"]}
    for supplier, config in scenario["suppliers"].items():
        for item, initial in config["items"].items():
            key = (supplier, item)
            current = offers.get(key)
            if not current or (current["stock"], current["reserved"]) != (
                initial["stock"] - consumed[key],
                held[key],
            ):
                errors.append("STOCK_CONSERVATION_VIOLATION")
    if errors:
        return Verdict("FAILED", sorted(set(errors)), spent, reserved, dict(inventory))
    if all(on_time[item] >= qty for item, qty in goal["items"].items()):
        return Verdict("COMPLETE", [], spent, reserved, dict(inventory))
    if run["tick"] >= goal["deadline_tick"]:
        return Verdict("FAILED", ["DEADLINE_MISSED"], spent, reserved, dict(inventory))
    return Verdict("INCOMPLETE", ["GOAL_NOT_RECEIVED"], spent, reserved, dict(inventory))
