"""Notification failures must not change authoritative quantities or hide late events."""

import asyncio
import copy
import hashlib
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from rehearsal.commerce.observations import ObservationJournal, Projection
from rehearsal.commerce.observer import Observer, finish_thread, sse_frames
from rehearsal.commerce.server import create_app
from rehearsal.world.storage import ContractError


def snapshot(tick=0, quantity=0, run_id="one"):
    return {
        "run_id": run_id,
        "tick": tick,
        "clock_mode": "operating-one-second-ticks",
        "goal": {"items": {"tent": 3}, "deadline_tick": 60, "destination": "venue"},
        "inventory": {"tent": quantity},
        "balance": {
            "budget": 500,
            "spent": 190 if quantity else 0,
            "reserved": 0,
            "available": 310 if quantity else 500,
        },
        "suppliers": ["A", "B", "C"],
    }


def test_delayed_delivery_duplicate_and_old_replay_survive_restart(tmp_path):
    path = tmp_path / "notifications.sqlite3"
    journal = ObservationJournal(path, ["one"])
    initial = journal.record("one", snapshot(), 100)
    journal.publish(100)
    journal.arm_delivery("one", 2000, 2)
    delivered = journal.record("one", snapshot(1, 3), 101)
    newer = journal.record("one", snapshot(2, 3), 102)
    assert journal.publish(102) == 1
    projection = Projection("one")
    batch = journal.read("one", 0, 102)
    assert [v["event"]["version"] for v in batch["events"]] == [1, 3]
    assert all(projection.apply(d) == "applied" for d in batch["events"])
    assert projection.snapshot["inventory"] == {"tent": 3}
    journal = ObservationJournal(path, ["one"])
    assert journal.publish(103) == 2
    journal.replay("one", initial["event_id"], 104)
    journal.publish(104)
    reconnect = journal.read("one", projection.cursor, 104)
    assert [projection.apply(d) for d in reconnect["events"]] == ["old", "duplicate", "duplicate"]
    assert [d["cursor"] for d in reconnect["events"]] == [3, 4, 5]
    assert [d["event"]["event_id"] for d in reconnect["events"]] == [
        delivered["event_id"],
        delivered["event_id"],
        initial["event_id"],
    ]
    assert projection.version == newer["version"]
    assert projection.snapshot == snapshot(2, 3)
    assert projection.cursor == 5
    assert journal.read("one", 5, 104)["events"] == []


def test_retention_reset_latest_and_pending_event_is_not_deleted(tmp_path):
    journal = ObservationJournal(tmp_path / "n.db", ["one"], retention=2)
    journal.record("one", snapshot(), 100)
    journal.publish(100)
    journal.arm_delivery("one", 5000, 1)
    delayed = journal.record("one", snapshot(1, 3), 101)
    for tick in range(2, 6):
        journal.record("one", snapshot(tick, 3), 100 + tick)
        journal.publish(100 + tick)
    reset = journal.read("one", 1, 105)
    assert reset["reset"] and reset["events"] == []
    projection = Projection("one")
    projection.reset(reset)
    assert projection.snapshot == snapshot(5, 3)
    assert projection.cursor == 5
    assert journal.publish(106) == 1
    late = journal.read("one", 5, 106)["events"][0]
    assert late["event"]["event_id"] == delayed["event_id"]
    assert projection.apply(late) == "old"
    assert projection.snapshot["inventory"]["tent"] == 3
    with pytest.raises(ContractError, match="CURSOR_AHEAD"):
        journal.read("one", 99, 106)
    with pytest.raises(ContractError, match="CURSOR_REGRESSION"):
        projection.reset(reset)


