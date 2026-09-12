#!/usr/bin/env python3
"""Declared notification delay/copies/replay over real Medusa and an independent SSE consumer."""

import json
import os
import threading
import time
from copy import deepcopy

import httpx
from model_session import ROOT, Session
from notification_smoke import stream_until

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.commerce.observations import Projection
from rehearsal.evaluation import batch, external_batch
from rehearsal.evaluation.frozen_run import fixture_factory
from rehearsal.experiments.frozen import FrozenPolicy
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN
from rehearsal.world.storage import identifier


class ScheduledClient(OperatingClient):
    quotes = 0
    held = False

    def request(self, method, path, body=None):
        if path == "quotes":
            self.quotes += 1
            if self.quotes == 2:
                while super().request("GET", "snapshot")["tick"] < 6:
                    time.sleep(0.1)
        value = super().request(method, path, body)
        if path == "snapshot" and not self.held and value["inventory"] == value["goal"]["items"]:
            self.held = True
            while value["tick"] < 28:
                time.sleep(0.1)
                value = super().request("GET", "snapshot")
        return value


def main():
    os.umask(0o077)
    directory = ROOT / ".local/evaluation" / identifier("notification-events")
    training = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    changed = deepcopy(training)
    changed["scenario_version"] = "declared-delayed-notification-replay-v1"
    changed["goal"]["deadline_tick"] = 120
    changed["events"] = [
        {
            "id": "notice",
            "kind": "delivery_notification",
            "at_tick": 3,
            "max_lateness_ticks": 2,
            "delay_ms": 2000,
            "copies": 2,
        },
        {
            "id": "replay",
            "kind": "notification_replay",
            "at_tick": 23,
            "max_lateness_ticks": 2,
            "delay_ms": 1000,
            "copies": 2,
            "source_event": "notice",
        },
    ]
    pending = deepcopy(changed)
    pending["scenario_version"] = "declared-unused-notification-v1"
    for event in pending["events"]:
        event["at_tick"] += 60
    cases = {"changed": changed, "pending": pending}
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-evaluation-fixture",
        RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
        100000,
        max_model_calls=48,
        max_tool_calls=48,
    )
    batch.prepare(
        directory,
        training,
        cases,
        1,
        settings,
        500000,
        "offline-scripted-model",
        evaluation_environment="external-medusa",
    )
    result = {
        "passed": False,
        "real_model_calls": 0,
        "sessions": {},
        "consumers": {},
        "test_transport_schedule": (
            "second quote after tick 6; completed-inventory response held until tick 28"
        ),
    }
    try:
        for cid, method in [("changed", "B0"), ("changed", "B1"), ("pending", "B0")]:
            cell = f"{cid}-{method}-r1"
            path = directory / "runs" / cell
            session = client = worker = reader = inspector = None
            stopping = threading.Event()
            frames = []
            errors = []
            try:
                assert (
                    external_batch.learn(directory, cell, fixture_factory)["status"]
                    == "WAITING_EXTERNAL"
                )
                policy = FrozenPolicy.load(path / "policy.json", ROOT).policy
                session = Session(path / "policy.json", fixture=True, case=cases[cid])
                sp = session.start()
                result["sessions"][cell] = str(sp.relative_to(ROOT))
                worker = threading.Thread(target=session.wait, args=(stopping,))
                worker.start()
                config = json.loads((sp / "buyer-config.json").read_text())
                if cid == "changed":
                    credentials = json.loads((sp.parent / "operating/credentials.json").read_text())
                    inspector = httpx.Client(base_url=ORIGIN, timeout=10, trust_env=False)
                    counts = []

                    def receive():
                        def accept(frame):
                            if (
                                frame["type"] == "observation"
                                and frame["data"]["event"]["event_type"] == "delivery.observed"
                            ):
                                counts.append(frame["id"])
                            return len(counts) == 4

                        try:
                            frames.extend(
                                stream_until(
                                    inspector,
                                    config["run_id"],
                                    {
                                        "Authorization": "Bearer "
                                        + credentials["runs"][config["run_id"]]["observer"]
                                    },
                                    0,
                                    accept,
                                    seconds=40,
                                )
                            )
                        except Exception as exc:
                            errors.append(type(exc).__name__)

                    reader = threading.Thread(target=receive)
                    reader.start()
                client = ScheduledClient(
                    ORIGIN, config["run_id"], config["buyer_token"], timeout=10
                )
                external_batch.execute(
                    directory,
                    cell,
                    None if method == "B0" else fixture_factory("buyer", policy),
                    client,
                    condition_path=sp / session.record["conditions_path"],
                )
                if reader:
                    reader.join(5)
                    assert not reader.is_alive() and not errors, errors
                stopping.set()
                worker.join(5)
                assert not worker.is_alive()
                session.close("NOTIFICATION_EVENT_SMOKE_FINISHED")
                final = external_batch.settle(directory, cell, sp / "selection.json")
                selected = next(c for c in final["cells"] if c["id"] == cell)
                assert selected["external_transaction_verified"]
                assert selected["condition_alignment_verified"] == (cid == "changed")
                assert session.record["verdict"]["spent"] == 310
                if cid == "changed":
                    evidence = json.loads((path / "external-evidence.json").read_text())[
                        "condition_events"
                    ]
                    audit = evidence["scheduled_deliveries"]
                    projection = Projection(config["run_id"])
                    outcomes = []
                    for frame in frames:
                        if frame["type"] == "observation":
                            outcome = projection.apply(frame["data"])
                            if frame["data"]["event"]["event_type"] == "delivery.observed":
                                outcomes.append(outcome)
                    delivery = [f for f in frames if f.get("id") in {r["cursor"] for r in audit}]
                    assert len(audit) == len(delivery) == 4
                    schedules = {r["schedule_id"]: r for r in evidence["notification_schedules"]}
                    for row in audit:
                        frame = next(f for f in delivery if f["id"] == row["cursor"])
                        assert frame["data"]["published_at"] == row["published_at"]
                        assert frame["data"]["event"] == json.loads(
                            schedules[row["schedule_id"]]["observation_data"]
                        )
                    assert projection.snapshot["inventory"] == {"tent": 3, "light": 6}
                    assert outcomes[1:] == ["duplicate"] * 3
                    batch.write(directory / f"{cell}-sse.json", frames)
                    result["consumers"][cell] = {
                        "copies": 4,
                        "outcomes": outcomes,
                        "inventory": projection.snapshot["inventory"],
                        "published_rows_match_received_frames": True,
                    }
                batch.write(directory / f"after-{cell}.json", final)
            finally:
                stopping.set()
                if worker:
                    worker.join(5)
                if session:
                    session.close("NOTIFICATION_EVENT_SMOKE_CLEANUP")
                if client:
                    client.close()
                if inspector:
                    inspector.close()
                if reader:
                    reader.join(5)
        final = external_batch.summarize(directory)
        assert final["status_counts"] == {"EXTERNAL_VERIFIED": 3, "NOT_RUN": 5}
        assert final["held_micro_usd"] == 0
        result.update(passed=True, report=final)
        batch.write(directory / "report.json", final)
    finally:
        batch.write(directory / "smoke.json", result)
        print(f"{'PASS' if result['passed'] else 'FAIL'} notification events: {directory}")


if __name__ == "__main__":
    main()
