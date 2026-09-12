#!/usr/bin/env python3
"""Declared timed price/stock mutations during controlled local HTTP execution."""

import json
import os
import threading
import time
from copy import deepcopy

from model_session import ROOT, Session

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.evaluation import batch, external_batch
from rehearsal.evaluation.frozen_run import fixture_factory
from rehearsal.experiments.frozen import FrozenPolicy
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN
from rehearsal.world.storage import identifier


class DelayedSecondQuote(OperatingClient):
    """Explicit test transport schedule; production buyer gets no timing hook."""

    quotes = 0

    def request(self, method, path, body=None):
        if path == "quotes":
            self.quotes += 1
            if self.quotes == 2:
                while super().request("GET", "snapshot")["tick"] < 15:
                    time.sleep(0.1)
        return super().request(method, path, body)


def main():
    os.umask(0o077)
    directory = ROOT / ".local/evaluation" / identifier("events")
    training = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    timed = deepcopy(training)
    timed["scenario_version"] = "declared-timed-price-and-stock-v1"
    timed["goal"]["deadline_tick"] = 120
    timed["events"] = [
        {
            "id": "priceA",
            "at_tick": 10,
            "max_lateness_ticks": 3,
            "kind": "price",
            "supplier": "A",
            "item": "tent",
            "value": 100,
        },
        {
            "id": "stockA",
            "at_tick": 12,
            "max_lateness_ticks": 3,
            "kind": "stock",
            "supplier": "A",
            "item": "light",
            "value": 0,
        },
    ]
    pending = deepcopy(timed)
    pending["scenario_version"] = "declared-events-after-execution-v1"
    for event in pending["events"]:
        event["at_tick"] += 40
    cases = {"timed": timed, "pending": pending}
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
        "controlled_delay": "second quote request waits until tick 15 only for timed cases",
    }
    try:
        for cid, method in [("timed", "B0"), ("pending", "B0"), ("timed", "B1")]:
            cell = f"{cid}-{method}-r1"
            path = directory / "runs" / cell
            session = client = worker = None
            stopping = threading.Event()
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
                cls = DelayedSecondQuote if cid == "timed" else OperatingClient
                client = cls(ORIGIN, config["run_id"], config["buyer_token"], timeout=30)
                external_batch.execute(
                    directory,
                    cell,
                    None if method == "B0" else fixture_factory("buyer", policy),
                    client,
                    condition_path=sp / session.record["conditions_path"],
                )
                stopping.set()
                worker.join(5)
                assert not worker.is_alive()
                session.close("TIMED_EVENT_SMOKE_FINISHED")
                final = external_batch.settle(directory, cell, sp / "selection.json")
                selected = next(c for c in final["cells"] if c["id"] == cell)
                attestation = json.loads((path / "attestation.json").read_text())
                assert attestation["transaction_verified"] == (method == "B0"), session.record[
                    "verdict"
                ]
                assert selected["condition_alignment_verified"] == (cid == "timed")
                assert session.record["verdict"]["spent"] == (
                    0 if method == "B1" else 380 if cid == "timed" else 310
                )
                review = json.loads((path / "attestation.json").read_text())["event_review"]
                assert review["observed"] == (2 if cid == "timed" else 0)
                batch.write(directory / f"after-{cell}.json", final)
            finally:
                stopping.set()
                if worker:
                    worker.join(5)
                if session:
                    session.close("TIMED_EVENT_SMOKE_CLEANUP")
                if client:
                    client.close()
        final = external_batch.summarize(directory)
        assert final["status_counts"].get("NOT_RUN") == 5
        assert (
            sum(
                final["status_counts"].get(k, 0)
                for k in ("EXTERNAL_VERIFIED", "EXTERNAL_INCOMPLETE")
            )
            == 3
        )
        assert sum(m["condition_verified"] for m in final["methods"].values()) == 2
        assert final["recorded_micro_usd"] == 224
        assert final["held_micro_usd"] == 99776
        result["known_sdk_failure"] = (
            "stale A quote retained after refresh failure; missing order id; "
            "last call usage unresolved"
        )
        try:
            external_batch.learn(directory, "timed-B2-r1", fixture_factory)
        except ValueError as exc:
            assert str(exc) == "UNRESOLVED_USAGE"
            result["unresolved_usage_blocks_next_cell"] = True
        else:
            raise AssertionError("Unresolved SDK usage admitted another cell")
        result.update(passed=True, report=final)
        batch.write(directory / "report.json", final)
    finally:
        batch.write(directory / "smoke.json", result)
        print(f"{'PASS' if result['passed'] else 'FAIL'} declared timed events: {directory}")


if __name__ == "__main__":
    main()
