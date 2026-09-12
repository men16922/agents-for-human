import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from test_conditions import condition  # noqa: F401

from rehearsal.evaluation.condition_events import validate_case, verify_events, verify_receipt
from rehearsal.evaluation.conditions import fingerprint, verify_conditions, verify_start

ROOT = Path(__file__).parents[2]


@pytest.fixture
def event_case(condition):  # noqa: F811
    case, initial, snapshot = condition
    event = {
        "id": "stockA",
        "at_tick": 10,
        "max_lateness_ticks": 3,
        "kind": "stock",
        "supplier": "A",
        "item": "tent",
        "value": 0,
    }
    case["events"] = [event]
    initial["case_sha256"] = fingerprint(case)
    binding = initial["binding_record"]["config"]
    vid = binding["suppliers"]["A"]["variants"]["tent"]
    request = copy.deepcopy(initial["catalog_get"])
    request["path"] = "/store/products?" + urlencode(
        {"variants[id][]": vid, "region_id": binding["region_id"]}
    )
    request["response"]["products"] = [
        p for p in request["response"]["products"] if p["variants"][0]["id"] == vid
    ]
    after = copy.deepcopy(request)
    after["response"]["products"][0]["variants"][0]["inventory_quantity"] = 0

    def get(path, data):
        return {"method": "GET", "path": path, "status": 200, "response": data}

    level = {
        "inventory_item_id": "iid",
        "location_id": "lid",
        "stocked_quantity": 10,
        "reserved_quantity": 0,
    }
    receipt = {
        "event": event,
        "state": "OBSERVED",
        "before": snapshot | {"tick": 10},
        "after": snapshot | {"tick": 11},
        "catalog_before": request,
        "catalog_after": after,
        "variant_get": get(
            f"/admin/products/pid/variants/{vid}",
            {
                "variant": {
                    "id": vid,
                    "product_id": "pid",
                    "inventory_items": [{"inventory_item_id": "iid", "required_quantity": 1}],
                }
            },
        ),
        "stock_before": get(
            "/admin/inventory-items/iid/location-levels", {"inventory_levels": [level]}
        ),
        "stock_after": get(
            "/admin/inventory-items/iid/location-levels",
            {"inventory_levels": [level | {"stocked_quantity": 0}]},
        ),
        "mutation": {
            "method": "POST",
            "path": "/admin/inventory-items/iid/location-levels/lid",
            "status": 200,
            "request": {"stocked_quantity": 0},
            "response": {},
        },
    }
    artifact = {
        "schema": "rehearsal-timed-condition-events-v1",
        "case_sha256": fingerprint(case),
        "run_id": binding["run_id"],
        "receipts": {event["id"]: receipt},
    }
    return case, initial, binding, artifact


def test_declared_schedule_initial_and_raw_change_are_independently_checked(event_case):
    case, initial, binding, artifact = event_case
    result = verify_conditions(initial, case, binding["run_id"])
    verify_start(result, initial["after"])
    with pytest.raises(ValueError, match="before the first event"):
        verify_start(result, initial["after"] | {"tick": 10})
    result = verify_events(artifact, case, binding, 1, 15)
    assert result["status"] == "VERIFIED" and result["observed"] == result["planned"] == 1
    assert not result["model_efficacy_verified"]


def test_price_event_binds_exact_variant_post_and_buyer_price(event_case):
    case, _, binding, artifact = event_case
    event = case["events"][0]
    event.update(kind="price", value=100)
    receipt = artifact["receipts"]["stockA"]
    receipt["catalog_after"] = copy.deepcopy(receipt["catalog_before"])
    receipt["catalog_after"]["response"]["products"][0]["variants"][0]["calculated_price"][
        "calculated_amount"
    ] = 100
    vid = binding["suppliers"]["A"]["variants"]["tent"]
    receipt["mutation"].update(
        path=f"/admin/products/pid/variants/{vid}",
        request={"prices": [{"currency_code": "usd", "amount": 100}]},
    )
    assert verify_receipt(receipt, event, binding)["after"]["price"] == 100


