"""Independent evidence aggregation. Model prose and stored summaries have no verdict authority."""

from __future__ import annotations

import copy

from rehearsal.serverless.domain import Json, Rejected, digest, identifier
from rehearsal.serverless.verifier import verify

from .contracts import (
    CONDITIONS,
    REPORT_TTL,
    SCHEMA,
    cell_id,
    plan_for,
    scenario_for,
    validate_plan,
    validate_snapshot,
)


def audit_cell(report_id: str, value: Json, artifact: Json) -> Json:
    if digest({k: v for k, v in artifact.items() if k != "artifact_sha256"}) != artifact.get(
        "artifact_sha256"
    ):
        raise Rejected("ARTIFACT_HASH_MISMATCH")
    plan, condition = artifact["plan"], artifact["condition"]
    validate_plan(value, plan)
    expected_id = cell_id(report_id, plan["supplier"], condition)
    expected_scenario = scenario_for(value, condition)
    if artifact["run_id"] != expected_id or artifact["scenario"] != expected_scenario:
        raise Rejected("SIMULATION_SCOPE_MISMATCH")
    state, records, trace = artifact["state"], artifact["journal"], artifact["trace"]
    verdict = verify(state, records, expected_id, expected_scenario)
    if verdict["status"] == "INVALID":
        raise Rejected("INVALID_JOURNAL:" + ",".join(verdict["errors"]))
    orders = list(state["orders"].values())
    if len(orders) > 1 or any(
        o["supplier"] != plan["supplier"] or o["items"] != plan["items"] for o in orders
    ):
        raise Rejected("EXECUTED_PLAN_MISMATCH")
    authorizations = [e for r in records for e in r["entries"] if e["kind"] == "PAYMENT_AUTHORIZED"]
    if len(authorizations) > 1 or len(state["payment_keys"]) != len(authorizations):
        raise Rejected("DUPLICATE_PAYMENT")
    # Verify the simulated lost-response/reconciliation evidence rather than trusting its label.
    recovery = "NOT_NEEDED"
    losses = [t for t in trace if t.get("transport") == "RESPONSE_LOST_AFTER_COMMIT"]
    unknown = [t for t in trace if t.get("action") == "payment_knowledge"]
    queries = [t for t in trace if t.get("action") == "get_payment"]
    if condition == "payment-response-lost" and authorizations:
        if len(losses) != 1 or len(unknown) != 1 or len(queries) != 1:
            raise Rejected("MISSING_RESPONSE_LOSS_EVIDENCE")
        payment = authorizations[0]
        if (
            losses[0]["action"] != "authorize_payment"
            or losses[0]["args"]["order_id"] != payment["order_id"]
            or unknown[0]["status"] != "UNKNOWN"
            or unknown[0]["reservation_retained"] != payment["amount"]
            or queries[0]["args"]["order_id"] != payment["order_id"]
            or queries[0]["result"]["id"] != payment["order_id"]
            or queries[0]["result"]["status"] != "AUTHORIZED"
        ):
            raise Rejected("INVALID_PAYMENT_RECONCILIATION")
        recovery = "RECONCILED_SAME_ORDER"
    elif losses or unknown or queries:
        raise Rejected("UNEXPECTED_TRANSPORT_EVIDENCE")
    rejections = [t["error"] for t in trace if "error" in t]
    deliveries = [o["delivered_tick"] for o in orders if o["status"] == "DELIVERED"]
    summary = {
        "condition": condition,
        "status": verdict["status"],
        "spent": verdict["spent"],
        "reserved": verdict["reserved"],
        "received_on_time": verdict["received_on_time"],
        "received_eventually": copy.deepcopy(state["inventory"]),
        "last_delivery_minute": max(deliveries) if deliveries else None,
        "orders_created": len(orders),
        "payments_authorized": len(authorizations),
        "duplicate_payments": max(0, len(authorizations) - 1),
        "rejection": rejections[-1] if rejections else None,
        "payment_recovery": recovery,
        "external_orders_created": 0,
    }
    if summary != artifact["summary"] or verdict != artifact["verdict"]:
        raise Rejected("STORED_RESULT_MISMATCH")
    return {**summary, "artifact_sha256": artifact["artifact_sha256"], "run_id": expected_id}


