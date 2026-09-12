#!/usr/bin/env python3
"""Frozen reaction settings across four external arms; scripted fixtures, not model efficacy."""

import json
import os
import threading

from model_session import ROOT, Session
from reaction_smoke import DelayedBuyer, RecordedClient

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.commerce.reaction import ReactionSettings
from rehearsal.evaluation import batch, external_batch
from rehearsal.evaluation.frozen_run import fixture_factory
from rehearsal.world.storage import identifier


class ComparisonBuyer(DelayedBuyer):
    def get_config(self):
        return {"model_id": "offline-evaluation-fixture"}


def main():
    os.umask(0o077)
    directory = ROOT / ".local/evaluation" / identifier("reaction-batch")
    training = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    case = json.loads(json.dumps(training))
    case["goal"]["deadline_tick"] = 90
    case["events"] = [
        {
            "id": "stock",
            "kind": "stock",
            "at_tick": 10,
            "max_lateness_ticks": 2,
            "supplier": "A",
            "item": "tent",
            "value": 0,
        }
    ]
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-evaluation-fixture",
        RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
        100000,
        max_model_calls=48,
        max_tool_calls=48,
    )
    manifest = batch.prepare(
        directory,
        training,
        {"changed": case},
        1,
        settings,
        500000,
        "offline-scripted-model",
        evaluation_environment="external-medusa",
        external_reactions=ReactionSettings(8),
    )
    report = {
        "passed": False,
        "real_model_calls": 0,
        "model_efficacy_verified": False,
        "sessions": {},
        "delayed_calls": {},
    }
    try:
        for method in ("B0", "B1", "B2", "B3"):
            cell = f"changed-{method}-r1"
            path = directory / "runs" / cell
            session = client = worker = None
            stopping = threading.Event()
            try:
                learned = external_batch.learn(directory, cell, fixture_factory)
                assert learned["status"] == "WAITING_EXTERNAL"
                session = Session(path / "policy.json", fixture=True, case=case)
                sp = session.start()
                report["sessions"][cell] = str(sp.relative_to(ROOT))
                worker = threading.Thread(target=session.wait, args=(stopping,))
                worker.start()
                config = json.loads((sp / "buyer-config.json").read_text())
                client = RecordedClient(config, path)
                model = None if method == "B0" else ComparisonBuyer()
                result = external_batch.execute(
                    directory,
                    cell,
                    model,
                    client,
                    condition_path=sp / session.record["conditions_path"],
                )
                if model:
                    report["delayed_calls"][cell] = model.delayed_call
                stopping.set()
                worker.join(5)
                assert not worker.is_alive()
                session.close("REACTION_BATCH_SMOKE_FINISHED")
                final = external_batch.settle(directory, cell, sp / "selection.json")
                selected = next(c for c in final["cells"] if c["id"] == cell)
                assert selected["external_transaction_verified"]
                assert selected["condition_alignment_verified"]
                assert selected["reaction_execution_verified"] == (method != "B0")
                assert session.record["verdict"]["spent"] == (310 if method == "B0" else 380)
                runtime = json.loads((path / "execution/report.json").read_text())
                assert len(runtime["usage"]["calls"]) == len(learned["total_usage"]["calls"]) + (
                    model.calls if model else 0
                )
                assert (
                    runtime["usage"]["calls"][: len(learned["total_usage"]["calls"])]
                    == learned["total_usage"]["calls"]
                )
                if model:
                    assert (
                        runtime["reactions"]["settings"] == manifest["external_reactions"][method]
                    )
                    assert runtime["reactions"]["blocked_effects"] >= 1
                    assert result["total_usage"]["all_usage_recorded"]
                    audit = [
                        json.loads(line)
                        for line in (path / "execution/observations.jsonl").read_text().splitlines()
                    ]
                    assert any(
                        r["kind"] == "journal"
                        and model.delayed_call["started_at"]
                        <= r["at"]
                        <= model.delayed_call["finished_at"]
                        and any(
                            o["supplier"] == "A" and o["item"] == "tent" and o["stock"] == 0
                            for d in r["value"]["events"]
                            for o in d["event"]["snapshot"]["commerce"]["catalog"]["offers"]
                        )
                        for r in audit
                    )
                    requests = [
                        json.loads(line)
                        for line in (path / "buyer-http.jsonl").read_text().splitlines()
                    ]
                    assert (
                        sum(r["method"] == "POST" and r["path"] == "orders" for r in requests) == 1
                    )
                    assert (
                        sum(r["method"] == "POST" and r["path"] == "payments" for r in requests)
                        == 1
                    )
                else:
                    assert "reactions" not in runtime and runtime["usage"]["calls"] == []
                batch.write(directory / f"after-{cell}.json", final)
            finally:
                stopping.set()
                if worker:
                    worker.join(5)
                if session:
                    session.close("REACTION_BATCH_SMOKE_CLEANUP")
                if client:
                    client.close()
        final = external_batch.summarize(directory)
        assert final["status_counts"] == {"EXTERNAL_VERIFIED": 4} and final["held_micro_usd"] == 0
        assert all(m["condition_verified"] == 1 for m in final["methods"].values())
        report.update(passed=True, report=final)
        batch.write(directory / "report.json", final)
    finally:
        batch.write(directory / "smoke.json", report)
        print(f"{'PASS' if report['passed'] else 'FAIL'} reaction comparison: {directory}")


if __name__ == "__main__":
    main()
