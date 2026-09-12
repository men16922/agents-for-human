from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rehearsal.operating.server import Grant, ServerSettings, create_app
from rehearsal.world import World


@pytest.fixture
def setup(tmp_path):
    fixture = json.loads(
        (Path(__file__).resolve().parents[2] / "scenarios/normal-v1.json").read_text()
    )
    world = World(tmp_path)
    for run_id in ("one", "two"):
        world.create_run(run_id, fixture, environment="operating-test")
    grants = {
        hashlib.sha256(token.encode()).hexdigest(): Grant(run_id, role)
        for token, run_id, role in (
            ("buyer-one", "one", "buyer"),
            ("buyer-two", "two", "buyer"),
            ("observer", "one", "observer"),
            ("control", "one", "control"),
        )
    }
    app = create_app(ServerSettings(tmp_path, grants, ["one", "two"]), start_worker=False)
    with TestClient(app) as client:
        yield client, app


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def purchase(client, run_id="one", token="buyer-one"):
    quote = client.post(
        f"/runs/{run_id}/quotes",
        headers=headers(token),
        json={"supplier": "A", "items": {"tent": 3, "light": 6}},
    )
    assert quote.status_code == 200
    result = client.post(
        f"/runs/{run_id}/orders",
        headers=headers(token),
        json={"quote_id": quote.json()["id"], "idempotency_key": "buy"},
    )
    assert result.status_code == 200
    return result.json()


def test_every_read_and_mutation_is_authenticated_and_run_scoped(setup):
    client, _ = setup
    order = purchase(client)
    paths = [
        ("GET", "/runs/one/snapshot", None),
        ("GET", f"/runs/one/orders/{order['id']}", None),
        ("POST", "/runs/one/quotes", {"supplier": "A", "items": {"tent": 1}}),
        ("POST", "/runs/one/payments", {"order_id": order["id"], "idempotency_key": "pay"}),
    ]
    for method, path, body in paths:
        assert client.request(method, path, json=body).status_code == 401
        assert (
            client.request(method, path, json=body, headers=headers("buyer-two")).status_code == 403
        )
    assert (
        client.get(f"/runs/two/orders/{order['id']}", headers=headers("buyer-two")).status_code
        == 404
    )
    assert (
        client.get(f"/runs/two/payments/{order['id']}", headers=headers("buyer-two")).status_code
        == 404
    )


def test_observer_cannot_mutate_and_buyer_cannot_control(setup):
    client, _ = setup
    assert client.get("/runs/one/snapshot", headers=headers("observer")).status_code == 200
    assert (
        client.post(
            "/runs/one/quotes",
            headers=headers("observer"),
            json={"supplier": "A", "items": {"tent": 1}},
        ).status_code
        == 403
    )
    for path, body in (
        ("offers/A/tent/price", {"price": 100}),
        ("faults/payment-response-delay", {"delay_ms": 100}),
    ):
        assert (
            client.post(
                f"/admin/runs/one/{path}", headers=headers("buyer-one"), json=body
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/admin/runs/one/{path}", headers=headers("control"), json=body
            ).status_code
            == 200
        )
    assert client.get("/runs/one/snapshot", headers=headers("control")).status_code == 403


def test_snapshot_hides_evaluation_metadata_and_clock_has_no_buyer_mutation_route(setup):
    client, _ = setup
    result = client.get("/runs/one/snapshot", headers=headers("buyer-one")).json()
    assert result["clock_mode"] == "operating-one-second-ticks"
    assert all(
        k not in json.dumps(result) for k in ("seed", "fixture", "wall_anchor", "payment_delay")
    )
    assert (
        client.post(
            "/runs/one/advance", headers=headers("buyer-one"), json={"tick": 60}
        ).status_code
        == 404
    )
    assert client.post("/runs/one/reset", headers=headers("buyer-one")).status_code == 404


def test_untrusted_payment_amount_and_boolean_quantities_are_rejected(setup):
    client, _ = setup
    order = purchase(client)
    assert (
        client.post(
            "/runs/one/payments",
            headers=headers("buyer-one"),
            json={"order_id": order["id"], "idempotency_key": "pay", "amount": 1},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/runs/one/quotes",
            headers=headers("buyer-one"),
            json={"supplier": "A", "items": {"tent": True}},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/runs/one/payments",
            headers=headers("buyer-one"),
            json={"order_id": order["id"], "idempotency_key": "pay"},
        ).json()["amount"]
        == 310
    )


def test_worker_failure_denies_new_mutations_and_reports_unhealthy(setup):
    client, app = setup
    app.state.worker.error = "InjectedFailure"
    assert client.get("/health").status_code == 503
    assert client.get("/runs/one/snapshot", headers=headers("buyer-one")).status_code == 200
    assert (
        client.post(
            "/runs/one/quotes",
            headers=headers("buyer-one"),
            json={"supplier": "A", "items": {"tent": 1}},
        ).status_code
        == 503
    )
