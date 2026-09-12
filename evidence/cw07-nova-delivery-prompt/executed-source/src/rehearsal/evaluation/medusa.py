"""Independent exported Medusa + budget/mapping evidence checks. No gateway imports.

The caller supplies the expected goal and budget separately. A manual provider's
records prove this test backend's delivery state, never physical recipient receipt.
"""

from __future__ import annotations

import json
from typing import Any


def verify_medusa(
    evidence: dict[str, Any], expected_goal: dict[str, Any], expected_budget: int
) -> dict[str, Any]:
    errors: list[str] = []
    missing = False
    received = dict.fromkeys(expected_goal["items"], 0)

    def check(condition: bool, reason: str) -> None:
        if not condition:
            errors.append(reason)

    def indexed(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
        result = {r[key]: r for r in rows}
        check(len(rows) == len(result), f"duplicate {key}")
        return result

    try:
        config = evidence["binding"]
        check(config["goal"] == expected_goal, "goal mismatch")
        check(config["budget"] == expected_budget, "budget mismatch")
        tables = evidence["tables"]
        accounts = tables["accounts"]
        check(len(accounts) == 1, "account count")
        account = accounts[0]
        check(account["run_id"] == config["run_id"], "account scope")
        check(account["budget"] == expected_budget, "account budget")
        for field in ("budget", "spent", "reserved"):
            check(type(account[field]) is int and account[field] >= 0, "account integer")
        check(account["spent"] + account["reserved"] <= expected_budget, "budget exceeded")
        purchases = indexed(tables["purchases"], "id")
        quotes = indexed(tables["quotes"], "id")
        intents = indexed(tables["intents"], "id")
        indexed(tables["purchases"], "key")
        indexed(tables["purchases"], "quote_id")
        indexed(tables["intents"], "order_id")
        indexed(tables["intents"], "idempotency_key")
        orders = indexed(evidence["external_orders"], "id")
        mapped = [p["external_id"] for p in purchases.values() if p["external_id"]]
        check(len(mapped) == len(set(mapped)), "external order reused")
        check(not set(orders) - set(mapped), "unmapped external order")
        spent = reserved = 0
        capture_ids: set[str] = set()
        for intent in intents.values():
            check(intent["run_id"] == config["run_id"], "intent scope")
            check(type(intent["amount"]) is int and intent["amount"] > 0, "intent amount")
            purchase = purchases[intent["order_id"]]
            quote = json.loads(quotes[purchase["quote_id"]]["data"])
            check(quote["run_id"] == config["run_id"], "quote scope")
            check(intent["recipient"] == quote["supplier"], "payee mismatch")
            check(intent["amount"] == quote["amount"], "intent quote amount")
            if intent["status"] == "RESERVED":
                reserved += intent["amount"]
            elif intent["status"] == "SETTLED":
                spent += intent["amount"]
            else:
                errors.append("invalid intent state")
            external = orders.get(purchase["external_id"])
            if not external:
                missing = True
                continue
            check(purchase["stage"] == "MAPPED", "unmapped purchase")
            check(external["customer_id"] == config["customer_id"], "external customer")
            check(external["currency_code"] == "usd", "external currency")
            check(external["region_id"] == config["region_id"], "external region")
            check(
                external["metadata"]
                == {"rehearsal_run": config["run_id"], "rehearsal_quote": quote["id"]},
                "external metadata",
            )
            supplier = config["suppliers"][quote["supplier"]]
            expected_items = {supplier["variants"][n]: q for n, q in quote["items"].items()}
            lines = indexed(external["items"], "variant_id")
            check({v: i["quantity"] for v, i in lines.items()} == expected_items, "external items")
            methods = external["shipping_methods"]
            check(
                len(methods) == 1
                and methods[0]["shipping_option_id"] == supplier["shipping_option_id"],
                "external shipping",
            )
            total = external["shipping_total"] + sum(
                i["quantity"] * i["unit_price"] for i in lines.values()
            )
            check(total == external["total"] == intent["amount"], "external total")
            check(not external["tax_total"] and not external["discount_total"], "adjustments")
            check(external["shipping_total"] == quote["shipping"], "quote shipping")
            for name, price in quote["unit_prices"].items():
                check(lines[supplier["variants"][name]]["unit_price"] == price, "quote price")
            collections = external["payment_collections"]
            check(len(collections) == 1, "payment collection count")
            collection = collections[0]
            check(
                collection["currency_code"] == "usd" and collection["amount"] == total,
                "payment collection amount",
            )
            check(not collection.get("refunded_amount", 0), "refund unsupported")
            if intent["status"] == "SETTLED":
                check(external["payment_status"] == "captured", "settled without capture")
                check(collection["captured_amount"] == total, "captured total")
                payments = collection["payments"]
                check(
                    len(payments) == 1 and payments[0]["provider_id"] == "pp_system_default",
                    "payment provider or count",
                )
                captures = payments[0]["captures"]
                check(sum(c["amount"] for c in captures) == total, "capture sum")
                for capture in captures:
                    check(capture["id"] not in capture_ids, "capture reused")
                    capture_ids.add(capture["id"])
            elif external["payment_status"] == "captured":
                missing = True  # Actual capture exists, local reconciliation has not caught up.
            if purchase["received_tick"] is not None:
                check(intent["status"] == "SETTLED", "received before settlement")
                check(external["fulfillment_status"] == "delivered", "received without delivery")
                fulfillments = external["fulfillments"]
                check(
                    bool(fulfillments)
                    and all(f["delivered_at"] and not f["canceled_at"] for f in fulfillments),
                    "delivery records",
                )
                check(
                    all(i["detail"]["delivered_quantity"] == i["quantity"] for i in lines.values()),
                    "delivered quantities",
                )
                check(
                    type(purchase["received_tick"]) is int
                    and purchase["created_tick"]
                    <= purchase["received_tick"]
                    <= evidence["captured_at_tick"],
                    "receipt clock",
                )
                if purchase["received_tick"] <= expected_goal["deadline_tick"]:
                    for name, quantity in quote["items"].items():
                        received[name] = received.get(name, 0) + quantity
        check(account["spent"] == spent and account["reserved"] == reserved, "account sums")
        check(
            all(
                p["id"] in {i["order_id"] for i in intents.values()}
                for p in purchases.values()
                if p["stage"] != "ACCEPTED"
            ),
            "missing intent",
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return {"status": "UNKNOWN", "errors": errors + ["incomplete or malformed evidence"]}
    complete = all(received.get(n, 0) >= q for n, q in expected_goal["items"].items())
    status = (
        "FAILED"
        if errors
        else "UNKNOWN"
        if missing
        else "COMPLETE"
        if complete
        else (
            "FAILED"
            if evidence["captured_at_tick"] >= expected_goal["deadline_tick"]
            else "INCOMPLETE"
        )
    )
    return {
        "status": status,
        "errors": errors,
        "received_on_time": received,
        "spent": account["spent"],
        "reserved": account["reserved"],
        "scope": "independent-medusa-manual-provider-records",
    }
