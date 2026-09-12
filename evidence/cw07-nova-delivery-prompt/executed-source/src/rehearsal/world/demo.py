"""Run the hand-calculated synthetic fixture and retain its SQLite evidence."""

from __future__ import annotations

import json
from pathlib import Path

from . import World
from .storage import Json, identifier


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    fixture = json.loads((root / "scenarios/normal-v1.json").read_text())
    run_id = identifier("normal")
    directory = root / ".local/world" / run_id
    world = World(directory)
    world.create_run(run_id, fixture)
    quote = world.shop.quote(run_id, "A", fixture["goal"]["items"])
    order = world.shop.create_order(run_id, quote["id"], "event-supplies")
    payment = world.authorize_payment(run_id, order["id"], "event-supplies-payment")
    world.settle_payment(run_id, payment["id"])
    world.advance(run_id, 10)
    report: Json = {
        "scope": "CW01-local-synthetic-fixture",
        "snapshot": world.snapshot(run_id),
        "order": world.shop.order(run_id, order["id"]),
        "shop_events": world.shop.events(run_id),
        "payment_events": world.payments.events(run_id),
    }
    assert report["snapshot"]["inventory"] == {"tent": 3, "light": 6}
    assert report["snapshot"]["balance"]["spent"] == 310
    assert report["snapshot"]["balance"]["reserved"] == 0
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: synthetic delivery at tick 10; spent=310, reserved=0. Evidence: {directory}")


if __name__ == "__main__":
    main()
