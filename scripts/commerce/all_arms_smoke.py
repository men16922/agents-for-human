#!/usr/bin/env python3
"""Four prospective comparison arms over fresh local Medusa sessions, without paid models."""

import json
import os

from model_session import ROOT, Session

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.commerce.learning_budget import BudgetCarryover
from rehearsal.evaluation import batch, external_batch
from rehearsal.evaluation.frozen_run import fixture_factory
from rehearsal.experiments.frozen import FrozenPolicy
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN
from rehearsal.world.storage import identifier


def main():
    os.umask(0o077)
    directory = ROOT / ".local/evaluation" / identifier("external-arms")
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-evaluation-fixture",
        RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
        100000,
        max_model_calls=48,
        max_tool_calls=48,
    )
    training, cases = batch.generated_known_cases(ROOT, 1)
    cases["case-01"]["goal"] = {
        "items": {"tent": 3, "light": 6},
        "deadline_tick": 120,
        "recipient": "venue",
        "budget": 500,
    }
    batch.prepare(
        directory,
        training,
        cases,
        1,
        settings,
        500000,
        "offline-scripted-model",
        evaluation_environment="external-medusa",
    )
    result = {
        "passed": False,
        "real_model_calls": 0,
        "condition_alignment_verified": False,
        "sessions": {},
    }
    batch.write(directory / "before.json", external_batch.summarize(directory))
    expected_costs = {"B0": 0, "B1": 392, "B2": 1036, "B3": 1008}
    try:
        for method in ("B0", "B1", "B2", "B3"):
            cell = f"case-01-{method}-r1"
            path = directory / "runs" / cell
            session, client = None, None
            try:
                learning = external_batch.learn(directory, cell, fixture_factory)
                assert learning["status"] == "WAITING_EXTERNAL"
                policy = FrozenPolicy.load(path / "policy.json", ROOT).policy
                BudgetCarryover(
                    path / "learning",
                    path / "policy.json",
                    settings,
                    "offline-scripted-model",
                    method,
                )
                session = Session(path / "policy.json", fixture=True)
                session_path = session.start()
                config = json.loads((session_path / "buyer-config.json").read_text())
                result["sessions"][method] = str(session_path.relative_to(ROOT))
                client = OperatingClient(
                    ORIGIN, config["run_id"], config["buyer_token"], timeout=10
                )
                external_batch.execute(
                    directory,
                    cell,
                    None if method == "B0" else fixture_factory("buyer", policy),
                    client,
                )
                session.close("ALL_ARMS_SDK_FINISHED")
                final = external_batch.settle(directory, cell, session_path / "selection.json")
                assert session.record["verdict"]["spent"] == 310
                runtime = json.loads((path / "execution/report.json").read_text())
                assert runtime["usage"]["recorded_micro_usd"] == expected_costs[method]
                assert final["methods"][method]["transaction_verified"] == 1
                assert final["methods"][method]["condition_verified"] == 0
                batch.write(directory / f"after-{method}.json", final)
            finally:
                if session:
                    session.close("ALL_ARMS_SDK_CLEANUP")
                if client:
                    client.close()
        final = external_batch.summarize(directory)
        assert final["status_counts"] == {"EXTERNAL_VERIFIED": 4}
        assert final["recorded_micro_usd"] == 2436 and final["held_micro_usd"] == 0
        batch.write(directory / "report.json", final)
        result.update(passed=True, report=final)
    finally:
        batch.write(directory / "smoke.json", result)
        print(f"{'PASS' if result['passed'] else 'FAIL'} external four arms: {directory}")


if __name__ == "__main__":
    main()
