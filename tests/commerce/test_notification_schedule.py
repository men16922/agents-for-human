import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from test_observations import auth, snapshot
from test_observations import http_setup as http_setup

from rehearsal.commerce.observations import ObservationJournal
from rehearsal.evaluation.condition_events import validate_case
from rehearsal.evaluation.notification_conditions import verify_notification_event
from rehearsal.world.storage import ContractError


def export(journal):
    with journal.db.connect() as db:
        return {
            table: [dict(r) for r in db.execute(f"SELECT * FROM {table}")]
            for table in ("notification_schedules", "scheduled_deliveries")
        } | {"clock_started_at": 1000}


def declaration(kind, tick, eid, **extra):
    return {
        "id": eid,
        "kind": kind,
        "at_tick": tick,
        "max_lateness_ticks": 2,
        "delay_ms": 2000 if kind == "delivery_notification" else 1000,
        "copies": 2,
    } | extra


def receipt(event):
    body = {
        "event_id": event["id"],
        "kind": event["kind"],
        "delay_ms": event["delay_ms"],
        "copies": event["copies"],
    }
    if "source_event" in event:
        body["source_event"] = event["source_event"]
    return {
        "event": event,
        "state": "OBSERVED",
        "before": snapshot(event["at_tick"]),
        "after": snapshot(event["at_tick"]),
        "mutation": {
            "method": "POST",
            "path": "/admin/runs/one/faults/scheduled-notification",
            "status": 200,
            "request": body,
            "response": {"armed": True, "event_id": event["id"]},
        },
    }


@pytest.fixture
def scheduled(tmp_path):
    journal = ObservationJournal(tmp_path / "observations.db", ["one", "two"], retention=1)
    journal.record("one", snapshot(), 1000)
    journal.publish(1000)
    notice = declaration("delivery_notification", 3, "notice")
    replay = declaration("notification_replay", 15, "replay", source_event="notice")
    journal.arm_scheduled("one", "notice", "delivery_notification", 2000, 2, None, 3, 1003)
    observed = journal.record("one", snapshot(10, 3), 1010)
    journal.record("one", snapshot(11, 3), 1011)
    journal.publish(1012)
    journal = ObservationJournal(journal.db.path, ["one", "two"], retention=1)
    journal.arm_scheduled("one", "replay", "notification_replay", 1000, 2, "notice", 15, 1015)
    journal.publish(1016)
    return journal, notice, replay, observed


def test_delayed_copies_and_replay_keep_exact_observation_after_retention_and_restart(scheduled):
    journal, notice, replay, observed = scheduled
    artifact = export(journal)
    binding = {"run_id": "one", "goal": snapshot()["goal"]}
    first = verify_notification_event(receipt(notice), notice, binding, artifact)
    second = verify_notification_event(receipt(replay), replay, binding, artifact)
    assert first["end_tick"] == 12 and second["end_tick"] == 16
    assert first["observation_id"] == second["observation_id"] == observed["event_id"]
    assert first["copies"] == second["copies"] == 2
    assert max(first["cursors"]) < min(second["cursors"])
    assert first["publication_only"]


def test_no_publication_is_not_a_completed_event(tmp_path):
    journal = ObservationJournal(tmp_path / "journal", ["one"])
    event = declaration("delivery_notification", 3, "notice")
    binding = {"run_id": "one", "goal": snapshot()["goal"]}
    journal.record("one", snapshot(), 1000)
    journal.arm_scheduled("one", "notice", "delivery_notification", 2000, 2, None, 3, 1003)
    assert verify_notification_event(receipt(event), event, binding, export(journal)) is None
    journal.record("one", snapshot(10, 3), 1010)
    assert verify_notification_event(receipt(event), event, binding, export(journal)) is None
    with pytest.raises(ContractError, match="REPLAY_SOURCE_NOT_PUBLISHED"):
        journal.arm_scheduled("one", "replay", "notification_replay", 0, 2, "notice", 11, 1011)


def test_atomic_publish_never_duplicates_a_scheduled_copy_across_instances(tmp_path):
    path = tmp_path / "journal"
    one = ObservationJournal(path, ["one"])
    two = ObservationJournal(path, ["one"])
    one.record("one", snapshot(), 1000)
    one.publish(1000)
    one.arm_scheduled("one", "notice", "delivery_notification", 2000, 2, None, 3, 1003)
    one.record("one", snapshot(10, 3), 1010)
    with ThreadPoolExecutor(2) as pool:
        assert sum(pool.map(lambda j: j.publish(1012), (one, two))) == 2
    rows = export(one)["scheduled_deliveries"]
    assert len(rows) == len({r["cursor"] for r in rows}) == 2


