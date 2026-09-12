"""Single-owner timed changes to this session's fixtures; no retry after claim."""

from copy import deepcopy
from urllib.parse import urlencode

from rehearsal.commerce.details import FIELDS
from rehearsal.commerce.model_runner import write
from rehearsal.evaluation.condition_events import verify_receipt
from rehearsal.evaluation.conditions import fingerprint


def capture_get(session, path, role="seller"):
    session.spike.get(path, role)
    return deepcopy(session.spike.report["requests"][-1])


def apply_response_event(session, event):
    import httpx

    from rehearsal.operating.local import ORIGIN

    before = session.buyer.observe_world()
    if before["tick"] > event["at_tick"] + event["max_lateness_ticks"]:
        return {"event": event, "state": "MISSED", "before": before}
    path = f"/admin/runs/{session.run['binding']['run_id']}/faults/scheduled-payment-response"
    body = {"event_id": event["id"], "delay_ms": event["delay_ms"]}
    with httpx.Client(base_url=ORIGIN, timeout=10, trust_env=False) as client:
        result = client.post(
            path, json=body, headers={"Authorization": "Bearer " + session.control_token}
        )
        result.raise_for_status()
    return {
        "event": event,
        "state": "OBSERVED",
        "before": before,
        "after": session.buyer.observe_world(),
        "mutation": {
            "method": "POST",
            "path": path,
            "request": body,
            "status": result.status_code,
            "response": result.json(),
        },
    }


def apply_event(session, event):
    if event["kind"] == "payment_response_delay":
        return apply_response_event(session, event)
    fixture = session.fixtures[event["supplier"]]
    index = ("tent", "light").index(event["item"])
    vid, pid = fixture["variants"][index], fixture["products"][index]
    params = [
        ("variants[id][]", vid),
        ("region_id", session.run["binding"]["region_id"]),
        ("fields", FIELDS),
    ]
    catalog = "/store/products?" + urlencode(params)
    receipt = {"event": event, "state": "CLAIMED", "before": session.buyer.observe_world()}
    if receipt["before"]["tick"] > event["at_tick"] + event["max_lateness_ticks"]:
        return receipt | {"state": "MISSED"}
    receipt["catalog_before"] = capture_get(session, catalog, "buyer")
    receipt["variant_get"] = capture_get(
        session,
        f"/admin/products/{pid}/variants/{vid}?"
        + urlencode(
            {"fields": "+inventory_items.inventory_item_id,+inventory_items.required_quantity"}
        ),
    )
    if event["kind"] == "stock":
        iid, lid = fixture["inventory"][index], fixture["location"]["id"]
        levels_path = f"/admin/inventory-items/{iid}/location-levels"
        receipt["stock_before"] = capture_get(session, levels_path)
        levels = receipt["stock_before"]["response"]["inventory_levels"]
        if (
            len(levels) != 1
            or levels[0]["location_id"] != lid
            or levels[0]["reserved_quantity"] != 0
        ):
            raise ValueError("Refuse event against reserved or ambiguous inventory")
        path, body = f"{levels_path}/{lid}", {"stocked_quantity": event["value"]}
    else:
        path, body = (
            f"/admin/products/{pid}/variants/{vid}",
            {"prices": [{"currency_code": "usd", "amount": event["value"]}]},
        )
    session.spike.post(path, body)
    receipt["mutation"] = deepcopy(session.spike.report["requests"][-1])
    if event["kind"] == "stock":
        receipt["stock_after"] = capture_get(session, levels_path)
    receipt["catalog_after"] = capture_get(session, catalog, "buyer")
    receipt["after"] = session.buyer.observe_world()
    receipt["state"] = "OBSERVED"
    verify_receipt(receipt, event, session.run["binding"])
    return receipt


def tick_events(session):
    events = session.case.get("events", []) if session.case else []
    if not events:
        return
    tick = session.buyer.observe_world()["tick"]
    for event in events:
        path = session.path / ("event-" + event["id"] + ".json")
        if path.exists() or tick < event["at_tick"]:
            continue
        # Durable claim precedes every provider operation. Death/unknown never auto-resubmits.
        with path.open("x") as output:
            import json

            json.dump({"event": event, "state": "CLAIMED"}, output)
            output.flush()
            import os

            os.fsync(output.fileno())
        try:
            receipt = apply_event(session, event)
        except Exception as exc:
            receipt = {"event": event, "state": "UNKNOWN", "error_type": type(exc).__name__}
        write(path, receipt)


def export_events(session):
    import json

    receipts = {}
    for event in session.case["events"]:
        path = session.path / ("event-" + event["id"] + ".json")
        receipts[event["id"]] = (
            json.loads(path.read_text()) if path.exists() else {"event": event, "state": "NOT_RUN"}
        )
    result = {
        "schema": "rehearsal-timed-condition-events-v1",
        "case_sha256": fingerprint(session.case),
        "run_id": session.run["binding"]["run_id"],
        "receipts": receipts,
    }

    if any(e["kind"] == "payment_response_delay" for e in session.case["events"]):
        from pathlib import Path

        from rehearsal.commerce.seller import read_rows

        result["response_faults"] = [
            r
            for r in read_rows(
                Path(session.run["directory"]).parent / "response-faults.sqlite3", "response_faults"
            )
            if r["run_id"] == session.run["binding"]["run_id"]
        ]
    return result