def test_atomic_record_and_publication_roll_back_on_write_failure(tmp_path):
    journal = ObservationJournal(tmp_path / "n.db", ["one"])
    with journal.db.connect() as db:
        db.execute(
            "CREATE TRIGGER fail_pending BEFORE INSERT ON pending "
            "BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        journal.record("one", snapshot(), 100)
    with journal.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
        assert db.execute("SELECT version,last_poll FROM heads").fetchone()[:] == (0, None)
        db.execute("DROP TRIGGER fail_pending")
    journal.record("one", snapshot(), 100)
    with journal.db.connect() as db:
        db.execute(
            "CREATE TRIGGER fail_delivery BEFORE INSERT ON deliveries "
            "BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        journal.publish(100)
    assert journal.read("one", 0, 100)["current_cursor"] == 0
    with journal.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM pending").fetchone()[0] == 1
        db.execute("DROP TRIGGER fail_delivery")
    assert journal.publish(100) == 1
    assert journal.publish(100) == 0


def test_concurrent_publishers_allocate_once_and_cursors_are_per_run(tmp_path):
    journal = ObservationJournal(tmp_path / "n.db", ["one", "two"])
    first = journal.record("one", snapshot(), 100)
    journal.record("two", snapshot(run_id="two"), 100)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(journal.publish, [100] * 4)) == 2
    for run_id in ("one", "two"):
        batch = journal.read(run_id, 0, 100)
        assert batch["next_cursor"] == 1
        assert {d["event"]["run_id"] for d in batch["events"]} == {run_id}
    with pytest.raises(ContractError, match="NOT_FOUND"):
        journal.replay("two", first["event_id"], 101)
    with pytest.raises(ContractError, match="RUN_SCOPE_DENIED"):
        journal.record("two", snapshot(), 101)


def test_freshness_unchanged_poll_failure_and_clock_regression(tmp_path):
    journal = ObservationJournal(tmp_path / "n.db", ["one"])
    assert journal.read("one", 0, 100)["stale"]
    journal.record("one", snapshot() | {"store_token": "must-not-leak"}, 100)
    journal.publish(100)
    assert journal.record("one", snapshot(), 104) is None
    batch = journal.read("one", 0, 104)
    assert not batch["stale"] and "must-not-leak" not in json.dumps(batch)
    journal.failed("one")
    assert journal.read("one", 0, 104)["error"] == "OBSERVATION_UNAVAILABLE"
    assert journal.read("one", 0, 104)["stale"]
    journal.record("one", snapshot(), 105)
    assert not journal.read("one", 0, 106)["stale"]
    assert journal.read("one", 0, 104)["stale"]
    assert journal.read("one", 0, 110)["stale"]


def test_projection_rejects_cross_run_and_conflict_without_advancing(tmp_path):
    journal = ObservationJournal(tmp_path / "n.db", ["one"])
    journal.record("one", snapshot(), 100)
    journal.publish(100)
    delivery = journal.read("one", 0, 100)["events"][0]
    projection = Projection("one")
    assert projection.apply(delivery) == "applied"
    for field, value, code in (
        ("run_id", "two", "RUN_SCOPE_DENIED"),
        ("observed_at", 101, "EVENT_CONTENT_CONFLICT"),
    ):
        bad = copy.deepcopy(delivery)
        bad["event"][field], bad["cursor"] = value, 2
        with pytest.raises(ContractError, match=code):
            projection.apply(bad)
        assert projection.cursor == 1 and projection.snapshot == snapshot()
    bad = copy.deepcopy(delivery)
    bad["event"]["event_id"] = "another"
    bad["event"]["snapshot"]["inventory"]["tent"] = 9
    with pytest.raises(ContractError, match="OBSERVATION_VERSION_CONFLICT"):
        projection.apply(bad)


@pytest.mark.parametrize("delay,copies", [(-1, 1), (5001, 1), (0, 0), (0, 4), (True, 1)])
def test_fault_bounds(tmp_path, delay, copies):
    journal = ObservationJournal(tmp_path / "n.db", ["one"])
    with pytest.raises(ContractError):
        journal.arm_delivery("one", delay, copies)


class Backend:
    def __init__(self, run_id):
        self.value, self.fail, self.closed = snapshot(run_id=run_id), False, False
        self.store = self

    def close(self):
        self.closed = True

    def observe_world(self, *, include_details=False):
        if self.fail:
            raise RuntimeError("secret must not reach observer")
        return copy.deepcopy(self.value)


def test_observer_tracks_backend_without_buyer_calls_and_exposes_errors(tmp_path):
    journal = ObservationJournal(tmp_path / "n.db", ["one"])
    backend = Backend("one")
    observer = Observer(journal, {"one": backend})
    observer.poll("one")
    observer.publish()
    backend.value = snapshot(4, 3)
    observer.poll("one")
    observer.publish()
    events = observer.read("one", 0)["events"]
    assert events[-1]["event"]["event_type"] == "delivery.observed"
    backend.fail = True
    observer.poll("one")
    assert observer.read("one", 2)["stale"]
    assert "secret" not in json.dumps(observer.read("one", 2))
    with journal.db.connect() as db:
        db.execute(
            "CREATE TRIGGER fail_delivery BEFORE INSERT ON deliveries "
            "BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
    journal.replay("one", events[0]["event"]["event_id"], time.time())
    observer.publish()
    assert observer.read("one", 2)["publication_error"] == "NOTIFICATION_PUBLICATION_UNAVAILABLE"


@pytest.fixture
def http_setup(tmp_path):
    backends = {r: Backend(r) for r in ("one", "two")}
    config = {
        "directory": str(tmp_path),
        "runs": dict.fromkeys(backends, {}),
        "grants": {
            hashlib.sha256(token.encode()).hexdigest(): {"run_id": run_id, "role": role}
            for token, run_id, role in (
                ("buyer", "one", "buyer"),
                ("observer", "one", "observer"),
                ("control", "one", "control"),
                ("other", "two", "observer"),
            )
        },
    }
    app = create_app(config, backends, start_observer=False)
    with TestClient(app) as client:
        yield client, app.state.observer
    assert all(b.closed for b in backends.values())


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_http_auth_cursor_fault_validation_and_replay_scope(http_setup):
    client, observer = http_setup
    for path in ("observations", "events"):
        assert client.get(f"/runs/one/{path}").status_code == 401
        for token in ("other", "control"):
            assert client.get(f"/runs/one/{path}", headers=auth(token)).status_code == 403
        assert client.get(f"/runs/one/{path}?after=999", headers=auth("buyer")).status_code == 409
    for cursor in ("-1", "1.5", "nan", "１２", "9" * 30):
        # Non-ASCII cannot be sent as an HTTP header by httpx; use a query for that case.
        if cursor == "１２":
            continue
        assert (
            client.get(
                "/runs/one/events",
                headers=auth("observer")
                | {
                    "Last-Event-ID": cursor,
                },
            ).status_code
            == 422
        )
    for query in ("after=-1", "limit=0", "limit=101"):
        assert (
            client.get(f"/runs/one/observations?{query}", headers=auth("buyer")).status_code == 422
        )
    path = "/admin/runs/one/faults/delivery-notification"
    for token in ("buyer", "observer", "other"):
        assert client.post(path, json={}, headers=auth(token)).status_code == 403
    for body in ({"copies": 4}, {"delay_ms": True}, {"amount": 999}, {"delay_ms": 5001}):
        assert client.post(path, json=body, headers=auth("control")).status_code == 422
    assert client.post(path, json={"copies": 2}, headers=auth("control")).status_code == 200
    observer.poll("one")
    observer.poll("two")
    observer.publish()
    other = observer.read("two", 0)["events"][0]["event"]["event_id"]
    assert (
        client.post(
            "/admin/runs/one/faults/replay-notification",
            headers=auth("control"),
            json={"event_id": other},
        ).status_code
        == 404
    )
    batch = client.get("/runs/one/observations", headers=auth("observer")).json()
    assert batch["next_cursor"] == 1 and not batch["stale"]


def test_stream_frames_have_delivery_ids_and_freshness_without_cursor_advance(tmp_path):
    journal = ObservationJournal(tmp_path / "n.db", ["one"])
    journal.record("one", snapshot(), 100)
    journal.publish(100)
    frames = list(sse_frames(journal.read("one", 0, 100)))
    assert frames[0].startswith("id: 1\nevent: observation\ndata: ")
    assert frames[0].endswith("\n\n")
    assert frames[1].startswith("event: status\ndata: ") and "id:" not in frames[1]
    journal.failed("one")
    frames = list(sse_frames(journal.read("one", 1, 101)))
    assert len(frames) == 1 and '"stale":true' in frames[0]


def test_background_tasks_stop_before_backend_is_closed(tmp_path):
    journal = ObservationJournal(tmp_path / "n.db", ["one"])
    backend = Backend("one")
    observer = Observer(journal, {"one": backend})

    async def run():
        task = asyncio.create_task(observer.serve())
        deadline = time.monotonic() + 3
        while observer.read("one", 0)["current_cursor"] < 1:
            assert time.monotonic() < deadline
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        version = observer.read("one", 0)["current_cursor"]
        await asyncio.sleep(0.25)
        assert observer.read("one", 0)["current_cursor"] == version

    asyncio.run(run())


def test_cancellation_waits_for_running_http_thread():
    entered, release = threading.Event(), threading.Event()

    def request():
        entered.set()
        assert release.wait(3)

    async def run():
        task = asyncio.create_task(finish_thread(request))
        try:
            while not entered.is_set():
                await asyncio.sleep(0.001)
            task.cancel()
            await asyncio.sleep(0.02)
            assert not task.done(), "Closing clients now would interrupt an in-flight request"
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())


def test_actual_asgi_stream_reconnect_header_and_retention_reset(tmp_path):
    config = {
        "directory": str(tmp_path),
        "runs": {"one": {}},
        "grants": {
            hashlib.sha256(b"observer").hexdigest(): {"run_id": "one", "role": "observer"},
        },
    }
    app = create_app(config, {"one": Backend("one")}, start_observer=False)
    journal = app.state.observer.journal
    for tick in range(3):
        journal.record("one", snapshot(tick), time.time())
        journal.publish(time.time())

    async def stream(cursor):
        disconnected = asyncio.Event()
        messages = []

        async def receive():
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
            if b"event: status" in message.get("body", b""):
                disconnected.set()

        await asyncio.wait_for(
            app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0", "spec_version": "2.3"},
                    "http_version": "1.1",
                    "method": "GET",
                    "scheme": "http",
                    "path": "/runs/one/events",
                    "raw_path": b"/runs/one/events",
                    "query_string": b"after=0",
                    "root_path": "",
                    "headers": [
                        (b"authorization", b"Bearer observer"),
                        (b"last-event-id", str(cursor).encode()),
                    ],
                    "server": ("testserver", 80),
                    "client": ("testclient", 1),
                },
                receive,
                send,
            ),
            timeout=3,
        )
        return messages

    messages = asyncio.run(stream(1))
    assert messages[0]["status"] == 200
    assert b"text/event-stream" in dict(messages[0]["headers"])[b"content-type"]
    body = b"".join(message.get("body", b"") for message in messages).decode()
    assert "id: 1\n" not in body
    assert "id: 2\nevent: observation" in body and "id: 3\nevent: observation" in body
    journal.retention = 1
    journal.record("one", snapshot(4, 3), time.time())
    journal.publish(time.time())
    messages = asyncio.run(stream(1))
    body = b"".join(message.get("body", b"") for message in messages).decode()
    assert "id: 4\nevent: snapshot" in body and '"tent":3' in body
    assert "event: observation" not in body


