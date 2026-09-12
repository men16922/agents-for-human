"""Single-use scheduled response delay evidence, independent of purchase/model output."""

from __future__ import annotations

from pathlib import Path

from rehearsal.world.storage import ContractError, Database, Json, integer

SCHEMA = """
CREATE TABLE IF NOT EXISTS response_faults (
 run_id TEXT NOT NULL, event_id TEXT NOT NULL, delay_ms INTEGER NOT NULL,
 armed_tick INTEGER NOT NULL, armed_at REAL NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('ARMED','CONSUMED','FINISHED','INTERRUPTED')),
 order_id TEXT, response_status TEXT, consumed_at REAL, finished_at REAL,
 consumed_tick INTEGER, finished_tick INTEGER,
 PRIMARY KEY(run_id,event_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_armed_response ON response_faults(run_id) WHERE state='ARMED';
"""


class ResponseFaults:
    def __init__(self, path: Path):
        self.db = Database(path, SCHEMA)

    def arm(self, run_id: str, event_id: str, delay_ms: int, tick: int, now: float) -> Json:
        if not event_id.isascii() or not event_id.isalnum() or len(event_id) > 32:
            raise ContractError("INVALID_FAULT_ID")
        if integer(delay_ms, 1) > 5000:
            raise ContractError("INVALID_RESPONSE_DELAY")
        integer(tick)
        with self.db.transaction() as db:
            if db.execute(
                "SELECT 1 FROM response_faults WHERE run_id=? AND (event_id=? OR state='ARMED')",
                (run_id, event_id),
            ).fetchone():
                raise ContractError("RESPONSE_FAULT_ALREADY_ADMITTED")
            db.execute(
                "INSERT INTO response_faults VALUES(?,?,?,?,?,'ARMED',"
                "NULL,NULL,NULL,NULL,NULL,NULL)",
                (run_id, event_id, delay_ms, tick, now),
            )
        return {"armed": True, "event_id": event_id}

    def consume(
        self, run_id: str, order_id: str, status: str, now: float, tick: int
    ) -> Json | None:
        with self.db.transaction() as db:
            row = db.execute(
                "SELECT * FROM response_faults WHERE run_id=? AND state='ARMED'", (run_id,)
            ).fetchone()
            if row is None:
                return None
            value = dict(row)
            db.execute(
                "UPDATE response_faults SET state='CONSUMED',order_id=?,response_status=?,"
                "consumed_at=?,consumed_tick=? WHERE run_id=? AND event_id=?",
                (order_id, status, now, tick, run_id, value["event_id"]),
            )
            return value

    def finish(
        self, run_id: str, event_id: str, now: float, tick: int, *, interrupted: bool = False
    ) -> None:
        with self.db.transaction() as db:
            db.execute(
                "UPDATE response_faults SET state=?,finished_at=?,finished_tick=? "
                "WHERE run_id=? AND event_id=? AND state='CONSUMED'",
                ("INTERRUPTED" if interrupted else "FINISHED", now, tick, run_id, event_id),
            )
