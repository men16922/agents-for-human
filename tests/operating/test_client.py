from unittest.mock import patch

import httpx
import pytest

from rehearsal.operating.client import OperatingClient
from rehearsal.operating.tools import purchasing_http_tools
from rehearsal.world.storage import ContractError


def test_http_response_loss_never_triggers_an_automatic_replacement_payment():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            raise httpx.ReadTimeout("Response lost after server commit", request=request)
        return httpx.Response(200, json={"id": "pay-1", "status": "SETTLED"})

    client = OperatingClient("http://127.0.0.1:18001", "one", "token")
    client.http.close()
    client.http = httpx.Client(
        base_url="http://127.0.0.1:18001", transport=httpx.MockTransport(handler)
    )
    try:
        observation = client.authorize_payment("order-1", "stable-intent")
        assert observation.status == "UNKNOWN" and observation.payment is None
        assert calls == [("POST", "/runs/one/payments")]
        assert client.get_payment("order-1").status == "SETTLED"
        assert calls == [("POST", "/runs/one/payments"), ("GET", "/runs/one/payments/order-1")]
    finally:
        client.close()


def test_registered_http_wait_only_waits_and_reads_never_drives_server_state():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"tick": 4, "inventory": {"tent": 1}})

    client = OperatingClient("http://127.0.0.1:18001", "one", "token")
    client.http.close()
    client.http = httpx.Client(
        base_url="http://127.0.0.1:18001", transport=httpx.MockTransport(handler)
    )
    try:
        tools = {t.tool_name: t for t in purchasing_http_tools(client)}
        with patch("rehearsal.operating.tools.time.sleep") as sleep:
            assert tools["wait_for_updates"](ticks=3) == {"tick": 4, "received": {"tent": 1}}
            sleep.assert_called_once_with(3)
        assert calls == [("GET", "/runs/one/snapshot")]
        with pytest.raises(ContractError, match="WAIT_TOO_LONG"):
            tools["wait_for_updates"](ticks=11)
        assert len(calls) == 1
    finally:
        client.close()


@pytest.mark.parametrize(
    "origin,run",
    [
        ("https://example.com", "one"),
        ("http://127.0.0.1:18001", "../admin"),
        ("http://user:secret@127.0.0.1:18001", "one"),
    ],
)
def test_adapter_refuses_external_origins_and_path_injection(origin, run):
    with pytest.raises(ValueError):
        OperatingClient(origin, run, "token")
