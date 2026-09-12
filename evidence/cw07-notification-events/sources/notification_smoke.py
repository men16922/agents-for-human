#!/usr/bin/env python3
"""Real Medusa delivery with delayed/duplicate/reordered SSE and durable reconnect."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import httpx
from contract_spike import ROOT, Spike
from operating_fixture import prepare, start_gateway, start_seller
from operating_smoke import wait_until

from rehearsal.commerce.observations import Projection
from rehearsal.commerce.seller import ORDER_FIELDS, read_rows
from rehearsal.evaluation.medusa import verify_medusa
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN, stop


def stream_until(client, run_id, headers, cursor, accept, seconds=25):
    frames, fields = [], {}
    deadline = time.monotonic() + seconds
    with client.stream(
        "GET",
        f"/runs/{run_id}/events",
        headers=headers
        | {
            "Last-Event-ID": str(cursor),
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            assert time.monotonic() < deadline, "SSE condition timed out"
            if line:
                key, _, value = line.partition(":")
                fields[key] = value.lstrip()
            elif fields:
                frame = {
                    "type": fields["event"],
                    "data": json.loads(fields["data"]),
                    "received_at": time.time(),
                }
                if "id" in fields:
                    frame["id"] = int(fields["id"])
                frames.append(frame)
                fields = {}
                if accept(frame):
                    return frames
    raise AssertionError("SSE ended before expected notification")


def main():
    os.umask(0o077)
    spike = Spike()
    spike.report["scope"] = "medusa-notification-fixture-and-admin-observer"
    processes, clients = [], []
    report = {
        "passed": False,
        "scope": "live-medusa-f03-http-sse-known-fixture",
        "real_model_calls": 0,
        "browser_ui_verified": False,
        "run_id": spike.run_id,
    }
    try:
        directory, credentials, config, _ = prepare(spike)
        seller = start_seller(directory)
        processes.append(seller)
        gateway = start_gateway(directory)
        processes.append(gateway)
        run_id, other_run = list(config["runs"])
        run = config["runs"][run_id]
        headers = {
            role: {"Authorization": "Bearer " + token}
            for role, token in credentials["runs"][run_id].items()
        }
        buyer = OperatingClient(ORIGIN, run_id, credentials["runs"][run_id]["buyer"], timeout=10)
        clients.append(buyer)
        frames, outcomes = [], []
        report["frames"], report["projection_outcomes"] = frames, outcomes
        projection = Projection(run_id)
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=10) as inspector:
            checks = {
                "unauthenticated_stream": inspector.get(f"/runs/{run_id}/events").status_code,
                "cross_run_stream": inspector.get(
                    f"/runs/{other_run}/events", headers=headers["observer"]
                ).status_code,
                "buyer_fault_denied": inspector.post(
                    f"/admin/runs/{run_id}/faults/delivery-notification",
                    headers=headers["buyer"],
                    json={},
                ).status_code,
            }
            assert checks == {
                "unauthenticated_stream": 401,
                "cross_run_stream": 403,
                "buyer_fault_denied": 403,
            }
            report["checks"] = checks
            frames.extend(
                stream_until(
                    inspector,
                    run_id,
                    headers["observer"],
                    0,
                    lambda frame: frame["type"] == "observation",
                )
            )
            first = frames[-1]["data"]
            assert projection.apply(first) == "applied"
            assert first["event"]["snapshot"]["inventory"] == {"tent": 0, "light": 0}
            response = inspector.post(
                f"/admin/runs/{run_id}/faults/delivery-notification",
                headers=headers["control"],
                json={"delay_ms": 2000, "copies": 2},
            )
            assert response.status_code == 200
            quote = buyer.get_quotes("A", {"tent": 3, "light": 6})
            order = buyer.create_order(quote["id"], "f03-buy")
            payment = buyer.authorize_payment(order["id"], "f03-pay")
            assert payment.status in {"RESERVED", "SETTLED"}
            # From here until notification recovery, only observer/admin GETs and SSE occur.
            rows = wait_until(
                lambda: read_rows(Path(run["directory"]) / "medusa.sqlite3", "purchases"),
                lambda rows: any(p["external_id"] for p in rows),
            )
            oid = next(p["external_id"] for p in rows if p["id"] == order["id"])

            def external():
                return spike.get(f"/admin/orders/{oid}?fields={ORDER_FIELDS}")["order"]

            delayed = []

            def accept_delivery(frame):
                if frame["type"] != "observation":
                    return False
                value = frame["data"]
                outcomes.append({"cursor": value["cursor"], "result": projection.apply(value)})
                event = value["event"]
                if event["event_type"] == "delivery.observed":
                    delayed.append(value)
                elif event["snapshot"]["inventory"] == {"tent": 3, "light": 6} and not delayed:
                    actual = external()
                    assert actual["fulfillment_status"] == "delivered"
                    pending = read_rows(directory / "observations.sqlite3", "pending")
                    assert len(pending) >= 2
                    checks["actual_delivery_precedes_delayed_notice"] = True
                    report["external_while_notice_pending"] = actual
                return len(delayed) == 2

            frames.extend(
                stream_until(
                    inspector, run_id, headers["observer"], projection.cursor, accept_delivery
                )
            )
            assert checks["actual_delivery_precedes_delayed_notice"]
            assert [d["event"]["event_id"] for d in delayed] == [
                delayed[0]["event"]["event_id"]
            ] * 2
            assert [o["result"] for o in outcomes[-2:]] == ["old", "duplicate"]
            checks["delayed_seconds"] = (
                delayed[0]["published_at"] - delayed[0]["event"]["observed_at"]
            )
            assert checks["delayed_seconds"] >= 2
            assert projection.snapshot["inventory"] == {"tent": 3, "light": 6}
            before_replay = projection.cursor
            response = inspector.post(
                f"/admin/runs/{run_id}/faults/replay-notification",
                headers=headers["control"],
                json={"event_id": first["event"]["event_id"]},
            )
            assert response.status_code == 200

            def accept_replay(frame):
                if frame["type"] != "observation":
                    return False
                result = projection.apply(frame["data"])
                outcomes.append({"cursor": frame["id"], "result": result})
                if frame["data"]["event"]["event_id"] == first["event"]["event_id"]:
                    assert result == "duplicate" and frame["id"] > before_replay
                    return True
                return False

            frames.extend(
                stream_until(inspector, run_id, headers["observer"], before_replay, accept_replay)
            )
            checks["old_snapshot_cannot_remove_received_items"] = projection.snapshot[
                "inventory"
            ] == {"tent": 3, "light": 6}
            assert checks["old_snapshot_cannot_remove_received_items"]
            # Pending duplicate notifications and delivery cursor survive server restart.
            event_id = delayed[0]["event"]["event_id"]
            assert (
                inspector.post(
                    f"/admin/runs/{run_id}/faults/replay-notification",
                    headers=headers["control"],
                    json={"event_id": event_id, "delay_ms": 3000, "copies": 2},
                ).status_code
                == 200
            )
            assert len(read_rows(directory / "observations.sqlite3", "pending")) >= 2
            before_restart = projection.cursor
            stop(gateway)
            restarted = start_gateway(directory)
            processes.append(restarted)
            recovered = []

            def accept_restart(frame):
                if frame["type"] == "observation":
                    result = projection.apply(frame["data"])
                    outcomes.append({"cursor": frame["id"], "result": result})
                    if frame["data"]["event"]["event_id"] == event_id:
                        assert result == "duplicate"
                        recovered.append(frame["id"])
                return len(recovered) == 2

            frames.extend(
                stream_until(inspector, run_id, headers["observer"], before_restart, accept_restart)
            )
            assert min(recovered) > before_restart
            checks["pending_and_cursor_survive_restart"] = True
            final_snapshot = buyer.observe_world()
            for field in ("balance", "inventory", "goal"):
                assert projection.snapshot[field] == final_snapshot[field]
            assert final_snapshot["balance"] == {
                "budget": 500,
                "spent": 310,
                "reserved": 0,
                "available": 190,
            }
            # A deliberately small retention window exercises HTTP/SSE snapshot reset.
            stop(restarted)
            config["observation_retention"] = 2
            (directory / "server.json").write_text(json.dumps(config, indent=2) + "\n")
            limited = start_gateway(directory)
            processes.append(limited)
            wait_until(
                lambda: inspector.get(
                    f"/runs/{run_id}/observations", headers=headers["observer"]
                ).json(),
                lambda batch: batch["retained_after"] > 0,
            )
            reset_frames = stream_until(
                inspector, run_id, headers["observer"], 0, lambda frame: frame["type"] == "snapshot"
            )
            reset = reset_frames[-1]["data"]
            reset_projection = Projection(run_id)
            reset_projection.reset(reset)
            assert reset_projection.snapshot["inventory"] == final_snapshot["inventory"]
            checks["expired_cursor_snapshot_reset"] = True
            frames.extend(reset_frames)
            stop(limited)
        stop(seller)
        final = external()
        evidence = {
            "binding": run["binding"],
            "external_orders": [final],
            "tables": {},
            "captured_at_tick": final_snapshot["tick"],
            "scope": report["scope"],
        }
        for filename, tables in (
            ("medusa.sqlite3", ("purchases", "quotes")),
            ("payments.sqlite3", ("accounts", "intents")),
        ):
            for table in tables:
                evidence["tables"][table] = read_rows(Path(run["directory"]) / filename, table)
        evidence["seller_actions"] = read_rows(directory / "seller.sqlite3", "actions")
        assert len(evidence["seller_actions"]) == 4
        assert all(a["status"] == "OBSERVED" for a in evidence["seller_actions"])
        verdict = verify_medusa(evidence, run["binding"]["goal"], 500)
        assert verdict["status"] == "COMPLETE", verdict
        evidence_path = spike.directory / "notification-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
        report.update(
            passed=True,
            snapshot=final_snapshot,
            verdict=verdict,
            medusa_version=spike.report["medusa_version"],
            package_lock_sha256=spike.report["package_lock_sha256"],
            evidence_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            process_pids=[p.pid for p in processes],
            source_sha256={
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in (
                    "scripts/commerce/notification_smoke.py",
                    "scripts/commerce/operating_fixture.py",
                    "src/rehearsal/commerce/observations.py",
                    "src/rehearsal/commerce/observer.py",
                    "src/rehearsal/commerce/server.py",
                    "src/rehearsal/commerce/gateway.py",
                    "src/rehearsal/commerce/seller.py",
                    "src/rehearsal/evaluation/medusa.py",
                )
            },
        )
    finally:
        for process in reversed(processes):
            stop(process)
        for client in clients:
            client.close()
        spike.report["passed"] = report["passed"]
        spike.save()
        (spike.directory / "notification-report.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        for client in spike.clients.values():
            client.close()
        print(f"Evidence: {spike.directory.relative_to(ROOT)}")
    print(
        "PASS: actual Medusa delivery, F03 SSE recovery and independent ledger; no model/UI claim."
    )


if __name__ == "__main__":
    main()
