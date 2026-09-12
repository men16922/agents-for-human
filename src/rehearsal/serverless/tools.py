"""Run-bound Strands tools invoke an IAM-protected commerce Lambda."""

from __future__ import annotations

import json
import time
from typing import Any

from strands import tool
from strands.types.tools import AgentTool

from rehearsal.world.storage import ContractError

from .domain import Json, integer


def purchasing_tools(client: Any, function: str, run_id: str) -> list[AgentTool]:
    def call(action: str, args: Json) -> Json:
        response = client.invoke(
            FunctionName=function,
            Payload=json.dumps({"run_id": run_id, "action": action, "args": args}).encode(),
        )
        if response.get("FunctionError"):
            raise TimeoutError("Commerce result unknown; query the same order")
        data = json.loads(response["Payload"].read())
        if not data.get("ok"):
            error = data.get("error", "UNKNOWN_COMMERCE_RESPONSE")
            raise ContractError("INSUFFICIENT_STOCK" if error == "STOCK_UNAVAILABLE" else error)
        result: Json = data["result"]
        if action == "get_quotes":
            result["based_on_tick"] = result["issued_tick"]
        elif action == "get_payment":
            result["status"] = (
                "SETTLED"
                if result["status"] in {"PAID", "DELIVERED"}
                else "APPROVED"
                if result["status"] == "AUTHORIZED"
                else "NOT_AUTHORIZED"
            )
        elif action == "get_inventory":
            result["received"] = result["inventory"]
        return result

    @tool
    def observe_world() -> Json:
        """Read your fixed goal, observed inventory, budget and supplier availability."""
        return call("observe_world", {})

    @tool
    def get_quotes(supplier: str, items: dict[str, int]) -> Json:
        """Get a short-lived quote for positive quantities from one supplier.

        Args:
            supplier: Public supplier name A, B or C.
            items: Item names mapped to requested positive quantities.
        """
        return call("get_quotes", {"supplier": supplier, "items": items})

    @tool
    def create_order(quote_id: str, idempotency_key: str) -> Json:
        """Create an order from a valid quote; reuse the same key on retry.

        Args:
            quote_id: Identifier returned by get_quotes.
            idempotency_key: Stable key for this purchase intent.
        """
        return call("create_order", {"quote_id": quote_id, "idempotency_key": idempotency_key})

    @tool
    def authorize_payment(order_id: str, idempotency_key: str) -> Json:
        """Reserve the canonical order amount. Payment is not delivery.

        Args:
            order_id: Your existing order ID.
            idempotency_key: Stable payment key reused for retries.
        """
        return call("authorize_payment", {"order_id": order_id, "idempotency_key": idempotency_key})

    @tool
    def get_payment(order_id: str) -> Json:
        """Query the same payment after uncertainty; do not create a replacement.

        Args:
            order_id: Your existing order ID.
        """
        return call("get_payment", {"order_id": order_id})

    @tool
    def get_order(order_id: str) -> Json:
        """Read the actual fulfillment state of an existing order.

        Args:
            order_id: Your existing order ID.
        """
        return call("get_order", {"order_id": order_id})

    @tool
    def get_inventory() -> Json:
        """Read only actually delivered goods; no clock or balance mutation."""
        return call("get_inventory", {})

    @tool
    def wait_for_updates(ticks: int) -> Json:
        """Wait 1 to 10 real seconds; an independent AWS workflow advances delivery.

        Args:
            ticks: Bounded wait, from 1 to 10 seconds.
        """
        integer(ticks, 1, 10)
        time.sleep(ticks)
        return call("observe_world", {})

    return [
        observe_world,
        get_quotes,
        create_order,
        authorize_payment,
        get_payment,
        get_order,
        get_inventory,
        wait_for_updates,
    ]
