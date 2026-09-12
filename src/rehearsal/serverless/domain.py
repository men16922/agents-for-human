"""Bounded synthetic commerce transitions, committed atomically with raw journal entries."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

Json = dict[str, Any]


class Rejected(ValueError):
    """A known pre-commit rejection; external transport failures are not this exception."""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value: Any, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise Rejected("INVALID_INTEGER")
    return value


def exact(args: Json, names: set[str]) -> None:
    if not isinstance(args, dict) or set(args) != names:
        raise Rejected("INVALID_ARGUMENTS")


def identifier(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 100:
        raise Rejected("INVALID_IDENTIFIER")
    if any(not (c.isascii() and (c.isalnum() or c in "-_:")) for c in value):
        raise Rejected("INVALID_IDENTIFIER")
    return value


def initial(run_id: str, scenario: Json, now: int) -> Json:
    identifier(run_id)
    return {
        "run_id": run_id,
        "version": 0,
        "created_at": now,
        "started_at": None,
        "goal": copy.deepcopy(scenario["goal"]),
        "suppliers": copy.deepcopy(scenario["suppliers"]),
        "conditions": copy.deepcopy(scenario.get("events", [])),
        "applied": [],
        "quotes": {},
        "orders": {},
        "order_keys": {},
        "payment_keys": {},
        "spent": 0,
        "reserved": 0,
        "inventory": {},
    }


def tick(state: Json, now: int) -> int:
    return max(0, now - state["started_at"]) if state["started_at"] is not None else 0


def observation(state: Json, now: int) -> Json:
    return {
        "run_id": state["run_id"],
        "version": state["version"],
        "tick": tick(state, now),
        "clock_mode": "independent-wall-clock",
        "goal": state["goal"],
        "inventory": state["inventory"],
        "balance": {
            "budget": state["goal"]["budget"],
            "spent": state["spent"],
            "reserved": state["reserved"],
            "available": state["goal"]["budget"] - state["spent"] - state["reserved"],
        },
        "suppliers": list(state["suppliers"]),
        "offers": state["suppliers"],
        "orders": list(state["orders"].values()),
    }


def quote_live(state: Json, quote: Json, now: int) -> None:
    if tick(state, now) > quote["expires_tick"]:
        raise Rejected("QUOTE_EXPIRED")
    supplier = state["suppliers"][quote["supplier"]]
    amount = supplier["shipping"]
    for item, quantity in quote["items"].items():
        offer = supplier["items"][item]
        if offer["stock"] < quantity:
            raise Rejected("STOCK_UNAVAILABLE")
        amount += offer["price"] * quantity
    if amount != quote["amount"]:
        raise Rejected("QUOTE_CHANGED")


def transition(
    original: Json, action: str, args: Json, now: int, *, actor: str = "buyer"
) -> tuple[Json, Any, list[Json]]:
    """No credentials, scope, amounts or recipients can be supplied by purchasing tools."""
    state = copy.deepcopy(original)
    entries: list[Json] = []
    current = tick(state, now)

    def emit(kind: str, **data: Any) -> None:
        entries.append({"kind": kind, "tick": current, **data})

    if action in {"activate", "advance"}:
        if actor != "seller":
            raise Rejected("FORBIDDEN")
        exact(args, set())
        if action == "activate":
            if state["started_at"] is None:
                state["started_at"] = now
                emit("ACTIVATED", started_at=now)
        elif state["started_at"] is not None:
            for condition in state["conditions"]:
                if condition["id"] in state["applied"] or current < condition["at_tick"]:
                    continue
                kind = condition["kind"]
                if kind not in {"stock", "price"}:
                    raise Rejected("UNSUPPORTED_CONDITION")
                offer = state["suppliers"][condition["supplier"]]["items"][condition["item"]]
                offer[kind] = condition["value"]
                state["applied"].append(condition["id"])
                emit("CONDITION_APPLIED", condition=condition)
            for order in state["orders"].values():
                if order["status"] == "AUTHORIZED":
                    order["status"] = "PAID"
                    state["reserved"] -= order["amount"]
                    state["spent"] += order["amount"]
                    emit("PAYMENT_CAPTURED", order_id=order["id"], amount=order["amount"])
                if order["status"] == "PAID" and current >= order["due_tick"]:
                    order["status"] = "DELIVERED"
                    order["delivered_tick"] = current
                    for item, quantity in order["items"].items():
                        state["inventory"][item] = state["inventory"].get(item, 0) + quantity
                    emit(
                        "DELIVERED",
                        order_id=order["id"],
                        items=order["items"],
                        recipient=state["goal"]["recipient"],
                    )
        result: Any = observation(state, now)
    elif actor != "buyer":
        raise Rejected("FORBIDDEN")
    elif action == "observe_world":
        exact(args, set())
        result = observation(state, now)
    elif action == "get_inventory":
        exact(args, set())
        result = {"inventory": state["inventory"], "tick": current}
    elif action in {"get_order", "get_payment"}:
        exact(args, {"order_id"})
        oid = identifier(args["order_id"])
        if oid not in state["orders"]:
            raise Rejected("ORDER_NOT_FOUND")
        result = state["orders"][oid]
    elif action == "get_quotes":
        exact(args, {"supplier", "items"})
        if state["started_at"] is None or current > state["goal"]["deadline_tick"]:
            raise Rejected("RUN_NOT_ACTIVE")
        supplier = state["suppliers"].get(identifier(args["supplier"]))
        items = args["items"]
        if not supplier or not isinstance(items, dict) or not items or len(items) > 2:
            raise Rejected("INVALID_QUOTE")
        amount = supplier["shipping"]
        for item, quantity in items.items():
            if item not in state["goal"]["items"]:
                raise Rejected("UNKNOWN_ITEM")
            integer(quantity, 1, state["goal"]["items"][item])
            offer = supplier["items"][item]
            if offer["stock"] < quantity:
                raise Rejected("STOCK_UNAVAILABLE")
            amount += offer["price"] * quantity
        if len(state["quotes"]) >= 60:
            raise Rejected("QUOTE_LIMIT")
        qid = f"quote-{state['version'] + 1}"
        quote = {
            "id": qid,
            "supplier": args["supplier"],
            "items": copy.deepcopy(items),
            "amount": amount,
            "issued_tick": current,
            "expires_tick": current + 15,
            "lead_ticks": supplier["lead_ticks"],
        }
        state["quotes"][qid] = quote
        emit("QUOTED", quote=quote)
        result = {
            **quote,
            "supplier_content": {
                "trust": "untrusted",
                "text": supplier.get("description", "Synthetic supplier quote."),
            },
        }
    elif action == "create_order":
        exact(args, {"quote_id", "idempotency_key"})
        key, qid = identifier(args["idempotency_key"]), identifier(args["quote_id"])
        if key in state["order_keys"]:
            order = state["orders"][state["order_keys"][key]]
            if order["quote_id"] != qid:
                raise Rejected("IDEMPOTENCY_CONFLICT")
            return state, order, []
        if current > state["goal"]["deadline_tick"] or state["started_at"] is None:
            raise Rejected("RUN_NOT_ACTIVE")
        if qid not in state["quotes"]:
            raise Rejected("QUOTE_NOT_FOUND")
        quote = state["quotes"][qid]
        quote_live(state, quote, now)
        if len(state["orders"]) >= 12:
            raise Rejected("ORDER_LIMIT")
        oid = f"order-{state['version'] + 1}"
        order = {
            "id": oid,
            "quote_id": qid,
            "supplier": quote["supplier"],
            "items": copy.deepcopy(quote["items"]),
            "amount": quote["amount"],
            "recipient": state["goal"]["recipient"],
            "status": "CREATED",
            "created_tick": current,
            "due_tick": current + quote["lead_ticks"],
        }
        state["orders"][oid] = order
        state["order_keys"][key] = oid
        emit("ORDER_CREATED", order=copy.deepcopy(order), idempotency_key=key)
        result = order
    elif action == "authorize_payment":
        exact(args, {"order_id", "idempotency_key"})
        key, oid = identifier(args["idempotency_key"]), identifier(args["order_id"])
        if oid not in state["orders"]:
            raise Rejected("ORDER_NOT_FOUND")
        order = state["orders"][oid]
        if key in state["payment_keys"] and state["payment_keys"][key] != oid:
            raise Rejected("IDEMPOTENCY_CONFLICT")
        if order["status"] != "CREATED":
            if state["payment_keys"].get(key) != oid:
                raise Rejected("PAYMENT_KEY_CHANGED")
            return state, order, []
        if current > state["goal"]["deadline_tick"]:
            raise Rejected("DEADLINE_REACHED")
        quote = state["quotes"][order["quote_id"]]
        quote_live(state, quote, now)
        if state["spent"] + state["reserved"] + order["amount"] > state["goal"]["budget"]:
            raise Rejected("BUDGET_EXCEEDED")
        for item, quantity in order["items"].items():
            state["suppliers"][order["supplier"]]["items"][item]["stock"] -= quantity
        state["reserved"] += order["amount"]
        order["status"] = "AUTHORIZED"
        order["due_tick"] = current + quote["lead_ticks"]
        state["payment_keys"][key] = oid
        emit(
            "PAYMENT_AUTHORIZED",
            order_id=oid,
            amount=order["amount"],
            due_tick=order["due_tick"],
            idempotency_key=key,
        )
        result = order
    else:
        raise Rejected("UNKNOWN_ACTION")
    if entries:
        state["version"] += 1
    return state, copy.deepcopy(result), entries