def test_failed_observer_still_closes_clients_and_releases_lock(tmp_path):
    backend = Backend("one")
    config = {"directory": str(tmp_path), "runs": {"one": {}}, "grants": {}}
    app = create_app(config, {"one": backend})

    async def run():
        failed = asyncio.Event()

        async def fail():
            failed.set()
            raise RuntimeError("worker failed")

        app.state.observer.serve = fail
        with pytest.raises(RuntimeError, match="worker failed"):
            async with app.router.lifespan_context(app):
                await failed.wait()
        assert backend.closed
        replacement = Backend("one")
        restarted = create_app(config, {"one": replacement}, start_observer=False)
        async with restarted.router.lifespan_context(restarted):
            assert not replacement.closed
        assert replacement.closed

    asyncio.run(run())


def test_duplicate_gateway_cannot_start_second_observer(tmp_path):
    config = {"directory": str(tmp_path), "runs": {"one": {}}, "grants": {}}
    first, second = Backend("one"), Backend("one")
    app = create_app(config, {"one": first}, start_observer=False)
    other = create_app(config, {"one": second}, start_observer=False)
    with TestClient(app):
        with pytest.raises(BlockingIOError), TestClient(other):
            pytest.fail("Second observer acquired the same process lock")
        assert second.closed and not first.closed
    assert first.closed


