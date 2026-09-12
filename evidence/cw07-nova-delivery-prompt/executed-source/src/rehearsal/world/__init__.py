"""Local rehearsal composition. Agents will receive a restricted tool facade."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .payments import PaymentLedger
from .shop import Shop
from .storage import ContractError, Json, integer


class OperatingClock:
    """A monotonic one-second tick source independent of model/tool execution.

    This is a clock primitive, not the CW05 background service. A worker must poll
    it and call advance; no wall-clock progression is claimed for the offline runner.
    """

    def __init__(self, initial_tick: int = 0):
        self.initial_tick = integer(initial_tick)
        self.started = time.monotonic()

    def now(self) -> int:
        return self.initial_tick + int(time.monotonic() - self.started)


class World:
    def __init__(self, directory: Path):
        fork_manifest = directory / "fork.json"
        if (
            fork_manifest.exists()
            and json.loads(fork_manifest.read_text()).get("status") != "READY"
        ):
            raise ContractError("INCOMPLETE_FORK")
        self.shop = Shop(directory / "shop.sqlite3")
        self.payments = PaymentLedger(directory / "payments.sqlite3")

    def create_run(
        self,
        run_id: str,
        fixture: Json,
        policy_version: str = "fixture-v1",
        environment: str = "practice",
    ) -> None:
        if environment not in {"practice", "operating-test"}:
            raise ContractError("INVALID_ENVIRONMENT")
        metadata = {
            "environment": environment,
            "run_id": run_id,
            "scenario_version": fixture["scenario_version"],
            "policy_version": policy_version,
            "seed": fixture["seed"],
        }
        # Separate DB transactions. Idempotent initialization resumes a partial setup.
        self.shop.create_run(run_id, fixture, metadata)
        self.payments.create_account(run_id, fixture["goal"]["budget"], metadata)

    def authorize_payment(self, run_id: str, order_id: str, key: str) -> Json:
        order = self.shop.order(run_id, order_id)
        tick = self.shop.run(run_id)["tick"]
        # Amount and payee never come from the model's payment arguments.
        payment = self.payments.reserve(
            run_id, order_id, key, order["supplier"], order["amount"], tick
        )
        self.synchronize(run_id)
        return payment

    def settle_payment(self, run_id: str, intent_id: str) -> Json:
        payment = self.payments.settle(run_id, intent_id, self.shop.run(run_id)["tick"])
        self.synchronize(run_id)
        return payment

    def synchronize(self, run_id: str) -> None:
        # At-least-once delivery; shop receipts survive restart. A durable cursor is
        # an optimization for CW05, not a substitute for consumer deduplication.
        for event in self.payments.events(run_id):
            self.shop.apply_payment(run_id, event)

    def advance(self, run_id: str, tick: int) -> None:
        self.synchronize(run_id)
        self.shop.advance(run_id, tick)

    def snapshot(self, run_id: str) -> Json:
        run = self.shop.run(run_id)
        return {
            "metadata": run["metadata"],
            "tick": run["tick"],
            "goal": run["goal"],
            "balance": self.payments.balance(run_id),
            "inventory": self.shop.inventory(run_id),
        }
