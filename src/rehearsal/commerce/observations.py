"""Durable, read-model notifications. Delivery never commands the commerce ledger."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

from rehearsal.commerce import notification_schedule
from rehearsal.commerce.details import public_details
from rehearsal.world.storage import (
    ContractError,
    Database,
    Json,
    canonical,
    identifier,
    integer,
    row,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS heads (
    run_id TEXT PRIMARY KEY, version INTEGER NOT NULL DEFAULT 0,
    cursor INTEGER NOT NULL DEFAULT 0, floor INTEGER NOT NULL DEFAULT 0,
    last_poll REAL, error TEXT
);
CREATE TABLE IF NOT EXISTS observations (
    event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES heads(run_id),
    version INTEGER NOT NULL, data TEXT NOT NULL, UNIQUE(run_id,version)
);
CREATE TABLE IF NOT EXISTS pending (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES observations(event_id), due_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deliveries (
    run_id TEXT NOT NULL REFERENCES heads(run_id), cursor INTEGER NOT NULL,
    event_id TEXT NOT NULL REFERENCES observations(event_id), published_at REAL NOT NULL,
    PRIMARY KEY(run_id,cursor)
);
CREATE TABLE IF NOT EXISTS notification_faults (
    run_id TEXT PRIMARY KEY REFERENCES heads(run_id), delay_ms INTEGER NOT NULL,
    copies INTEGER NOT NULL
);
"""


def timestamp(value: float) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ContractError("INVALID_TIMESTAMP")
    return value


def public_snapshot(run_id: str, value: Json) -> Json:
    """Select only the public gateway contract, never credentials or fault controls."""
    if value.get("run_id") != run_id:
        raise ContractError("RUN_SCOPE_DENIED")
    keys = ("run_id", "goal", "tick", "clock_mode", "inventory", "balance", "suppliers")
    try:
        result: Json = json.loads(canonical({k: value[k] for k in keys}))
        if "commerce" in value:
            result["commerce"] = public_details(value["commerce"], result)
        integer(result["tick"])
        for quantity in result["inventory"].values():
            integer(quantity)
        for key in ("budget", "spent", "reserved", "available"):
            integer(result["balance"][key])
    except (KeyError, TypeError, AttributeError) as exc:
        raise ContractError("INVALID_SNAPSHOT") from exc
    return result


