"""Read-only replay of raw commerce facts. Does not call the mutation implementation."""

from __future__ import annotations

import copy
from typing import Any

from .domain import Json, digest


def verify(state: Json, records: list[Json], expected_run_id: str, scenario: Json) -> Json:
    errors: list[str] = []
    orders: Json = {}
    quotes: Json = {}
    spent = reserved = 0
    received: dict[str, int] = {}
    all_received: dict[str, int] = {}
    order_keys: dict[str, str] = {}
    payment_keys: dict[str, str] = {}
    previous: str | None = None
    goal: Json = {}
    suppliers: Json = {}
    started: int | None = None
    applied: list[str] = []
    conditions: Json = {}

    def require(ok: Any, message: str) -> None:
        if not ok:
            raise ValueError(message)

    try:
        require(state["run_id"] == expected_run_id, "EXPECTED_RUN_MISMATCH")
        require(len(records) == state["version"] + 1, "JOURNAL_GAP")
        for version, record in enumerate(records):
            require(
                record["version"] == version and record["run_id"] == state["run_id"],
                "JOURNAL_SCOPE",
            )
            require(record["previous_sha256"] == previous, "HASH_CHAIN")
            previous = record["state_sha256"]
            for event in record["entries"]:
                kind = event["kind"]
                if kind == "CREATED":
                    require(version == 0 and not goal, "DUPLICATE_CREATION")
                    require(event["scenario"] == scenario, "EXPECTED_SCENARIO_MISMATCH")
                    goal = scenario["goal"]
                    suppliers = copy.deepcopy(scenario["suppliers"])
                    conditions = {c["id"]: c for c in scenario.get("events", [])}
                    continue
                t = event["tick"]
                require(type(t) is int and t >= 0, "INVALID_EVENT_TICK")
                if kind == "ACTIVATED":
                    require(started is None and t == 0, "DUPLICATE_ACTIVATION")
                    started = event["started_at"]
                    require(started == record["at"], "ACTIVATION_TIME")
                    continue
                require(started is not None and t == max(0, record["at"] - started), "EVENT_TIME")
                if kind == "CONDITION_APPLIED":
                    c = event["condition"]
                    require(
                        c == conditions[c["id"]] and c["id"] not in applied and t >= c["at_tick"],
                        "INVALID_CONDITION",
                    )
                    suppliers[c["supplier"]]["items"][c["item"]][c["kind"]] = c["value"]
                    applied.append(c["id"])
                    continue
                if kind == "QUOTED":
                    q = event["quote"]
                    require(q["id"] not in quotes and t <= goal["deadline_tick"], "INVALID_QUOTE")
                    supplier = suppliers[q["supplier"]]
                    total = supplier["shipping"]
                    require(bool(q["items"]), "EMPTY_QUOTE")
                    for item, quantity in q["items"].items():
                        require(
                            type(quantity) is int and 0 < quantity <= goal["items"][item],
                            "QUOTE_QUANTITY",
                        )
                        offer = supplier["items"][item]
                        require(offer["stock"] >= quantity, "QUOTE_STOCK")
                        total += quantity * offer["price"]
                    require(
                        total == q["amount"]
                        and q["issued_tick"] == t
                        and q["expires_tick"] == t + 15
                        and q["lead_ticks"] == supplier["lead_ticks"],
                        "QUOTE_CANONICAL",
                    )
                    quotes[q["id"]] = copy.deepcopy(q)
                    continue
                if kind == "ORDER_CREATED":
                    order = copy.deepcopy(event["order"])
                    key = event["idempotency_key"]
                    q = quotes[order["quote_id"]]
                    require(order["id"] not in orders and key not in order_keys, "DUPLICATE_ORDER")
                    require(t <= min(q["expires_tick"], goal["deadline_tick"]), "STALE_ORDER")
                    require(
                        order["status"] == "CREATED"
                        and order["created_tick"] == t
                        and order["due_tick"] == t + q["lead_ticks"],
                        "ORDER_TIME",
                    )
                    require(
                        all(order[k] == q[k] for k in ["items", "supplier", "amount"])
                        and order["recipient"] == goal["recipient"],
                        "ORDER_CANONICAL",
                    )
                    supplier = suppliers[q["supplier"]]
                    total = supplier["shipping"]
                    for item, quantity in q["items"].items():
                        require(supplier["items"][item]["stock"] >= quantity, "ORDER_STOCK")
                        total += supplier["items"][item]["price"] * quantity
                    require(total == order["amount"], "ORDER_PRICE")
                    orders[order["id"]] = order
                    order_keys[key] = order["id"]
                    continue
                order = orders[event["order_id"]]
                q = quotes[order["quote_id"]]
                if kind == "PAYMENT_AUTHORIZED":
                    require(
                        order["status"] == "CREATED"
                        and t <= goal["deadline_tick"]
                        and t <= q["expires_tick"],
                        "INVALID_AUTHORIZATION",
                    )
                    key = event["idempotency_key"]
                    require(
                        key not in payment_keys and event["amount"] == order["amount"],
                        "PAYMENT_CANONICAL",
                    )
                    require(spent + reserved + event["amount"] <= goal["budget"], "OVER_BUDGET")
                    supplier = suppliers[order["supplier"]]
                    total = supplier["shipping"]
                    for item, quantity in order["items"].items():
                        offer = supplier["items"][item]
                        require(offer["stock"] >= quantity, "PAYMENT_STOCK")
                        total += offer["price"] * quantity
                        offer["stock"] -= quantity
                    require(total == order["amount"], "PAYMENT_PRICE")
                    require(event["due_tick"] == t + q["lead_ticks"], "DELIVERY_SCHEDULE")
                    order.update(status="AUTHORIZED", due_tick=event["due_tick"])
                    reserved += event["amount"]
                    payment_keys[key] = order["id"]
                elif kind == "PAYMENT_CAPTURED":
                    require(
                        order["status"] == "AUTHORIZED" and event["amount"] == order["amount"],
                        "INVALID_CAPTURE",
                    )
                    order["status"] = "PAID"
                    reserved -= event["amount"]
                    spent += event["amount"]
                elif kind == "DELIVERED":
                    require(order["status"] == "PAID" and t >= order["due_tick"], "EARLY_DELIVERY")
                    require(
                        event["items"] == order["items"]
                        and event["recipient"] == goal["recipient"],
                        "DELIVERY_CANONICAL",
                    )
                    order.update(status="DELIVERED", delivered_tick=t)
                    for item, quantity in event["items"].items():
                        all_received[item] = all_received.get(item, 0) + quantity
                        if t <= goal["deadline_tick"]:
                            received[item] = received.get(item, 0) + quantity
                else:
                    raise ValueError("UNKNOWN_EVENT")
        require(
            state["order_keys"] == order_keys and state["payment_keys"] == payment_keys,
            "IDEMPOTENCY_MAP_MISMATCH",
        )
        require(previous == digest(state), "FINAL_STATE_HASH")
        require(state["goal"] == goal and state["started_at"] == started, "GOAL_OR_CLOCK_CHANGED")
        require(state["suppliers"] == suppliers and state["applied"] == applied, "STOCK_MISMATCH")
        require(state["quotes"] == quotes and state["orders"] == orders, "ORDER_MISMATCH")
        require(
            state["spent"] == spent
            and state["reserved"] == reserved
            and state["inventory"] == all_received,
            "BALANCE_MISMATCH",
        )
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        errors.append(str(exc))
    complete = bool(goal) and all(received.get(k, 0) >= v for k, v in goal.get("items", {}).items())
    return {
        "status": "INVALID" if errors else "COMPLETE" if complete else "INCOMPLETE",
        "scope": "independent-serverless-synthetic-commerce-journal",
        "run_id": state.get("run_id"),
        "version": state.get("version"),
        "spent": spent,
        "reserved": reserved,
        "received_on_time": received,
        "errors": errors,
    }
