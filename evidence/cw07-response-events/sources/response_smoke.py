#!/usr/bin/env python3
"""Known scheduled delayed payment responses with actual client read timeouts."""

import json
import os
import threading
import time
from copy import deepcopy

import httpx
from model_session import ROOT, Session

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.evaluation import batch, external_batch
from rehearsal.evaluation.frozen_run import fixture_factory
from rehearsal.experiments.frozen import FrozenPolicy
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN
from rehearsal.world.storage import identifier


class TimedClient(OperatingClient):
    quotes = 0

    def request(self, method, path, body=None):
        if path == "quotes":
            self.quotes += 1
            if self.quotes == 2:
                while super().request("GET", "snapshot")["tick"] < 6:
                    time.sleep(0.1)
        previous = self.http.timeout
        if method == "POST" and path == "payments":
            self.http.timeout = httpx.Timeout(2)
        try:
            return super().request(method, path, body)
        finally:
            self.http.timeout = previous


def main():
    os.umask(0o077)
    directory = ROOT / ".local/evaluation" / identifier("response-events")
    training = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    loss = deepcopy(training)
    loss["scenario_version"] = "declared-payment-delay-v1"
    loss["goal"]["deadline_tick"] = 120
    loss["events"] = [
        {
            "id": "loss",
            "kind": "payment_response_delay",
            "at_tick": 3,
            "max_lateness_ticks": 2,
            "delay_ms": 4000,
        }
    ]
    pending = deepcopy(loss)
    pending["scenario_version"] = "declared-unused-payment-delay-v1"
    pending["events"][0]["at_tick"] = 60
    cases = {"loss": loss, "pending": pending}
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
        "transport_schedule": "second quote waits until tick 6; payment read timeout 2 seconds",
    }
    try:
        for cid, method in [("loss", "B0"), ("loss", "B1"), ("pending", "B0")]:
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
                client = TimedClient(ORIGIN, config["run_id"], config["buyer_token"], timeout=10)
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
                session.close("RESPONSE_EVENT_SMOKE_FINISHED")
                final = external_batch.settle(directory, cell, sp / "selection.json")
                selected = next(c for c in final["cells"] if c["id"] == cell)
                assert selected["external_transaction_verified"]
                assert selected["condition_alignment_verified"] == (cid == "loss")
                assert session.record["verdict"]["spent"] == 310
                runtime = json.loads((path / "execution/report.json").read_text())
                assert len(runtime["payment_transport_events"]) == 1
                observed = runtime["payment_transport_events"][0]
                assert (observed.get("error_type") == "ReadTimeout") == (cid == "loss")
                review = json.loads((path / "attestation.json").read_text())["event_review"]
                assert review["observed"] == (1 if cid == "loss" else 0)
                if cid == "loss":
                    assert review["client_timeouts_verified"]
                batch.write(directory / f"after-{cell}.json", final)
            finally:
                stopping.set()
                if worker:
                    worker.join(5)
                if session:
                    session.close("RESPONSE_EVENT_SMOKE_CLEANUP")
                if client:
                    client.close()
        final = external_batch.summarize(directory)
        assert final["status_counts"] == {"EXTERNAL_VERIFIED": 3, "NOT_RUN": 5}
        assert final["held_micro_usd"] == 0
        result.update(passed=True, report=final)
        batch.write(directory / "report.json", final)
    finally:
        batch.write(directory / "smoke.json", result)
        print(f"{'PASS' if result['passed'] else 'FAIL'} response events: {directory}")


if __name__ == "__main__":
    main()
