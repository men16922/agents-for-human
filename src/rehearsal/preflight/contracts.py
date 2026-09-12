"""Server-owned shopper intent and immutable source/plan contracts."""

from __future__ import annotations

import copy

from rehearsal.serverless.domain import Json, Rejected, digest, exact, identifier, integer

CONDITIONS = ("normal", "stock-disappears", "price-increases", "payment-response-lost")
SCHEMA = "preflight-impact-v1"
REPORT_TTL = 900


def catalog(name: str = "family-camping") -> Json:
    if name not in {"family-camping", "no-tents"}:
        raise Rejected("UNKNOWN_SHOPPING_REQUEST")
    suppliers = {}
    for sid, tent, light, lead in [("A", 109, 15, 1440), ("B", 129, 20, 2520), ("C", 99, 10, 7200)]:
        suppliers[sid] = {
            "shipping": 10,
            "lead_ticks": lead,
            "items": {
                "tent": {"price": tent, "stock": 0 if name == "no-tents" else 10},
                "light": {"price": light, "stock": 10},
            },
        }
    return {
        "schema": SCHEMA,
        "request_id": name,
        "revision": 1,
        "source": "operator-owned synthetic catalog; not Amazon/Rufus data",
        "intent": {
            "text": (
                "We leave for our first family camping trip on Saturday. Buy one tent and "
                "two lanterns for at most $200 including shipping, arriving at home by Friday "
                "6 PM. Do not buy lanterns alone if no tent can arrive on time."
            ),
            "goal": {
                "items": {"tent": 1, "light": 2},
                "budget": 200,
                "deadline_tick": 2880,
                "recipient": "family-home",
            },
            "all_items_required": True,
            "clock": "virtual minutes from Wednesday 6 PM; Friday 6 PM deadline",
            "currency": "synthetic USD",
        },
        "suppliers": suppliers,
    }


def snapshot(source: Json, captured_at: int) -> Json:
    integer(captured_at, 1, 9_999_999_999)
    value = {
        "source": copy.deepcopy(source),
        "source_sha256": digest(source),
        "captured_at": captured_at,
    }
    value["snapshot_sha256"] = digest(value)
    return value


def validate_snapshot(value: Json) -> None:
    exact(value, {"source", "source_sha256", "captured_at", "snapshot_sha256"})
    integer(value["captured_at"], 1, 9_999_999_999)
    if (
        digest(value["source"]) != value["source_sha256"]
        or digest({k: v for k, v in value.items() if k != "snapshot_sha256"})
        != value["snapshot_sha256"]
    ):
        raise Rejected("SNAPSHOT_HASH_MISMATCH")
    source = value["source"]
    # Operator catalog revisions may change offers; intent remains server owned.
    expected = catalog(source["request_id"])
    if source["schema"] != SCHEMA or source["intent"] != expected["intent"]:
        raise Rejected("SHOPPER_INTENT_CHANGED")
    integer(source["revision"], 1, 1_000_000)
    if set(source["suppliers"]) != {"A", "B", "C"}:
        raise Rejected("SUPPLIER_SCOPE_CHANGED")
    for supplier in source["suppliers"].values():
        exact(supplier, {"shipping", "lead_ticks", "items"})
        integer(supplier["shipping"], 0, 10000)
        integer(supplier["lead_ticks"], 1, 10080)
        if set(supplier["items"]) != {"tent", "light"}:
            raise Rejected("ITEM_SCOPE_CHANGED")
        for offer in supplier["items"].values():
            exact(offer, {"price", "stock"})
            integer(offer["price"], 0, 10000)
            integer(offer["stock"], 0, 10000)


def plan_for(value: Json, supplier: str) -> Json:
    validate_snapshot(value)
    if supplier not in value["source"]["suppliers"]:
        raise Rejected("UNKNOWN_SUPPLIER")
    plan = {
        "schema": SCHEMA,
        "supplier": supplier,
        "snapshot_sha256": value["snapshot_sha256"],
        "intent_sha256": digest(value["source"]["intent"]),
        "items": copy.deepcopy(value["source"]["intent"]["goal"]["items"]),
        "payment_recovery": "query_same_order",
        "partial_purchase": False,
        "execution": "quote-create-authorize-reconcile-observe-delivery",
    }
    plan["plan_sha256"] = digest(plan)
    return plan


def validate_plan(value: Json, plan: Json) -> None:
    if not isinstance(plan, dict) or plan != plan_for(value, plan.get("supplier", "")):
        raise Rejected("PLAN_CONTRACT_MISMATCH")


def scenario_for(value: Json, condition: str) -> Json:
    validate_snapshot(value)
    if condition not in CONDITIONS:
        raise Rejected("UNKNOWN_IMPACT_CONDITION")
    source = value["source"]
    result = {
        "scenario_version": SCHEMA + "-" + condition,
        "goal": copy.deepcopy(source["intent"]["goal"]),
        "suppliers": copy.deepcopy(source["suppliers"]),
        "events": [],
    }
    if condition in {"stock-disappears", "price-increases"}:
        result["events"] = [
            {
                "id": condition,
                "kind": "stock" if condition == "stock-disappears" else "price",
                "at_tick": 2,
                "supplier": "A",
                "item": "tent",
                "value": 0 if condition == "stock-disappears" else 209,
            }
        ]
    return result


def cell_id(report_id: str, supplier: str, condition: str) -> str:
    identifier(report_id)
    return "impact-" + digest([report_id, supplier, condition])[:36]


def expected_decision(report: Json, plan_hash: str, source: Json, now: int) -> Json:
    """Read-only eligibility; persistence must atomically recheck this source revision."""
    if digest({k: v for k, v in report.items() if k != "report_sha256"}) != report.get(
        "report_sha256"
    ):
        raise Rejected("REPORT_HASH_MISMATCH")
    if report.get("status") != "REPORT_READY" or not report.get("evidence_complete"):
        raise Rejected("REPORT_NOT_READY")
    if now >= report["expires_at"]:
        raise Rejected("REPORT_EXPIRED")
    if digest(source) != report["snapshot"]["source_sha256"]:
        raise Rejected("SOURCE_CHANGED_REHEARSAL_REQUIRED")
    options = [p for p in report["plans"] if p["plan"]["plan_sha256"] == plan_hash]
    if len(options) != 1 or not options[0]["eligible_for_handoff"]:
        raise Rejected("PLAN_NOT_ELIGIBLE")
    option = options[0]
    return {
        "schema": SCHEMA,
        "report_id": report["report_id"],
        "report_sha256": report["report_sha256"],
        "plan": option["plan"],
        "source_sha256": report["snapshot"]["source_sha256"],
        "source_revision": source["revision"],
        "revalidated_at": now,
        "expires_at": report["expires_at"],
        "decision": "ACCEPTED_FOR_EXECUTION_REVIEW",
        "scope": "simulation evidence handoff; not an Amazon order or payment authorization",
        "external_orders_created": 0,
    }
