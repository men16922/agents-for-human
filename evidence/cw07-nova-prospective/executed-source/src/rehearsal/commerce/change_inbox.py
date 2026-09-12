"""One pending semantic change over a durable public observation cursor."""

from __future__ import annotations

import threading
from collections.abc import Callable
from copy import deepcopy

from rehearsal.commerce.observations import Projection, public_snapshot
from rehearsal.world.storage import ContractError, Json, canonical, integer


def meaning(snapshot: Json) -> str:
    value = {k: v for k, v in snapshot.items() if k != "tick"}
    # Collection order is not a purchasing condition. Preserve every validated field.
    value = deepcopy(value)
    value["suppliers"] = sorted(value["suppliers"])
    if "commerce" in value:
        detail = value["commerce"]
        detail["catalog"]["offers"].sort(key=lambda r: (r["supplier"], r["item"]))
        detail["orders"]["items"].sort(key=lambda r: r["id"])
    return canonical(value)


class ChangeInbox:
    def __init__(self, run_id: str, checked: Callable[[Json], Json]):
        self.projection = Projection(run_id)
        self.checked = checked
        self.lock = threading.RLock()
        self.changed = threading.Event()
        self.basis: str | None = None
        self.latest: Json | None = None
        self.generation = 0
        self.acknowledged = 0
        self.error: str | None = None
        self.counts = dict(applied=0, duplicate=0, old=0, reset=0, coalesced=0)

    def validate(self, value: Json) -> Json:
        return self.checked(public_snapshot(self.projection.run_id, value))

    def _latest(self) -> None:
        value = self.projection.snapshot
        if value is None:
            return
        self.latest = deepcopy(value)
        self.generation += 1
        if meaning(value) != self.basis:
            if self.changed.is_set():
                self.counts["coalesced"] += 1
            self.changed.set()
        else:
            self.changed.clear()

    def ingest(self, batch: Json) -> None:
        with self.lock:
            if batch["run_id"] != self.projection.run_id:
                raise ContractError("RUN_SCOPE_DENIED")
            if batch["reset"]:
                if batch["snapshot_event"] is not None:
                    self.validate(batch["snapshot_event"]["snapshot"])
                self.projection.reset(batch)
                self.counts["reset"] += 1
                self._latest()
            else:
                # Validate the whole response before accepting any cursor progress.
                for row in batch["events"]:
                    self.validate(row["event"]["snapshot"])
                    integer(row["cursor"], 1)
                for row in batch["events"]:
                    result = self.projection.apply(row)
                    self.counts[result] += 1
                    if result == "applied":
                        self._latest()
                if batch["next_cursor"] != self.projection.cursor:
                    raise ContractError("OBSERVATION_CURSOR_MISMATCH")
            self.error = "OBSERVATION_STALE" if batch["stale"] else None

    def capture(self) -> int:
        with self.lock:
            return self.generation

    def acknowledge(self, snapshot: Json, captured: int) -> None:
        with self.lock:
            self.basis = meaning(self.validate(snapshot))
            self.acknowledged = captured
            # An event arriving during the fresh HTTP read must survive this acknowledgement.
            if self.generation <= captured or (
                self.latest is not None and meaning(self.latest) == self.basis
            ):
                self.changed.clear()
            else:
                self.changed.set()

    def cursor(self) -> int:
        with self.lock:
            return self.projection.cursor

    def report(self) -> Json:
        with self.lock:
            return {
                "cursor": self.projection.cursor,
                "version": self.projection.version,
                "generation": self.generation,
                "acknowledged": self.acknowledged,
                "pending": self.changed.is_set(),
                "error": self.error,
                "counts": dict(self.counts),
            }
