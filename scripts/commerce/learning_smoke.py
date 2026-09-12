#!/usr/bin/env python3
"""Known B3 SDK learning -> original budget -> live local Medusa -> separate attestation."""

import json
import os

from model_session import ROOT, Session

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.commerce.learning_budget import B3Carryover, prepare
from rehearsal.commerce.model_runner import execute_http, write
from rehearsal.experiments.b3 import BuyerFixture, ReviewerFixture, run_b3
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN
from rehearsal.world.storage import identifier


def main():
    os.umask(0o077)
    directory = ROOT / ".local/commerce-learning" / identifier("b3-http")
    directory.mkdir(parents=True, mode=0o700)
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-b3-fixture",
        RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
        100000,
        max_model_calls=48,
        max_tool_calls=48,
    )
    report = {
        "scope": "known-scripted-B3-learning-and-actual-local-Medusa",
        "planned_external_runs": 1,
        "attempted_external_runs": 0,
        "real_model_calls": 0,
        "model_efficacy_verified": False,
        "passed": False,
    }
    session, client, carry = None, None, None
    try:
        report["learning"] = run_b3(
            BuyerFixture,
            lambda _: ReviewerFixture(),
            settings,
            directory / "learning",
            json.loads((ROOT / "scenarios/normal-v1.json").read_text()),
            "offline-scripted-model",
        )
        policy_path = directory / "policy.json"
        frozen = prepare(directory / "learning", policy_path, settings, "offline-scripted-model")
        carry = B3Carryover(directory / "learning", policy_path, settings, "offline-scripted-model")
        session = Session(policy_path, fixture=True)
        path = session.start()
        config = json.loads((path / "buyer-config.json").read_text())
        client = OperatingClient(ORIGIN, config["run_id"], config["buyer_token"], timeout=10)
        execution = ROOT / ".local/commerce-model" / config["run_id"]
        report["execution_directory"] = str(execution.relative_to(ROOT))
        report["session_directory"] = str(path.relative_to(ROOT))
        report["execution"] = execute_http(
            BuyerFixture(frozen.policy),
            settings,
            client,
            execution,
            config["expected_goal"],
            config["expected_budget"],
            frozen,
            "offline-scripted-model",
            carryover=carry,
        )
        session.close("SDK_LEARNING_SMOKE_FINISHED")
        attestation = json.loads((path / "attestation.json").read_text())
        assert attestation["success"] and session.record["state"] == "STOPPED"
        assert session.record["verdict"]["spent"] == 310
        assert carry.ledger.report()["recorded_micro_usd"] == 1008
        assert carry.ledger.report()["recorded_total_tokens"] == 720
        assert carry.ledger.report()["admitted_tool_calls"] == 31
        report.update(passed=True, attestation=attestation)
    finally:
        if session:
            session.close("SDK_LEARNING_SMOKE_CLEANUP")
        if client:
            client.close()
        if carry:
            report["accounting"] = carry.accounting()
            report["attempted_external_runs"] = report["accounting"]["attempted_external_runs"]
        write(directory / "report.json", report)
        print(f"{'PASS' if report['passed'] else 'FAIL'} B3/Medusa shared budget: {directory}")


if __name__ == "__main__":
    main()
