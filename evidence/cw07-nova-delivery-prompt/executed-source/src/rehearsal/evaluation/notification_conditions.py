"""Independent scheduled-publication checks; publishing is not client receipt or model judgment."""

from __future__ import annotations

import json

from rehearsal.evaluation.condition_events import response
from rehearsal.evaluation.response_conditions import moment
from rehearsal.world.storage import Json, integer


def select(rows: list[Json], run_id: str, schedule_id: str) -> Json:
    values = [r for r in rows if r["run_id"] == run_id and r["schedule_id"] == schedule_id]
    if len(values) != 1:
        raise ValueError("Notification schedule missing or duplicated")
    return values[0]


def publications(rows: list[Json], schedule: Json) -> list[Json]:
    values = [
        r
        for r in rows
        if r["run_id"] == schedule["run_id"] and r["schedule_id"] == schedule["schedule_id"]
    ]
    if len(values) != schedule["copies"] or len({integer(r["seq"], 1) for r in values}) != len(
        values
    ):
        raise ValueError("Notification copy denominator changed")
    for value in values:
        if (
            value["observation_id"] != schedule["observation_id"]
            or abs(
                moment(value["due_at"])
                - (moment(schedule["consumed_at"]) + schedule["delay_ms"] / 1000)
            )
            > 1e-6
        ):
            raise ValueError("Notification queue mapping/delay mismatch")
        if (value["cursor"] is None) != (value["published_at"] is None):
            raise ValueError("Partial notification publication record")
        if value["cursor"] is not None and (
            integer(value["cursor"], 1) < 1 or moment(value["published_at"]) < value["due_at"]
        ):
            raise ValueError("Notification published before declared delay")
    delivered = [r for r in values if r["cursor"] is not None]
    if len({r["cursor"] for r in delivered}) != len(delivered):
        raise ValueError("Duplicate publication cursor")
    return delivered


def verify_notification_event(
    receipt: Json, event: Json, binding: Json, artifact: Json
) -> Json | None:
    before, after = receipt["before"], receipt["after"]
    run_id = binding["run_id"]
    for snapshot in (before, after):
        if (
            snapshot["run_id"] != run_id
            or snapshot["goal"] != binding["goal"]
            or snapshot["clock_mode"] != "operating-one-second-ticks"
        ):
            raise ValueError("Notification schedule clock/run mismatch")
        integer(snapshot["tick"])
    if (
        not event["at_tick"]
        <= before["tick"]
        <= after["tick"]
        <= event["at_tick"] + event["max_lateness_ticks"]
    ):
        raise ValueError("Notification schedule armed outside declared window")
    arm = receipt["mutation"]
    payload = {
        "event_id": event["id"],
        "kind": event["kind"],
        "delay_ms": event["delay_ms"],
        "copies": event["copies"],
    }
    if event["kind"] == "notification_replay":
        payload["source_event"] = event["source_event"]
    if arm["request"] != payload or response(
        arm, "POST", f"/admin/runs/{run_id}/faults/scheduled-notification"
    ) != {"armed": True, "event_id": event["id"]}:
        raise ValueError("Notification arm differs from declaration")
    schedules = artifact["notification_schedules"]
    rows = artifact["scheduled_deliveries"]
    schedule = select(schedules, run_id, event["id"])
    if (
        schedule["kind"] != event["kind"]
        or schedule["delay_ms"] != event["delay_ms"]
        or schedule["copies"] != event["copies"]
        or schedule["source_schedule"] != event.get("source_event")
        or not before["tick"] <= integer(schedule["armed_tick"]) <= after["tick"]
    ):
        raise ValueError("Notification journal differs from declaration")
    if schedule["state"] == "ARMED":
        return None
    if schedule["state"] != "CONSUMED" or moment(schedule["consumed_at"]) < moment(
        schedule["armed_at"]
    ):
        raise ValueError("Invalid notification consumption")
    observed = json.loads(schedule["observation_data"])
    previous = json.loads(schedule["previous_data"])
    if (
        observed["event_id"] != schedule["observation_id"]
        or observed["run_id"] != run_id
        or previous["run_id"] != run_id
        or observed["event_type"] != "delivery.observed"
        or observed["source"] != "medusa-customer-poll"
        or observed["version"] != previous["version"] + 1
    ):
        raise ValueError("Notification observation binding/version mismatch")
    for value in (observed, previous):
        if value["snapshot"]["goal"] != binding["goal"] or value["snapshot"]["run_id"] != run_id:
            raise ValueError("Notification snapshot goal/run mismatch")
        for quantity in value["snapshot"]["inventory"].values():
            integer(quantity)
    if moment(previous["observed_at"]) > moment(observed["observed_at"]) or not any(
        n > previous["snapshot"]["inventory"].get(k, 0)
        for k, n in observed["snapshot"]["inventory"].items()
    ):
        raise ValueError("Notification is not an observed inventory increase")
    published = publications(rows, schedule)
    if len(published) != event["copies"]:
        return None
    if event["kind"] == "delivery_notification":
        if (
            observed["observed_at"] != schedule["consumed_at"]
            or observed["observed_at"] < schedule["armed_at"]
        ):
            raise ValueError("Delivery notification preceded its schedule")
    else:
        source = select(schedules, run_id, event["source_event"])
        original = publications(rows, source)
        if (
            source["kind"] != "delivery_notification"
            or len(original) != source["copies"]
            or source["observation_data"] != schedule["observation_data"]
            or source["previous_data"] != schedule["previous_data"]
            or max(r["published_at"] for r in original) > schedule["armed_at"]
            or min(r["cursor"] for r in published) <= max(r["cursor"] for r in original)
        ):
            raise ValueError("Replay is not after the same published source observation")
    anchor = moment(artifact["clock_started_at"])
    end = max(r["published_at"] for r in published)
    if anchor > schedule["armed_at"]:
        raise ValueError("Notification clock anchor follows admission")
    return {
        "id": event["id"],
        "kind": event["kind"],
        "begin_tick": before["tick"],
        "end_tick": int(end - anchor),
        "observation_id": observed["event_id"],
        "copies": len(published),
        "cursors": [r["cursor"] for r in published],
        "publication_only": True,
    }
