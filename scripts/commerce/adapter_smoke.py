#!/usr/bin/env python3
"""Real Medusa adapter checks; explicit synthetic seller actions, no model/transfer claim."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path

import httpx
from contract_spike import ROOT, Spike, scrub

from rehearsal.commerce.gateway import Binding, MedusaGateway, StoreAPI
from rehearsal.world.storage import ContractError


class RecordingStore(StoreAPI):
    def __init__(self, spike):
        headers = spike.clients["buyer"].headers
        super().__init__(
            headers["Authorization"].removeprefix("Bearer "), headers["x-publishable-api-key"]
        )
        self.spike = spike
        self.lose_complete = False
        self.http.event_hooks["response"].append(self.record)

    def record(self, response):
        response.read()
        request = response.request
        self.spike.report["requests"].append(
            {
                "role": "adapter-customer",
                "method": request.method,
                "path": request.url.raw_path.decode(),
                "request": scrub(json.loads(request.content)) if request.content else None,
                "response": scrub(response.json()),
                "status": response.status_code,
            }
        )
        self.spike.save()

    def call(self, method, path, body=None):
        result = super().call(method, path, body)
        if self.lose_complete and path.endswith("/complete"):
            self.lose_complete = False
            raise httpx.ReadTimeout("Locally discarded real completed response")
        return result


def rejected(action, code):
    try:
        action()
    except ContractError as exc:
        assert exc.code == code, (exc.code, code)
    else:
        raise AssertionError(f"Expected {code}")


def main():
    os.umask(0o077)
    spike = Spike()
    spike.report["scope"] = "live-medusa-adapter-http-recording"
    api = None
    report = {
        "passed": False,
        "scope": "live-medusa-adapter-with-explicit-test-seller",
        "real_model_calls": 0,
        "policy_transfer_verified": False,
        "adapter_sha256": hashlib.sha256(
            (ROOT / "src/rehearsal/commerce/gateway.py").read_bytes()
        ).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "run_id": spike.run_id,
        "medusa_version": spike.report["medusa_version"],
        "package_lock_sha256": spike.report["package_lock_sha256"],
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "src/rehearsal/evaluation/medusa.py",
                "src/rehearsal/world/payments.py",
                "scripts/commerce/contract_spike.py",
            )
        },
    }
    try:
        fixture = spike.seed()
        buyer = spike.get("/store/customers/me", "buyer")["customer"]
        binding = Binding(
            spike.run_id,
            buyer["id"],
            fixture["region"]["id"],
            {
                "A": {
                    "variants": dict(zip(("tent", "light"), fixture["variants"])),
                    "shipping_option_id": fixture["shipping"]["id"],
                    "lead_ticks": 2,
                }
            },
            {"items": {"tent": 3, "light": 6}, "deadline_tick": 120, "recipient": "venue"},
        )
        (spike.directory / "binding.json").write_text(json.dumps(asdict(binding), indent=2))
        api = RecordingStore(spike)
        gateway = MedusaGateway(spike.directory / "gateway", binding, api)
        quote = gateway.get_quotes("A", {"tent": 3, "light": 6})
        assert quote["amount"] == 310
        # Actual catalogue change, then same-quantity cart refresh rejects old terms.
        spike.post(
            f"/admin/products/{fixture['products'][0]}/variants/{fixture['variants'][0]}",
            {"prices": [{"currency_code": "usd", "amount": 100}]},
        )
        rejected(lambda: gateway.create_order(quote["id"], "stale"), "STALE_QUOTE")
        assert gateway.payments.balance(binding.run_id)["reserved"] == 0
        spike.post(
            f"/admin/products/{fixture['products'][0]}/variants/{fixture['variants'][0]}",
            {"prices": [{"currency_code": "usd", "amount": 60}]},
        )
        quote = gateway.get_quotes("A", {"tent": 3, "light": 6})
        order = gateway.create_order(quote["id"], "buy")
        assert gateway.create_order(quote["id"], "buy")["id"] == order["id"]
        rejected(lambda: gateway.create_order(quote["id"], "replacement"), "QUOTE_ALREADY_ORDERED")
        rejected(lambda: gateway.get_order("order_not_owned"), "NOT_FOUND")
        api.lose_complete = True
        assert gateway.authorize_payment(order["id"], "pay")["status"] == "UNKNOWN"
        assert gateway.payments.balance(binding.run_id)["reserved"] == 310
        # Reconstruct gateway from disk after the unobserved real checkout commit.
        gateway = MedusaGateway(spike.directory / "gateway", binding, api)
        before = len(spike.report["requests"])
        payment = gateway.get_payment(order["id"])
        assert payment["status"] == "RESERVED"
        assert all(r["method"] == "GET" for r in spike.report["requests"][before:])
        assert gateway.authorize_payment(order["id"], "pay")["id"] == payment["id"]
        rejected(
            lambda: gateway.authorize_payment(order["id"], "replacement"),
            "ORDER_ALREADY_HAS_INTENT",
        )
        mapped = gateway._purchase(order["id"])
        oid = mapped["external_id"]
        rejected(lambda: gateway.get_order(oid), "NOT_FOUND")
        # A separate same-customer run also cannot resolve the first run's handle.
        other_binding = Binding(
            binding.run_id + "-other",
            binding.customer_id,
            binding.region_id,
            binding.suppliers,
            binding.goal,
        )
        other_gateway = MedusaGateway(spike.directory / "other-gateway", other_binding, api)
        rejected(lambda: other_gateway.get_order(order["id"]), "NOT_FOUND")
        # Store API itself still exposes this ID to another customer; gateway checks identity.
        assert spike.get(f"/store/orders/{oid}", "other")["order"]["id"] == oid
        original_header = api.http.headers["Authorization"]
        api.http.headers["Authorization"] = spike.clients["other"].headers["Authorization"]
        rejected(lambda: gateway.get_order(order["id"]), "CUSTOMER_SCOPE_MISMATCH")
        api.http.headers["Authorization"] = original_header
        # A 210 purchase exceeds remaining 190 while requesting only available stock.
        more = gateway.get_quotes("A", {"tent": 3, "light": 1})
        extra_order = gateway.create_order(more["id"], "over-budget")
        before = len(spike.report["requests"])
        rejected(
            lambda: gateway.authorize_payment(extra_order["id"], "over-budget"), "BUDGET_EXCEEDED"
        )
        assert not any(
            "payment-collections" in r["path"] or r["path"].endswith("/complete")
            for r in spike.report["requests"][before:]
        )
        assert gateway.payments.balance(binding.run_id)["reserved"] == 310
        # Explicit test seller operations. Independent scheduled seller is the next integration.
        admin_path = (
            f"/admin/orders/{oid}?fields=+customer_id,+currency_code,"
            "*payment_collections.payments.captures,*fulfillments,*items"
        )
        external = spike.get(admin_path)["order"]
        pid = external["payment_collections"][0]["payments"][0]["id"]
        spike.post(f"/admin/payments/{pid}/capture", {})
        line_items = [{"id": i["id"], "quantity": i["quantity"]} for i in external["items"]]
        spike.post(
            f"/admin/orders/{oid}/fulfillments",
            {
                "items": line_items,
                "location_id": fixture["location"]["id"],
                "shipping_option_id": fixture["shipping"]["id"],
                "no_notification": True,
            },
        )
        external = spike.get(admin_path)["order"]
        fid = external["fulfillments"][0]["id"]
        spike.post(
            f"/admin/orders/{oid}/fulfillments/{fid}/shipments",
            {"items": line_items, "labels": [], "no_notification": True},
        )
        spike.post(
            f"/admin/orders/{oid}/fulfillments/{fid}/mark-as-delivered", {"no_notification": True}
        )
        external = spike.get(admin_path)["order"]
        assert gateway.get_payment(order["id"])["status"] == "SETTLED"
        snapshot = gateway.observe_world()
        assert snapshot["inventory"] == {"tent": 3, "light": 6}
        assert snapshot["balance"] == {"budget": 500, "spent": 310, "reserved": 0, "available": 190}
        assert gateway.observe_world()["inventory"] == snapshot["inventory"]
        gateway = MedusaGateway(spike.directory / "gateway", binding, api)
        assert gateway.observe_world()["inventory"] == snapshot["inventory"]
        evidence = {
            "binding": asdict(binding),
            "external_orders": [external],
            "tables": {},
            "scope": report["scope"],
            "captured_at_tick": gateway.tick(),
        }
        for filename, tables in (
            ("medusa.sqlite3", ("purchases", "quotes")),
            ("payments.sqlite3", ("accounts", "intents")),
        ):
            with sqlite3.connect(
                f"file:{spike.directory / 'gateway' / filename}?mode=ro", uri=True
            ) as db:
                db.row_factory = sqlite3.Row
                for table in tables:
                    evidence["tables"][table] = [
                        dict(r) for r in db.execute(f"SELECT * FROM {table}")
                    ]
        from rehearsal.evaluation.medusa import verify_medusa

        (spike.directory / "adapter-evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        verdict = verify_medusa(evidence, binding.goal, 500)
        assert verdict["status"] == "COMPLETE", verdict
        report.update(
            {
                "passed": True,
                "snapshot": snapshot,
                "verdict": verdict,
                "checks": [
                    "real-price-refresh-stale",
                    "durable-lost-complete-read-only-recovery",
                    "same-key-replay",
                    "replacement-key-rejected",
                    "run-scope",
                    "external-id-not-a-handle",
                    "customer-identity",
                    "budget-before-payment",
                    "captured-and-delivered",
                    "repeat-poll-no-double-receipt",
                    "restart",
                ],
                "http_calls": len(spike.report["requests"]),
                "evidence_sha256": hashlib.sha256(
                    (spike.directory / "adapter-evidence.json").read_bytes()
                ).hexdigest(),
            }
        )
    finally:
        if api:
            api.close()
        spike.report["passed"] = report["passed"]
        spike.save()
        (spike.directory / "adapter-report.json").write_text(json.dumps(report, indent=2) + "\n")
        for client in spike.clients.values():
            client.close()
        print(f"Evidence: {spike.directory.relative_to(ROOT)}")
    print(
        "PASS: real Medusa customer adapter; synthetic seller; no model calls or policy transfer."
    )


if __name__ == "__main__":
    main()
