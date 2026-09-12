"""Independent initial-condition checks from raw Store/admin GETs and fresh ledgers.

Only the explicit static A/B/C tent/light scenario is supported. This is a bounded
pre-execution observation, not atomic isolation or evidence of model effectiveness.
"""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qs, urlsplit

from rehearsal.evaluation.medusa import verify_medusa
from rehearsal.evidence_view import goal, integer
from rehearsal.world.storage import Json, canonical

MAX_CAPTURE_TICKS = 5
MAX_START_AGE_TICKS = 5


def fingerprint(case: Json) -> str:
    return hashlib.sha256(canonical(case).encode()).hexdigest()


def validate_static(case: Json) -> None:
    if set(case) != {"scenario_version", "seed", "goal", "suppliers"}:
        raise ValueError("Unsupported case fields/events; static conditions only")
    if not isinstance(case["scenario_version"], str) or not case["scenario_version"]:
        raise ValueError("Scenario version required")
    integer(case["seed"])
    if set(case["goal"]) != {"items", "deadline_tick", "recipient", "budget"}:
        raise ValueError("Invalid static goal")
    goal({k: v for k, v in case["goal"].items() if k != "budget"})
    integer(case["goal"]["budget"], 1)
    if set(case["goal"]["items"]) != {"tent", "light"} or set(case["suppliers"]) != {"A", "B", "C"}:
        raise ValueError("Static fixture supports only A/B/C and tent/light")
    for supplier in case["suppliers"].values():
        if set(supplier) != {"shipping", "lead_ticks", "items"}:
            raise ValueError("Unsupported supplier fields/events")
        integer(supplier["shipping"])
        integer(supplier["lead_ticks"], 1)
        if set(supplier["items"]) != {"tent", "light"}:
            raise ValueError("Unsupported supplier items")
        for item in supplier["items"].values():
            if set(item) != {"price", "stock"}:
                raise ValueError("Unsupported item fields/events")
            integer(item["price"], 1)
            integer(item["stock"])


def number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError("Invalid provider quantity")
    return integer(int(value))


