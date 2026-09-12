"""Transaction invariants and independent journal replay; no cloud/model calls."""

import copy
import json
from pathlib import Path

import pytest

from rehearsal.serverless.domain import Rejected, digest, initial, transition
from rehearsal.serverless.verifier import verify


@pytest.fixture
def scenario():
    return json.loads(Path("scenarios/normal-v1.json").read_text())


class Experiment:
    def __init__(self, scenario):
        self.scenario = scenario
        self.state = initial("test-run", scenario, 100)
        self.events = [
            {
                "run_id": "test-run",
                "version": 0,
                "at": 100,
                "entries": [{"kind": "CREATED", "scenario": copy.deepcopy(scenario)}],
                "previous_sha256": None,
                "state_sha256": digest(self.state),
            }
        ]
        self.call("activate", {}, 100, actor="seller")

    def call(self, action, args, now=101, actor="buyer"):
        state, result, entries = transition(self.state, action, args, now, actor=actor)
        if entries:
            self.events.append(
                {
                    "run_id": "test-run",
                    "version": state["version"],
                    "at": now,
                    "entries": entries,
                    "previous_sha256": digest(self.state),
                    "state_sha256": digest(state),
                }
            )
        self.state = state
        return result

    def verdict(self):
        return verify(self.state, self.events, "test-run", self.scenario)

    def order(self, supplier="A", key="buy", items=None, now=101):
        quote = self.call(
            "get_quotes", {"supplier": supplier, "items": items or {"tent": 3, "light": 6}}, now
        )
        return self.call("create_order", {"quote_id": quote["id"], "idempotency_key": key}, now)


def test_delivery_requires_independent_seller_and_exactly_once_payment(scenario):
    run = Experiment(scenario)
    order = run.order()
    args = {"order_id": order["id"], "idempotency_key": "pay"}
    run.call("authorize_payment", args)
    assert run.verdict()["status"] == "INCOMPLETE"
    assert run.verdict()["reserved"] == 310
    version = run.state["version"]
    run.call("authorize_payment", args, 102)
    assert run.state["version"] == version
    run.call("advance", {}, 103, actor="seller")
    assert run.verdict()["spent"] == 310
    assert run.verdict()["status"] == "INCOMPLETE"
    run.call("advance", {}, 111, actor="seller")
    verdict = run.verdict()
    assert verdict["status"] == "COMPLETE" and verdict["reserved"] == 0
    assert verdict["received_on_time"] == {"tent": 3, "light": 6}
    assert run.state["suppliers"]["A"]["items"]["tent"]["stock"] == 7
    version = run.state["version"]
    run.call("advance", {}, 120, actor="seller")
    run.call("authorize_payment", args, 120)
    assert run.state["version"] == version


def test_stock_change_blocks_old_order_and_alternative_delivers(scenario):
    scenario["events"] = [
        {"id": "stock", "kind": "stock", "at_tick": 6, "supplier": "A", "item": "tent", "value": 0}
    ]
    run = Experiment(scenario)
    quote = run.call("get_quotes", {"supplier": "A", "items": {"tent": 3, "light": 6}})
    run.call("advance", {}, 106, actor="seller")
    with pytest.raises(Rejected, match="STOCK_UNAVAILABLE"):
        run.call("create_order", {"quote_id": quote["id"], "idempotency_key": "old"}, 107)
    order = run.order("B", now=107)
    run.call("authorize_payment", {"order_id": order["id"], "idempotency_key": "pay"}, 107)
    run.call("advance", {}, 122, actor="seller")
    assert run.verdict()["status"] == "COMPLETE"
    assert run.verdict()["spent"] == 380


def test_stock_change_between_order_and_payment_cannot_spend(scenario):
    scenario["events"] = [
        {"id": "stock", "kind": "stock", "at_tick": 6, "supplier": "A", "item": "tent", "value": 0}
    ]
    run = Experiment(scenario)
    order = run.order()
    run.call("advance", {}, 106, actor="seller")
    with pytest.raises(Rejected, match="STOCK_UNAVAILABLE"):
        run.call("authorize_payment", {"order_id": order["id"], "idempotency_key": "pay"}, 107)
    assert run.verdict()["spent"] == run.verdict()["reserved"] == 0


