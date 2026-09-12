"""Test-only factory: synchronize two real Medusa checkout requests, never fake results."""

import json
import os
import threading
import time
from pathlib import Path

from rehearsal.commerce.gateway import Binding, MedusaGateway, StoreAPI
from rehearsal.commerce.server import create_app as commerce_app


def create_app():
    config = json.loads(Path(os.environ["REHEARSAL_MEDUSA_CONFIG"]).read_text())
    if len(config["runs"]) != 2:
        raise ValueError("Race fixture requires exactly two isolated runs")
    barrier, lock = threading.Barrier(2), threading.Lock()
    path = Path(config["directory"]) / "race-trace.jsonl"
    arrived = set()

    def record(value):
        with lock, path.open("a") as f:
            f.write(json.dumps(value) + "\n")

    class RacingStore(StoreAPI):
        def __init__(self, run_id, values):
            super().__init__(values["store_token"], values["publishable_key"])
            self.run_id = run_id

        def call(self, method, route, body=None):
            checkout = method == "POST" and route.endswith("/complete")
            if checkout:
                with lock:
                    if self.run_id in arrived:
                        raise AssertionError("Unexpected checkout resubmission")
                    arrived.add(self.run_id)
                record({"phase": "arrived", "run_id": self.run_id, "at": time.monotonic()})
                barrier.wait(timeout=15)
            started = time.monotonic()
            result, error = None, None
            try:
                result = super().call(method, route, body)
                return result
            except Exception as exc:
                error = getattr(exc, "code", type(exc).__name__)
                raise
            finally:
                value = {
                    "run_id": self.run_id,
                    "method": method,
                    "path": route,
                    "started": started,
                    "ended": time.monotonic(),
                    "error": error,
                }
                if checkout:
                    value["response_type"] = result.get("type") if result else None
                    value["checkout_error"] = result.get("error") if result else None
                record(value)

    gateways = {
        rid: MedusaGateway(Path(run["directory"]), Binding(**run["binding"]), RacingStore(rid, run))
        for rid, run in config["runs"].items()
    }
    return commerce_app(config=config, gateways=gateways)
