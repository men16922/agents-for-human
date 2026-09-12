#!/usr/bin/env python3
"""Real local Medusa with two independent browsers and bounded retention recovery."""

from __future__ import annotations

import hashlib
import json
import os
import sys

import httpx
from contract_spike import ROOT, Spike
from observer_smoke import ready, start_local, wait_file
from operating_fixture import prepare, start_gateway, start_seller
from operating_smoke import wait_until
from stock_smoke import change_stock, export_run

from rehearsal.evaluation.medusa import verify_medusa
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN, check_port, stop
from rehearsal.world.storage import ContractError


def main():
    os.umask(0o077)
    for port in (18000, 15173, 18001):
        check_port(port)
    spike = Spike()
    processes, buyer = [], None
    report = {
        "passed": False,
        "scope": "two-browser-local-medusa-recovery",
        "run_id": spike.run_id,
        "real_model_calls": 0,
        "observation_retention": 8,
    }
    try:
        directory, credentials, config, fixtures = prepare(spike)
        config["observation_retention"] = 8
        (directory / "server.json").write_text(json.dumps(config, indent=2) + "\n")
        processes.append(start_seller(directory))
        processes.append(start_gateway(directory))
        run_id = next(iter(config["runs"]))
        buyer = OperatingClient(ORIGIN, run_id, credentials["runs"][run_id]["buyer"], timeout=10)
        browser_dir = spike.directory / "convergence-browser"
        browser_dir.mkdir()
        env = dict(os.environ, REHEARSAL_OBSERVER_CONFIG=str(directory / "observer-buyer.json"))
        env.pop("REHEARSAL_EVIDENCE_CONFIG", None)
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
            ["node", "scripts/commerce/convergence_browser.mjs", str(browser_dir)],
            browser_dir / "browser.log",
            env,
        )
        processes.append(browser)
        report["initial"] = wait_file(browser_dir / "initial.json", browser)
        report["short_offline"] = wait_file(browser_dir / "short-offline.json", browser)
        report["stock_change"] = change_stock(spike, fixtures["A"], "tent", 0)
        report["short_recovered"] = wait_file(browser_dir / "short-recovered.json", browser)
        report["long_offline"] = wait_file(browser_dir / "long-offline.json", browser)
        quote = buyer.get_quotes("B", {"tent": 3, "light": 6})
        order = buyer.create_order(quote["id"], "two-browser-buy")
        payment = buyer.authorize_payment(order["id"], "two-browser-pay")
        assert payment.status in {"RESERVED", "SETTLED", "UNKNOWN"}
        report["read_errors"] = []

        def receipt():
            try:
                return buyer.get_order(order["id"])
            except ContractError as exc:
                if exc.code != "EXTERNAL_DELIVERY_MISMATCH":
                    raise
                report["read_errors"].append(exc.code)
                return {"status": "OBSERVATION_UNAVAILABLE"}

        wait_until(receipt, lambda value: value["status"] == "DELIVERED", 25)
        assert buyer.get_payment(order["id"]).status == "SETTLED"
        cursor = int(report["long_offline"]["cursor"])
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=10) as observer:

            def batch():
                response = observer.get(
                    f"/runs/{run_id}/observations",
                    params={"after": cursor},
                    headers={"Authorization": "Bearer " + credentials["runs"][run_id]["observer"]},
                )
                response.raise_for_status()
                return response.json()

            reset = wait_until(batch, lambda b: b["reset"] and b["retained_after"] > cursor, 25)
        report["retention"] = reset
        temporary = browser_dir / "retention.tmp"
        temporary.write_text(json.dumps(reset, indent=2) + "\n")
        temporary.replace(browser_dir / "retention-ready.json")
        report["browser"] = wait_file(browser_dir / "convergence-browser.json", browser)
        assert browser.wait(timeout=10) == 0
        snapshot = buyer.observe_world()
        evidence = export_run(spike, config["runs"][run_id], snapshot)
        evidence["scope"] = report["scope"]
        verdict = verify_medusa(evidence, config["runs"][run_id]["binding"]["goal"], 500)
        assert verdict["status"] == "COMPLETE" and verdict["spent"] == 380
        for state in report["browser"]["final"]:
            assert state["spent"] == "380크레딧" and state["reserved"] == "0크레딧"
            assert state["inventory-tent"] == "3 / 3" and state["inventory-light"] == "6 / 6"
            assert state["run"] == run_id
        evidence_path = spike.directory / "convergence-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
        report.update(
            passed=True,
            verdict=verdict,
            final_snapshot=snapshot,
            evidence_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        )
        sources = [
            "scripts/commerce/convergence_smoke.py",
            "scripts/commerce/convergence_browser.mjs",
            "scripts/commerce/observer_smoke.py",
            "scripts/commerce/operating_fixture.py",
            "src/rehearsal/commerce/server.py",
            "src/rehearsal/commerce/observations.py",
            "src/rehearsal/commerce/observer.py",
            "src/rehearsal/commerce/gateway.py",
            "src/rehearsal/commerce/details.py",
            "src/rehearsal/observer_view.py",
            "src/rehearsal/evaluation/medusa.py",
            "web/src/main.tsx",
            "web/src/observation.ts",
            "web/src/useObserver.ts",
            "web/src/metrics.ts",
            "web/src/Commerce.tsx",
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
        (spike.directory / "convergence-report.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        for client in spike.clients.values():
            client.close()
        print(f"Evidence: {spike.directory.relative_to(ROOT)}")
    print("PASS: two browsers converge after independent cursor and retention snapshot recovery.")


if __name__ == "__main__":
    main()
