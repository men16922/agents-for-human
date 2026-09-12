"""Scoped local fixture and process helpers for the Medusa operating sandbox."""

from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from contract_spike import Spike

from rehearsal.commerce.gateway import Binding, MedusaGateway, StoreAPI
from rehearsal.commerce.server import seller_health
from rehearsal.operating.local import ORIGIN, start, stop


def add_supplier(spike, fixture, name, prices, shipping_price):
    label = f"{spike.run_id}-{name}"
    profile = spike.post("/admin/shipping-profiles", {"name": label, "type": "default"})[
        "shipping_profile"
    ]
    shipping = spike.post(
        "/admin/shipping-options",
        {
            "name": label,
            "price_type": "flat",
            "service_zone_id": fixture["shipping"]["service_zone_id"],
            "shipping_profile_id": profile["id"],
            "provider_id": "manual_manual",
            "type": {
                "label": "Synthetic delivery",
                "code": name,
                "description": "No real shipment",
            },
            "prices": [{"currency_code": "usd", "amount": shipping_price}],
            "rules": [
                {"attribute": "enabled_in_store", "operator": "eq", "value": "true"},
                {"attribute": "is_return", "operator": "eq", "value": "false"},
            ],
        },
    )["shipping_option"]
    result = {
        "shipping": shipping,
        "variants": [],
        "products": [],
        "inventory": [],
        "location": fixture["location"],
    }
    for item, price in zip(("tent", "light"), prices):
        inventory = spike.post("/admin/inventory-items", {"sku": f"{label}-{item}", "title": item})[
            "inventory_item"
        ]
        spike.post(
            f"/admin/inventory-items/{inventory['id']}/location-levels",
            {"location_id": fixture["location"]["id"], "stocked_quantity": 10},
        )
        product = spike.post(
            "/admin/products",
            {
                "title": f"{label}-{item}",
                "status": "published",
                "shipping_profile_id": profile["id"],
                "sales_channels": [{"id": fixture["channel"]["id"]}],
                "options": [{"title": "Kind", "values": [item]}],
                "variants": [
                    {
                        "title": item,
                        "sku": f"{label}-{item}",
                        "options": {"Kind": item},
                        "manage_inventory": True,
                        "inventory_items": [
                            {"inventory_item_id": inventory["id"], "required_quantity": 1}
                        ],
                        "prices": [{"currency_code": "usd", "amount": price}],
                    }
                ],
            },
        )["product"]
        result["products"].append(product["id"])
        result["variants"].append(product["variants"][0]["id"])
        result["inventory"].append(inventory["id"])
    return result


def prepare(spike: Spike, case=None):
    if case is not None:
        from rehearsal.evaluation.conditions import validate_static

        validate_static(case)
    fixture = spike.seed()
    fixtures = {
        "A": fixture,
        "B": add_supplier(spike, fixture, "B", (70, 25), 20),
        "C": add_supplier(spike, fixture, "C", (90, 35), 15),
    }
    if case is not None:
        from case_fixture import apply_case

        apply_case(spike, fixtures, case)
    suppliers = {
        name: {
            "variants": dict(zip(("tent", "light"), f["variants"])),
            "shipping_option_id": f["shipping"]["id"],
            "lead_ticks": case["suppliers"][name]["lead_ticks"]
            if case is not None
            else {"A": 4, "B": 6, "C": 8}[name],
        }
        for name, f in fixtures.items()
    }
    directory = spike.directory / "operating"
    directory.mkdir(mode=0o700)
    server = {"directory": str(directory), "runs": {}, "grants": {}}
    seller = {
        "directory": str(directory),
        "runs": {},
        "admin_token": spike.clients["seller"].headers["Authorization"].removeprefix("Bearer "),
    }
    credentials = {"origin": ORIGIN, "runs": {}}
    for role in ("buyer", "other"):
        run_id = f"{spike.run_id}-{role}"
        customer = spike.get("/store/customers/me", role)["customer"]
        binding = Binding(
            run_id,
            customer["id"],
            fixture["region"]["id"],
            suppliers,
            {k: v for k, v in case["goal"].items() if k != "budget"}
            if case is not None
            else {"items": {"tent": 3, "light": 6}, "deadline_tick": 120, "recipient": "venue"},
            budget=case["goal"]["budget"] if case is not None else 500,
        )
        run_directory = directory / role
        headers = spike.clients[role].headers
        values = {
            "directory": str(run_directory),
            "binding": asdict(binding),
            "store_token": headers["Authorization"].removeprefix("Bearer "),
            "publishable_key": headers["x-publishable-api-key"],
        }
        server["runs"][run_id] = values
        seller["runs"][run_id] = {
            "directory": str(run_directory),
            "binding": asdict(binding),
            "locations": {n: f["location"]["id"] for n, f in fixtures.items()},
        }
        api = StoreAPI(values["store_token"], values["publishable_key"])
        try:
            MedusaGateway(run_directory, binding, api)
        finally:
            api.close()
        credentials["runs"][run_id] = {}
        for grant_role in ("buyer", "observer", "control"):
            token = secrets.token_urlsafe(32)
            credentials["runs"][run_id][grant_role] = token
            server["grants"][hashlib.sha256(token.encode()).hexdigest()] = {
                "run_id": run_id,
                "role": grant_role,
            }
        observer_path = directory / f"observer-{role}.json"
        observer_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "observer_token": credentials["runs"][run_id]["observer"],
                },
                indent=2,
            )
            + "\n"
        )
        observer_path.chmod(0o600)
    for name, value in (("server", server), ("seller", seller), ("credentials", credentials)):
        path = directory / f"{name}.json"
        path.write_text(json.dumps(value, indent=2) + "\n")
        path.chmod(0o600)
    return directory, credentials, server, fixtures


def start_seller(directory: Path):
    with (directory / "seller.log").open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "rehearsal.commerce.seller", str(directory / "seller.json")],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Seller process exited; inspect private seller.log")
        value = seller_health(directory)
        try:
            owner = json.loads((directory / "seller-status.json").read_text()).get("pid")
        except (OSError, ValueError):
            owner = None
        if value["status"] == "ok" and owner == process.pid:
            return process
        time.sleep(0.1)
    stop(process)
    raise RuntimeError("Seller readiness timed out")


def start_gateway(directory: Path):
    return start(
        directory,
        factory="rehearsal.commerce.server:create_app",
        config_variable="REHEARSAL_MEDUSA_CONFIG",
    )
