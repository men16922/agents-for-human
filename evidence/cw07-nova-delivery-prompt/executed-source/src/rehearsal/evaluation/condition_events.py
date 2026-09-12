"""Declared timed provider changes and independent raw evidence checks.

A bounded single-controller schedule, not atomic isolation or model efficacy.
"""

from __future__ import annotations

from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

from rehearsal.evaluation.conditions import fingerprint, number, validate_static
from rehearsal.world.storage import Json, integer


def static_case(case: Json) -> Json:
    return {k: deepcopy(v) for k, v in case.items() if k != "events"}


def validate_case(case: Json) -> None:
    validate_static(static_case(case))
    if "events" not in case:
        return
    events = case["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= 8:
        raise ValueError("One to eight explicit timed events required")
    ids: set[str] = set()
    previous = 0
    kinds: dict[str, str] = {}
    for event in events:
        kind = event.get("kind")
        extra = {"delay_ms"} if kind == "payment_response_delay" else {"supplier", "item", "value"}
        if kind in {"delivery_notification", "notification_replay"}:
            extra = {"delay_ms", "copies"} | (
                {"source_event"} if kind == "notification_replay" else set()
            )
        if set(event) != {"id", "at_tick", "max_lateness_ticks", "kind"} | extra:
            raise ValueError("Unsupported event fields")
        eid = event["id"]
        if (
            not isinstance(eid, str)
            or not eid.isascii()
            or not eid.isalnum()
            or len(eid) > 32
            or eid in ids
        ):
            raise ValueError("Unique alphanumeric event id required")
        ids.add(eid)
        tick = integer(event["at_tick"], 1)
        late = integer(event["max_lateness_ticks"])
        if tick <= previous or late > 5 or tick + late >= case["goal"]["deadline_tick"]:
            raise ValueError("Ordered bounded schedule before deadline required")
        previous = tick
        if kind in {"delivery_notification", "notification_replay"}:
            if integer(event["delay_ms"]) > 5000 or integer(event["copies"], 1) > 3:
                raise ValueError("Unsupported notification schedule")
            if (
                kind == "notification_replay"
                and kinds.get(event["source_event"]) != "delivery_notification"
            ):
                raise ValueError("Replay requires an earlier declared delivery notification")
            kinds[eid] = kind
            continue
        kinds[eid] = event["kind"]
        if event["kind"] == "payment_response_delay":
            if integer(event["delay_ms"], 1) > 5000:
                raise ValueError("Unsupported response delay")
            continue
        if (
            event["kind"] not in {"price", "stock"}
            or event["supplier"] not in {"A", "B", "C"}
            or event["item"] not in {"tent", "light"}
        ):
            raise ValueError("Unsupported provider event")
        integer(event["value"], 1 if event["kind"] == "price" else 0)


def response(request: Json, method: str, path: str) -> Json:
    if request["method"] != method or request["path"] != path or request["status"] != 200:
        raise ValueError("Event HTTP scope/status mismatch")
    value: Json = request["response"]
    return value


def catalog_value(request: Json, binding: Json, event: Json) -> Json:
    vid = binding["suppliers"][event["supplier"]]["variants"][event["item"]]
    url = urlsplit(request["path"])
    query = parse_qs(url.query)
    if (
        url.scheme
        or url.netloc
        or url.path != "/store/products"
        or query.get("region_id") != [binding["region_id"]]
        or query.get("variants[id][]") != [vid]
    ):
        raise ValueError("Event catalog scope mismatch")
    data = response(request, "GET", request["path"])
    variants = [v for p in data["products"] for v in p["variants"]]
    if len(variants) != 1 or variants[0]["id"] != vid:
        raise ValueError("Event variant missing or duplicated")
    value = variants[0]
    if (
        value["manage_inventory"] is not True
        or value["allow_backorder"] is not False
        or value["calculated_price"]["currency_code"] != "usd"
    ):
        raise ValueError("Event catalog inventory/currency mismatch")
    return {
        "price": number(value["calculated_price"]["calculated_amount"]),
        "stock": number(value["inventory_quantity"]),
    }


def verify_receipt(receipt: Json, event: Json, binding: Json) -> Json:
    if receipt["event"] != event or receipt["state"] != "OBSERVED":
        raise ValueError("Event was not observed")
    begin, end = receipt["before"], receipt["after"]
    for snapshot in (begin, end):
        if (
            snapshot["run_id"] != binding["run_id"]
            or snapshot["clock_mode"] != "operating-one-second-ticks"
            or snapshot["goal"] != binding["goal"]
        ):
            raise ValueError("Event clock/run mismatch")
        integer(snapshot["tick"])
    if (
        not event["at_tick"]
        <= begin["tick"]
        <= end["tick"]
        <= event["at_tick"] + event["max_lateness_ticks"]
    ):
        raise ValueError("Event applied outside declared window")
    before = catalog_value(receipt["catalog_before"], binding, event)
    after = catalog_value(receipt["catalog_after"], binding, event)
    kind = event["kind"]
    if before[kind] == event["value"] or after[kind] != event["value"]:
        raise ValueError("Declared event did not change the observed value")
    # Bind the admin mutation target to the buyer-visible variant via an independent GET.
    vid = binding["suppliers"][event["supplier"]]["variants"][event["item"]]
    link_get = receipt["variant_get"]
    url = urlsplit(link_get["path"])
    variant = response(link_get, "GET", link_get["path"])["variant"]
    pid = variant["product_id"]
    if (
        url.scheme
        or url.netloc
        or url.path != f"/admin/products/{pid}/variants/{vid}"
        or variant["id"] != vid
    ):
        raise ValueError("Event admin variant mapping mismatch")
    mutation = receipt["mutation"]
    if kind == "price":
        path = f"/admin/products/{pid}/variants/{vid}"
        expected = {"prices": [{"currency_code": "usd", "amount": event["value"]}]}
        response(mutation, "POST", path)
    else:
        links = variant["inventory_items"]
        if len(links) != 1 or number(links[0]["required_quantity"]) != 1:
            raise ValueError("Event inventory mapping is not one-to-one")
        iid = links[0]["inventory_item_id"]
        rows = []
        for name in ("stock_before", "stock_after"):
            levels = response(
                receipt[name], "GET", f"/admin/inventory-items/{iid}/location-levels"
            )["inventory_levels"]
            if (
                len(levels) != 1
                or levels[0]["inventory_item_id"] != iid
                or number(levels[0]["reserved_quantity"]) != 0
            ):
                raise ValueError("Event stock scope/reservation mismatch")
            rows.append(levels[0])
        first, last = rows
        if (
            first["location_id"] != last["location_id"]
            or number(first["stocked_quantity"]) != before["stock"]
            or number(last["stocked_quantity"]) != after["stock"]
        ):
            raise ValueError("Event stock GET and buyer observation differ")
        path = f"/admin/inventory-items/{iid}/location-levels/{first['location_id']}"
        expected = {"stocked_quantity": event["value"]}
        response(mutation, "POST", path)
    if mutation["request"] != expected:
        raise ValueError("Event mutation differs from declaration")
    return {
        "id": event["id"],
        "begin_tick": begin["tick"],
        "end_tick": end["tick"],
        "before": before,
        "after": after,
    }


def verify_events(
    artifact: Json, case: Json, binding: Json, initial_tick: int, final_tick: int
) -> Json:
    validate_case(case)
    events = case.get("events", [])
    if (
        not events
        or artifact["schema"] != "rehearsal-timed-condition-events-v1"
        or artifact["case_sha256"] != fingerprint(case)
        or artifact["run_id"] != binding["run_id"]
    ):
        raise ValueError("Event evidence declaration/run mismatch")
    if initial_tick >= events[0]["at_tick"]:
        raise ValueError("Initial observation followed the first declared event")
    receipts = artifact["receipts"]
    if set(receipts) != {e["id"] for e in events}:
        raise ValueError("Event denominator changed")
    verified = []
    for event in events:
        receipt = receipts[event["id"]]
        if receipt["event"] != event:
            raise ValueError("Event declaration changed")
        if receipt["state"] == "OBSERVED":
            if event["kind"] in {"delivery_notification", "notification_replay"}:
                from rehearsal.evaluation.notification_conditions import verify_notification_event

                result = verify_notification_event(receipt, event, binding, artifact)
                if result is None:
                    continue
            elif event["kind"] == "payment_response_delay":
                from rehearsal.evaluation.response_conditions import verify_response_event

                result = verify_response_event(
                    receipt, event, binding, artifact.get("response_faults", [])
                )
                if result is None:
                    continue
            else:
                result = verify_receipt(receipt, event, binding)
            if result["end_tick"] > final_tick:
                raise ValueError("Event observation followed final export")
            verified.append(result)
        elif receipt["state"] not in {"NOT_RUN", "CLAIMED", "UNKNOWN", "MISSED"}:
            raise ValueError("Invalid event state")
    return {
        "status": "VERIFIED" if len(verified) == len(events) else "INCOMPLETE",
        "scope": "timed-provider-change-observations-not-atomic-isolation",
        "planned": len(events),
        "observed": len(verified),
        "events": verified,
        "model_efficacy_verified": False,
    }
