"""CW02 known cases, not held-out evaluation or an LLM benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from rehearsal.world import World
from rehearsal.world.client import observe_payment
from rehearsal.world.storage import ContractError, Json, identifier

from .verifier import verify, verify_export


def run_case(directory: Path, case: str, scenario: Json) -> Json:
    world = World(directory)
    run_id = case
    world.create_run(run_id, scenario, policy_version="handwritten-fixture-v1")
    notes: list[str] = []
    if case == "F06":
        for supplier in scenario["suppliers"]:
            try:
                world.shop.quote(run_id, supplier, scenario["goal"]["items"])
            except ContractError as exc:
                assert exc.code == "INSUFFICIENT_STOCK"
                notes.append(f"{supplier}: {exc.code}")
            else:
                raise AssertionError("Impossible-stock fixture unexpectedly quotable")
        world.advance(run_id, scenario["goal"]["deadline_tick"])
    else:
        quote = world.shop.quote(run_id, "A", scenario["goal"]["items"])
        if case == "F01":
            world.shop.change_price(run_id, "A", "tent", 100)
            try:
                world.shop.create_order(run_id, quote["id"], "supplies")
            except ContractError as exc:
                assert exc.code == "STALE_QUOTE"
                notes.append(exc.code)
            else:
                raise AssertionError("Stale quote unexpectedly accepted")
            candidates = [
                world.shop.quote(run_id, s, scenario["goal"]["items"])
                for s in scenario["suppliers"]
            ]
            quote = min(candidates, key=lambda q: q["amount"])
        order = world.shop.create_order(run_id, quote["id"], "supplies")

        def commit() -> Json:
            payment = world.authorize_payment(run_id, order["id"], "stable-intent")
            return world.settle_payment(run_id, payment["id"])

        if case == "F02":

            def drop_response() -> Json:
                commit()
                raise TimeoutError("synthetic client boundary response loss")

            observation = observe_payment(drop_response)
            assert observation.status == "UNKNOWN"
            notes.append("client: UNKNOWN; no replacement payment")
            observation = observe_payment(lambda: world.payments.for_order(run_id, order["id"]))
            assert observation.status == "SETTLED"
            notes.append("explicit order-linked query: SETTLED")
        else:
            commit()
        world.advance(run_id, quote["lead_ticks"])
    result = verify(directory, run_id, scenario, export_to=directory / "evidence.json")
    assert result.status == ("FAILED" if case == "F06" else "COMPLETE"), result
    assert verify_export(directory / "evidence.json") == result
    return {"case": case, "notes": notes, "verdict": result.as_dict()}


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    batch = root / ".local/evaluation" / identifier("cw02")
    reports = []
    for case in ("normal", "F01", "F02", "F06"):
        scenario = json.loads((root / "scenarios/normal-v1.json").read_text())
        if case == "F06":
            scenario["scenario_version"] = "impossible-stock-v1"
            for supplier in scenario["suppliers"].values():
                supplier["items"]["tent"]["stock"] = 0
        reports.append(run_case(batch / case, case, scenario))
    (batch / "report.json").write_text(
        json.dumps(
            {
                "scope": "CW02-handwritten-known-fixtures-no-model-no-transfer",
                "cases": reports,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"PASS: normal/F01/F02 completed; F06 correctly failed with zero spend. Evidence: {batch}"
    )


if __name__ == "__main__":
    main()