def verify_conditions(artifact: Json, case: Json, run_id: str) -> Json:
    from rehearsal.evaluation.condition_events import validate_case

    validate_case(case)
    if artifact["schema"] != "rehearsal-static-condition-observation-v1":
        raise ValueError("Invalid initial condition schema")
    if artifact["case_sha256"] != fingerprint(case):
        raise ValueError("Condition declaration changed")
    binding = artifact["binding_record"]["config"]
    expected_goal = {k: v for k, v in case["goal"].items() if k != "budget"}
    if (
        binding["run_id"] != run_id
        or binding["goal"] != expected_goal
        or binding["budget"] != case["goal"]["budget"]
        or set(binding["suppliers"]) != set(case["suppliers"])
    ):
        raise ValueError("Condition run/goal/budget mismatch")
    for snapshot in (artifact["before"], artifact["after"]):
        if (
            snapshot["run_id"] != run_id
            or snapshot["goal"] != expected_goal
            or snapshot["clock_mode"] != "operating-one-second-ticks"
            or snapshot["balance"]
            != {
                "budget": binding["budget"],
                "spent": 0,
                "reserved": 0,
                "available": binding["budget"],
            }
            or snapshot["inventory"] != {"tent": 0, "light": 0}
        ):
            raise ValueError("Fresh condition observation required")
    begin, end = integer(artifact["before"]["tick"]), integer(artifact["after"]["tick"])
    if not begin <= end < expected_goal["deadline_tick"] or end - begin > MAX_CAPTURE_TICKS:
        raise ValueError("Condition capture expired or clock reversed")
    if case.get("events") and end >= case["events"][0]["at_tick"]:
        raise ValueError("Initial capture must precede the event schedule")
    initial = artifact["initial_evidence"]
    if (
        initial["binding"] != binding
        or initial["captured_at_tick"] != end
        or initial["tables"]["quotes"]
        or initial["tables"]["purchases"]
        or initial["tables"]["intents"]
        or initial["external_orders"]
    ):
        raise ValueError("Condition evidence is not pre-purchase")
    initial_verdict = verify_medusa(initial, expected_goal, binding["budget"])
    if (
        initial_verdict["status"] != "INCOMPLETE"
        or initial_verdict["spent"] != 0
        or initial_verdict["reserved"] != 0
    ):
        raise ValueError("Invalid independent initial ledger")
    request = artifact["catalog_get"]
    url = urlsplit(request["path"])
    query = parse_qs(url.query)
    wanted = {v for s in binding["suppliers"].values() for v in s["variants"].values()}
    if (
        len(wanted) != 6
        or url.path != "/store/products"
        or url.scheme
        or url.netloc
        or request["method"] != "GET"
        or request["status"] != 200
        or query.get("region_id") != [binding["region_id"]]
        or set(query.get("variants[id][]", [])) != wanted
    ):
        raise ValueError("Catalog request scope mismatch")
    variants = {}
    for product in request["response"]["products"]:
        for variant in product["variants"]:
            if variant["id"] in variants:
                raise ValueError("Duplicate condition variant")
            variants[variant["id"]] = variant
    if set(variants) != wanted or set(artifact["shipping_gets"]) != set(case["suppliers"]):
        raise ValueError("Incomplete condition observations")
    for name, supplier in case["suppliers"].items():
        mapping = binding["suppliers"][name]
        if (
            set(mapping["variants"]) != set(supplier["items"])
            or mapping["lead_ticks"] != supplier["lead_ticks"]
        ):
            raise ValueError("Declared delivery configuration mismatch")
        for item, expected in supplier["items"].items():
            variant = variants[mapping["variants"][item]]
            price = variant["calculated_price"]
            if (
                variant["manage_inventory"] is not True
                or variant["allow_backorder"] is not False
                or number(variant["inventory_quantity"]) != expected["stock"]
                or price["currency_code"] != "usd"
                or number(price["calculated_amount"]) != expected["price"]
            ):
                raise ValueError("Declared price/stock differs from Store GET")
        shipping_get = artifact["shipping_gets"][name]
        shipping = shipping_get["response"]["shipping_option"]
        prices = shipping["prices"]
        if (
            shipping_get["method"] != "GET"
            or shipping_get["status"] != 200
            or shipping_get["path"] != "/admin/shipping-options/" + mapping["shipping_option_id"]
            or shipping["id"] != mapping["shipping_option_id"]
            or shipping["price_type"] != "flat"
            or len(prices) != 1
            or prices[0]["currency_code"] != "usd"
            or prices[0]["rules_count"] != 0
            or prices[0]["price_rules"]
            or number(prices[0]["amount"]) != supplier["shipping"]
        ):
            raise ValueError("Declared shipping differs from provider GET")
    result = {
        "status": "VERIFIED",
        "scope": "static-initial-observation-not-atomic-isolation",
        "run_id": run_id,
        "case_sha256": fingerprint(case),
        "capture_begin_tick": begin,
        "capture_end_tick": end,
        "initial_conditions_verified": True,
        "event_conditions_supported": False,
        "model_efficacy_verified": False,
    }
    if case.get("events"):
        result["first_event_tick"] = case["events"][0]["at_tick"]
    return result


def verify_start(verdict: Json, initial: Json) -> None:
    if (
        verdict.get("first_event_tick") is not None
        and initial["tick"] >= verdict["first_event_tick"]
    ):
        raise ValueError("Execution must start before the first event")
    if (
        initial["run_id"] != verdict["run_id"]
        or not verdict["capture_end_tick"]
        <= initial["tick"]
        <= verdict["capture_end_tick"] + MAX_START_AGE_TICKS
    ):
        raise ValueError("Condition observation too old or from another run")
