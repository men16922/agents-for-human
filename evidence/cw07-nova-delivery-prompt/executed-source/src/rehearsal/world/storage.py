"""SQLite primitives shared by storage, not by the independent verifier."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

Json = dict[str, Any]


class ContractError(ValueError):
    """A rejected request with a stable, machine-readable reason."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def integer(value: int, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ContractError("INVALID_INTEGER")
    return value


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def row(db: sqlite3.Connection, sql: str, args: tuple[object, ...]) -> Json:
    result = db.execute(sql, args).fetchone()
    if result is None:
        raise ContractError("NOT_FOUND")
    return dict(result)


EVENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL, source TEXT NOT NULL, aggregate_id TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL, occurred_tick INTEGER NOT NULL,
    event_type TEXT NOT NULL, payload TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path, schema: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript(schema + EVENT_SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def events(self, run_id: str, after: int = 0) -> list[Json]:
        integer(after)
        with self.connect() as db:
            values = db.execute(
                "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after)
            ).fetchall()
        return [dict(v) | {"payload": json.loads(v["payload"])} for v in values]


def emit(
    db: sqlite3.Connection,
    run_id: str,
    source: str,
    aggregate: str,
    version: int,
    tick: int,
    kind: str,
    payload: Json,
) -> None:
    db.execute(
        "INSERT INTO events(event_id,run_id,source,aggregate_id,aggregate_version,"
        "occurred_tick,event_type,payload) VALUES(?,?,?,?,?,?,?,?)",
        (identifier("evt"), run_id, source, aggregate, version, tick, kind, canonical(payload)),
    )
