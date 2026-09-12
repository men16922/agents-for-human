"""A coherent, run-scoped state fork into an isolated pair of SQLite databases."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from . import World
from .storage import ContractError, Json, canonical, identifier

SHOP_TABLES = ("runs", "suppliers", "offers", "quotes", "orders", "receipts", "inventory", "events")
PAYMENT_TABLES = ("accounts", "intents", "events")


def _collect(db: sqlite3.Connection, tables: tuple[str, ...], run_id: str) -> dict[str, list[Json]]:
    actual = {
        r[0]
        for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if not r[0].startswith("sqlite_")
    }
    if actual != set(tables):
        raise ContractError("UNSUPPORTED_FORK_SCHEMA")
    return {
        table: [
            dict(row)
            for row in db.execute(
                f"SELECT * FROM {table} WHERE {'id' if table == 'runs' else 'run_id'}=?", (run_id,)
            )
        ]
        for table in tables
    }


def fork_world(
    source: World,
    source_run_id: str,
    destination: Path,
    child_run_id: str,
    policy_version: str,
) -> tuple[World, Json]:
    """Freeze both source stores briefly, then copy only one run and its history.

    Business IDs are retained within the new isolated database pair. Event IDs are
    regenerated (including consumer receipts) so external streams cannot confuse
    parent and child events. The caller must not merge child DBs into the parent.
    """
    if not child_run_id or child_run_id == source_run_id or not policy_version:
        raise ContractError("INVALID_FORK_IDENTITY")
    if destination.exists():
        raise ContractError("FORK_DESTINATION_EXISTS")
    # Every world operation holds at most one storage transaction at a time.
    # Fixed shop -> payments order therefore takes a coherent cut without a cycle.
    with source.shop.transaction() as shop_db, source.payments.transaction() as payment_db:
        shop = _collect(shop_db, SHOP_TABLES, source_run_id)
        payments = _collect(payment_db, PAYMENT_TABLES, source_run_id)
        if len(shop["runs"]) != 1 or len(payments["accounts"]) != 1:
            raise ContractError("FORK_SOURCE_NOT_FOUND")
    # Sources are unlocked before destination writes; all copied data is in memory.
    fingerprint = hashlib.sha256(
        canonical({"shop": shop, "payments": payments}).encode()
    ).hexdigest()
    parent_metadata = json.loads(shop["runs"][0]["metadata"])
    metadata = parent_metadata | {
        "run_id": child_run_id,
        "environment": "practice",
        "policy_version": policy_version,
        "fork_parent_run_id": source_run_id,
        "fork_snapshot_sha256": fingerprint,
        "fork_tick": shop["runs"][0]["tick"],
    }
    event_ids = {
        e["event_id"]: identifier("evt") for dataset in (shop, payments) for e in dataset["events"]
    }

    def remap(table: str, record: Json) -> Json:
        result = dict(record)
        if table == "runs":
            result["id"] = child_run_id
        else:
            result["run_id"] = child_run_id
        if table in {"runs", "accounts"}:
            result["metadata"] = canonical(metadata)
        if table == "quotes":
            result["data"] = canonical(json.loads(result["data"]) | {"run_id": child_run_id})
        if table == "events":
            result["event_id"] = event_ids[record["event_id"]]
            if result["aggregate_id"] == source_run_id:
                result["aggregate_id"] = child_run_id
            payload = json.loads(result["payload"])
            if payload.get("run_id") == source_run_id:
                payload["run_id"] = child_run_id
            if result["event_type"] == "run.created":
                payload.update(metadata)
            result["payload"] = canonical(payload)
        if table == "receipts":
            if record["event_id"] not in event_ids:
                raise ContractError("FORK_ORPHAN_RECEIPT")
            result["event_id"] = event_ids[record["event_id"]]
        return result

    transformed = [
        {table: [remap(table, record) for record in records] for table, records in dataset.items()}
        for dataset in (shop, payments)
    ]
    destination.mkdir(parents=True, exist_ok=False)
    # Incomplete forks keep a manifest and never return a usable World.
    manifest: Json = {
        "parent_run_id": source_run_id,
        "child_run_id": child_run_id,
        "snapshot_sha256": fingerprint,
        "tick": metadata["fork_tick"],
        "policy_version": policy_version,
        "status": "CREATING",
        "history_mode": "inherited_snapshot",
        "inherited_event_ids": {child: parent for parent, child in event_ids.items()},
    }
    child = World(destination)
    manifest_path = destination / "fork.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    for store, dataset in zip((child.shop, child.payments), transformed):
        with store.transaction() as db:
            for table, records in dataset.items():
                for record in records:
                    columns = ",".join(record)
                    placeholders = ",".join("?" for _ in record)
                    values: tuple[Any, ...] = tuple(record.values())
                    db.execute(f"INSERT INTO {table}({columns}) VALUES({placeholders})", values)
    manifest["status"] = "READY"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return child, manifest
