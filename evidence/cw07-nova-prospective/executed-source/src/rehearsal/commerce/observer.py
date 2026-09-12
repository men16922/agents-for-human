"""Customer-only polling and independent notification publication."""

import asyncio
import time
from collections.abc import Callable, Iterator

from rehearsal.world.storage import Json, canonical, identifier

from .gateway import MedusaGateway
from .observations import ObservationJournal


async def finish_thread(function: Callable[[], None]) -> None:
    task = asyncio.create_task(asyncio.to_thread(function))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task  # Do not close shared HTTP clients or release process locks mid-request.
        raise


class Observer:
    def __init__(self, journal: ObservationJournal, backends: dict[str, MedusaGateway]):
        self.journal, self.backends = journal, backends
        self.publication_error: str | None = None
        self.process_id = identifier("observer")
        self.poll_stats: dict[str, Json] = {
            run: {
                "process_id": self.process_id,
                "attempted": 0,
                "completed": 0,
                "failed": 0,
                "unchanged": 0,
                "in_flight": False,
            }
            for run in backends
        }

    def poll(self, run_id: str) -> None:
        before = self.poll_stats[run_id]
        self.poll_stats[run_id] = before | {"attempted": before["attempted"] + 1, "in_flight": True}
        started_at, started_mono = time.time(), time.monotonic()
        try:
            snapshot = self.backends[run_id].observe_world(include_details=True)
            event = self.journal.record(
                run_id,
                snapshot,
                time.time(),
                poll_started_at=started_at,
                poll_elapsed_seconds=time.monotonic() - started_mono,
            )
            stats = self.poll_stats[run_id]
            self.poll_stats[run_id] = stats | {
                "completed": stats["completed"] + 1,
                "unchanged": stats["unchanged"] + (event is None),
                "in_flight": False,
            }
        except Exception:
            stats = self.poll_stats[run_id]
            self.poll_stats[run_id] = stats | {"failed": stats["failed"] + 1, "in_flight": False}
            self.journal.failed(run_id)

    def publish(self) -> None:
        try:
            self.journal.publish(time.time())
            self.publication_error = None
        except Exception:
            self.publication_error = "NOTIFICATION_PUBLICATION_UNAVAILABLE"

    async def poll_loop(self, run_id: str) -> None:
        while True:
            await finish_thread(lambda: self.poll(run_id))
            await asyncio.sleep(1)

    async def publish_loop(self) -> None:
        while True:
            await finish_thread(self.publish)
            await asyncio.sleep(0.2)

    async def serve(self) -> None:
        async with asyncio.TaskGroup() as group:
            for run_id in self.backends:
                group.create_task(self.poll_loop(run_id))
            group.create_task(self.publish_loop())

    def read(self, run_id: str, after: int, limit: int = 100) -> Json:
        batch = self.journal.read(run_id, after, time.time(), limit)
        batch["poll_stats"] = dict(self.poll_stats[run_id])
        batch["publication_error"] = self.publication_error
        batch["stale"] = batch["stale"] or self.publication_error is not None
        return batch


def sse_frames(batch: Json) -> Iterator[str]:
    if batch["reset"]:
        yield f"id: {batch['next_cursor']}\nevent: snapshot\ndata: {canonical(batch)}\n\n"
    else:
        for delivery in batch["events"]:
            yield f"id: {delivery['cursor']}\nevent: observation\ndata: {canonical(delivery)}\n\n"
    # Freshness must still be sent when there are no events or the upstream is unavailable.
    status = {k: v for k, v in batch.items() if k not in {"events", "snapshot_event"}}
    yield f"event: status\ndata: {canonical(status)}\n\n"
