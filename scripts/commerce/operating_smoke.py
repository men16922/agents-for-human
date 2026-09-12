#!/usr/bin/env python3
"""Real HTTP -> Medusa -> independent seller, with all three supplier catalogues."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path

import httpx
from contract_spike import ROOT, Spike
from operating_fixture import prepare, start_gateway, start_seller

from rehearsal.commerce.seller import ORDER_FIELDS, read_rows
from rehearsal.evaluation.medusa import verify_medusa
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN, stop
from rehearsal.world.storage import ContractError


def wait_until(read, predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(0.15)
    raise AssertionError("Timed out waiting for explicit remote state")


def main():
    os.umask(0o077)
    spike = Spike()
    spike.report["scope"] = "medusa-operating-sandbox-fixture-and-observer"
    processes, clients = [], []
    report = {
        "passed": False,
        "scope": "live-http-medusa-independent-seller",
        "real_model_calls": 0,
        "policy_transfer_verified": False,
        "scenario_version": "medusa-operating-smoke-v1",
        "run_id": spike.run_id,
    }
    try:
        directory, credentials, config, fixtures = prepare(spike)
        seller = start_seller(directory)
        processes.append(seller)
        gateway = start_gateway(directory)
        processes.append(gateway)
        run_id, other_run = list(config["runs"])
        run = config["runs"][run_id]
        tokens = credentials["runs"][run_id]
        buyer = OperatingClient(ORIGIN, run_id, tokens["buyer"], timeout=10)
        clients.append(buyer)
        headers = {role: {"Authorization": "Bearer " + token} for role, token in tokens.items()}
        checks = {}
        report["checks"] = checks
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=10) as inspector:
            checks["unauthenticated"] = inspector.get(f"/runs/{run_id}/snapshot").status_code
            checks["cross_run"] = inspector.get(
                f"/runs/{other_run}/snapshot", headers=headers["buyer"]
            ).status_code
            checks["observer_write"] = inspector.post(
                f"/runs/{run_id}/quotes",
                headers=headers["observer"],
                json={"supplier": "A", "items": {"tent": 1}},
            ).status_code
            checks["amount_injection"] = inspector.post(
                f"/runs/{run_id}/payments",
                headers=headers["buyer"],
                json={"order_id": "order_bad", "idempotency_key": "bad", "amount": 1},
            ).status_code
            assert checks == {
                "unauthenticated": 401,
                "cross_run": 403,
                "observer_write": 403,
                "amount_injection": 422,
            }, checks
            quotes = {
                name: buyer.get_quotes(name, {"tent": 3, "light": 6}) for name in ("A", "B", "C")
            }
            checks["supplier_totals"] = {name: q["amount"] for name, q in quotes.items()}
            assert checks["supplier_totals"] == {"A": 310, "B": 380, "C": 495}
            a = fixtures["A"]
            spike.post(
                f"/admin/products/{a['products'][0]}/variants/{a['variants'][0]}",
                {"prices": [{"currency_code": "usd", "amount": 100}]},
            )
            try:
                buyer.create_order(quotes["A"]["id"], "stale")
            except ContractError as exc:
                assert exc.code == "STALE_QUOTE", exc.code
                checks["stale_quote"] = exc.code
            else:
                raise AssertionError("Expected real stale quote rejection")
            fresh = buyer.get_quotes("B", {"tent": 3, "light": 6})
            order = buyer.create_order(fresh["id"], "buy")
            checks["other_order"] = inspector.get(
                f"/runs/{other_run}/orders/{order['id']}",
                headers={"Authorization": "Bearer " + credentials["runs"][other_run]["buyer"]},
            ).status_code
            assert checks["other_order"] == 404
            fault = f"/admin/runs/{run_id}/faults/payment-response-delay"
            assert (
                inspector.post(fault, headers=headers["buyer"], json={"delay_ms": 1200}).status_code
                == 403
            )
            assert (
                inspector.post(
                    fault, headers=headers["control"], json={"delay_ms": 1200}
                ).status_code
                == 200
            )
            uncertain = OperatingClient(ORIGIN, run_id, tokens["buyer"], timeout=0.4)
            clients.append(uncertain)
            checks["lost_http_response"] = uncertain.authorize_payment(order["id"], "pay").status
            assert checks["lost_http_response"] == "UNKNOWN"
            # Read local mappings and admin observations; buyer tools do not drive the seller.
            rows = wait_until(
                lambda: read_rows(Path(run["directory"]) / "medusa.sqlite3", "purchases"),
                lambda rows: any(p["external_id"] for p in rows),
            )
            oid = next(p["external_id"] for p in rows if p["id"] == order["id"])

            def external():
                return spike.get(f"/admin/orders/{oid}?fields={ORDER_FIELDS}")["order"]

            shipped = wait_until(external, lambda o: o["fulfillment_status"] == "shipped")
            assert shipped["payment_status"] == "captured"
            stop(seller)
            checks["seller_stopped_health"] = inspector.get("/health").status_code
            checks["seller_stopped_write"] = inspector.post(
                f"/runs/{run_id}/quotes",
                headers=headers["buyer"],
                json={"supplier": "C", "items": {"tent": 1}},
            ).status_code
            assert checks["seller_stopped_health"] == checks["seller_stopped_write"] == 503
            assert (
                inspector.get(
                    f"/runs/{run_id}/orders/{order['id']}", headers=headers["observer"]
                ).status_code
                == 200
            )
        stop(gateway)
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", 18001)) != 0
        schedule_before = read_rows(directory / "seller.sqlite3", "schedules")
        restarted_seller = start_seller(directory)
        processes.append(restarted_seller)
        delivered = wait_until(external, lambda o: o["fulfillment_status"] == "delivered")
        assert gateway.poll() is not None, "Delivery must occur while purchasing HTTP is stopped"
        checks["delivery_without_purchasing_server"] = True
        schedule_after = read_rows(directory / "seller.sqlite3", "schedules")
        assert schedule_before == schedule_after
        schedule = next(s for s in schedule_after if s["order_id"] == oid)
        delivered_at = datetime.fromisoformat(
            delivered["fulfillments"][0]["delivered_at"].replace("Z", "+00:00")
        ).timestamp()
        assert delivered_at >= schedule["due_at"] - 0.1
        checks["lead_seconds"] = schedule["due_at"] - schedule["first_seen"]
        assert checks["lead_seconds"] == 6
        restarted_gateway = start_gateway(directory)
        processes.append(restarted_gateway)
        payment = buyer.get_payment(order["id"])
        assert payment.status == "SETTLED" and payment.payment is not None
        replay = buyer.authorize_payment(order["id"], "pay")
        assert replay.payment["id"] == payment.payment["id"]
        snapshot = buyer.observe_world()
        assert snapshot["inventory"] == {"tent": 3, "light": 6}
        assert snapshot["balance"] == {"budget": 500, "spent": 380, "reserved": 0, "available": 120}
        assert buyer.observe_world()["inventory"] == snapshot["inventory"]
        stop(restarted_gateway)
        stop(restarted_seller)
        final = external()
        evidence = {
            "binding": run["binding"],
            "external_orders": [final],
            "tables": {},
            "captured_at_tick": snapshot["tick"],
            "scope": report["scope"],
        }
        for filename, tables in (
            ("medusa.sqlite3", ("purchases", "quotes")),
            ("payments.sqlite3", ("accounts", "intents")),
        ):
            for table in tables:
                evidence["tables"][table] = read_rows(Path(run["directory"]) / filename, table)
        evidence["seller_schedules"] = schedule_after
        evidence["seller_actions"] = read_rows(directory / "seller.sqlite3", "actions")
        actions = evidence["seller_actions"]
        assert len(actions) == 4 and {a["action"] for a in actions} == {
            "capture",
            "fulfill",
            "ship",
            "deliver",
        }
        assert all(a["status"] == "OBSERVED" for a in actions)
        assert (
            next(a["started_at"] for a in actions if a["action"] == "deliver") >= schedule["due_at"]
        )
        verdict = verify_medusa(
            evidence,
            {"items": {"tent": 3, "light": 6}, "deadline_tick": 120, "recipient": "venue"},
            500,
        )
        assert verdict["status"] == "COMPLETE", verdict
        (spike.directory / "operating-evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        report.update(
            {
                "passed": True,
                "snapshot": snapshot,
                "verdict": verdict,
                "seller_pids": [seller.pid, restarted_seller.pid],
                "gateway_pids": [gateway.pid, restarted_gateway.pid],
                "medusa_version": spike.report["medusa_version"],
                "package_lock_sha256": spike.report["package_lock_sha256"],
                "evidence_sha256": hashlib.sha256(
                    (spike.directory / "operating-evidence.json").read_bytes()
                ).hexdigest(),
                "source_sha256": {
                    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in (
                        "scripts/commerce/operating_smoke.py",
                        "scripts/commerce/operating_fixture.py",
                        "src/rehearsal/commerce/gateway.py",
                        "src/rehearsal/commerce/seller.py",
                        "src/rehearsal/commerce/server.py",
                        "src/rehearsal/evaluation/medusa.py",
                        "src/rehearsal/operating/local.py",
                        "src/rehearsal/operating/client.py",
                    )
                },
            }
        )
    finally:
        for process in reversed(processes):
            stop(process)
        for client in clients:
            client.close()
        spike.report["passed"] = report["passed"]
        spike.save()
        (spike.directory / "operating-report.json").write_text(json.dumps(report, indent=2) + "\n")
        for client in spike.clients.values():
            client.close()
        print(f"Evidence: {spike.directory.relative_to(ROOT)}")
    print(
        "PASS: real HTTP, independent Medusa seller and restart; no model/transfer claim."
    )


if __name__ == "__main__":
    main()