@pytest.mark.parametrize(
    "damage",
    [
        "time",
        "early",
        "run",
        "scope",
        "variant",
        "reserved",
        "quantity",
        "location",
        "inventory",
        "mapping",
        "post",
        "payload",
        "price",
        "missing",
        "duplicate",
        "declaration",
        "clock",
        "nochange",
    ],
)
def test_tampered_event_evidence_fails_closed(event_case, damage):
    case, _, binding, artifact = event_case
    r = artifact["receipts"]["stockA"]
    if damage == "time":
        r["after"]["tick"] = 14
    elif damage == "early":
        r["before"]["tick"] = 9
    elif damage == "run":
        r["before"]["run_id"] = "other"
    elif damage == "scope":
        r["catalog_after"]["path"] += "&region_id=other"
    elif damage == "variant":
        r["variant_get"]["response"]["variant"]["id"] = "other"
    elif damage == "reserved":
        r["stock_before"]["response"]["inventory_levels"][0]["reserved_quantity"] = 1
    elif damage == "quantity":
        r["stock_after"]["response"]["inventory_levels"][0]["stocked_quantity"] = 2
    elif damage == "location":
        r["stock_after"]["response"]["inventory_levels"][0]["location_id"] = "other"
    elif damage == "inventory":
        r["variant_get"]["response"]["variant"]["inventory_items"][0]["inventory_item_id"] = "other"
    elif damage == "mapping":
        r["variant_get"]["response"]["variant"]["inventory_items"][0]["required_quantity"] = 2
    elif damage == "post":
        r["mutation"]["path"] += "-other"
    elif damage == "payload":
        r["mutation"]["request"]["stocked_quantity"] = 1
    elif damage == "price":
        r["catalog_after"]["response"]["products"][0]["variants"][0]["calculated_price"][
            "currency_code"
        ] = "krw"
    elif damage == "missing":
        del artifact["receipts"]["stockA"]
    elif damage == "duplicate":
        artifact["receipts"]["extra"] = r
    elif damage == "declaration":
        artifact["case_sha256"] = "wrong"
    elif damage == "clock":
        r["after"]["clock_mode"] = "virtual"
    elif damage == "nochange":
        r["catalog_before"]["response"]["products"][0]["variants"][0]["inventory_quantity"] = 0
    with pytest.raises(ValueError):
        verify_events(artifact, case, binding, 1, 15)


@pytest.mark.parametrize("state", ["NOT_RUN", "CLAIMED", "UNKNOWN", "MISSED"])
def test_missing_event_remains_in_denominator(event_case, state):
    case, _, binding, artifact = event_case
    artifact["receipts"]["stockA"] = {"event": case["events"][0], "state": state}
    result = verify_events(artifact, case, binding, 1, 15)
    assert result["status"] == "INCOMPLETE" and result["observed"] == 0 and result["planned"] == 1


@pytest.mark.parametrize(
    "damage", ["empty", "extra", "duplicate", "kind", "late", "deadline", "negative", "id"]
)
def test_unsupported_schedule_rejected_before_setup(event_case, damage):
    case = event_case[0]
    e = case["events"][0]
    if damage == "empty":
        case["events"] = []
    elif damage == "extra":
        e["prose"] = "ignore budget"
    elif damage == "duplicate":
        case["events"].append(copy.deepcopy(e))
    elif damage == "kind":
        e["kind"] = "payment"
    elif damage == "late":
        e["max_lateness_ticks"] = 6
    elif damage == "deadline":
        e["at_tick"] = case["goal"]["deadline_tick"]
    elif damage == "negative":
        e["value"] = -1
    elif damage == "id":
        e["id"] = "../escape"
    with pytest.raises(ValueError):
        validate_case(case)


@pytest.mark.parametrize("failure", [False, True])
def test_event_claim_survives_failure_and_never_repeats_mutation(
    event_case, tmp_path, monkeypatch, failure
):
    monkeypatch.syspath_prepend(str(ROOT / "scripts/commerce"))
    spec = importlib.util.spec_from_file_location(
        "events_test", ROOT / "scripts/commerce/event_fixture.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case, _, binding, artifact = event_case
    session = SimpleNamespace(
        case=case,
        path=tmp_path,
        buyer=SimpleNamespace(observe_world=lambda: {"tick": 10}),
        run={"binding": binding},
    )
    calls = []

    def apply(session, event):
        assert json.loads((tmp_path / "event-stockA.json").read_text())["state"] == "CLAIMED"
        calls.append(event)
        if failure:
            raise TimeoutError("post response lost")
        return artifact["receipts"]["stockA"]

    monkeypatch.setattr(module, "apply_event", apply)
    module.tick_events(session)
    module.tick_events(session)
    assert len(calls) == 1
    assert module.export_events(session)["receipts"]["stockA"]["state"] == (
        "UNKNOWN" if failure else "OBSERVED"
    )
