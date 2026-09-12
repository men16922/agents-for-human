"""Recheck server delay receipts and client timeout observations from sealed raw artifacts."""

from __future__ import annotations

import math

from rehearsal.evaluation.condition_events import response
from rehearsal.world.storage import Json, integer


def moment(value: float) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid fault timestamp")
    return value


def verify_response_event(
    receipt: Json, event: Json, binding: Json, rows: list[Json]
) -> Json | None:
    before, after = receipt["before"], receipt["after"]
    for snapshot in (before, after):
        if (
            snapshot["run_id"] != binding["run_id"]
            or snapshot["goal"] != binding["goal"]
            or snapshot["clock_mode"] != "operating-one-second-ticks"
        ):
            raise ValueError("Response event clock/run mismatch")
        integer(snapshot["tick"])
    if (
        not event["at_tick"]
        <= before["tick"]
        <= after["tick"]
        <= event["at_tick"] + event["max_lateness_ticks"]
    ):
        raise ValueError("Response event armed outside declared window")
    arm = receipt["mutation"]
    payload = {"event_id": event["id"], "delay_ms": event["delay_ms"]}
    if (
        response(arm, "POST", f"/admin/runs/{binding['run_id']}/faults/scheduled-payment-response")
        != {"armed": True, "event_id": event["id"]}
        or arm["request"] != payload
    ):
        raise ValueError("Response event arm contract mismatch")
    selected = [
        r for r in rows if r["run_id"] == binding["run_id"] and r["event_id"] == event["id"]
    ]
    if len(selected) != 1:
        raise ValueError("Response event journal missing or duplicated")
    row = selected[0]
    if (
        row["delay_ms"] != event["delay_ms"]
        or not before["tick"] <= integer(row["armed_tick"]) <= after["tick"]
    ):
        raise ValueError("Response event journal differs from declaration")
    if row["state"] in {"ARMED", "CONSUMED", "INTERRUPTED"}:
        return None
    if (
        row["state"] != "FINISHED"
        or not row["order_id"]
        or row["response_status"] not in {"RESERVED", "SETTLED", "UNKNOWN"}
    ):
        raise ValueError("Invalid response delay completion")
    if (
        not moment(row["armed_at"]) <= moment(row["consumed_at"]) <= moment(row["finished_at"])
        or (row["finished_at"] - row["consumed_at"]) * 1000 + 0.001 < event["delay_ms"]
    ):
        raise ValueError("Declared response delay not observed")
    if not row["armed_tick"] <= integer(row["consumed_tick"]) <= integer(row["finished_tick"]):
        raise ValueError("Response event clock reversed")
    return {
        "id": event["id"],
        "kind": "payment_response_delay",
        "begin_tick": before["tick"],
        "end_tick": row["finished_tick"],
        "order_id": row["order_id"],
        "consumed_at": row["consumed_at"],
        "finished_at": row["finished_at"],
    }


def timeout_observed(event: Json, run_id: str, observations: list[Json]) -> bool:
    matches = [
        r
        for r in observations
        if r.get("run_id") == run_id
        and r.get("order_id") == event["order_id"]
        and r.get("method") == "POST"
        and r.get("path") == "payments"
    ]
    return (
        len(matches) == 1
        and matches[0].get("error_type") == "ReadTimeout"
        and moment(matches[0]["started_at"])
        <= event["consumed_at"]
        <= moment(matches[0]["finished_at"])
        < event["finished_at"]
    )
