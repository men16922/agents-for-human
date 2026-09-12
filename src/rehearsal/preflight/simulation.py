"""Execute a frozen basket in a fresh in-memory world; no network or commerce credentials."""

from __future__ import annotations

import copy
from typing import Any

from rehearsal.serverless.domain import Json, Rejected, digest, initial, transition
from rehearsal.serverless.verifier import verify

from .contracts import CONDITIONS, cell_id, scenario_for, validate_plan


class Simulation:
    def __init__(self, run_id: str, scenario: Json):
        self.scenario = copy.deepcopy(scenario)
        self.state = initial(run_id, scenario, 1)
        self.records: list[Json] = [
            {
                "version": 0,
                "run_id": run_id,
                "at": 1,
                "entries": [{"kind": "CREATED", "scenario": copy.deepcopy(scenario)}],
                "previous_sha256": None,
                "state_sha256": digest(self.state),
            }
        ]
        self.trace: list[Json] = []
        self.current = 0
        self.command("activate", {}, actor="seller")

    def command(self, action: str, args: Json, *, actor: str = "buyer") -> Any:
        before = self.state
        try:
            after, result, entries = transition(before, action, args, 1 + self.current, actor=actor)
        except Rejected as exc:
            self.trace.append(
                {
                    "tick": self.current,
                    "actor": actor,
                    "action": action,
                    "args": copy.deepcopy(args),
                    "error": str(exc),
                }
            )
            raise
        if entries:
            self.records.append(
                {
                    "version": after["version"],
                    "run_id": after["run_id"],
                    "at": 1 + self.current,
                    "entries": entries,
                    "previous_sha256": digest(before),
                    "state_sha256": digest(after),
                }
            )
        self.state = after
        self.trace.append(
            {
                "tick": self.current,
                "actor": actor,
                "action": action,
                "args": copy.deepcopy(args),
                "result": copy.deepcopy(result),
            }
        )
        return result

    def advance(self, tick: int) -> None:
        if tick < self.current:
            raise ValueError("Simulation clock cannot move backward")
        self.current = tick
        self.command("advance", {}, actor="seller")


def measure(report_id: str, value: Json, plan: Json, condition: str) -> Json:
    validate_plan(value, plan)
    scenario = scenario_for(value, condition)
    sim = Simulation(cell_id(report_id, plan["supplier"], condition), scenario)
    rejection = None
    recovery = "NOT_NEEDED"
    try:
        quote = sim.command("get_quotes", {"supplier": plan["supplier"], "items": plan["items"]})
        sim.advance(1)
        order = sim.command("create_order", {"quote_id": quote["id"], "idempotency_key": "basket"})
        # The environment changes after the plan/quote and before payment, independently.
        sim.advance(2)
        sim.command("authorize_payment", {"order_id": order["id"], "idempotency_key": "payment"})
        if condition == "payment-response-lost":
            # Inject a lost *response after the commit*, not a failed payment.
            sim.trace[-1].pop("result", None)
            sim.trace[-1]["transport"] = "RESPONSE_LOST_AFTER_COMMIT"
            sim.trace.append(
                {
                    "tick": sim.current,
                    "action": "payment_knowledge",
                    "status": "UNKNOWN",
                    "reservation_retained": sim.state["reserved"],
                }
            )
            payment = sim.command("get_payment", {"order_id": order["id"]})
            recovery = "RECONCILED_SAME_ORDER" if payment["status"] == "AUTHORIZED" else "UNKNOWN"
        sim.advance(3)
        # A virtual horizon records the deadline first, then eventual late delivery.
        deadline = scenario["goal"]["deadline_tick"]
        due = max(o["due_tick"] for o in sim.state["orders"].values())
        sim.advance(min(deadline, due))
        sim.advance(max(deadline, due))
    except Rejected as exc:
        rejection = str(exc)
        sim.advance(max(sim.current, scenario["goal"]["deadline_tick"]))
    verdict = verify(sim.state, sim.records, sim.state["run_id"], scenario)
    deliveries = [
        o["delivered_tick"] for o in sim.state["orders"].values() if o["status"] == "DELIVERED"
    ]
    summary = {
        "condition": condition,
        "status": verdict["status"],
        "spent": verdict["spent"],
        "reserved": verdict["reserved"],
        "received_on_time": verdict["received_on_time"],
        "received_eventually": copy.deepcopy(sim.state["inventory"]),
        "last_delivery_minute": max(deliveries) if deliveries else None,
        "orders_created": len(sim.state["orders"]),
        "payments_authorized": len(sim.state["payment_keys"]),
        "duplicate_payments": max(0, len(sim.state["payment_keys"]) - 1),
        "rejection": rejection,
        "payment_recovery": recovery,
        "external_orders_created": 0,
    }
    artifact = {
        "run_id": sim.state["run_id"],
        "plan": copy.deepcopy(plan),
        "condition": condition,
        "scenario": scenario,
        "state": sim.state,
        "journal": sim.records,
        "trace": sim.trace,
        "verdict": verdict,
        "summary": summary,
    }
    artifact["artifact_sha256"] = digest(artifact)
    return artifact


def measure_all(report_id: str, value: Json, plans: list[Json]) -> list[Json]:
    return [
        measure(report_id, value, plan, condition) for plan in plans for condition in CONDITIONS
    ]
