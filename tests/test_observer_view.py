"""Exercise the actual bridge routes against controlled upstream HTTP responses."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rehearsal.observer_view import ObserverSettings, observer_routes

TOKEN = "observer-only-credential-1234"
SETTINGS = ObserverSettings("view-run", TOKEN)


def client(handler, settings=SETTINGS):
    app = FastAPI()
    app.include_router(observer_routes(settings, httpx.MockTransport(handler)))
    return TestClient(app)


def test_unconfigured_and_read_only():
    def forbidden(request):
        pytest.fail("Unconfigured view must not access upstream")

    with client(forbidden, None) as api:
        assert api.get("/observer/config").json()["configured"] is False
        assert api.get("/observer/observations").status_code == 503
        assert api.get("/observer/events").status_code == 503
        assert api.post("/observer/events").status_code == 405
        assert api.post("/observer/tools/pay").status_code == 404
        assert api.get("/observer/runs/another/events").status_code == 404


def test_fixed_origin_scope_no_browser_token_or_forwarded_credentials():
    seen = []

    def upstream(request):
        seen.append(request)
        assert (
            str(request.url) == "http://127.0.0.1:18001/runs/view-run/observations?after=4&limit=2"
        )
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert "cookie" not in request.headers
        return httpx.Response(200, json={"run_id": "view-run", "events": []})

    with client(upstream) as api:
        assert TOKEN not in api.get("/observer/config").text
        result = api.get(
            "/observer/observations?after=4&limit=2&url=http://example.invalid&run_id=other",
            headers={"Authorization": "Bearer buyer-token", "Cookie": "secret=value"},
        )
        assert result.status_code == 200
        assert TOKEN not in result.text
        assert len(seen) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"Location": "http://example.invalid"}),
        httpx.Response(403, text=TOKEN),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"run_id": "other"}),
        httpx.Response(200, text="not json"),
    ],
)
def test_bad_upstream_is_generic_no_redirect_or_secret(response):
    requests = []

    def upstream(request):
        requests.append(request)
        return response

    with client(upstream) as api:
        result = api.get("/observer/observations")
        assert result.status_code == 502
        assert TOKEN not in result.text
        assert len(requests) == 1


@pytest.mark.parametrize("cursor", ["-1", "1.5", "9" * 20, "9007199254740992", "abc"])
def test_invalid_cursor_never_reaches_upstream(cursor):
    def upstream(request):
        pytest.fail("Invalid cursor reached upstream")

    with client(upstream) as api:
        assert api.get("/observer/events", headers={"Last-Event-ID": cursor}).status_code == 422
        assert api.get("/observer/observations", params={"after": cursor}).status_code == 422


def test_sse_forwards_chunks_cursor_and_closes_stream():
    class Chunks(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"id: 7\nevent: observation\n"
            yield b'data: {"run_id":"view-run"}\n\n'

        async def aclose(self):
            self.closed = True

    chunks = Chunks()

    def upstream(request):
        assert str(request.url) == "http://127.0.0.1:18001/runs/view-run/events"
        assert request.headers["Last-Event-ID"] == "6"
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, stream=chunks)

    with client(upstream) as api:
        response = api.get("/observer/events?after=2", headers={"Last-Event-ID": "6"})
        assert response.status_code == 200
        assert response.text == 'id: 7\nevent: observation\ndata: {"run_id":"view-run"}\n\n'
        assert response.headers["cache-control"] == "no-store"
        assert TOKEN not in response.text
    assert chunks.closed


def test_sse_transport_failure_closes_and_emits_generic_error():
    class Broken(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b": connected\n\n"
            raise httpx.ReadError(TOKEN)

        async def aclose(self):
            self.closed = True

    stream = Broken()
    with client(
        lambda _: httpx.Response(200, headers={"Content-Type": "text/event-stream"}, stream=stream)
    ) as api:
        response = api.get("/observer/events")
        assert "bridge_error" in response.text and TOKEN not in response.text
    assert stream.closed


@pytest.mark.parametrize(
    "status,mime",
    [(200, "application/json"), (302, "text/event-stream"), (403, "text/event-stream")],
)
def test_sse_rejects_status_and_content_type(status, mime):
    with client(
        lambda _: httpx.Response(status, headers={"Content-Type": mime}, text=TOKEN)
    ) as api:
        response = api.get("/observer/events")
        assert response.status_code == 502 and TOKEN not in response.text


def test_settings_allow_only_bound_run_and_observer_token(tmp_path: Path):
    path = tmp_path / "observer.json"
    path.write_text(json.dumps({"run_id": "view-run", "observer_token": TOKEN}))
    assert ObserverSettings.load(path) == SETTINGS
    for extra in ({"origin": "https://example.invalid"}, {"buyer_token": TOKEN}):
        path.write_text(json.dumps({"run_id": "view-run", "observer_token": TOKEN, **extra}))
        with pytest.raises(ValueError):
            ObserverSettings.load(path)
    with pytest.raises(ValueError):
        ObserverSettings("../other", TOKEN)
    with pytest.raises(ValueError):
        ObserverSettings("view-run", "secret\nheader")
