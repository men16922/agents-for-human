#!/usr/bin/env python3
"""Bound actual stock-change-to-DOM latency; requires the owned make commerce service.

No purchases, models, simulated browser responses, or performance pass threshold.
The request interval bounds a source change; it is not its exact occurrence time.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import sys
import time
from pathlib import Path

from contract_spike import ROOT, Spike
from observer_smoke import ready, start_local, wait_file
from operating_fixture import prepare, start_gateway, start_seller
from stock_smoke import change_stock

from rehearsal.operating.local import check_port, stop


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def distribution(values):
    values = sorted(values)
    return {
        "n": len(values),
        **{
            name: values[max(0, math.ceil(q * len(values)) - 1)] if values else None
            for name, q in [("p50", 0.5), ("p95", 0.95), ("max", 1)]
        },
    }


def main():
    os.umask(0o077)
    for port in (18000, 15173, 18001):
        check_port(port)
    spike = Spike()
    processes = []
    report = {
        "passed": False,
        "scope": "local-stock-change-interval-to-dom",
        "real_model_calls": 0,
        "purchases": 0,
        "performance_target_verified": False,
        "trials": [],
        "limits": [
            "source change is bounded by the stock helper invocation, not timestamped",
            "cross-process wall times assume comparable local clocks; no clock sync proof",
            "two animation frames approximate paint opportunity, not physical display",
            "one browser, twenty sequential stock changes; not all event types or load",
            "initial state, clocks, delivery, reconnect and timeouts are not zero-latency",
        ],
    }
    try:
        directory, _, config, fixtures = prepare(spike)
        run_id = next(iter(config["runs"]))
        report["run_id"] = run_id
        browser_dir = spike.directory / "latency-browser"
        browser_dir.mkdir()
        plan = {
            "run_id": run_id,
            "target_ms": 1000,
            "trial_count": 20,
            "trials": [
                {"id": i, "quantity": i, "delay_seconds": [0, 0.07, 0.23, 0.41][i % 4]}
                for i in range(1, 21)
            ],
        }
        write(browser_dir / "plan.json", plan)
        report["trials"] = [dict(t, status="NOT_RUN") for t in plan["trials"]]
        processes.append(start_seller(directory))
        processes.append(start_gateway(directory))
        env = dict(os.environ, REHEARSAL_OBSERVER_CONFIG=str(directory / "observer-buyer.json"))
        env.pop("REHEARSAL_EXECUTION_CONFIG", None)
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
            ["node", "scripts/commerce/latency_browser.mjs", str(browser_dir)],
            browser_dir / "browser.log",
            env,
        )
        processes.append(browser)
        for trial in report["trials"]:
            wait_file(browser_dir / f"armed-{trial['id']}.json", browser)
            time.sleep(trial["delay_seconds"])
            trial.update(
                status="STARTED",
                started_ms=time.time() * 1000,
                started_mono_ms=time.monotonic() * 1000,
            )
            write(spike.directory / "latency-report.json", report)
            trial["change"] = change_stock(spike, fixtures["A"], "tent", trial["quantity"])
            trial.update(completed_ms=time.time() * 1000, completed_mono_ms=time.monotonic() * 1000)
            trial["browser"] = wait_file(browser_dir / f"render-{trial['id']}.json", browser)
            trial["status"] = trial["browser"]["status"]
            write(spike.directory / "latency-report.json", report)
        report["browser"] = wait_file(browser_dir / "browser-report.json", browser)
        assert browser.wait(timeout=10) == 0
        with sqlite3.connect(f"file:{directory}/observations.sqlite3?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            journal = [
                dict(r)
                for r in db.execute(
                    "SELECT d.cursor,d.published_at,o.data FROM deliveries d "
                    "JOIN observations o USING(event_id) WHERE d.run_id=? ORDER BY d.cursor",
                    (run_id,),
                )
            ]
        for row in journal:
            row["event"] = json.loads(row.pop("data"))
        write(browser_dir / "journal.json", journal)
        for trial in report["trials"]:
            if trial["status"] != "RENDERED":
                continue
            probe = trial["browser"]
            first, painted = probe["first"], probe["painted"]
            event = next(r["event"] for r in journal if r["cursor"] == first["cursor"])
            assert event["version"] == first["version"]
            supplier = next(
                s
                for s in event["snapshot"]["commerce"]["catalog"]["offers"]
                if s["supplier"] == "A" and s["item"] == "tent"
            )
            assert supplier["status"] == "OBSERVED" and supplier["stock"] == trial["quantity"]
            trial["journal_match"] = {
                "event_id": event["event_id"],
                "cursor": first["cursor"],
                "version": event["version"],
                "supplier": supplier,
            }
            assert first["stock"].strip() == painted["stock"].strip() == str(trial["quantity"])
            assert first["visible"] and painted["visible"] and probe["armed"]["visible"]
            # Detect jumps during each local interval, but do not assert clock synchronization.
            host_delta = trial["completed_ms"] - trial["started_ms"]
            assert abs(host_delta - (trial["completed_mono_ms"] - trial["started_mono_ms"])) < 100
            assert (
                abs(
                    (painted["wall_ms"] - probe["armed"]["wall_ms"])
                    - (painted["mono_ms"] - probe["armed"]["mono_ms"])
                )
                < 100
            )
            assert painted["wall_ms"] >= trial["started_ms"]
            trial["conditional_bounds_ms"] = {
                "lower": max(0, painted["wall_ms"] - trial["completed_ms"]),
                "upper": painted["wall_ms"] - trial["started_ms"],
            }
        valid = [
            t["conditional_bounds_ms"] for t in report["trials"] if "conditional_bounds_ms" in t
        ]
        report["bounds_summary_ms"] = {
            k: distribution([v[k] for v in valid]) for k in ["lower", "upper"]
        }
        report["status_counts"] = {
            s: sum(t["status"] == s for t in report["trials"])
            for s in ["NOT_RUN", "STARTED", "TIMEOUT", "RENDERED"]
        }
        report["passed"] = True
    finally:
        for process in reversed(processes):
            stop(process)
        spike.report["passed"] = report["passed"]
        spike.save()
        for client in spike.clients.values():
            client.close()
        sources = [
            Path(__file__),
            ROOT / "scripts/commerce/latency_browser.mjs",
            ROOT / "web/src/metrics.ts",
            ROOT / "web/src/main.tsx",
            ROOT / "src/rehearsal/commerce/observer.py",
            ROOT / "src/rehearsal/commerce/observations.py",
        ]
        report["source_hashes"] = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        }
        write(spike.directory / "latency-report.json", report)
        print(f"Evidence: {spike.directory.relative_to(ROOT)}")
    print("PASS: source intervals and actual DOM observations retained; no target pass inferred.")


if __name__ == "__main__":
    main()
