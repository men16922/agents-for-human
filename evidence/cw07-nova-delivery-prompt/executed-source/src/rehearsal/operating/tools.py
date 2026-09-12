"""The purchasing tool contract over HTTP, with no local world object."""

from __future__ import annotations

import time

from strands import tool
from strands.types.tools import AgentTool

from rehearsal.world.client import PaymentObservation
from rehearsal.world.storage import ContractError, Json, integer

from .client import OperatingClient


def _payment(observation: PaymentObservation) -> Json:
    return observation.payment if observation.payment is not None else {"status": "UNKNOWN"}


def purchasing_http_tools(client: OperatingClient) -> list[AgentTool]:
    @tool
    def observe_world() -> Json:
        """Read your server goal, clock mode, balance, received goods and supplier names."""
        return client.observe_world()

    @tool
    def get_quotes(supplier: str, items: dict[str, int]) -> Json:
        """Get a short-lived server quote.

        Args:
            supplier: Public supplier name.
            items: Item names mapped to positive integer quantities.
        """
        return client.get_quotes(supplier, items)

    @tool
    def create_order(quote_id: str, idempotency_key: str) -> Json:
        """Accept an existing quote using a stable purchase key.

        Args:
            quote_id: Your server quote identifier.
            idempotency_key: Stable key reused when retrying this quote.
        """
        return client.create_order(quote_id, idempotency_key)

    @tool
    def authorize_payment(order_id: str, idempotency_key: str) -> Json:
        """Request canonical payment; transport uncertainty returns UNKNOWN.

        Args:
            order_id: Your accepted order ID.
            idempotency_key: Stable payment key; never replace an uncertain intent.
        """
        return _payment(client.authorize_payment(order_id, idempotency_key))

    @tool
    def get_payment(order_id: str) -> Json:
        """Query the same order's existing payment, without initiating another.

        Args:
            order_id: Your order identifier.
        """
        return _payment(client.get_payment(order_id))

    @tool
    def get_order(order_id: str) -> Json:
        """Read your order's actual server state.

        Args:
            order_id: Your order identifier.
        """
        return client.get_order(order_id)

    @tool
    def get_inventory() -> Json:
        """Read only goods actually delivered to your goal recipient."""
        snapshot = client.observe_world()
        return {"received": snapshot["inventory"], "tick": snapshot["tick"]}

    @tool
    def wait_for_updates(ticks: int) -> Json:
        """Wait 1 to 10 seconds; the independent server advances itself.

        Args:
            ticks: Bounded waiting interval; one operating tick is one second.
        """
        integer(ticks, 1)
        if ticks > 10:
            raise ContractError("WAIT_TOO_LONG")
        time.sleep(ticks)
        return get_inventory()

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