class ObservationJournal:
    def __init__(self, path: Path, runs: list[str], retention: int = 1000):
        self.retention = integer(retention, 1)
        self.db = Database(path, SCHEMA + notification_schedule.SCHEMA)
        with self.db.transaction() as db:
            for run_id in runs:
                db.execute("INSERT OR IGNORE INTO heads(run_id) VALUES(?)", (run_id,))

    def _head(self, db: sqlite3.Connection, run_id: str) -> Json:
        return row(db, "SELECT * FROM heads WHERE run_id=?", (run_id,))

    def _latest(self, db: sqlite3.Connection, head: Json) -> Json | None:
        if not head["version"]:
            return None
        value = row(
            db,
            "SELECT data FROM observations WHERE run_id=? AND version=?",
            (head["run_id"], head["version"]),
        )
        event: Json = json.loads(value["data"])
        return event

    def record(
        self,
        run_id: str,
        snapshot: Json,
        now: float,
        *,
        poll_started_at: float | None = None,
        poll_elapsed_seconds: float | None = None,
    ) -> Json | None:
        snapshot = public_snapshot(run_id, snapshot)
        timestamp(now)
        if (poll_started_at is None) != (poll_elapsed_seconds is None):
            raise ContractError("INCOMPLETE_POLL_TIMING")
        if poll_started_at is not None and poll_elapsed_seconds is not None:
            timestamp(poll_started_at)
            timestamp(poll_elapsed_seconds)
        with self.db.transaction() as db:
            head = self._head(db, run_id)
            previous = self._latest(db, head)
            db.execute("UPDATE heads SET last_poll=?,error=NULL WHERE run_id=?", (now, run_id))
            if previous and previous["snapshot"] == snapshot:
                return None
            kind = "snapshot.observed"
            if previous:
                before = previous["snapshot"]
                if any(n > before["inventory"].get(k, 0) for k, n in snapshot["inventory"].items()):
                    kind = "delivery.observed"
                elif {k: v for k, v in before.items() if k != "tick"} == {
                    k: v for k, v in snapshot.items() if k != "tick"
                }:
                    kind = "clock.observed"
                else:
                    kind = "state.observed"
            event = {
                "event_id": identifier("obs"),
                "run_id": run_id,
                "version": head["version"] + 1,
                "observed_at": now,
                "source": "medusa-customer-poll",
                "event_type": kind,
                "snapshot": snapshot,
            }
            if poll_started_at is not None:
                event["poll_started_at"] = poll_started_at
                event["poll_elapsed_seconds"] = poll_elapsed_seconds
            db.execute(
                "INSERT INTO observations VALUES(?,?,?,?)",
                (
                    event["event_id"],
                    run_id,
                    event["version"],
                    canonical(event),
                ),
            )
            db.execute("UPDATE heads SET version=? WHERE run_id=?", (event["version"], run_id))
            if (
                previous is not None
                and kind == "delivery.observed"
                and notification_schedule.consume_delivery(db, run_id, event, now, previous)
            ):
                return event
            fault = (
                db.execute("SELECT * FROM notification_faults WHERE run_id=?", (run_id,)).fetchone()
                if kind == "delivery.observed"
                else None
            )
            delay, copies = (fault["delay_ms"], fault["copies"]) if fault else (0, 1)
            if fault:
                db.execute("DELETE FROM notification_faults WHERE run_id=?", (run_id,))
            self._enqueue(db, event["event_id"], now + delay / 1000, copies)
            return event

    @staticmethod
    def _enqueue(db: sqlite3.Connection, event_id: str, due: float, copies: int) -> None:
        db.executemany(
            "INSERT INTO pending(event_id,due_at) VALUES(?,?)", [(event_id, due)] * copies
        )

    def failed(self, run_id: str) -> None:
        # Do not store exception text: upstream errors may contain credentials or raw payloads.
        with self.db.transaction() as db:
            self._head(db, run_id)
            db.execute("UPDATE heads SET error='OBSERVATION_UNAVAILABLE' WHERE run_id=?", (run_id,))

    @staticmethod
    def _fault_values(delay_ms: int, copies: int) -> None:
        if integer(delay_ms) > 5000 or integer(copies, 1) > 3:
            raise ContractError("INVALID_NOTIFICATION_FAULT")

    def arm_scheduled(
        self,
        run_id: str,
        schedule_id: str,
        kind: str,
        delay_ms: int,
        copies: int,
        source_schedule: str | None,
        tick: int,
        now: float,
    ) -> Json:
        self._fault_values(delay_ms, copies)
        timestamp(now)
        integer(tick)
        with self.db.transaction() as db:
            self._head(db, run_id)
            return notification_schedule.arm(
                db, run_id, schedule_id, kind, delay_ms, copies, source_schedule, tick, now
            )

    def arm_delivery(self, run_id: str, delay_ms: int, copies: int) -> None:
        self._fault_values(delay_ms, copies)
        with self.db.transaction() as db:
            self._head(db, run_id)
            if db.execute(
                "SELECT 1 FROM notification_schedules WHERE run_id=? AND state='ARMED'", (run_id,)
            ).fetchone():
                raise ContractError("NOTIFICATION_FAULT_ALREADY_ARMED")
            db.execute(
                "INSERT INTO notification_faults VALUES(?,?,?) ON CONFLICT(run_id) "
                "DO UPDATE SET delay_ms=excluded.delay_ms,copies=excluded.copies",
                (run_id, delay_ms, copies),
            )

    def replay(
        self, run_id: str, event_id: str, now: float, delay_ms: int = 0, copies: int = 1
    ) -> None:
        self._fault_values(delay_ms, copies)
        timestamp(now)
        with self.db.transaction() as db:
            row(
                db,
                "SELECT event_id FROM observations WHERE run_id=? AND event_id=?",
                (run_id, event_id),
            )
            # Bound pending work even for repeated operator calls.
            if db.execute("SELECT COUNT(*) FROM pending").fetchone()[0] + copies > 10000:
                raise ContractError("NOTIFICATION_QUEUE_FULL")
            self._enqueue(db, event_id, now + delay_ms / 1000, copies)

    def publish(self, now: float) -> int:
        timestamp(now)
        with self.db.transaction() as db:
            ready = db.execute(
                "SELECT p.*,o.run_id FROM pending p JOIN observations o USING(event_id) "
                "WHERE due_at<=? ORDER BY due_at,seq LIMIT 1000",
                (now,),
            ).fetchall()
            for item in ready:
                db.execute("UPDATE heads SET cursor=cursor+1 WHERE run_id=?", (item["run_id"],))
                head = self._head(db, item["run_id"])
                db.execute(
                    "INSERT INTO deliveries VALUES(?,?,?,?)",
                    (
                        item["run_id"],
                        head["cursor"],
                        item["event_id"],
                        now,
                    ),
                )
                db.execute(
                    "UPDATE scheduled_deliveries SET cursor=?,published_at=? WHERE seq=?",
                    (head["cursor"], now, item["seq"]),
                )
                db.execute("DELETE FROM pending WHERE seq=?", (item["seq"],))
            for run_id in {item["run_id"] for item in ready}:
                head = self._head(db, run_id)
                floor = max(head["floor"], head["cursor"] - self.retention)
                db.execute("UPDATE heads SET floor=? WHERE run_id=?", (floor, run_id))
                db.execute("DELETE FROM deliveries WHERE run_id=? AND cursor<=?", (run_id, floor))
                db.execute(
                    "DELETE FROM observations WHERE run_id=? AND version<? "
                    "AND event_id NOT IN (SELECT event_id FROM pending) "
                    "AND event_id NOT IN (SELECT event_id FROM deliveries) "
                    "AND event_id NOT IN (SELECT observation_id FROM notification_schedules "
                    "WHERE observation_id IS NOT NULL)",
                    (run_id, head["version"]),
                )
            return len(ready)

    def read(self, run_id: str, after: int, now: float, limit: int = 100) -> Json:
        integer(after)
        if integer(limit, 1) > 100:
            raise ContractError("INVALID_LIMIT")
        timestamp(now)
        with self.db.transaction() as db:
            head = self._head(db, run_id)
            if after > head["cursor"]:
                raise ContractError("CURSOR_AHEAD")
            reset = after < head["floor"]
            latest = self._latest(db, head) if reset else None
            values = (
                []
                if reset
                else db.execute(
                    "SELECT d.cursor,d.published_at,o.data FROM deliveries d "
                    "JOIN observations o USING(event_id) WHERE d.run_id=? AND cursor>? "
                    "ORDER BY cursor LIMIT ?",
                    (run_id, after, limit),
                ).fetchall()
            )
            events = [
                dict(
                    cursor=v["cursor"], published_at=v["published_at"], event=json.loads(v["data"])
                )
                for v in values
            ]
            age = None if head["last_poll"] is None else now - head["last_poll"]
            return {
                "run_id": run_id,
                "events": events,
                "reset": reset,
                "snapshot_event": latest,
                "next_cursor": head["cursor"]
                if reset
                else (events[-1]["cursor"] if events else after),
                "current_cursor": head["cursor"],
                "retained_after": head["floor"],
                "last_poll": head["last_poll"],
                "age_seconds": age,
                "stale": bool(head["error"] or age is None or age < 0 or age >= 5),
                "error": head["error"],
            }


