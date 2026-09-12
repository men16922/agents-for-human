#!/usr/bin/env python3
"""CW00: real HTTP contracts on the fixed loopback Medusa, synthetic funds only.

Run while `make commerce` is active. Each invocation adds labeled fixtures to the
rehearsal-dev DB; no existing records or volumes are deleted. Secrets stay local.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import secrets
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:19000"


def scrub(value):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if k in {"token", "password", "secret", "jwt"} else scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


class Spike:
    def __init__(self):
        self.run_id = "cw00-" + uuid.uuid4().hex[:12]
        self.directory = ROOT / ".local/commerce" / self.run_id
        self.directory.mkdir(parents=True, mode=0o700)
        installed = json.loads((ROOT / "node_modules/@medusajs/medusa/package.json").read_text())
        if installed["version"] != "2.20.1":
            raise RuntimeError("CW00 contract requires installed Medusa 2.20.1")
        self.report = {
            "run_id": self.run_id,
            "medusa_version": installed["version"],
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "package_lock_sha256": hashlib.sha256(
                (ROOT / "package-lock.json").read_bytes()
            ).hexdigest(),
            "started_at": datetime.now(UTC).isoformat(),
            "scope": "local-manual-provider-contract-spike",
            "passed": False,
            "requests": [],
            "observations": {},
        }
        self.clients = {
            role: httpx.Client(base_url=BASE, timeout=30, trust_env=False)
            for role in ("seller", "buyer", "other", "guest")
        }

    def save(self):
        (self.directory / "responses.json").write_text(json.dumps(self.report, indent=2) + "\n")

    def call(self, role, method, path, body=None, expected=(200, 201)):
        response = self.clients[role].request(method, path, json=body)
        try:
            data = response.json()
        except ValueError:
            data = {"body": response.text}
        self.report["requests"].append(
            {
                "role": role,
                "method": method,
                "path": path,
                "request": scrub(body),
                "status": response.status_code,
                "response": scrub(data),
            }
        )
        self.save()
        if response.status_code not in expected:
            raise RuntimeError(
                f"{role} {method} {path}: HTTP {response.status_code}: {scrub(data)}"
            )
        return data

    def post(self, path, body, role="seller"):
        return self.call(role, "POST", path, body)

    def get(self, path, role="seller"):
        return self.call(role, "GET", path)

    def customer(self, role):
        credentials = {
            "email": f"{role}-{self.run_id}@example.invalid",
            "password": secrets.token_urlsafe(32),
        }
        token = self.post("/auth/customer/emailpass/register", credentials, role)["token"]
        self.clients[role].headers["Authorization"] = "Bearer " + token
        self.post("/store/customers", {"email": credentials["email"], "first_name": role}, role)
        token = self.post("/auth/customer/emailpass", credentials, role)["token"]
        self.clients[role].headers["Authorization"] = "Bearer " + token

    def seed(self):
        # Bootstrap one synthetic seller via the installed CLI, never via a cloud account.
        spec = importlib.util.spec_from_file_location("local_dev", ROOT / "scripts/dev/local.py")
        local = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(local)
        credentials = {
            "email": f"seller-{self.run_id}@example.invalid",
            "password": secrets.token_urlsafe(32),
        }
        with (self.directory / "bootstrap.log").open("w") as log:
            bootstrap = subprocess.run(
                [
                    "npm",
                    "exec",
                    "--workspace=@rehearsal/medusa",
                    "--",
                    "medusa",
                    "user",
                    "-e",
                    credentials["email"],
                    "-p",
                    credentials["password"],
                ],
                cwd=ROOT,
                env=local.environment(),
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if bootstrap.returncode:
            raise RuntimeError("Local seller bootstrap failed; inspect private bootstrap.log")
        token = self.post("/auth/user/emailpass", credentials)["token"]
        self.clients["seller"].headers["Authorization"] = "Bearer " + token
        channel = self.post("/admin/sales-channels", {"name": self.run_id})["sales_channel"]
        key = self.post("/admin/api-keys", {"title": self.run_id, "type": "publishable"})["api_key"]
        self.post(f"/admin/api-keys/{key['id']}/sales-channels", {"add": [channel["id"]]})
        for role in ("buyer", "other", "guest"):
            self.clients[role].headers["x-publishable-api-key"] = key["token"]
        regions = self.get("/admin/regions")["regions"]
        region = next((r for r in regions if r["name"] == "CW00 synthetic region"), None)
        if region is None:
            region = self.post(
                "/admin/regions",
                {
                    "name": "CW00 synthetic region",
                    "currency_code": "usd",
                    "countries": ["us"],
                    "automatic_taxes": False,
                    "payment_providers": ["pp_system_default"],
                },
            )["region"]
        profile = self.post("/admin/shipping-profiles", {"name": self.run_id, "type": "default"})[
            "shipping_profile"
        ]
        location = self.post(
            "/admin/stock-locations",
            {
                "name": self.run_id,
                "address": {"address_1": "Synthetic warehouse", "country_code": "us"},
            },
        )["stock_location"]
        self.post(
            f"/admin/stock-locations/{location['id']}/sales-channels", {"add": [channel["id"]]}
        )
        self.post(
            f"/admin/stock-locations/{location['id']}/fulfillment-providers",
            {"add": ["manual_manual"]},
        )
        self.post(
            f"/admin/stock-locations/{location['id']}/fulfillment-sets",
            {"name": self.run_id, "type": "shipping"},
        )
        location = self.get(f"/admin/stock-locations/{location['id']}?fields=*fulfillment_sets")[
            "stock_location"
        ]
        fs = location["fulfillment_sets"][0]
        zone = self.post(
            f"/admin/fulfillment-sets/{fs['id']}/service-zones",
            {"name": self.run_id, "geo_zones": [{"type": "country", "country_code": "us"}]},
        )
        zone_id = zone["fulfillment_set"]["service_zones"][0]["id"]
        shipping = self.post(
            "/admin/shipping-options",
            {
                "name": self.run_id,
                "price_type": "flat",
                "service_zone_id": zone_id,
                "shipping_profile_id": profile["id"],
                "provider_id": "manual_manual",
                "type": {
                    "label": "Synthetic delivery",
                    "code": "cw00",
                    "description": "No real shipment",
                },
                "prices": [{"currency_code": "usd", "amount": 10}],
                "rules": [
                    {"attribute": "enabled_in_store", "operator": "eq", "value": "true"},
                    {"attribute": "is_return", "operator": "eq", "value": "false"},
                ],
            },
        )["shipping_option"]
        variants = []
        inventory = []
        products = []
        for name, price in (("tent", 60), ("light", 20)):
            item = self.post(
                "/admin/inventory-items", {"sku": f"{self.run_id}-{name}", "title": name}
            )["inventory_item"]
            self.post(
                f"/admin/inventory-items/{item['id']}/location-levels",
                {"location_id": location["id"], "stocked_quantity": 10},
            )
            inventory.append(item["id"])
            product = self.post(
                "/admin/products",
                {
                    "title": f"{self.run_id}-{name}",
                    "status": "published",
                    "shipping_profile_id": profile["id"],
                    "sales_channels": [{"id": channel["id"]}],
                    "options": [{"title": "Kind", "values": [name]}],
                    "variants": [
                        {
                            "title": name,
                            "sku": f"{self.run_id}-{name}",
                            "options": {"Kind": name},
                            "manage_inventory": True,
                            "inventory_items": [
                                {"inventory_item_id": item["id"], "required_quantity": 1}
                            ],
                            "prices": [{"currency_code": "usd", "amount": price}],
                        }
                    ],
                },
            )["product"]
            variants.append(product["variants"][0]["id"])
            products.append(product["id"])
        self.customer("buyer")
        self.customer("other")
        return {
            "region": region,
            "channel": channel,
            "location": location,
            "shipping": shipping,
            "variants": variants,
            "inventory": inventory,
            "products": products,
        }

    def run(self):
        fixture = self.seed()
        region, location, shipping = (fixture[k] for k in ("region", "location", "shipping"))
        variants, inventory = fixture["variants"], fixture["inventory"]
        self.call("guest", "GET", "/admin/orders", expected=(401, 403))
        self.call("buyer", "GET", "/admin/orders", expected=(401, 403))
        cart = self.post(
            "/store/carts",
            {
                "region_id": region["id"],
                "shipping_address": {
                    "first_name": "Test",
                    "last_name": "Buyer",
                    "address_1": "Synthetic venue",
                    "city": "Test",
                    "country_code": "us",
                    "postal_code": "10001",
                },
                "items": [{"variant_id": v, "quantity": q} for v, q in zip(variants, (3, 6))],
            },
            "buyer",
        )["cart"]
        cid = cart["id"]
        # A rejected stock mutation must not alter the accepted cart quantities.
        self.call(
            "buyer",
            "POST",
            f"/store/carts/{cid}/line-items",
            {"variant_id": variants[0], "quantity": 100},
            expected=(400, 409),
        )
        checked = self.get(f"/store/carts/{cid}", "buyer")["cart"]
        assert sorted(i["quantity"] for i in checked["items"]) == [3, 6]
        self.get(f"/store/shipping-options?cart_id={cid}", "buyer")
        cart = self.post(
            f"/store/carts/{cid}/shipping-methods", {"option_id": shipping["id"]}, "buyer"
        )["cart"]
        assert cart["total"] == 310, cart["total"]
        collection = self.post("/store/payment-collections", {"cart_id": cid}, "buyer")[
            "payment_collection"
        ]
        collection = self.post(
            f"/store/payment-collections/{collection['id']}/payment-sessions",
            {"provider_id": "pp_system_default"},
            "buyer",
        )["payment_collection"]
        self.report["observations"]["session_before_complete"] = collection["payment_sessions"][0][
            "status"
        ]
        completed = self.post(f"/store/carts/{cid}/complete", {}, "buyer")
        assert completed["type"] == "order", completed
        order = completed["order"]
        oid = order["id"]
        repeated = self.post(f"/store/carts/{cid}/complete", {}, "buyer")
        assert repeated["order"]["id"] == oid
        self.report["observations"]["same_cart_retry_same_order"] = True
        self.report["observations"]["states"] = []

        def snapshot(stage):
            current = self.get(
                f"/admin/orders/{oid}?fields=*payment_collections.payments,*fulfillments,*items"
            )["order"]
            self.report["observations"]["states"].append(
                {
                    "stage": stage,
                    "order": current["status"],
                    "payment": current["payment_status"],
                    "fulfillment": current["fulfillment_status"],
                    "total": current["total"],
                }
            )
            return current

        order = snapshot("authorized")
        payment = order["payment_collections"][0]["payments"][0]
        self.report["observations"]["order_read_access"] = {}
        for role in ("buyer", "guest", "other"):
            self.call(role, "GET", f"/store/orders/{oid}", expected=(200, 401, 403, 404))
            self.report["observations"]["order_read_access"][role] = self.report["requests"][-1][
                "status"
            ]
        # List authentication/ownership differs from retrieve-by-ID.
        self.call("guest", "GET", "/store/orders", expected=(401, 403))
        assert oid in [o["id"] for o in self.get("/store/orders", "buyer")["orders"]]
        assert oid not in [o["id"] for o in self.get("/store/orders", "other")["orders"]]
        self.call(
            "buyer", "POST", f"/admin/payments/{payment['id']}/capture", {}, expected=(401, 403)
        )
        self.call(
            "buyer",
            "POST",
            f"/admin/orders/{oid}/fulfillments",
            {"items": [{"id": i["id"], "quantity": i["quantity"]} for i in order["items"]]},
            expected=(401, 403),
        )
        captured = self.post(f"/admin/payments/{payment['id']}/capture", {})["payment"]
        repeated_capture = self.post(f"/admin/payments/{payment['id']}/capture", {})["payment"]
        assert len(captured["captures"]) == len(repeated_capture["captures"]) == 1
        assert captured["captures"][0]["id"] == repeated_capture["captures"][0]["id"]
        assert captured["captures"][0]["amount"] == 310
        self.report["observations"]["repeated_full_capture_same_record"] = True
        snapshot("captured")
        items = [{"id": i["id"], "quantity": i["quantity"]} for i in order["items"]]
        self.post(
            f"/admin/orders/{oid}/fulfillments",
            {
                "items": items,
                "location_id": location["id"],
                "shipping_option_id": shipping["id"],
                "no_notification": True,
            },
        )
        fulfilled = snapshot("fulfilled")
        fid = fulfilled["fulfillments"][0]["id"]
        self.post(
            f"/admin/orders/{oid}/fulfillments/{fid}/shipments",
            {"items": items, "labels": [], "no_notification": True},
        )
        snapshot("shipped")
        self.post(
            f"/admin/orders/{oid}/fulfillments/{fid}/mark-as-delivered", {"no_notification": True}
        )
        final = snapshot("delivered")
        assert final["payment_status"] == "captured"
        assert final["fulfillment_status"] == "delivered"
        for iid, remaining in zip(inventory, (7, 4)):
            levels = self.get(f"/admin/inventory-items/{iid}/location-levels")["inventory_levels"]
            assert levels[0]["stocked_quantity"] == remaining
            assert levels[0]["reserved_quantity"] == 0
        buyer_order = self.get(f"/store/orders/{oid}", "buyer")["order"]
        assert buyer_order["fulfillment_status"] == "delivered"
        self.report["observations"]["order_id"] = oid
        self.report["observations"]["expected_total"] = 310
        assert [
            (s["payment"], s["fulfillment"]) for s in self.report["observations"]["states"]
        ] == [
            ("authorized", "not_fulfilled"),
            ("captured", "not_fulfilled"),
            ("captured", "fulfilled"),
            ("captured", "shipped"),
            ("captured", "delivered"),
        ]
        assert all(s["total"] == 310 for s in self.report["observations"]["states"])
        self.report["passed"] = True
        self.save()


def main():
    os.umask(0o077)
    spike = Spike()
    try:
        spike.run()
    finally:
        spike.save()
        for client in spike.clients.values():
            client.close()
        print(f"Evidence: {spike.directory.relative_to(ROOT)}/responses.json")
    print("PASS: CW00 local contracts; no model calls or real funds.")


if __name__ == "__main__":
    main()
