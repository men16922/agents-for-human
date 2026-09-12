#!/usr/bin/env python3
"""Local Medusa stock change, scripted purchase, browser SSE and restart evidence.

Requires make commerce. Starts only own loopback gateway, observer API and web.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

import httpx
from contract_spike import ROOT, Spike
from operating_fixture import prepare, start_gateway, start_seller
from operating_smoke import wait_until
from stock_smoke import change_stock, expect_stock_rejection, export_run

from rehearsal.evaluation.medusa import verify_medusa
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN, check_port, stop
from rehearsal.world.storage import ContractError


def wait_file(path, process, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text())
        if process.poll() is not None:
            raise RuntimeError("Browser exited; inspect its private report/log")
        time.sleep(0.1)
    raise RuntimeError(f"Browser checkpoint timed out: {path.name}")


def start_local(command, path, env):
    with path.open("ab") as log:
        return subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def ready(url, process):
    deadline = time.monotonic() + 20
    with httpx.Client(trust_env=False, timeout=0.5) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Local view service exited")
            try:
                if client.get(url).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.1)
    raise RuntimeError("Local view readiness timed out")


def main():
    os.umask(0o077)
    for port in (18000, 15173, 18001):
        check_port(port)
    spike = Spike()
    processes, buyer = [], None
    report = {
        "passed": False,
        "scope": "live-medusa-browser-stock-scripted-purchase",
        "run_id": spike.run_id,
        "real_model_calls": 0,
        "model_replanning_verified": False,
    }
    try:
        directory, credentials, config, fixtures = prepare(spike)
        processes.append(start_seller(directory))
        gateway = start_gateway(directory)
        processes.append(gateway)
        run_id = next(iter(config["runs"]))
        buyer = OperatingClient(ORIGIN, run_id, credentials["runs"][run_id]["buyer"], timeout=10)
        browser_dir = spike.directory / "browser"
        browser_dir.mkdir()
        env = dict(
            os.environ,
            REHEARSAL_OBSERVER_CONFIG=str(directory / "observer-buyer.json"),
            REHEARSAL_EVIDENCE_CONFIG=str(browser_dir / "selection.json"),
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
            ["node", "scripts/commerce/observer_browser.mjs", str(browser_dir)],
            browser_dir / "browser.log",
            env,
        )
        processes.append(browser)
        report["initial_ui"] = wait_file(browser_dir / "initial.json", browser)
        quote = buyer.get_quotes("A", {"tent": 3, "light": 6})
        report["stock_change"] = change_stock(spike, fixtures["A"], "tent", 0)
        report["rejection"] = expect_stock_rejection(
            lambda: buyer.create_order(quote["id"], "ui-stale-stock")
        )
        report["stock_ui"] = wait_file(browser_dir / "stock-change.json", browser)
        quote = buyer.get_quotes("B", {"tent": 3, "light": 6})
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=5) as control:
            fault = control.post(
                f"/admin/runs/{run_id}/faults/delivery-notification",
                headers={"Authorization": "Bearer " + credentials["runs"][run_id]["control"]},
                json={"delay_ms": 2000, "copies": 2},
            )
            assert fault.status_code == 200
        report["notification_fixture"] = {"delay_ms": 2000, "copies": 2}
        order = buyer.create_order(quote["id"], "ui-alternative-buy")
        payment = buyer.authorize_payment(order["id"], "ui-alternative-pay")
        assert payment.status in {"RESERVED", "SETTLED", "UNKNOWN"}
        report["read_errors"] = []

        def receipt():
            try:
                return buyer.get_order(order["id"])
            except ContractError as exc:
                if exc.code != "EXTERNAL_DELIVERY_MISMATCH":
                    raise
                # A transient inconsistent GET stays rejected by the gateway.
                # Retry only observation, never purchase or payment mutations.
                report["read_errors"].append({"code": exc.code, "at": time.time()})
                return {"status": "OBSERVATION_UNAVAILABLE"}

        wait_until(receipt, lambda value: value["status"] == "DELIVERED", 25)
        assert buyer.get_payment(order["id"]).status == "SETTLED"
        report["purchase"] = {"quote": quote, "order": order, "snapshot": buyer.observe_world()}
        report["received_ui"] = wait_file(browser_dir / "received.json", browser)
        stop(gateway)
        processes.remove(gateway)
        report["disconnected_ui"] = wait_file(browser_dir / "disconnected.json", browser)
        processes.append(start_gateway(directory))
        report["browser"] = wait_file(browser_dir / "browser-report.json", browser)
        snapshot = buyer.observe_world()
        evidence = export_run(spike, config["runs"][run_id], snapshot)
        evidence["scope"] = report["scope"]
        evidence_path = spike.directory / "observer-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
        verdict = verify_medusa(evidence, config["runs"][run_id]["binding"]["goal"], 500)
        assert verdict["status"] == "COMPLETE" and verdict["spent"] == 380
        selection = {
            "run_id": run_id,
            "expected_goal": config["runs"][run_id]["binding"]["goal"],
            "expected_budget": 500,
            "artifact_path": str(evidence_path),
            "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        }
        temporary = browser_dir / "selection.tmp"
        temporary.write_text(json.dumps(selection, indent=2) + "\n")
        temporary.replace(browser_dir / "selection.json")
        report["evidence_ui"] = wait_file(browser_dir / "evidence-browser.json", browser)
        assert browser.wait(timeout=10) == 0
        metrics_path = browser_dir / "latency.json"
        metrics = json.loads(metrics_path.read_text())
        assert metrics["counters"]["duplicate"] >= 1
        assert metrics["counters"]["old"] >= 1
        assert metrics["summary"]["render"]["n"] >= 8
        report["latency"] = {
            "summary": metrics["summary"],
            "counters": metrics["counters"],
            "sha256": hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
        }
        report.update(
            passed=True,
            verdict=verdict,
            final_snapshot=snapshot,
            evidence_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        )
        sources = [
            "scripts/commerce/observer_smoke.py",
            "scripts/commerce/observer_browser.mjs",
            "scripts/commerce/operating_fixture.py",
            "src/rehearsal/api.py",
            "src/rehearsal/observer_view.py",
            "src/rehearsal/evidence_view.py",
            "src/rehearsal/evaluation/medusa.py",
            "web/src/Evidence.tsx",
            "web/src/Commerce.tsx",
            "web/src/metrics.ts",
            "web/src/MetricsPanel.tsx",
            "src/rehearsal/commerce/details.py",
            "src/rehearsal/commerce/gateway.py",
            "src/rehearsal/commerce/observations.py",
            "src/rehearsal/commerce/observer.py",
            "web/src/main.tsx",
            "web/src/useObserver.ts",
            "web/src/observation.ts",
            "web/src/style.css",
        ]
        report["source_hashes"] = {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources
        }
    finally:
        for process in reversed(processes):
            stop(process)
        if buyer:
            buyer.close()
        spike.report["passed"] = report["passed"]
        spike.save()
        (spike.directory / "observer-report.json").write_text(json.dumps(report, indent=2) + "\n")
        for client in spike.clients.values():
            client.close()
        print(f"Evidence: {spike.directory.relative_to(ROOT)}")
    print("PASS: browser observed real Medusa B 380 delivery, disconnect and cursor recovery.")


if __name__ == "__main__":
    main()