class Projection:
    """Reference consumer: full-state replacement, independent of arrival order."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.version = 0
        self.cursor = 0
        self.snapshot: Json | None = None
        self.seen: dict[str, str] = {}

    def apply(self, delivery: Json) -> str:
        cursor = integer(delivery["cursor"])
        event = delivery["event"]
        if event["run_id"] != self.run_id:
            raise ContractError("RUN_SCOPE_DENIED")
        snapshot = public_snapshot(self.run_id, event["snapshot"])
        version = integer(event["version"], 1)
        event_id, encoded = event["event_id"], canonical(event)
        if event_id in self.seen and self.seen[event_id] != encoded:
            raise ContractError("EVENT_CONTENT_CONFLICT")
        if version == self.version and snapshot != self.snapshot:
            raise ContractError("OBSERVATION_VERSION_CONFLICT")
        result = (
            "duplicate"
            if event_id in self.seen
            else "old"
            if version <= self.version
            else "applied"
        )
        self.seen[event_id] = encoded
        # Old versions remain harmless after fingerprint eviction: they cannot replace newer state.
        if len(self.seen) > 1000:
            del self.seen[next(iter(self.seen))]
        if version > self.version:
            self.version, self.snapshot = version, snapshot
        self.cursor = max(self.cursor, cursor)
        return result

    def reset(self, batch: Json) -> None:
        if batch["run_id"] != self.run_id or not batch["reset"]:
            raise ContractError("INVALID_SNAPSHOT_RESET")
        cursor = integer(batch["next_cursor"])
        if cursor < self.cursor:
            raise ContractError("CURSOR_REGRESSION")
        if batch["snapshot_event"] is not None:
            self.apply({"cursor": cursor, "event": batch["snapshot_event"]})
        self.cursor = cursor
