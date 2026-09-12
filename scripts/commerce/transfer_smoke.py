#!/usr/bin/env python3
"""Frozen B0 rule-policy execution on practice and independent Medusa known fixtures.

This is neither learned/LLM policy transfer nor a held-out performance evaluation.
Fault operators are outside the frozen controller and are retained in the record.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import httpx
from contract_spike import ROOT, Spike
from operating_fixture import prepare, start_gateway, start_seller

from rehearsal.agents.executor import purchasing_tools
from rehearsal.commerce.seller import ORDER_FIELDS, read_rows
from rehearsal.evaluation.medusa import verify_medusa
from rehearsal.evaluation.verifier import verify
from rehearsal.experiments.baseline import ToolPort, run_baseline
from rehearsal.experiments.frozen import freeze
from rehearsal.experiments.policy import Policy
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN, stop
from rehearsal.operating.tools import purchasing_http_tools
from rehearsal.world import World
from rehearsal.world.storage import identifier


class KnownPriceFault(ToolPort):
    def __init__(self, tools, change_price=None):
        super().__init__(tools)
        self.change_price = change_price
        self.injected = False

    def call(self, name, **arguments):
        result = super().call(name, **arguments)
        if (
            name == "get_quotes"
            and arguments["supplier"] == "A"
            and not self.injected
            and self.change_price
        ):
            self.change_price()
            self.injected = True
        return result


def scenario_for(partial, impossible=False):
    scenario = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    scenario["scenario_version"] = (
        "known-frozen-b0-partial-v1" if partial else "known-frozen-b0-price-loss-v1"
    )
    scenario["goal"].update(deadline_tick=120, recipient="venue")
    for name, supplier in scenario["suppliers"].items():
        supplier["lead_ticks"] = {"A": 4, "B": 6, "C": 8}[name]
    if partial:
        scenario["suppliers"]["A"]["items"]["light"]["stock"] = 0
        scenario["suppliers"]["B"]["items"]["tent"]["stock"] = 0
        for item in scenario["suppliers"]["C"]["items"].values():
            item["stock"] = 0
    if impossible:
        scenario["scenario_version"] = "known-frozen-b0-unavailable-required-item-v1"
        for supplier in scenario["suppliers"].values():
            supplier["items"]["tent"]["stock"] = 0
    return scenario


def practice(directory, frozen, partial, impossible=False):
    scenario = scenario_for(partial, impossible)
    world = World(directory)
    world.create_run("practice", scenario, policy_version=frozen.identifier)
    port = KnownPriceFault(
        purchasing_tools(world, "practice"),
        None
        if partial or impossible
        else lambda: world.shop.change_price("practice", "A", "tent", 100),
    )
    if not partial and not impossible:
        original = port.tools["authorize_payment"]

        def lost_response(**arguments):
            original(**arguments)
            return {"status": "UNKNOWN"}

        port.tools["authorize_payment"] = lost_response
    result = run_baseline(frozen, port, "fixed-b0")
    verdict = verify(directory, "practice", scenario, export_to=directory / "evidence.json")
    report = {
        "environment": "practice",
        "scenario": scenario,
        "run_id": "practice",
        "executor": result,
        "verdict": verdict.as_dict(),
        "real_model_calls": 0,
        "fault_scope": (
            "known-direct-simulator-stock-configuration"
            if partial or impossible
            else "known-direct-simulator-price-change-and-lost-observation"
        ),
    }
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def medusa(directory, frozen, partial, impossible=False):
    spike = Spike()
    spike.report["scope"] = "frozen-b0-known-fixture-operator-http"
    processes, clients = [], []
    report = {
        "environment": "medusa-operating",
        "run_id": spike.run_id,
        "scenario": scenario_for(partial, impossible),
        "real_model_calls": 0,
        "fault_scope": (
            "known-admin-inventory-configuration"
            if partial or impossible
            else "known-admin-catalogue-change-and-real-http-response-delay"
        ),
    }
    try:
        service_dir, credentials, config, fixtures = prepare(spike)
        run_id = next(iter(config["runs"]))
        run = config["runs"][run_id]
        if partial or impossible:
            empty = (
                (("A", "tent"), ("B", "tent"), ("C", "tent"))
                if impossible
                else (("A", "light"), ("B", "tent"), ("C", "tent"), ("C", "light"))
            )
            for name, item in empty:
                fixture = fixtures[name]
                iid = fixture["inventory"][("tent", "light").index(item)]
                lid = fixture["location"]["id"]
                spike.post(
                    f"/admin/inventory-items/{iid}/location-levels/{lid}", {"stocked_quantity": 0}
                )
        seller = start_seller(service_dir)
        processes.append(seller)
        gateway = start_gateway(service_dir)
        processes.append(gateway)
        tokens = credentials["runs"][run_id]
        client = OperatingClient(ORIGIN, run_id, tokens["buyer"], timeout=10)
        clients.append(client)
        a = fixtures["A"]

        def change_price():
            spike.post(
                f"/admin/products/{a['products'][0]}/variants/{a['variants'][0]}",
                {"prices": [{"currency_code": "usd", "amount": 100}]},
            )

        port = KnownPriceFault(
            purchasing_http_tools(client), None if partial or impossible else change_price
        )
        if not partial and not impossible:
            original = port.tools["authorize_payment"]

            def delayed_payment(**arguments):
                with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=5) as operator:
                    response = operator.post(
                        f"/admin/runs/{run_id}/faults/payment-response-delay",
                        headers={"Authorization": "Bearer " + tokens["control"]},
                        json={"delay_ms": 1200},
                    )
                    response.raise_for_status()
                previous = client.http.timeout
                client.http.timeout = httpx.Timeout(0.4)
                try:
                    return original(**arguments)
                finally:
                    client.http.timeout = previous

            port.tools["authorize_payment"] = delayed_payment
        started = time.monotonic()
        result = run_baseline(frozen, port, "fixed-b0")
        report["executor"] = result
        report["execution_seconds"] = time.monotonic() - started
        # Quiesce both processes before collecting the mapping and budget evidence.
        stop(gateway)
        stop(seller)
        evidence = {
            "binding": run["binding"],
            "external_orders": [],
            "tables": {},
            "captured_at_tick": int(
                max(
                    0,
                    time.time()
                    - json.loads(
                        read_rows(Path(run["directory"]) / "medusa.sqlite3", "binding")[0]["data"]
                    )["started_at"],
                )
            ),
            "scope": "known-frozen-B0-external-backend",
        }
        for filename, tables in (
            ("medusa.sqlite3", ("purchases", "quotes")),
            ("payments.sqlite3", ("accounts", "intents")),
        ):
            for table in tables:
                evidence["tables"][table] = read_rows(Path(run["directory"]) / filename, table)
        for purchase in evidence["tables"]["purchases"]:
            if purchase["external_id"]:
                evidence["external_orders"].append(
                    spike.get(f"/admin/orders/{purchase['external_id']}?fields={ORDER_FIELDS}")[
                        "order"
                    ]
                )
        evidence["seller_actions"] = read_rows(service_dir / "seller.sqlite3", "actions")
        report["verdict"] = verify_medusa(evidence, run["binding"]["goal"], 500)
        report["local_service_run"] = str(spike.directory.relative_to(ROOT))
        report["medusa_version"] = spike.report["medusa_version"]
        report["package_lock_sha256"] = spike.report["package_lock_sha256"]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    finally:
        for process in reversed(processes):
            stop(process)
        for client in clients:
            client.close()
        spike.save()
        for client in spike.clients.values():
            client.close()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Recorded {directory.relative_to(ROOT)}", flush=True)
    return report


def main():
    os.umask(0o077)
    directory = ROOT / ".local/transfer" / identifier("b0")
    directory.mkdir(parents=True, mode=0o700)
    policies = {
        "before": freeze(Policy(refresh_quote_before_order=False), directory / "before.json", ROOT),
        "revised": freeze(
            Policy(),
            directory / "revised.json",
            ROOT,
            {"known-cw04-reexperiment": ROOT / "evidence/cw04-offline/after/experiment.json"},
        ),
    }
    rows = []
    for name, policy_name, partial, impossible, amount, runtime_status in (
        ("before-price-loss", "before", False, False, 0, "INCOMPLETE"),
        ("revised-price-loss", "revised", False, False, 380, "GOAL_OBSERVED"),
        ("revised-partial", "revised", True, False, 360, "GOAL_OBSERVED"),
        ("revised-unavailable-item", "revised", False, True, 0, "INCOMPLETE"),
    ):
        frozen = policies[policy_name]
        for backend, execute in (("practice", practice), ("medusa", medusa)):
            path = directory / name / backend
            report = execute(path, frozen, partial, impossible)
            row = {
                "case": name,
                "backend": backend,
                "frozen_id": frozen.identifier,
                "runtime": report["executor"]["status"],
                "verdict": report["verdict"]["status"],
                "spent": report["verdict"]["spent"],
                "tool_calls": len(report["executor"]["trace"]),
                "report_sha256": hashlib.sha256((path / "report.json").read_bytes()).hexdigest(),
                "evidence_sha256": hashlib.sha256(
                    (path / "evidence.json").read_bytes()
                ).hexdigest(),
            }
            rows.append(row)
            (directory / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
            assert row["runtime"] == runtime_status, row
            assert row["spent"] == amount, row
            assert row["verdict"] == ("INCOMPLETE" if amount == 0 else "COMPLETE"), row
            if impossible:
                assert report["executor"]["reason"] == "NO_EXECUTABLE_QUOTE", row
                assert not report["executor"]["orders"], row
                assert not any(
                    t["tool"] in {"create_order", "authorize_payment"}
                    for t in report["executor"]["trace"]
                )
            if not partial and not impossible and amount:
                trace = report["executor"]["trace"]
                assert any(
                    t["tool"] == "authorize_payment" and t["result"]["status"] == "UNKNOWN"
                    for t in trace
                )
                assert sum(t["tool"] == "authorize_payment" for t in trace) == 1
            print(f"PASS {name}/{backend}: {row['runtime']}, spent={amount}", flush=True)
    summary = {
        "scope": "known-fixture-B0-policy-contract-transfer-not-learned-or-LLM-transfer",
        "real_model_calls": 0,
        "cases": rows,
        "passed": True,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/commerce/transfer_smoke.py",
                "scripts/commerce/operating_fixture.py",
                "src/rehearsal/commerce/gateway.py",
                "src/rehearsal/commerce/seller.py",
                "src/rehearsal/commerce/server.py",
                "src/rehearsal/evaluation/medusa.py",
            )
        },
    }
    (directory / "report.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"PASS frozen B0 contract transfer. Evidence: {directory.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