def test_duplicate_conflict_legacy_override_and_cross_run_replay_are_rejected(scheduled):
    journal, _, _, _ = scheduled
    with pytest.raises(ContractError):
        journal.arm_scheduled("one", "notice", "delivery_notification", 0, 1, None, 20, 1020)
    with pytest.raises(ContractError):
        journal.arm_scheduled("two", "other", "notification_replay", 0, 1, "notice", 20, 1020)
    journal.arm_scheduled("one", "later", "delivery_notification", 0, 1, None, 20, 1020)
    with pytest.raises(ContractError):
        journal.arm_delivery("one", 0, 1)
    with pytest.raises(ContractError):
        journal.arm_scheduled("one", "override", "delivery_notification", 0, 1, None, 21, 1021)
    # Replay can coexist with a separately armed future delivery notification.
    journal.arm_scheduled("one", "again", "notification_replay", 0, 1, "notice", 22, 1022)


@pytest.mark.parametrize(
    "damage",
    [
        "body",
        "clock",
        "copies",
        "row-delay",
        "observation",
        "previous",
        "quantity",
        "source",
        "duplicate-seq",
        "duplicate-cursor",
        "early",
        "missing",
        "partial",
        "anchor",
        "replay-source",
    ],
)
def test_raw_notification_evidence_tampering_is_rejected(scheduled, damage):
    journal, event, replay, _ = scheduled
    artifact = export(journal)
    proof = receipt(event)
    selected = artifact["notification_schedules"][0]
    rows = artifact["scheduled_deliveries"]
    if damage == "body":
        proof["mutation"]["request"]["copies"] = 3
    elif damage == "clock":
        proof["after"]["tick"] = 6
    elif damage == "copies":
        selected["copies"] = 3
    elif damage == "row-delay":
        rows[0]["due_at"] -= 1
    elif damage == "observation":
        selected["observation_id"] = "other"
    elif damage == "previous":
        raw = json.loads(selected["previous_data"])
        raw["run_id"] = "other"
        selected["previous_data"] = json.dumps(raw)
    elif damage == "quantity":
        raw = json.loads(selected["previous_data"])
        raw["snapshot"]["inventory"]["tent"] = 3
        selected["previous_data"] = json.dumps(raw)
    elif damage == "source":
        raw = json.loads(selected["observation_data"])
        raw["source"] = "model"
        selected["observation_data"] = json.dumps(raw)
    elif damage == "duplicate-seq":
        rows[1]["seq"] = rows[0]["seq"]
    elif damage == "duplicate-cursor":
        rows[1]["cursor"] = rows[0]["cursor"]
    elif damage == "early":
        rows[0]["published_at"] = 1011
    elif damage == "missing":
        rows.pop(0)
    elif damage == "partial":
        rows[0]["published_at"] = None
    elif damage == "anchor":
        artifact["clock_started_at"] = 1004
    elif damage == "replay-source":
        event = replay
        proof = receipt(event)
        artifact["notification_schedules"][1]["observation_data"] = "{}"
    with pytest.raises((ValueError, KeyError)):
        verify_notification_event(
            proof, event, {"run_id": "one", "goal": snapshot()["goal"]}, artifact
        )


def test_schema_requires_an_earlier_delivery_schedule_for_replay():
    case = json.loads((Path(__file__).parents[2] / "scenarios/normal-v1.json").read_text())
    notice = declaration("delivery_notification", 3, "notice")
    replay = declaration("notification_replay", 15, "replay", source_event="notice")
    case["events"] = [notice, replay]
    validate_case(case)
    for wrong in (
        [replay],
        [notice, replay | {"source_event": "missing"}],
        [notice | {"copies": 4}],
        [notice | {"delay_ms": -1}],
    ):
        candidate = copy.deepcopy(case)
        candidate["events"] = wrong
        with pytest.raises(ValueError):
            validate_case(candidate)


def test_scheduled_notification_route_is_control_only_and_keeps_schema_bounds(http_setup):
    client, observer = http_setup
    observer.backends["one"].tick = lambda: 3
    path = "/admin/runs/one/faults/scheduled-notification"
    body = {"event_id": "notice", "kind": "delivery_notification", "delay_ms": 2000, "copies": 2}
    assert client.post(path, json=body).status_code == 401
    for token in ("buyer", "observer", "other"):
        assert client.post(path, json=body, headers=auth(token)).status_code == 403
    for bad in (body | {"copies": 4}, body | {"delay_ms": True}, body | {"amount": 1}):
        assert client.post(path, json=bad, headers=auth("control")).status_code == 422
    assert client.post(path, json=body, headers=auth("control")).status_code == 200
    assert client.post(path, json=body, headers=auth("control")).status_code == 409
