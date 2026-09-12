"""B0 fixed-rule comparator over exactly the purchasing tool surface.

This is an explicitly deterministic baseline, not the Strands executor or a hidden
planner inside the Medusa adapter. It receives no world, backend IDs, seed or admin.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import cast

import httpx
from strands.types.tools import AgentTool

from rehearsal.world.storage import ContractError, Json, integer

from .frozen import FrozenPolicy


class ToolPort:
    def __init__(self, tools: list[AgentTool], max_calls: int = 80, max_seconds: int = 180):
        self.tools = {t.tool_name: t for t in tools}
        self.max_calls = integer(max_calls, 1)
        self.max_seconds = integer(max_seconds, 1)
        self.started = time.monotonic()
        self.trace: list[Json] = []

    def call(self, name: str, **arguments: object) -> Json:
        if len(self.trace) >= self.max_calls:
            raise ContractError("TOOL_CALL_LIMIT")
        if time.monotonic() - self.started >= self.max_seconds:
            raise ContractError("WALL_TIME_LIMIT")
        record: Json = {"seq": len(self.trace) + 1, "tool": name, "arguments": arguments}
        self.trace.append(record)
        try:
            result = cast(Callable[..., Json], self.tools[name])(**arguments)
            record["result"] = result
            return result
        except Exception as exc:
            record["error"] = exc.code if isinstance(exc, ContractError) else type(exc).__name__
            raise
        finally:
            record["elapsed_seconds"] = time.monotonic() - self.started


def run_baseline(frozen: FrozenPolicy, port: ToolPort, execution_id: str) -> Json:
    """Buy one confirmed batch at a time; any unknown prior reservation stops replacement."""
    frozen.check()
    policy = frozen.policy
    orders: list[str] = []
    status, reason = "INCOMPLETE", None
    last: Json | None = None

    def remaining(observed: Json) -> dict[str, int]:
        return {
            n: q - observed["inventory"].get(n, 0)
            for n, q in observed["goal"]["items"].items()
            if q > observed["inventory"].get(n, 0)
        }

    def candidates(observed: Json) -> list[Json]:
        needs = remaining(observed)
        suppliers = observed["suppliers"][: policy.max_quote_candidates]

        def collect(groups: list[dict[str, int]]) -> list[Json]:
            found = []
            for items in groups:
                for supplier in suppliers:
                    try:
                        quote = port.call("get_quotes", supplier=supplier, items=items)
                    except ContractError as exc:
                        if exc.code not in {"INSUFFICIENT_STOCK", "NOT_FOUND", "MEDUSA_HTTP_400"}:
                            raise
                        continue
                    if (
                        quote["amount"] <= observed["balance"]["available"]
                        and quote["based_on_tick"] + quote["lead_ticks"]
                        <= observed["goal"]["deadline_tick"]
                    ):
                        found.append(quote)
            return found

        full = collect([needs])
        # Partial sourcing is explicit B0 logic and uses quoted quantities, never hidden stock.
        if full or len(needs) <= 1:
            return full
        partial = collect([{n: q} for n, q in sorted(needs.items())])
        # Do not buy an available subset when another required item has no
        # executable visible quote. This is current evidence, not a permanent
        # impossibility claim or permission to inspect hidden stock.
        covered = {item for quote in partial for item in quote["items"]}
        return partial if covered == set(needs) else []

    try:
        last = port.call("observe_world")
        if last["balance"]["reserved"]:
            return {
                "status": "UNKNOWN",
                "reason": "EXISTING_RESERVATION",
                "orders": [],
                "frozen_id": frozen.identifier,
                "scope": "B0-fixed-rule-not-model",
                "trace": port.trace,
                "snapshot": last,
            }
        while remaining(last):
            if last["tick"] >= last["goal"]["deadline_tick"]:
                reason = "DEADLINE_PASSED"
                break
            quotes = candidates(last)
            if policy.refresh_quote_before_order and quotes:
                quotes = candidates(last)
            if not quotes:
                reason = "NO_EXECUTABLE_QUOTE"
                break
            field = "amount" if policy.supplier_preference == "lowest_total" else "lead_ticks"
            selected = min(
                quotes, key=lambda q: (q[field], q["amount"], q["supplier"], sorted(q["items"]))
            )
            order = port.call(
                "create_order",
                quote_id=selected["id"],
                idempotency_key=f"{execution_id}:buy-{len(orders)}",
            )
            orders.append(order["id"])
            payment = port.call(
                "authorize_payment",
                order_id=order["id"],
                idempotency_key=f"{execution_id}:pay-{len(orders) - 1}",
            )
            # Wait for this exact order/payment, even if the authorizing response was lost.
            while True:
                payment = port.call("get_payment", order_id=order["id"])
                state = port.call("get_order", order_id=order["id"])
                last = port.call("observe_world")
                if payment["status"] == "SETTLED" and state["status"] == "DELIVERED":
                    break
                left = last["goal"]["deadline_tick"] - last["tick"]
                if left <= 0:
                    raise ContractError("DEADLINE_PASSED")
                port.call("wait_for_updates", ticks=min(policy.wait_ticks, left))
        if not remaining(last):
            status = "GOAL_OBSERVED"  # The independent verifier remains the completion authority.
    except ContractError as exc:
        reason = exc.code
        status = "LIMITED" if reason in {"TOOL_CALL_LIMIT", "WALL_TIME_LIMIT"} else "INCOMPLETE"
    except (TimeoutError, httpx.TransportError):
        status, reason = "UNKNOWN", "TRANSPORT_UNCERTAINTY"
    return {
        "status": status,
        "reason": reason,
        "orders": orders,
        "frozen_id": frozen.identifier,
        "scope": "B0-fixed-rule-not-model",
        "trace": port.trace,
        "snapshot": last,
    }
