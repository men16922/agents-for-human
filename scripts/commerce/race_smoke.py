#!/usr/bin/env python3
"""Two independent run budgets compete for one real Medusa inventory bundle."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from contract_spike import ROOT, Spike
from operating_fixture import prepare, start_seller
from operating_smoke import wait_until
from stock_smoke import change_stock, export_run, level

from rehearsal.evaluation.medusa import verify_medusa
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN, start, stop
from rehearsal.world.storage import ContractError


def main():
    os.umask(0o077)
    spike = Spike()
    processes, clients = [], []
    report = {
        "passed": False,
        "run_id": spike.run_id,
        "scope": "two-run-live-medusa-stock-race",
        "real_model_calls": 0,
        "read_errors": [],
    }
    try:
        directory, credentials, config, fixtures = prepare(spike)
        report["stock_changes"] = [
            change_stock(spike, fixtures["A"], item, qty)
            for item, qty in (("tent", 3), ("light", 6))
        ]
        processes.append(start_seller(directory))

        def gateway():
            return start(
                directory,
                factory="scripts.commerce.race_gateway:create_app",
                config_variable="REHEARSAL_MEDUSA_CONFIG",
            )

        server = gateway()
        processes.append(server)
        run_ids = list(config["runs"])
        for rid in run_ids:
            clients.append(
                OperatingClient(ORIGIN, rid, credentials["runs"][rid]["buyer"], timeout=30)
            )
        quotes = [c.get_quotes("A", {"tent": 3, "light": 6}) for c in clients]
        orders = [c.create_order(q["id"], "same-key-isolated-run") for c, q in zip(clients, quotes)]
        assert all(q["amount"] == 310 for q in quotes)
        report.update(quotes=quotes, orders=orders)
        barrier = threading.Barrier(2)

        def pay(index):
            barrier.wait(timeout=5)
            started = time.monotonic()
            value = clients[index].authorize_payment(orders[index]["id"], "same-pay-isolated-run")
            return {
                "run_id": run_ids[index],
                "started": started,
                "ended": time.monotonic(),
                "payment": asdict(value),
            }

        with ThreadPoolExecutor(max_workers=2) as pool:
            report["race"] = list(pool.map(pay, (0, 1)))

        def trace():
            return [
                json.loads(line)
                for line in (directory / "race-trace.jsonl").read_text().splitlines()
            ]

        completes = [v for v in trace() if v.get("path", "").endswith("/complete")]
        assert len(completes) == 2
        overlap = min(c["ended"] for c in completes) - max(c["started"] for c in completes)
        assert overlap > 0, "No overlapping checkout HTTP intervals observed"
        report["checkout_overlap_seconds"] = overlap
        report["checkout_responses"] = completes

        def observe(index):
            try:
                return clients[index].get_order(orders[index]["id"])
            except ContractError as exc:
                if exc.code != "EXTERNAL_DELIVERY_MISMATCH":
                    raise
                report["read_errors"].append({"run_id": run_ids[index], "code": exc.code})
                return {"status": "OBSERVATION_UNAVAILABLE"}

        observed = wait_until(
            lambda: [observe(i) for i in (0, 1)],
            lambda rows: sum(o["status"] == "DELIVERED" for o in rows) == 1,
            25,
        )
        winner = next(i for i, row in enumerate(observed) if row["status"] == "DELIVERED")
        loser = 1 - winner
        assert observed[loser]["status"] == "UNKNOWN"
        assert clients[winner].get_payment(orders[winner]["id"]).status == "SETTLED"
        assert clients[loser].get_payment(orders[loser]["id"]).status == "UNKNOWN"
        report.update(winner=run_ids[winner], loser=run_ids[loser], observed=observed)
        # Identical keys are local to each run; repetition must only reconcile an existing intent.
        with ThreadPoolExecutor(max_workers=2) as pool:
            repeated = list(
                pool.map(
                    lambda i: (
                        clients[i]
                        .authorize_payment(orders[i]["id"], "same-pay-isolated-run")
                        .status
                    ),
                    (0, 1),
                )
            )
        assert repeated[winner] == "SETTLED" and repeated[loser] == "UNKNOWN"
        before_restart = [c.observe_world() for c in clients]
        assert before_restart[winner]["balance"] == {
            "budget": 500,
            "spent": 310,
            "reserved": 0,
            "available": 190,
        }
        assert before_restart[loser]["balance"] == {
            "budget": 500,
            "spent": 0,
            "reserved": 310,
            "available": 190,
        }
        other_order_checks = []
        for i in (0, 1):
            try:
                clients[i].get_order(orders[1 - i]["id"])
            except ContractError as exc:
                assert exc.code == "NOT_FOUND"
                other_order_checks.append(exc.code)
            else:
                raise AssertionError("Cross-run order handle accepted")
        report["cross_run_handles"] = other_order_checks
        stop(server)
        processes.remove(server)
        processes.append(gateway())
        after_restart = [c.observe_world() for c in clients]
        for a, b in zip(before_restart, after_restart):
            for field in ("balance", "inventory", "goal"):
                assert a[field] == b[field]
        assert (
            clients[loser].authorize_payment(orders[loser]["id"], "same-pay-isolated-run").status
            == "UNKNOWN"
        )
        replacement_quote = clients[loser].get_quotes("B", {"tent": 3, "light": 6})
        replacement = clients[loser].create_order(replacement_quote["id"], "replacement-buy")
        try:
            clients[loser].authorize_payment(replacement["id"], "replacement-pay")
        except ContractError as exc:
            assert exc.code == "BUDGET_EXCEEDED"
            report["replacement_rejection"] = exc.code
        else:
            raise AssertionError("Uncertain funds reused for replacement purchase")
        report["final_inventory"] = {
            item: level(spike, fixtures["A"], item) for item in ("tent", "light")
        }
        assert all(
            v["stocked_quantity"] == 0 and v["reserved_quantity"] == 0
            for v in report["final_inventory"].values()
        )
        # List each authenticated customer's real orders independently of local mapping.
        lists = [spike.get("/store/orders", role) for role in ("buyer", "other")]
        assert lists[winner]["count"] == 1 and lists[loser]["count"] == 0
        report["customer_order_lists"] = lists
        report["verdicts"], report["evidence_hashes"] = {}, {}
        for i, rid in enumerate(run_ids):
            snapshot = clients[i].observe_world()
            evidence = export_run(spike, config["runs"][rid], snapshot)
            evidence["scope"] = report["scope"]
            verdict = verify_medusa(evidence, config["runs"][rid]["binding"]["goal"], 500)
            assert verdict["status"] == ("COMPLETE" if i == winner else "UNKNOWN"), verdict
            assert len(evidence["tables"]["intents"]) == 1
            filename = f"race-evidence-{i}.json"
            path = spike.directory / filename
            path.write_text(json.dumps(evidence, indent=2) + "\n")
            report["evidence_hashes"][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
            report["verdicts"][rid] = verdict
        all_trace = trace()
        assert len([v for v in all_trace if v.get("path", "").endswith("/complete")]) == 2
        report.update(passed=True, before_restart=before_restart, after_restart=after_restart)
        sources = [
            "scripts/commerce/race_smoke.py",
            "scripts/commerce/race_gateway.py",
            "scripts/commerce/operating_fixture.py",
            "src/rehearsal/commerce/gateway.py",
            "src/rehearsal/commerce/server.py",
            "src/rehearsal/world/payments.py",
            "src/rehearsal/evaluation/medusa.py",
            "node_modules/@medusajs/core-flows/dist/cart/workflows/complete-cart.js",
            "node_modules/@medusajs/core-flows/dist/cart/steps/reserve-inventory.js",
        ]
        report["source_hashes"] = {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources
        }
    except Exception as exc:
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        for process in reversed(processes):
            stop(process)
        for client in clients:
            client.close()
        spike.report["passed"] = report["passed"]
        spike.save()
        (spike.directory / "race-report.json").write_text(json.dumps(report, indent=2) + "\n")
        for client in spike.clients.values():
            client.close()
        print(f"Evidence: {spike.directory.relative_to(ROOT)}")
    print("PASS: overlapping checkout, one delivery, losing UNKNOWN reservation preserved.")


if __name__ == "__main__":
    main()