def test_budget_counts_authorized_reservations(scenario):
    run = Experiment(scenario)
    first = run.order()
    second = run.order("B", "second")
    run.call("authorize_payment", {"order_id": first["id"], "idempotency_key": "pay"})
    before = copy.deepcopy(run.state)
    with pytest.raises(Rejected, match="BUDGET_EXCEEDED"):
        run.call("authorize_payment", {"order_id": second["id"], "idempotency_key": "pay2"})
    assert run.state == before
    assert run.verdict()["reserved"] == 310


@pytest.mark.parametrize(
    "action,args",
    [
        ("advance", {}),
        ("activate", {}),
        ("observe_world", {"run_id": "other"}),
        ("get_quotes", {"supplier": "A", "items": {"tent": True}}),
        ("get_quotes", {"supplier": "A", "items": {"tent": 0}}),
        ("get_quotes", {"supplier": "A", "items": {"gold": 1}}),
        ("authorize_payment", {"order_id": "x", "idempotency_key": "k", "amount": 1}),
        ("authorize_payment", {"order_id": "x", "idempotency_key": "k", "recipient": "attacker"}),
    ],
)
def test_untrusted_tools_cannot_expand_scope_or_authority(scenario, action, args):
    run = Experiment(scenario)
    before = copy.deepcopy(run.state)
    with pytest.raises(Rejected):
        run.call(action, args)
    assert run.state == before


def test_expired_quote_and_conflicting_idempotency_rejected(scenario):
    run = Experiment(scenario)
    order = run.order()
    q = run.call("get_quotes", {"supplier": "B", "items": {"tent": 3}})
    with pytest.raises(Rejected, match="IDEMPOTENCY_CONFLICT"):
        run.call("create_order", {"quote_id": q["id"], "idempotency_key": "buy"})
    with pytest.raises(Rejected, match="QUOTE_EXPIRED"):
        run.call("authorize_payment", {"order_id": order["id"], "idempotency_key": "pay"}, 117)


def test_late_delivery_is_preserved_but_does_not_complete_goal(scenario):
    run = Experiment(scenario)
    order = run.order(now=150)
    run.call("authorize_payment", {"order_id": order["id"], "idempotency_key": "pay"}, 155)
    run.call("advance", {}, 166, actor="seller")
    assert run.state["inventory"] == {"tent": 3, "light": 6}
    assert run.verdict()["status"] == "INCOMPLETE"
    assert run.verdict()["received_on_time"] == {}


@pytest.mark.parametrize("damage", ["gap", "amount", "recipient", "inventory", "keys", "early"])
def test_independent_verifier_rejects_corrupted_records_even_with_final_hash(scenario, damage):
    run = Experiment(scenario)
    order = run.order()
    run.call("authorize_payment", {"order_id": order["id"], "idempotency_key": "pay"})
    run.call("advance", {}, 112, actor="seller")
    if damage == "gap":
        run.events.pop(2)
    elif damage == "amount":
        run.events[-1]["entries"][0]["amount"] = 1
    elif damage == "recipient":
        run.events[-1]["entries"][-1]["recipient"] = "attacker"
    elif damage == "inventory":
        run.state["inventory"]["tent"] = 999
    elif damage == "keys":
        run.state["payment_keys"] = {}
    else:
        run.events[-1]["at"] = 102
        for e in run.events[-1]["entries"]:
            e["tick"] = 2
    run.events[-1]["state_sha256"] = digest(run.state)
    assert run.verdict()["status"] == "INVALID"


def test_verifier_pins_operator_scenario_and_run(scenario):
    run = Experiment(scenario)
    altered = copy.deepcopy(scenario)
    altered["goal"]["recipient"] = "attacker"
    assert verify(run.state, run.events, "test-run", altered)["status"] == "INVALID"
    assert verify(run.state, run.events, "other", scenario)["status"] == "INVALID"
