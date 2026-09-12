#!/usr/bin/env python3
"""Actual SDK/Medusa execution observed through the read-only reaction UI."""

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from event_fixture import export_events
from model_session import ROOT, Session
from observer_smoke import ready, start_local, wait_file
from reaction_smoke import DelayedBuyer, RecordedClient
from stock_smoke import export_run

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.commerce.model_runner import attest, digest, execute_http, write
from rehearsal.commerce.reaction import ReactionSettings
from rehearsal.evaluation.condition_events import verify_events
from rehearsal.evaluation.conditions import verify_conditions
from rehearsal.experiments.frozen import freeze
from rehearsal.experiments.policy import Policy
from rehearsal.operating.local import check_port, stop
from rehearsal.world.storage import identifier


def main():
    os.umask(0o077)
    for port in (18000, 15173, 18001):
        check_port(port)
    directory = ROOT / ".local/evaluation" / identifier("reaction-ui")
    directory.mkdir(mode=0o700)
    browser_dir = directory / "browser"
    browser_dir.mkdir()
    case = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
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
    write(directory / "case.json", case)
    frozen = freeze(Policy(), directory / "policy.json", ROOT)
    session = client = worker = None
    stopping = threading.Event()
    processes, worker_errors = [], []
    pool = ThreadPoolExecutor(max_workers=1)
    report = {"passed": False, "real_model_calls": 0, "model_efficacy_verified": False}
    try:
        session = Session(directory / "policy.json", fixture=True, case=case)
        sp = session.start()
        report["session"] = str(sp.relative_to(ROOT))

        def maintain():
            try:
                session.wait(stopping)
            except Exception as exc:
                worker_errors.append(type(exc).__name__)

        worker = threading.Thread(target=maintain)
        worker.start()
        config = json.loads((sp / "buyer-config.json").read_text())
        initial = json.loads((sp / session.record["conditions_path"]).read_text())
        verified = verify_conditions(initial, case, config["run_id"])
        write(directory / "conditions.json", initial)
        env = dict(
            os.environ,
            REHEARSAL_OBSERVER_CONFIG=str(sp.parent / "operating/observer-buyer.json"),
            REHEARSAL_EXECUTION_CONFIG=str(browser_dir / "execution-selection.json"),
            REHEARSAL_EVIDENCE_CONFIG=str(browser_dir / "evidence-selection.json"),
        )
        api = start_local(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "rehearsal.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                "18000",
                "--no-access-log",
            ],
            browser_dir / "api.log",
            env,
        )
        processes.append(api)
        ready("http://127.0.0.1:18000/health", api)
        web = start_local(["npm", "run", "dev:web"], browser_dir / "web.log", env)
        processes.append(web)
        ready("http://127.0.0.1:15173", web)
        browser = start_local(
            ["node", "scripts/commerce/reaction_browser.mjs", str(browser_dir)],
            browser_dir / "browser.log",
            env,
        )
        processes.append(browser)
        report["initial_ui"] = wait_file(browser_dir / "initial.json", browser)
        client = RecordedClient(config, directory)
        settings = ModelSettings(
            "offline",
            "offline",
            "offline-review-fixture",
            RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
            100000,
            max_model_calls=32,
            max_tool_calls=32,
            timeout_seconds=60,
        )
        model = DelayedBuyer()
        execution = directory / "execution"
        future = pool.submit(
            execute_http,
            model,
            settings,
            client,
            execution,
            config["expected_goal"],
            config["expected_budget"],
            frozen,
            "offline-scripted-model",
            initial_condition={
                "sha256": digest(directory / "conditions.json"),
                "verification": verified,
            },
            reaction_settings=ReactionSettings(8),
        )
        deadline = time.monotonic() + 5
        while not (execution / "spec.json").exists():
            if future.done():
                future.result()
                raise RuntimeError("No execution spec")
            if time.monotonic() >= deadline:
                raise RuntimeError("Execution spec timeout")
            time.sleep(0.05)
        # Wait for a complete JSON write, then pin its exact bytes for the UI.
        while True:
            try:
                spec = json.loads((execution / "spec.json").read_text())
                break
            except json.JSONDecodeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        selected = {key: spec[key] for key in ("run_id", "expected_goal", "expected_budget")}
        selected.update(execution_path="../execution", spec_sha256=digest(execution / "spec.json"))
        write(browser_dir / "execution-selection.tmp", selected)
        (browser_dir / "execution-selection.tmp").replace(browser_dir / "execution-selection.json")
        result = future.result(timeout=75)
        report["runtime"] = result
        report["delayed_model_call"] = model.delayed_call
        assert result["runtime_accounted"] and not worker_errors
        report["ready_export_ui"] = wait_file(browser_dir / "ready-export.json", browser)
        evidence = export_run(session.spike, session.run, client.observe_world())
        evidence["condition_events"] = export_events(session)
        write(directory / "live-evidence.json", evidence)
        chosen = {key: config[key] for key in ("run_id", "expected_goal", "expected_budget")}
        chosen.update(
            artifact_path="../live-evidence.json", sha256=digest(directory / "live-evidence.json")
        )
        write(browser_dir / "evidence-selection.tmp", chosen)
        (browser_dir / "evidence-selection.tmp").replace(browser_dir / "evidence-selection.json")
        report["live_attestation"] = attest(execution, browser_dir / "evidence-selection.json")
        assert report["live_attestation"]["success"]
        report["events"] = verify_events(
            evidence["condition_events"],
            case,
            evidence["binding"],
            verified["capture_end_tick"],
            evidence["captured_at_tick"],
        )
        assert report["events"]["status"] == "VERIFIED"
        report["browser"] = wait_file(browser_dir / "browser-report.json", browser)
        assert browser.wait(timeout=10) == 0
        ui = report["browser"]["execution"]
        assert ui["execution"]["audit"]["replans"] == result["reactions"]["replans"]
        assert ui["execution"]["audit"]["cursor"] == result["reactions"]["inbox"]["cursor"]
        audit = [
            json.loads(line) for line in (execution / "observations.jsonl").read_text().splitlines()
        ]
        during = [
            row
            for row in audit
            if row["kind"] == "journal"
            and model.delayed_call["started_at"] <= row["at"] <= model.delayed_call["finished_at"]
            and any(
                offer["supplier"] == "A" and offer["item"] == "tent" and offer["stock"] == 0
                for delivery in row["value"]["events"]
                for offer in delivery["event"]["snapshot"]["commerce"]["catalog"]["offers"]
            )
        ]
        assert during
        calls = [
            json.loads(line) for line in (directory / "buyer-http.jsonl").read_text().splitlines()
        ]
        for effect in ("orders", "payments"):
            assert (
                len([row for row in calls if row["method"] == "POST" and row["path"] == effect])
                == 1
            )
        stopping.set()
        worker.join(5)
        assert not worker.is_alive() and not worker_errors
        session.close("REACTION_UI_SMOKE_FINISHED")
        report["final_attestation"] = attest(execution, sp / "selection.json")
        assert report["final_attestation"]["success"] and not session.record["cleanup_errors"]
        report.update(passed=True, changed_journal_batches_during_model=len(during))
    finally:
        pool.shutdown(wait=True)
        stopping.set()
        if worker:
            worker.join(5)
        for process in reversed(processes):
            stop(process)
        if session:
            session.close("REACTION_UI_SMOKE_CLEANUP")
        if client:
            client.close()
        write(directory / "smoke.json", report)
        print(f"{'PASS' if report['passed'] else 'FAIL'} live reaction UI: {directory}")


if __name__ == "__main__":
    main()
