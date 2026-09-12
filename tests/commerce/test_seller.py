"""Seller side-effect recovery against mutable copies of actual Medusa payloads."""

import copy
import json
from pathlib import Path

import httpx
import pytest

from rehearsal.commerce.seller import Seller, read_rows
from rehearsal.world.storage import ContractError


class AdminStandIn:
    def __init__(self, final):
        self.final = copy.deepcopy(final)
        self.order = copy.deepcopy(final)
        self.order.update(
            payment_status="authorized", fulfillment_status="not_fulfilled", fulfillments=[]
        )
        collection = self.order["payment_collections"][0]
        collection["captured_amount"] = 0
        collection["payments"][0]["captures"] = []
        self.posts = []
        self.drop_before = self.drop_after = False

    def call(self, method, path, body=None):
        if method == "GET":
            return {"order": copy.deepcopy(self.order)}
        self.posts.append(path)
        if self.drop_before:
            raise httpx.ReadTimeout("Request outcome unavailable")
        if path.endswith("/capture"):
            self.order["payment_status"] = "captured"
            self.order["payment_collections"] = copy.deepcopy(self.final["payment_collections"])
        elif path.endswith("/fulfillments"):
            self.order["fulfillments"] = copy.deepcopy(self.final["fulfillments"])
            self.order["fulfillments"][0].update(shipped_at=None, delivered_at=None)
            self.order["fulfillment_status"] = "fulfilled"
        elif path.endswith("/shipments"):
            self.order["fulfillments"][0]["shipped_at"] = self.final["fulfillments"][0][
                "shipped_at"
            ]
            self.order["fulfillment_status"] = "shipped"
        elif path.endswith("/mark-as-delivered"):
            self.order["fulfillments"] = copy.deepcopy(self.final["fulfillments"])
            self.order["fulfillment_status"] = "delivered"
        else:
            raise AssertionError(path)
        if self.drop_after:
            self.drop_after = False
            raise httpx.ReadTimeout("Committed, but response lost")
        return {}


@pytest.fixture
def setup(tmp_path):
    evidence = json.loads(
        (
            Path(__file__).resolve().parents[2] / "tests/fixtures/commerce/seller.json"
        ).read_text()
    )
    external = evidence["external_orders"][0]
    api = AdminStandIn(external)
    seller = Seller({"directory": str(tmp_path), "runs": {}}, api)
    clock = [1000.0]
    seller.now = lambda: clock[0]
    purchase = evidence["tables"]["purchases"][0]
    quote = next(
        json.loads(q["data"])
        for q in evidence["tables"]["quotes"]
        if q["id"] == purchase["quote_id"]
    )
    intent = evidence["tables"]["intents"][0]
    intent["status"] = "RESERVED"
    run = {
        "binding": evidence["binding"],
        "locations": {quote["supplier"]: external["fulfillments"][0]["location_id"]},
    }
    return seller, api, clock, (run, purchase, quote, intent)


def test_independent_due_time_and_restart_do_not_repeat_mutations(setup):
    seller, api, clock, args = setup
    seller.process(*args)
    assert len(api.posts) == 3 and api.order["fulfillment_status"] == "shipped"
    due = read_rows(seller.db.path, "schedules")[0]["due_at"]
    clock[0] = due - 0.1
    seller.process(*args)
    assert len(api.posts) == 3
    resumed = Seller(seller.config, api)
    resumed.now = lambda: due
    resumed.process(*args)
    resumed.process(*args)
    assert len(api.posts) == 4 and api.order["fulfillment_status"] == "delivered"
    assert read_rows(seller.db.path, "schedules")[0]["due_at"] == due
    assert all(a["status"] == "OBSERVED" for a in read_rows(seller.db.path, "actions"))


def test_committed_lost_response_is_reconciled_without_second_capture(setup):
    seller, api, _, args = setup
    api.drop_after = True
    with pytest.raises(httpx.ReadTimeout):
        seller.process(*args)
    assert read_rows(seller.db.path, "actions")[0]["status"] == "STARTED"
    seller.process(*args)
    assert sum(path.endswith("/capture") for path in api.posts) == 1
    assert api.order["fulfillment_status"] == "shipped"


def test_unobserved_action_never_blindly_retries(setup):
    seller, api, _, args = setup
    api.drop_before = True
    with pytest.raises(httpx.ReadTimeout):
        seller.process(*args)
    api.drop_before = False
    with pytest.raises(ContractError, match="SELLER_ACTION_UNCERTAIN_OR_REGRESSED"):
        seller.process(*args)
    assert len(api.posts) == 1
    assert read_rows(seller.db.path, "actions")[0]["status"] == "STARTED"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda o: o.update(customer_id="customer_other"),
        lambda o: o.update(total=1),
        lambda o: o["metadata"].update(rehearsal_run="another_run"),
    ],
)
def test_invalid_order_never_reaches_admin_mutation(setup, mutation):
    seller, api, _, args = setup
    mutation(api.order)
    with pytest.raises(ContractError, match="SELLER_ORDER_CONTRACT_MISMATCH"):
        seller.process(*args)
    assert api.posts == []
    assert read_rows(seller.db.path, "actions") == []


def test_settled_payment_regression_does_not_issue_capture(setup):
    seller, api, _, args = setup
    args[3]["status"] = "SETTLED"
    with pytest.raises(ContractError, match="SELLER_PAYMENT_REGRESSION"):
        seller.process(*args)
    assert not api.posts


def test_foreign_fulfillment_cannot_be_shipped_by_worker(setup):
    seller, api, _, args = setup
    api.order = copy.deepcopy(api.final)
    api.order["fulfillments"][0]["location_id"] = "location_foreign"
    with pytest.raises(ContractError, match="SELLER_FULFILLMENT_SCOPE_MISMATCH"):
        seller.process(*args)
    assert not api.posts
