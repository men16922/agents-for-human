"""Atomic scheduled notification admission, enqueue association and publication audit."""

from __future__ import annotations

import json
import sqlite3

from rehearsal.world.storage import ContractError, Json, canonical, row

SCHEMA = """
CREATE TABLE IF NOT EXISTS notification_schedules (
 run_id TEXT NOT NULL, schedule_id TEXT NOT NULL, kind TEXT NOT NULL,
 delay_ms INTEGER NOT NULL, copies INTEGER NOT NULL, source_schedule TEXT,
 armed_tick INTEGER NOT NULL, armed_at REAL NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('ARMED','CONSUMED')),
 observation_id TEXT, observation_data TEXT, previous_data TEXT, consumed_at REAL,
 PRIMARY KEY(run_id,schedule_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_armed_notification
 ON notification_schedules(run_id) WHERE state='ARMED' AND kind='delivery_notification';
CREATE TABLE IF NOT EXISTS scheduled_deliveries (
 run_id TEXT NOT NULL, schedule_id TEXT NOT NULL, seq INTEGER PRIMARY KEY,
 observation_id TEXT NOT NULL, due_at REAL NOT NULL, cursor INTEGER, published_at REAL,
 FOREIGN KEY(run_id,schedule_id) REFERENCES notification_schedules(run_id,schedule_id)
);
"""


def enqueue(
    db: sqlite3.Connection, schedule: Json, event: Json, now: float, previous: Json
) -> None:
    if db.execute("SELECT COUNT(*) FROM pending").fetchone()[0] + schedule["copies"] > 10000:
        raise ContractError("NOTIFICATION_QUEUE_FULL")
    due = now + schedule["delay_ms"] / 1000
    for _ in range(schedule["copies"]):
        seq = db.execute(
            "INSERT INTO pending(event_id,due_at) VALUES(?,?)", (event["event_id"], due)
        ).lastrowid
        db.execute(
            "INSERT INTO scheduled_deliveries VALUES(?,?,?,?,?,NULL,NULL)",
            (schedule["run_id"], schedule["schedule_id"], seq, event["event_id"], due),
        )
    db.execute(
        "UPDATE notification_schedules SET state='CONSUMED',observation_id=?,"
        "observation_data=?,previous_data=?,consumed_at=? WHERE run_id=? AND schedule_id=?",
        (
            event["event_id"],
            canonical(event),
            canonical(previous),
            now,
            schedule["run_id"],
            schedule["schedule_id"],
        ),
    )


def arm(
    db: sqlite3.Connection,
    run_id: str,
    schedule_id: str,
    kind: str,
    delay: int,
    copies: int,
    source: str | None,
    tick: int,
    now: float,
) -> Json:
    if not schedule_id.isascii() or not schedule_id.isalnum() or len(schedule_id) > 32:
        raise ContractError("INVALID_SCHEDULE_ID")
    if kind not in {"delivery_notification", "notification_replay"} or (
        kind == "notification_replay"
    ) != (source is not None):
        raise ContractError("INVALID_NOTIFICATION_SCHEDULE")
    if (
        db.execute(
            "SELECT COUNT(*) FROM notification_schedules WHERE run_id=?", (run_id,)
        ).fetchone()[0]
        >= 8
    ):
        raise ContractError("NOTIFICATION_SCHEDULE_LIMIT")
    if db.execute(
        "SELECT 1 FROM notification_schedules WHERE run_id=? AND schedule_id=?",
        (run_id, schedule_id),
    ).fetchone():
        raise ContractError("NOTIFICATION_SCHEDULE_ALREADY_ADMITTED")
    if kind == "delivery_notification" and (
        db.execute(
            "SELECT 1 FROM notification_schedules WHERE run_id=? AND state='ARMED'", (run_id,)
        ).fetchone()
        or db.execute("SELECT 1 FROM notification_faults WHERE run_id=?", (run_id,)).fetchone()
    ):
        raise ContractError("NOTIFICATION_FAULT_ALREADY_ARMED")
    original = None
    if source is not None:
        selected = row(
            db,
            "SELECT * FROM notification_schedules WHERE run_id=? AND schedule_id=?",
            (run_id, source),
        )
        copies_published = db.execute(
            "SELECT COUNT(*) FROM scheduled_deliveries WHERE run_id=? AND schedule_id=? "
            "AND cursor IS NOT NULL",
            (run_id, source),
        ).fetchone()[0]
        if (
            selected["kind"] != "delivery_notification"
            or selected["state"] != "CONSUMED"
            or copies_published != selected["copies"]
        ):
            raise ContractError("REPLAY_SOURCE_NOT_PUBLISHED")
        original = json.loads(selected["observation_data"])
    db.execute(
        "INSERT INTO notification_schedules VALUES(?,?,?,?,?,?,?,?,'ARMED',NULL,NULL,NULL,NULL)",
        (run_id, schedule_id, kind, delay, copies, source, tick, now),
    )
    if original:
        enqueue(
            db,
            {"run_id": run_id, "schedule_id": schedule_id, "delay_ms": delay, "copies": copies},
            original,
            now,
            json.loads(selected["previous_data"]),
        )
    return {"armed": True, "event_id": schedule_id}


def consume_delivery(
    db: sqlite3.Connection, run_id: str, event: Json, now: float, previous: Json
) -> bool:
    selected = db.execute(
        "SELECT * FROM notification_schedules WHERE run_id=? "
        "AND kind='delivery_notification' AND state='ARMED'",
        (run_id,),
    ).fetchone()
    if selected is None:
        return False
    enqueue(db, dict(selected), event, now, previous)
    return True
