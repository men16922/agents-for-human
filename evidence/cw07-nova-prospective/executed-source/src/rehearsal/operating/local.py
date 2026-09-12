"""Start/stop only a loopback operating process; preserve every run's databases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from rehearsal.evaluation.verifier import verify
from rehearsal.world import World
from rehearsal.world.storage import identifier

from .client import OperatingClient

PORT = 18001
ORIGIN = f"http://127.0.0.1:{PORT}"


def prepare(root: Path, smoke: bool) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    directory = root / ".local/operating" / identifier("http")
    directory.mkdir(parents=True, mode=0o700)
    world = World(directory)
    scenario = json.loads((root / "scenarios/normal-v1.json").read_text())
    if smoke:
        scenario["scenario_version"] = "http-smoke-v1"
        scenario["goal"]["deadline_tick"] = 30
        for supplier in scenario["suppliers"].values():
            supplier["lead_ticks"] = 2
    config: dict[str, Any] = {
        "directory": str(directory),
        "runs": ["buyer-one", "buyer-two"],
        "grants": {},
    }
    credentials: dict[str, Any] = {"origin": ORIGIN, "runs": {}}
    for run_id in config["runs"]:
        world.create_run(run_id, scenario, environment="operating-test")
        credentials["runs"][run_id] = {}
        for role in ("buyer", "observer", "control"):
            token = secrets.token_urlsafe(32)
            credentials["runs"][run_id][role] = token
            config["grants"][hashlib.sha256(token.encode()).hexdigest()] = {
                "run_id": run_id,
                "role": role,
            }
    (directory / "server.json").write_text(json.dumps(config, indent=2) + "\n")
    (directory / "credentials.json").write_text(json.dumps(credentials, indent=2) + "\n")
    return directory, credentials, scenario


def check_port(port: int) -> None:
    with socket.socket() as probe:
        # Match uvicorn's socket semantics: TIME_WAIT is not a live port owner.
        # SO_REUSEADDR still refuses an active listening socket.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))


def start(
    directory: Path,
    *,
    factory: str = "rehearsal.operating.server:create_app",
    config_variable: str = "REHEARSAL_OPERATING_CONFIG",
) -> subprocess.Popen[bytes]:
    check_port(PORT)
    env = dict(os.environ)
    env[config_variable] = str(directory / "server.json")
    with (directory / "server.log").open("ab") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                factory,
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
                "--no-access-log",
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Operating process exited; inspect private server.log")
        try:
            with httpx.Client(trust_env=False, timeout=0.5) as client:
                response = client.get(ORIGIN + "/health")
            if response.status_code == 200 and response.json()["worker_cycles"] > 0:
                return process
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    stop(process)
    raise RuntimeError("Operating process readiness timed out")


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def smoke(
    directory: Path, credentials: dict[str, Any], process: subprocess.Popen[bytes]
) -> dict[str, Any]:
    tokens = credentials["runs"]
    buyer = OperatingClient(ORIGIN, "buyer-one", tokens["buyer-one"]["buyer"], timeout=0.15)
    observed: dict[str, Any] = {"scope": "CW05-local-HTTP-not-Medusa-transfer", "checks": {}}
    checks = observed["checks"]
    control = {"Authorization": "Bearer " + tokens["buyer-one"]["control"]}
    try:
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=3) as inspector:
            checks["unauthenticated"] = inspector.get("/runs/buyer-one/snapshot").status_code
            checks["cross_run"] = inspector.get(
                "/runs/buyer-two/snapshot",
                headers={"Authorization": "Bearer " + tokens["buyer-one"]["buyer"]},
            ).status_code
            checks["observer_write"] = inspector.post(
                "/runs/buyer-one/quotes",
                headers={"Authorization": "Bearer " + tokens["buyer-one"]["observer"]},
                json={"supplier": "A", "items": {"tent": 1}},
            ).status_code
            assert checks["unauthenticated"] == 401
            assert checks["cross_run"] == checks["observer_write"] == 403
            quote = buyer.get_quotes("A", {"tent": 3, "light": 6})
            response = inspector.post(
                "/admin/runs/buyer-one/offers/A/tent/price", headers=control, json={"price": 100}
            )
            assert response.status_code == 200
            stale = inspector.post(
                "/runs/buyer-one/orders",
                headers={"Authorization": "Bearer " + tokens["buyer-one"]["buyer"]},
                json={"quote_id": quote["id"], "idempotency_key": "supplies"},
            )
            assert stale.status_code == 409 and stale.json()["error"] == "STALE_QUOTE"
            checks["stale_quote"] = stale.json()
            fresh = buyer.get_quotes("B", {"tent": 3, "light": 6})
            order = buyer.create_order(fresh["id"], "supplies")
            observed["order_id"] = order["id"]
            cross = inspector.get(
                f"/runs/buyer-two/orders/{order['id']}",
                headers={"Authorization": "Bearer " + tokens["buyer-two"]["buyer"]},
            )
            assert cross.status_code == 404
            checks["other_customer_order"] = cross.status_code
            assert (
                inspector.post(
                    "/admin/runs/buyer-one/faults/payment-response-delay",
                    headers=control,
                    json={"delay_ms": 700},
                ).status_code
                == 200
            )
        observation = buyer.authorize_payment(order["id"], "stable-payment")
        assert observation.status == "UNKNOWN"
        checks["lost_response"] = observation.status
        # No replacement purchase; the clock/seller advances with no buyer requests.
        before_tick = buyer.observe_world()["tick"]
        time.sleep(2.2)
        payment = buyer.get_payment(order["id"])
        assert payment.status == "SETTLED" and payment.payment is not None
        checks["reconciled_payment"] = payment.status
        retry = buyer.authorize_payment(order["id"], "stable-payment")
        assert retry.payment is not None and retry.payment["id"] == payment.payment["id"]
        snapshot = buyer.observe_world()
        assert snapshot["tick"] >= before_tick + 2
        # Settlement can straddle a tick boundary; read without driving the worker.
        deadline = time.monotonic() + 3
        while snapshot["inventory"] != {"tent": 3, "light": 6} and time.monotonic() < deadline:
            time.sleep(0.1)
            snapshot = buyer.observe_world()
        assert snapshot["inventory"] == {"tent": 3, "light": 6}
        assert snapshot["balance"]["spent"] == 380 and snapshot["balance"]["reserved"] == 0
        checks["autonomous_clock_and_delivery"] = True
        observed["snapshot_before_restart"] = snapshot
        stop(process)
        # Restart the identical DBs/config; no reset, migration or new token.
        restarted = start(directory)
        try:
            after = buyer.observe_world()
            assert after["tick"] >= snapshot["tick"]
            assert after["inventory"] == snapshot["inventory"]
            recovered = buyer.get_payment(order["id"]).payment
            assert recovered is not None and recovered["id"] == payment.payment["id"]
            checks["restart_preserved_state"] = True
            observed["snapshot_after_restart"] = after
        finally:
            stop(restarted)
        return observed
    finally:
        buyer.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(__file__).resolve().parents[3]
    directory, credentials, scenario = prepare(root, args.smoke)
    process = start(directory)
    try:
        if args.smoke:
            report = smoke(directory, credentials, process)
            verdict = verify(
                directory, "buyer-one", scenario, export_to=directory / "evidence.json"
            )
            assert verdict.status == "COMPLETE", verdict
            report["verdict"] = verdict.as_dict()
            (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(f"PASS: HTTP, worker, response loss, isolation, restart. Evidence: {directory}")
        else:
            print(
                f"Operating server: {ORIGIN}. Credentials: {directory / 'credentials.json'}",
                flush=True,
            )
            print("Ctrl+C stops this owned process and preserves its databases.", flush=True)
            process.wait()
    except KeyboardInterrupt:
        print("Stopping owned operating server; databases preserved.")
    finally:
        stop(process)


if __name__ == "__main__":
    main()
