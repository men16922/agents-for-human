#!/usr/bin/env python3
"""Observe real Medusa delivery through the gateway, preserving raw transitional GETs."""

import json
import os
import time
from copy import deepcopy
from pathlib import Path

from contract_spike import ROOT, Spike
from operating_fixture import prepare, start_seller
from stock_smoke import export_run

from rehearsal.commerce.gateway import Binding, MedusaGateway, StoreAPI
from rehearsal.commerce.model_runner import digest, write
from rehearsal.evaluation.medusa import verify_medusa
from rehearsal.operating.local import stop
from rehearsal.world.storage import identifier


class CapturedStore(StoreAPI):
    def __init__(self, *args):
        super().__init__(*args)
        self.last = None
        self.posts = []

    def call(self, method, path, body=None):
        value = super().call(method, path, body)
        if method == "POST":
            self.posts.append(path)
        if method == "GET" and path.startswith("/store/orders/"):
            self.last = deepcopy(value["order"])
        return value


def main():
    os.umask(0o077)
    folder = ROOT / ".local/evaluation" / identifier("delivery-fixed")
    folder.mkdir()
    spike = Spike()
    seller = store = None
    result = {
        "passed": False,
        "real_model_calls": 0,
        "samples": [],
        "counts": {},
        "source_sha256": digest(ROOT / "src/rehearsal/commerce/gateway.py"),
    }
    try:
        case = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
        case["goal"]["deadline_tick"] = 120
        directory, _, config, _ = prepare(spike, case=case)
        run = next(iter(config["runs"].values()))
        store = CapturedStore(run["store_token"], run["publishable_key"])
        gateway = MedusaGateway(Path(run["directory"]), Binding(**run["binding"]), store)
        seller = start_seller(directory)
        quote = gateway.get_quotes("A", {"tent": 3, "light": 6})
        order = gateway.create_order(quote["id"], "delivery-buy")
        gateway.authorize_payment(order["id"], "delivery-pay")
        result.update(
            session=str(spike.directory.relative_to(ROOT)),
            run_id=run["binding"]["run_id"],
            local_order=order["id"],
        )
        posts = list(store.posts)
        deadline = time.monotonic() + 30
        seen = set()
        while time.monotonic() < deadline:
            balance = gateway.payments.balance(gateway.binding.run_id)
            begin = time.time()
            payment = gateway.get_payment(order["id"])
            end = time.time()
            raw = store.last
            state = (
                "pending"
                if payment.get("reason") == "EXTERNAL_DELIVERY_PENDING"
                else raw["fulfillment_status"]
            )
            result["counts"][state] = result["counts"].get(state, 0) + 1
            if state not in seen or state == "pending":
                result["samples"].append(
                    {"begin": begin, "end": end, "state": state, "payment": payment, "order": raw}
                )
                seen.add(state)
            if state == "pending":
                assert gateway.payments.balance(gateway.binding.run_id) == balance
                assert gateway._purchase(order["id"])["received_tick"] is None
            if gateway._purchase(order["id"])["received_tick"] is not None:
                break
            time.sleep(0.005)
        snapshot = gateway.observe_world()
        assert snapshot["inventory"] == {"tent": 3, "light": 6}
        assert snapshot["balance"]["spent"] == 310 and snapshot["balance"]["reserved"] == 0
        assert store.posts == posts and sum(p.endswith("/complete") for p in posts) == 1
        stop(seller)
        seller = None
        evidence = export_run(spike, run, snapshot)
        write(folder / "evidence.json", evidence)
        verdict = verify_medusa(evidence, run["binding"]["goal"], run["binding"]["budget"])
        assert verdict["status"] == "COMPLETE"
        result.update(
            passed=True,
            snapshot=snapshot,
            verdict=verdict,
            checkout_count=1,
            read_only_after_checkout=True,
        )
    finally:
        if seller:
            stop(seller)
        if store:
            store.close()
        spike.save()
        for client in spike.clients.values():
            client.close()
        write(folder / "smoke.json", result)
        print(
            f"{'PASS' if result['passed'] else 'FAIL'} delivery transition: {folder}; "
            f"{result['counts']}"
        )


if __name__ == "__main__":
    main()
