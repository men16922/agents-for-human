import copy
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

from rehearsal.evaluation.conditions import (
    fingerprint,
    validate_static,
    verify_conditions,
    verify_start,
)

ROOT = Path(__file__).parents[2]


def artifact_for(case, original, snapshot):
    initial = copy.deepcopy(original)
    initial["tables"]["quotes"] = []
    initial["tables"]["purchases"] = []
    initial["tables"]["intents"] = []
    initial["external_orders"] = []
    initial["tables"]["accounts"][0].update(spent=0, reserved=0)
    initial["captured_at_tick"] = snapshot["tick"]
    binding = initial["binding"]
    # Deliberately scripted provider responses; live capture is a separate smoke.
    products, ids, shipping = [], [], {}
    for name, supplier in case["suppliers"].items():
        config = binding["suppliers"][name]
        config["lead_ticks"] = supplier["lead_ticks"]
        for item, expected in supplier["items"].items():
            vid = config["variants"][item]
            ids.append(("variants[id][]", vid))
            products.append(
                {
                    "id": "product-" + vid,
                    "variants": [
                        {
                            "id": vid,
                            "manage_inventory": True,
                            "allow_backorder": False,
                            "inventory_quantity": expected["stock"],
                            "calculated_price": {
                                "currency_code": "usd",
                                "calculated_amount": expected["price"],
                            },
                        }
                    ],
                }
            )
        shipping[name] = {
            "method": "GET",
            "status": 200,
            "path": "/admin/shipping-options/" + config["shipping_option_id"],
            "response": {
                "shipping_option": {
                    "id": config["shipping_option_id"],
                    "price_type": "flat",
                    "prices": [
                        {
                            "currency_code": "usd",
                            "amount": supplier["shipping"],
                            "rules_count": 0,
                            "price_rules": [],
                        }
                    ],
                }
            },
        }
    ids.append(("region_id", binding["region_id"]))
    return {
        "schema": "rehearsal-static-condition-observation-v1",
        "case_sha256": fingerprint(case),
        "binding_record": {"config": binding, "started_at": 1788880000},
        "before": copy.deepcopy(snapshot),
        "after": copy.deepcopy(snapshot),
        "initial_evidence": initial,
        "catalog_get": {
            "method": "GET",
            "status": 200,
            "path": "/store/products?" + urlencode(ids),
            "response": {"products": products},
        },
        "shipping_gets": shipping,
    }


@pytest.fixture
def condition():
    raw = json.loads((ROOT / "tests/fixtures/commerce/session.json").read_text())
    case = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    case["goal"] = raw["binding"]["goal"] | {"budget": raw["binding"]["budget"]}
    before = {
        "run_id": raw["binding"]["run_id"],
        "goal": raw["binding"]["goal"],
        "tick": 1,
        "clock_mode": "operating-one-second-ticks",
        "inventory": {"tent": 0, "light": 0},
        "balance": {"budget": 500, "spent": 0, "reserved": 0, "available": 500},
    }
    return case, artifact_for(case, raw, before), before


def test_raw_provider_and_independent_empty_ledgers_verify_only_static_initial_state(condition):
    case, artifact, before = condition
    result = verify_conditions(artifact, case, before["run_id"])
    assert result["initial_conditions_verified"] and not result["event_conditions_supported"]
    assert not result["model_efficacy_verified"]
    verify_start(result, before | {"tick": 6})
    for snapshot in (before | {"tick": 0}, before | {"tick": 7}, before | {"run_id": "other"}):
        with pytest.raises(ValueError):
            verify_start(result, snapshot)


@pytest.mark.parametrize(
    "damage",
    [
        "price",
        "stock",
        "currency",
        "backorder",
        "managed",
        "shipping",
        "shipping-rule",
        "lead",
        "duplicate",
        "request-scope",
        "incomplete",
        "run",
        "reservation",
        "quote",
        "clock",
        "capture-span",
    ],
)
def test_changed_or_incomplete_raw_conditions_cannot_verify(condition, damage):
    case, artifact, before = condition
    variant = artifact["catalog_get"]["response"]["products"][0]["variants"][0]
    if damage == "price":
        variant["calculated_price"]["calculated_amount"] += 1
    elif damage == "stock":
        variant["inventory_quantity"] += 1
    elif damage == "currency":
        variant["calculated_price"]["currency_code"] = "krw"
    elif damage == "backorder":
        variant["allow_backorder"] = True
    elif damage == "managed":
        variant["manage_inventory"] = False
    elif damage == "shipping":
        artifact["shipping_gets"]["A"]["response"]["shipping_option"]["prices"][0]["amount"] += 1
    elif damage == "shipping-rule":
        artifact["shipping_gets"]["A"]["response"]["shipping_option"]["prices"][0][
            "rules_count"
        ] = 1
    elif damage == "lead":
        artifact["binding_record"]["config"]["suppliers"]["A"]["lead_ticks"] += 1
    elif damage == "duplicate":
        artifact["catalog_get"]["response"]["products"].append({"variants": [variant]})
    elif damage == "request-scope":
        artifact["catalog_get"]["path"] = "/store/products?region_id=other"
    elif damage == "incomplete":
        artifact["catalog_get"]["response"]["products"].pop()
    elif damage == "run":
        artifact["binding_record"]["config"]["run_id"] = "other"
    elif damage == "reservation":
        artifact["after"]["balance"]["reserved"] = 1
    elif damage == "quote":
        artifact["initial_evidence"]["tables"]["quotes"].append({})
    elif damage == "clock":
        artifact["after"]["tick"] = 0
    else:
        artifact["after"]["tick"] = 7
    with pytest.raises(ValueError):
        verify_conditions(artifact, case, before["run_id"])


@pytest.mark.parametrize("where", ["events", "supplier", "item", "item-name"])
def test_unsupported_conditions_are_not_silently_ignored(condition, where):
    case, _, _ = condition
    if where == "events":
        case["events"] = []
    elif where == "supplier":
        case["suppliers"]["A"]["supplier_content"] = "untrusted prose"
    elif where == "item":
        case["suppliers"]["A"]["items"]["tent"]["discount"] = 10
    else:
        case["goal"]["items"]["food"] = 1
    with pytest.raises(ValueError):
        validate_static(case)
