"""Verify the development shell cannot be mistaken for a transaction implementation."""

import asyncio

import httpx

from rehearsal.api import app


def test_health_and_no_transaction_routes() -> None:
    async def probe() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {
                "status": "ok",
                "phase": "development-foundation",
                "model_calls_enabled": False,
            }
            for route in ("/orders", "/payments", "/world", "/agents"):
                assert (await client.post(route, json={})).status_code == 404

    asyncio.run(probe())
