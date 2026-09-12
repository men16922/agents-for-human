from __future__ import annotations

import json
from pathlib import Path

import pytest

from rehearsal.evaluation.verifier import verify
from rehearsal.world import World
from rehearsal.world.fork import fork_world
from rehearsal.world.storage import ContractError


@pytest.fixture
def source(tmp_path):
    scenario = json.loads(
        (Path(__file__).resolve().parents[2] / "scenarios/normal-v1.json").read_text()
    )
    world = World(tmp_path / "source")
    world.create_run("parent", scenario, environment="operating-test")
    world.create_run("unrelated", scenario)
    quote = world.shop.quote("parent", "A", scenario["goal"]["items"])
    order = world.shop.create_order("parent", quote["id"], "purchase")
    payment = world.authorize_payment("parent", order["id"], "pay")
    return world, scenario, order, payment


def test_fork_isolates_pending_state_and_other_runs(source, tmp_path):
    parent, scenario, order, payment = source
    before = parent.snapshot("parent")
    child, manifest = fork_world(parent, "parent", tmp_path / "child", "child", "policy-1")
    assert manifest["status"] == "READY"
    assert child.snapshot("child")["balance"]["reserved"] == 310
    assert child.shop.run("child")["metadata"]["environment"] == "practice"
    with pytest.raises(ContractError, match="NOT_FOUND"):
        child.shop.run("unrelated")
    with pytest.raises(ContractError, match="NOT_FOUND"):
        child.payments.balance("parent")
    child.settle_payment("child", payment["id"])
    child.advance("child", 10)
    assert verify(tmp_path / "child", "child", scenario).status == "COMPLETE"
    assert parent.snapshot("parent") == before
    assert parent.shop.order("parent", order["id"])["status"] == "PAYMENT_PENDING"
    assert not (
        {e["event_id"] for e in child.shop.events("child")}
        & {e["event_id"] for e in parent.shop.events("parent")}
    )
    assert not (
        {e["event_id"] for e in child.payments.events("child")}
        & {e["event_id"] for e in parent.payments.events("parent")}
    )


def test_fork_recovers_settled_but_not_projected_payment(source, tmp_path):
    parent, scenario, _, payment = source
    parent.payments.settle("parent", payment["id"], 0)
    child, _ = fork_world(parent, "parent", tmp_path / "child", "child", "policy-1")
    child.synchronize("child")
    child.synchronize("child")
    child.advance("child", 10)
    assert verify(tmp_path / "child", "child", scenario).status == "COMPLETE"
    assert parent.shop.inventory("parent") == {}


def test_already_delivered_fork_keeps_inventory_and_deduplication(source, tmp_path):
    parent, scenario, _, payment = source
    parent.settle_payment("parent", payment["id"])
    parent.advance("parent", 10)
    child, _ = fork_world(parent, "parent", tmp_path / "child", "child", "policy-1")
    child.synchronize("child")
    child.advance("child", 20)
    assert child.shop.inventory("child") == {"tent": 3, "light": 6}
    assert verify(tmp_path / "child", "child", scenario).status == "COMPLETE"
    with pytest.raises(ContractError, match="FORK_DESTINATION_EXISTS"):
        fork_world(parent, "parent", tmp_path / "child", "another", "policy-1")


def test_fork_rejects_unknown_schema_before_creating_destination(source, tmp_path):
    parent, _, _, _ = source
    with parent.shop.transaction() as db:
        db.execute("CREATE TABLE future_state (run_id TEXT)")
    with pytest.raises(ContractError, match="UNSUPPORTED_FORK_SCHEMA"):
        fork_world(parent, "parent", tmp_path / "child", "child", "policy-1")
    assert not (tmp_path / "child").exists()


def test_interrupted_fork_cannot_be_opened_as_a_valid_world(source, tmp_path, monkeypatch):
    import sqlite3

    from rehearsal.world import fork as implementation

    parent, _, _, _ = source
    collect = implementation._collect

    def corrupted_copy(db, tables, run_id):
        data = collect(db, tables, run_id)
        if tables == implementation.PAYMENT_TABLES:
            data["accounts"][0]["spent"] = 501
        return data

    monkeypatch.setattr(implementation, "_collect", corrupted_copy)
    destination = tmp_path / "interrupted"
    with pytest.raises(sqlite3.IntegrityError):
        fork_world(parent, "parent", destination, "child", "policy-1")
    assert json.loads((destination / "fork.json").read_text())["status"] == "CREATING"
    with pytest.raises(ContractError, match="INCOMPLETE_FORK"):
        World(destination)