def test_poll_timing_survives_publication_replay_and_legacy(tmp_path):
    journal = ObservationJournal(tmp_path / "timing.db", ["one"])
    first = journal.record(
        "one", snapshot(), 100.25, poll_started_at=100, poll_elapsed_seconds=0.24
    )
    assert first["poll_started_at"] == 100 and first["poll_elapsed_seconds"] == 0.24
    journal.publish(102)
    journal.replay("one", first["event_id"], 103)
    journal.publish(103)
    events = journal.read("one", 0, 104)["events"]
    assert [d["published_at"] for d in events] == [102, 103]
    assert events[0]["event"] == events[1]["event"]
    reopened = ObservationJournal(tmp_path / "timing.db", ["one"])
    assert reopened.read("one", 0, 104)["events"] == events
    legacy = journal.record("one", snapshot(1), 105)
    assert "poll_started_at" not in legacy and "poll_elapsed_seconds" not in legacy


@pytest.mark.parametrize(
    "start,elapsed",
    [(100, None), (None, 0.1), (-1, 0.1), (100, -1), (100, float("nan")), (True, 0.1)],
)
def test_invalid_timing_never_commits_event(tmp_path, start, elapsed):
    journal = ObservationJournal(tmp_path / "timing.db", ["one"])
    with pytest.raises(ContractError):
        journal.record("one", snapshot(), 101, poll_started_at=start, poll_elapsed_seconds=elapsed)
    assert journal.read("one", 0, 102)["current_cursor"] == 0
    with journal.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


def test_wall_clock_reversal_keeps_monotonic_measurement_and_state(tmp_path):
    journal = ObservationJournal(tmp_path / "timing.db", ["one"])
    event = journal.record("one", snapshot(), 99, poll_started_at=100, poll_elapsed_seconds=0.25)
    assert event["observed_at"] == 99
    assert event["poll_elapsed_seconds"] == 0.25
    assert event["snapshot"] == snapshot()


def test_poll_stats_include_unchanged_and_failure_with_new_process_identity(tmp_path):
    journal = ObservationJournal(tmp_path / "timing.db", ["one"])
    backend = Backend("one")
    observer = Observer(journal, {"one": backend})
    observer.poll("one")
    observer.poll("one")
    backend.fail = True
    observer.poll("one")
    stats = observer.read("one", 0)["poll_stats"]
    assert stats == {
        "process_id": observer.process_id,
        "attempted": 3,
        "completed": 2,
        "failed": 1,
        "unchanged": 1,
        "in_flight": False,
    }
    other = Observer(journal, {"one": backend})
    assert other.process_id != observer.process_id
    assert other.read("one", 0)["poll_stats"]["attempted"] == 0