def build_report(
    report_id: str,
    value: Json,
    artifacts: list[Json],
    *,
    proposed_supplier: str | None,
    generated_at: int,
    model_usage: Json | None = None,
) -> Json:
    identifier(report_id)
    validate_snapshot(value)
    if proposed_supplier is not None and proposed_supplier not in {"A", "B", "C"}:
        raise Rejected("INVALID_PROPOSED_PLAN")
    expected = {(supplier, condition) for supplier in "ABC" for condition in CONDITIONS}
    cells: dict[tuple[str, str], Json] = {}
    errors: list[Json] = []
    for artifact in artifacts:
        try:
            key = (artifact["plan"]["supplier"], artifact["condition"])
            if key not in expected or key in cells:
                raise Rejected("DUPLICATE_OR_UNEXPECTED_CELL")
            cells[key] = audit_cell(report_id, value, artifact)
        except (Rejected, KeyError, TypeError, ValueError) as exc:
            errors.append({"run_id": artifact.get("run_id"), "error": str(exc)[:160]})
    missing = sorted(expected - cells.keys())
    evidence_complete = not errors and not missing
    results = []
    for supplier in "ABC":
        measured = [cells[(supplier, c)] for c in CONDITIONS if (supplier, c) in cells]
        complete = sum(c["status"] == "COMPLETE" for c in measured)
        normal = cells.get((supplier, "normal"))
        eligible = (
            evidence_complete
            and complete == len(CONDITIONS)
            and all(c["reserved"] == 0 and c["duplicate_payments"] == 0 for c in measured)
        )
        results.append(
            {
                "plan": plan_for(value, supplier),
                "proposed_by_agent": supplier == proposed_supplier,
                "tested": len(measured),
                "planned_tests": len(CONDITIONS),
                "goals_met": complete,
                "normal_spend": normal["spent"] if normal else None,
                "normal_arrival_minute": normal["last_delivery_minute"] if normal else None,
                "max_simulated_spend": max((c["spent"] for c in measured), default=None),
                "eligible_for_handoff": eligible,
                "assessment": "MEETS_TESTED_CONDITIONS"
                if eligible
                else "EVIDENCE_INCOMPLETE"
                if not evidence_complete
                else "CONDITIONS_NOT_MET",
                "cells": measured,
            }
        )
    eligible_results = [r for r in results if r["eligible_for_handoff"]]
    recommended = (
        min(eligible_results, key=lambda r: r["normal_spend"]) if eligible_results else None
    )
    report = {
        "schema": SCHEMA,
        "report_id": report_id,
        "status": "REPORT_READY" if evidence_complete else "REVIEW_REQUIRED",
        "snapshot": copy.deepcopy(value),
        "generated_at": generated_at,
        "expires_at": value["captured_at"] + REPORT_TTL,
        "evidence_complete": evidence_complete,
        "coverage": {
            "planned": len(expected),
            "verified": len(cells),
            "missing": missing,
            "errors": errors,
        },
        "proposed_supplier": proposed_supplier,
        "recommended_supplier": recommended["plan"]["supplier"] if recommended else None,
        "plans": results,
        "model_usage": model_usage,
        "decision": "AWAITING_USER_DECISION" if recommended else "DO_NOT_EXECUTE",
        "execution_boundary": (
            "No external orders or payments; all measured transactions are isolated simulations."
        ),
        "limitations": [
            "Fixed synthetic catalog, not a live Amazon/Rufus connection.",
            "Four explicit conditions per plan; counts are not real-world success probabilities.",
            "Stock and price shocks target supplier A; supplier B disruptions are not covered.",
            "Payment response loss is injected after a simulated commit; no real network fault.",
            "Virtual delivery follows the configured schedule; no carrier delivery guarantee.",
            "The source revision and report expiry must be rechecked before any execution handoff.",
        ],
    }
    report["report_sha256"] = digest(report)
    return report
