"""HTTP-only purchasing adapter: no world DB, admin token or hidden recovery."""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from rehearsal.world.client import PaymentObservation
from rehearsal.world.storage import ContractError, Json


class OperatingClient:
    def __init__(self, base_url: str, run_id: str, token: str, timeout: float = 5):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Operating adapter requires a loopback HTTP origin")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
            raise ValueError("Invalid operating run ID")
        self.run_id = run_id
        self.transport_events: list[Json] = []
        self.http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            trust_env=False,
        )

    def close(self) -> None:
        self.http.close()

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Json:
        event: Json = {
            "method": method,
            "path": path,
            "run_id": self.run_id,
            "order_id": (body or {}).get("order_id"),
            "started_at": time.time(),
        }
        try:
            response = self.http.request(method, f"/runs/{self.run_id}/{path}", json=body)
            event["status"] = response.status_code
        except httpx.TransportError as exc:
            event["error_type"] = type(exc).__name__
            raise
        finally:
            event["finished_at"] = time.time()
            if method == "POST" and path == "payments":
                self.transport_events.append(event)
        if response.status_code >= 400:
            value = response.json()
            raise ContractError(
                value.get("error", value.get("detail", f"HTTP_{response.status_code}"))
            )
        result: Json = response.json()
        return result

    def observe_world(self) -> Json:
        return self.request("GET", "snapshot")

    def get_quotes(self, supplier: str, items: dict[str, int]) -> Json:
        return self.request("POST", "quotes", {"supplier": supplier, "items": items})

    def create_order(self, quote_id: str, idempotency_key: str) -> Json:
        return self.request(
            "POST", "orders", {"quote_id": quote_id, "idempotency_key": idempotency_key}
        )

    def authorize_payment(self, order_id: str, idempotency_key: str) -> PaymentObservation:
        try:
            value = self.request(
                "POST", "payments", {"order_id": order_id, "idempotency_key": idempotency_key}
            )
        except httpx.TransportError:
            return PaymentObservation("UNKNOWN", None)
        return PaymentObservation(value["status"], value)

    def get_payment(self, order_id: str) -> PaymentObservation:
        try:
            value = self.request("GET", f"payments/{order_id}")
        except httpx.TransportError:
            return PaymentObservation("UNKNOWN", None)
        return PaymentObservation(value["status"], value)

    def get_order(self, order_id: str) -> Json:
        return self.request("GET", f"orders/{order_id}")
