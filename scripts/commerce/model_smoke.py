#!/usr/bin/env python3
"""SDK fixture -> metered HTTP buyer -> actual Medusa -> separate export attestation."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from contract_spike import ROOT, Spike, scrub
from operating_fixture import prepare, start_gateway, start_seller
from stock_smoke import export_run

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.commerce.model_runner import attest, digest, execute_http, write
from rehearsal.experiments.b3 import BuyerFixture
from rehearsal.experiments.frozen import freeze
from rehearsal.experiments.policy import Policy
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN, stop


class RecordingBuyer(OperatingClient):
    def __init__(self, run_id, token, path):
        super().__init__(ORIGIN, run_id, token, timeout=10)
        self.path = path

    def request(self, method, path, body=None):
        record = {"method": method, "path": f"/runs/{self.run_id}/{path}", "request": scrub(body)}
        previous = self.http.timeout
        if method == "POST" and path == "payments":
            self.http.timeout = httpx.Timeout(0.4)
        try:
            value = super().request(method, path, body)
            record["response"] = scrub(value)
            return value
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            raise
        finally:
            self.http.timeout = previous
            with self.path.open("a") as output:
                output.write(json.dumps(record) + "\n")


def main():
    os.umask(0o077)
    spike = Spike()
    spike.report["scope"] = "actual-medusa-metered-sdk-fixture-operator"
    path = spike.directory / "model-http"
    path.mkdir(mode=0o700)
    processes, buyer = [], None
    report = {
        "passed": False,
        "scope": "actual-medusa-with-deterministic-sdk-fixture",
        "real_model_calls": 0,
        "model_efficacy_verified": False,
    }
    try:
        directory, credentials, config, _ = prepare(spike)
        run_id = next(iter(config["runs"]))
        run = config["runs"][run_id]
        seller = start_seller(directory)
        processes.append(seller)
        gateway = start_gateway(directory)
        processes.append(gateway)
        tokens = credentials["runs"][run_id]
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=10) as operator:
            response = operator.post(
                f"/admin/runs/{run_id}/faults/payment-response-delay",
                headers={"Authorization": "Bearer " + tokens["control"]},
                json={"delay_ms": 1200},
            )
            response.raise_for_status()
        frozen = freeze(Policy(), path / "policy.json", ROOT)
        buyer = RecordingBuyer(run_id, tokens["buyer"], path / "buyer-http.jsonl")
        settings = ModelSettings(
            "offline",
            "offline",
            "offline-b3-fixture",
            RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
            100000,
            max_model_calls=48,
            max_tool_calls=48,
        )
        result = execute_http(
            BuyerFixture(Policy()),
            settings,
            buyer,
            path / "execution",
            run["binding"]["goal"],
            500,
            frozen,
            "offline-scripted-model",
        )
        report["execution"] = result
        snapshot = buyer.observe_world()
        stop(gateway)
        stop(seller)
        evidence = export_run(spike, run, snapshot)
        evidence["scope"] = "actual-medusa-independent-export-after-metered-sdk-fixture"
        write(path / "evidence.json", evidence)
        write(
            path / "selection.json",
            {
                "run_id": run_id,
                "expected_goal": run["binding"]["goal"],
                "expected_budget": 500,
                "artifact_path": "evidence.json",
                "sha256": digest(path / "evidence.json"),
            },
        )
        reviewed = attest(path / "execution", path / "selection.json")
        write(path / "attestation.json", reviewed)
        assert result["transaction_status"] == "NOT_VERIFIED" and not result["success"]
        assert reviewed["success"] and reviewed["evidence_review"]["verdict"]["spent"] == 310
        calls = [json.loads(line) for line in (path / "buyer-http.jsonl").read_text().splitlines()]
        payments = [c for c in calls if c["method"] == "POST" and c["path"].endswith("/payments")]
        assert len(payments) == 1 and payments[0]["error_type"] == "ReadTimeout"
        assert all("/admin/" not in c["path"] for c in calls)
        report.update(
            passed=True,
            attestation=reviewed,
            http_requests=len(calls),
            source_hashes={str(Path(__file__).relative_to(ROOT)): digest(Path(__file__))},
        )
    finally:
        for process in reversed(processes):
            stop(process)
        if buyer:
            buyer.close()
        spike.save()
        for client in spike.clients.values():
            client.close()
        write(path / "report.json", report)
        print(
            f"{'PASS' if report['passed'] else 'FAILED'} SDK/Medusa HTTP buyer: "
            f"{path.relative_to(ROOT)}"
        )


if __name__ == "__main__":
    main()
