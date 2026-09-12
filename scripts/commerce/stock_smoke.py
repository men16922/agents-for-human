#!/usr/bin/env python3
"""Real Medusa stock reductions after quote/acceptance, with scripted recovery.

Run with make commerce active. Only this invocation's labelled inventory changes.
No model, learned policy, external payment provider or automatic checkout retry.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from contract_spike import ROOT, Spike
from operating_fixture import prepare, start_gateway, start_seller
from operating_smoke import wait_until

from rehearsal.commerce.seller import ORDER_FIELDS, read_rows
from rehearsal.evaluation.medusa import verify_medusa
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN, stop
from rehearsal.world.storage import ContractError


def level(spike, fixture, item):
    iid = fixture["inventory"][("tent", "light").index(item)]
    levels = spike.get(f"/admin/inventory-items/{iid}/location-levels")["inventory_levels"]
    return next(v for v in levels if v["location_id"] == fixture["location"]["id"])


def change_stock(spike, fixture, item, quantity):
    before = level(spike, fixture, item)
    assert before["reserved_quantity"] == 0, "Never overwrite another purchase's reservation"
    iid = fixture["inventory"][("tent", "light").index(item)]
    lid = fixture["location"]["id"]
    spike.post(
        f"/admin/inventory-items/{iid}/location-levels/{lid}", {"stocked_quantity": quantity}
    )
    after = level(spike, fixture, item)
    assert after["stocked_quantity"] == quantity and after["reserved_quantity"] == 0
    return {"item": item, "before": before, "after": after}


def expect_stock_rejection(action):
    try:
        action()
    except ContractError as exc:
        assert exc.code == "MEDUSA_HTTP_400", exc.code
        return exc.code
    raise AssertionError("Expected actual Medusa rejection after inventory reduction")


def purchase(client, supplier, items, key):
    quote = client.get_quotes(supplier, items)
    order = client.create_order(quote["id"], key + "-buy")
    payment = client.authorize_payment(order["id"], key + "-pay")
    assert payment.status in {"RESERVED", "SETTLED", "UNKNOWN"}
    wait_until(lambda: client.get_order(order["id"]), lambda o: o["status"] == "DELIVERED", 25)
    assert client.get_payment(order["id"]).status == "SETTLED"
    return {"quote": quote, "order": order, "snapshot": client.observe_world()}


def export_run(spike, run, snapshot):
    directory = Path(run["directory"])
    evidence = {
        "binding": run["binding"],
        "tables": {},
        "external_orders": [],
        "captured_at_tick": snapshot["tick"],
        "scope": "live-medusa-stock-scripted-recovery",
    }
    for filename, tables in (
        ("medusa.sqlite3", ("purchases", "quotes")),
        ("payments.sqlite3", ("accounts", "intents")),
    ):
        for table in tables:
            evidence["tables"][table] = read_rows(directory / filename, table)
    for row in evidence["tables"]["purchases"]:
        if row["external_id"]:
            evidence["external_orders"].append(
                spike.get(f"/admin/orders/{row['external_id']}?fields={ORDER_FIELDS}")["order"]
            )
    return evidence


def main():
    os.umask(0o077)
    spike = Spike()
    spike.report["scope"] = "live-medusa-stock-operator-http"
    processes, clients = [], []
    report = {
        "passed": False,
        "run_id": spike.run_id,
        "scope": "live-medusa-stock-scripted-recovery",
        "real_model_calls": 0,
        "learned_policy_transfer_verified": False,
        "changes": [],
        "cases": {},
    }
    try:
        directory, credentials, config, fixtures = prepare(spike)
        seller = start_seller(directory)
        processes.append(seller)
        gateway = start_gateway(directory)
        processes.append(gateway)
        run_ids = list(config["runs"])
        for rid in run_ids:
            clients.append(
                OperatingClient(ORIGIN, rid, credentials["runs"][rid]["buyer"], timeout=10)
            )
        first, second = clients
        items = {"tent": 3, "light": 6}
        # Independent operator changes real inventory after the buyer receives a quote.
        quote = first.get_quotes("A", items)
        assert quote["amount"] == 310
        report["changes"].append(change_stock(spike, fixtures["A"], "tent", 0))
        rejection = expect_stock_rejection(lambda: first.create_order(quote["id"], "stale-stock"))
        before = first.observe_world()
        assert before["balance"] == {"budget": 500, "spent": 0, "reserved": 0, "available": 500}
        assert not read_rows(
            Path(config["runs"][run_ids[0]]["directory"]) / "medusa.sqlite3", "purchases"
        )
        recovered = purchase(first, "B", items, "alternative-b")
        assert recovered["snapshot"]["balance"]["spent"] == 380
        report["cases"]["before_order"] = {
            "run_id": run_ids[0],
            "old_quote": quote,
            "rejection": rejection,
            "before_recovery": before,
            "recovery": [recovered],
        }
        report["changes"].append(change_stock(spike, fixtures["A"], "tent", 10))
        # Local acceptance is not an external stock/payment reservation.
        quote = second.get_quotes("A", items)
        order = second.create_order(quote["id"], "accepted-before-stock-change")
        report["changes"].append(change_stock(spike, fixtures["A"], "light", 0))
        rejection = expect_stock_rejection(
            lambda: second.authorize_payment(order["id"], "rejected-pay")
        )
        before = second.observe_world()
        assert before["balance"] == {"budget": 500, "spent": 0, "reserved": 0, "available": 500}
        second_dir = Path(config["runs"][run_ids[1]]["directory"])
        assert not read_rows(second_dir / "payments.sqlite3", "intents")
        assert second.get_order(order["id"])["status"] == "ACCEPTED"
        partial = [purchase(second, "A", {"tent": 3}, "partial-a")]
        assert partial[0]["snapshot"]["inventory"] == {"tent": 3, "light": 0}
        partial.append(purchase(second, "C", {"light": 6}, "partial-c"))
        assert [p["quote"]["amount"] for p in partial] == [190, 225]
        report["cases"]["before_payment"] = {
            "run_id": run_ids[1],
            "old_quote": quote,
            "accepted_order": order,
            "rejection": rejection,
            "before_recovery": before,
            "recovery": partial,
        }
        stop(gateway)
        restarted = start_gateway(directory)
        processes.append(restarted)
        snapshots = [client.observe_world() for client in clients]
        for snapshot, amount in zip(snapshots, (380, 415)):
            assert snapshot["inventory"] == items
            assert snapshot["balance"] == {
                "budget": 500,
                "spent": amount,
                "reserved": 0,
                "available": 500 - amount,
            }
        stop(restarted)
        stop(seller)
        verdicts, hashes = {}, {}
        for rid, snapshot in zip(run_ids, snapshots):
            run = config["runs"][rid]
            evidence = export_run(spike, run, snapshot)
            verdict = verify_medusa(evidence, run["binding"]["goal"], 500)
            assert verdict["status"] == "COMPLETE", verdict
            path = spike.directory / f"stock-evidence-{rid}.json"
            path.write_text(json.dumps(evidence, indent=2) + "\n")
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            verdicts[rid] = verdict
        actions = read_rows(directory / "seller.sqlite3", "actions")
        assert len(actions) == 12 and all(a["status"] == "OBSERVED" for a in actions)
        final_stock = {
            name: {item: level(spike, f, item) for item in items} for name, f in fixtures.items()
        }
        expected = {
            "A": {"tent": 7, "light": 0},
            "B": {"tent": 7, "light": 4},
            "C": {"tent": 10, "light": 4},
        }
        for name, quantities in expected.items():
            for item, quantity in quantities.items():
                assert final_stock[name][item]["stocked_quantity"] == quantity
                assert final_stock[name][item]["reserved_quantity"] == 0
        report.update(
            passed=True,
            snapshots=snapshots,
            verdicts=verdicts,
            evidence_sha256=hashes,
            seller_actions=actions,
            final_stock=final_stock,
            process_pids=[p.pid for p in processes],
            medusa_version=spike.report["medusa_version"],
            package_lock_sha256=spike.report["package_lock_sha256"],
            source_sha256={
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in (
                    "scripts/commerce/stock_smoke.py",
                    "scripts/commerce/operating_fixture.py",
                    "scripts/commerce/contract_spike.py",
                    "src/rehearsal/commerce/gateway.py",
                    "src/rehearsal/commerce/server.py",
                    "src/rehearsal/commerce/seller.py",
                    "src/rehearsal/evaluation/medusa.py",
                    "src/rehearsal/operating/client.py",
                )
            },
        )
    finally:
        for process in reversed(processes):
            stop(process)
        for client in clients:
            client.close()
        spike.report["passed"] = report["passed"]
        spike.save()
        (spike.directory / "stock-report.json").write_text(json.dumps(report, indent=2) + "\n")
        for client in spike.clients.values():
            client.close()
        print(f"Evidence: {spike.directory.relative_to(ROOT)}")
    print("PASS: real stock changes, scripted full/partial recovery and independent ledgers.")


if __name__ == "__main__":
    main()
