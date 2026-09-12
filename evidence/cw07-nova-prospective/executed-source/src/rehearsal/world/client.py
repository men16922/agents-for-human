"""Client observation boundary for synthetic transport fault experiments."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .storage import Json


@dataclass(frozen=True)
class PaymentObservation:
    status: str
    payment: Json | None


def observe_payment(request: Callable[[], Json]) -> PaymentObservation:
    """A lost response says nothing about the ledger's success or failure.

    A future HTTP adapter will map its transport timeouts to TimeoutError here.
    Business rejections are deliberately not caught as transport uncertainty.
    """
    try:
        payment = request()
    except TimeoutError:
        return PaymentObservation("UNKNOWN", None)
    return PaymentObservation(payment["status"], payment)
