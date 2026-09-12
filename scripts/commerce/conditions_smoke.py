#!/usr/bin/env python3
"""Install declared static conditions, capture provider GETs, and evaluate fresh local sessions."""

import json
import os
import threading
import time
from copy import deepcopy

from model_session import ROOT, Session, request_refresh

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.evaluation import batch, external_batch
from rehearsal.evaluation.frozen_run import fixture_factory
from rehearsal.experiments.frozen import FrozenPolicy
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN
from rehearsal.world.storage import identifier


def cases_for():
    training = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    changed = deepcopy(training)
    changed["scenario_version"] = "declared-static-price-stock-shipping-lead-v1"
    changed["goal"].update(budget=600, deadline_tick=120, recipient="venue")
    for name, prices, stocks, shipping, lead in (
        ("A", (65, 21), (0, 10), 11, 3),
        ("B", (85, 25), (8, 9), 25, 7),
        ("C", (100, 35), (4, 7), 30, 12),
    ):
        supplier = changed["suppliers"][name]
        supplier.update(shipping=shipping, lead_ticks=lead)
        for item, price, stock in zip(("tent", "light"), prices, stocks):
            supplier["items"][item].update(price=price, stock=stock)
    impossible = deepcopy(changed)
    impossible["scenario_version"] = "declared-static-no-tents-v1"
    for supplier in impossible["suppliers"].values():
        supplier["items"]["tent"]["stock"] = 0
    return training, {"changed": changed, "impossible": impossible}


def main():
    os.umask(0o077)
    directory = ROOT / ".local/evaluation" / identifier("conditions")
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-evaluation-fixture",
        RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
        100000,
        max_model_calls=48,
        max_tool_calls=48,
    )
    training, cases = cases_for()
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
    result = {"passed": False, "real_model_calls": 0, "sessions": {}, "checks": {}}
    batch.write(directory / "before.json", external_batch.summarize(directory))
    selections = [("changed", method) for method in ("B0", "B1", "B2", "B3")]
    selections.append(("impossible", "B0"))
    try:
        for case_id, method in selections:
            cell = f"{case_id}-{method}-r1"
            path = directory / "runs" / cell
            session, client, worker = None, None, None
            stopping = threading.Event()
            try:
                learning = external_batch.learn(directory, cell, fixture_factory)
                assert learning["status"] == "WAITING_EXTERNAL"
                policy = FrozenPolicy.load(path / "policy.json", ROOT).policy
                session = Session(path / "policy.json", fixture=True, case=cases[case_id])
                session_path = session.start()
                worker = threading.Thread(target=session.wait, args=(stopping,))
                worker.start()
                result["sessions"][cell] = str(session_path.relative_to(ROOT))
                config = json.loads((session_path / "buyer-config.json").read_text())
                client = OperatingClient(
                    ORIGIN, config["run_id"], config["buyer_token"], timeout=10
                )
                model = None if method == "B0" else fixture_factory("buyer", policy)
                conditions = session_path / session.record["conditions_path"]
                if cell == "changed-B0-r1":
                    bad = json.loads(conditions.read_text())
                    bad["catalog_get"]["response"]["products"][0]["variants"][0][
                        "inventory_quantity"
                    ] += 1
                    bad_path = directory / "rejected-provider-mismatch.json"
                    batch.write(bad_path, bad)
                    try:
                        external_batch.execute(
                            directory, cell, model, client, condition_path=bad_path
                        )
                    except ValueError as exc:
                        assert "Store GET" in str(exc)
                        result["checks"]["mismatch_before_purchase_rejected"] = True
                    else:
                        raise AssertionError("Mismatched observation admitted")
                    end_tick = json.loads(conditions.read_text())["after"]["tick"]
                    while client.observe_world()["tick"] <= end_tick + 5:
                        time.sleep(0.2)
                    try:
                        external_batch.execute(
                            directory, cell, model, client, condition_path=conditions
                        )
                    except ValueError as exc:
                        assert "too old" in str(exc)
                        result["checks"]["stale_before_attempt_rejected"] = True
                    else:
                        raise AssertionError("Stale observation admitted")
                    assert not (path / "execution").exists()
                    assert request_refresh(session_path) == 0
                    conditions = session_path / session.record["conditions_path"]
                    result["checks"]["live_read_only_refresh"] = str(conditions.relative_to(ROOT))
                external_batch.execute(directory, cell, model, client, condition_path=conditions)
                stopping.set()
                worker.join(5)
                assert not worker.is_alive()
                session.close("STATIC_CONDITION_SMOKE_FINISHED")
                final = external_batch.settle(directory, cell, session_path / "selection.json")
                verdict = session.record["verdict"]
                assert verdict["spent"] == (430 if case_id == "changed" else 0)
                assert verdict["status"] == ("COMPLETE" if case_id == "changed" else "INCOMPLETE")
                selected = next(c for c in final["cells"] if c["id"] == cell)
                assert selected["condition_alignment_verified"]
                assert selected["external_transaction_verified"] == (case_id == "changed")
                batch.write(directory / f"after-{cell}.json", final)
            finally:
                stopping.set()
                if worker:
                    worker.join(5)
                if session:
                    session.close("STATIC_CONDITION_SMOKE_CLEANUP")
                if client:
                    client.close()
        final = external_batch.summarize(directory)
        assert final["status_counts"] == {
            "EXTERNAL_VERIFIED": 4,
            "EXTERNAL_INCOMPLETE": 1,
            "NOT_RUN": 3,
        }
        assert sum(m["condition_verified"] for m in final["methods"].values()) == 5
        assert final["held_micro_usd"] == 0
        batch.write(directory / "report.json", final)
        result.update(passed=True, report=final)
    finally:
        batch.write(directory / "smoke.json", result)
        print(f"{'PASS' if result['passed'] else 'FAIL'} declared static conditions: {directory}")


if __name__ == "__main__":
    main()
