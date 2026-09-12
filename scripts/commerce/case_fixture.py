"""Apply static inputs to fresh fixtures and capture raw read-only condition evidence."""

import json
from urllib.parse import urlencode

from rehearsal.commerce.details import FIELDS
from rehearsal.commerce.seller import read_rows
from rehearsal.evaluation.conditions import fingerprint, validate_static, verify_conditions


def apply_case(spike, fixtures, case):
    validate_static(case)
    for name, supplier in case["suppliers"].items():
        fixture = fixtures[name]
        shipping = fixture["shipping"]
        spike.post(
            f"/admin/shipping-options/{shipping['id']}",
            {
                "prices": [
                    {
                        "id": shipping["prices"][0]["id"],
                        "currency_code": "usd",
                        "amount": supplier["shipping"],
                    }
                ],
            },
        )
        for index, item in enumerate(("tent", "light")):
            expected = supplier["items"][item]
            spike.post(
                f"/admin/products/{fixture['products'][index]}/variants/{fixture['variants'][index]}",
                {"prices": [{"currency_code": "usd", "amount": expected["price"]}]},
            )
            spike.post(
                f"/admin/inventory-items/{fixture['inventory'][index]}/location-levels/"
                + fixture["location"]["id"],
                {"stocked_quantity": expected["stock"]},
            )


def capture(session):
    from pathlib import Path

    from stock_smoke import export_run

    binding_record = json.loads(
        read_rows(Path(session.run["directory"]) / "medusa.sqlite3", "binding")[0]["data"]
    )
    binding = binding_record["config"]
    before = session.buyer.observe_world()
    params = [
        ("variants[id][]", v) for s in binding["suppliers"].values() for v in s["variants"].values()
    ]
    params += [("region_id", binding["region_id"]), ("fields", FIELDS), ("limit", "100")]
    session.spike.get("/store/products?" + urlencode(params), "buyer")
    catalog = session.spike.report["requests"][-1]
    shipping = {}
    for name, supplier in binding["suppliers"].items():
        session.spike.get("/admin/shipping-options/" + supplier["shipping_option_id"])
        shipping[name] = session.spike.report["requests"][-1]
    after = session.buyer.observe_world()
    artifact = {
        "schema": "rehearsal-static-condition-observation-v1",
        "case_sha256": fingerprint(session.case),
        "binding_record": binding_record,
        "before": before,
        "after": after,
        "catalog_get": catalog,
        "shipping_gets": shipping,
        "initial_evidence": export_run(session.spike, session.run, after),
    }
    verdict = verify_conditions(artifact, session.case, binding["run_id"])
    return artifact, verdict
