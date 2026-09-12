#!/usr/bin/env python3
"""Reserve a complete external roster before B3 SDK learning; settle one real Medusa run."""

import json
import os

from model_session import ROOT, Session

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.commerce.learning_budget import B3Carryover
from rehearsal.evaluation import batch, external_batch
from rehearsal.experiments.b3 import BuyerFixture, ReviewerFixture
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN
from rehearsal.world.storage import identifier


def main():
    os.umask(0o077)
    directory = ROOT / ".local/evaluation" / identifier("external-b3")
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-b3-fixture",
        RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
        100000,
        max_model_calls=48,
        max_tool_calls=48,
    )
    training, cases = batch.generated_known_cases(ROOT, 2)
    for case in cases.values():
        case["goal"] = {
            "items": {"tent": 3, "light": 6},
            "deadline_tick": 120,
            "recipient": "venue",
            "budget": 500,
        }
    # Supplier conditions are deliberately NOT installed in Medusa in this accounting
    # smoke. Only the independent transaction may verify, never condition alignment.
    batch.prepare(
        directory,
        training,
        cases,
        1,
        settings,
        100000,
        "offline-scripted-model",
        evaluation_environment="external-medusa",
    )
    cell_id = "case-01-B3-r1"
    session, client = None, None
    result = {"passed": False, "real_model_calls": 0, "condition_alignment_verified": False}
    try:
        batch.write(directory / "before-learning.json", external_batch.summarize(directory))
        external_batch.learn(
            directory,
            cell_id,
            lambda kind, p: ReviewerFixture() if kind == "reviewer" else BuyerFixture(p),
        )
        batch.write(directory / "after-learning.json", external_batch.summarize(directory))
        path = directory / "runs" / cell_id
        session = Session(path / "policy.json", fixture=True)
        session_path = session.start()
        config = json.loads((session_path / "buyer-config.json").read_text())
        policy = B3Carryover(
            path / "learning", path / "policy.json", settings, "offline-scripted-model"
        ).frozen.policy
        client = OperatingClient(ORIGIN, config["run_id"], config["buyer_token"], timeout=10)
        external_batch.execute(directory, cell_id, BuyerFixture(policy), client)
        batch.write(directory / "awaiting-evidence.json", external_batch.summarize(directory))
        session.close("EXTERNAL_BATCH_SDK_FINISHED")
        final = external_batch.settle(directory, cell_id, session_path / "selection.json")
        assert final["status_counts"] == {"NOT_RUN": 7, "EXTERNAL_VERIFIED": 1}
        assert final["recorded_micro_usd"] == 1008 and final["held_micro_usd"] == 0
        assert final["methods"]["B3"]["condition_verified"] == 0
        assert session.record["verdict"]["spent"] == 310
        try:
            external_batch.learn(directory, "case-02-B3-r1", lambda *_: None)
        except ValueError as exc:
            assert str(exc) == "BATCH_COST_LIMIT"
            result["next_admission"] = str(exc)
        else:
            raise AssertionError("Second full-cap admission should be rejected")
        result.update(
            passed=True, report=final, session_directory=str(session_path.relative_to(ROOT))
        )
        batch.write(directory / "report.json", final)
    finally:
        if session:
            session.close("EXTERNAL_BATCH_SDK_CLEANUP")
        if client:
            client.close()
        batch.write(directory / "smoke.json", result)
        print(f"{'PASS' if result['passed'] else 'FAIL'} external roster: {directory}")


if __name__ == "__main__":
    main()
