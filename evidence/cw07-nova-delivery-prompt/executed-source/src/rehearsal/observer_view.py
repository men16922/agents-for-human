"""Fixed loopback, read-only observer bridge; browser clients never receive tokens."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from rehearsal.world.storage import Json

ORIGIN = "http://127.0.0.1:18001"


@dataclass(frozen=True)
class ObserverSettings:
    run_id: str
    observer_token: str

    @classmethod
    def load(cls, path: Path) -> ObserverSettings:
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or set(value) != {"run_id", "observer_token"}:
            raise ValueError("Observer config requires only run_id and observer_token")
        return cls(**value)

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}", self.run_id
        ):
            raise ValueError("Invalid observer run ID")
        if not isinstance(self.observer_token, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{16,256}", self.observer_token
        ):
            raise ValueError("Invalid observer token")


def observer_routes(
    settings: ObserverSettings | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/observer")

    def configured() -> ObserverSettings:
        if settings is None:
            raise HTTPException(503, "OBSERVER_NOT_CONFIGURED")
        return settings

    def client() -> httpx.AsyncClient:
        config = configured()
        return httpx.AsyncClient(
            base_url=ORIGIN,
            timeout=10,
            trust_env=False,
            follow_redirects=False,
            headers={"Authorization": "Bearer " + config.observer_token},
            transport=transport,
        )

    @router.get("/config")
    def config() -> Json:
        return {
            "configured": settings is not None,
            "run_id": settings.run_id if settings else None,
            "mode": "live-observer",
            "read_only": True,
        }

    @router.get("/observations")
    async def observations(
        after: Annotated[int, Query(ge=0, le=2**53 - 1)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> Json:
        config = configured()
        try:
            async with client() as upstream:
                response = await upstream.get(
                    f"/runs/{config.run_id}/observations", params={"after": after, "limit": limit}
                )
                if response.status_code != 200:
                    raise HTTPException(502, "OBSERVER_UNAVAILABLE")
                value: Json = response.json()
                if not isinstance(value, dict) or value.get("run_id") != config.run_id:
                    raise HTTPException(502, "OBSERVER_SCOPE_MISMATCH")
                return value
        except (httpx.TransportError, ValueError) as exc:
            raise HTTPException(502, "OBSERVER_UNAVAILABLE") from exc

    @router.get("/events")
    async def events(
        request: Request,
        after: Annotated[int, Query(ge=0, le=2**53 - 1)] = 0,
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        config = configured()
        if last_event_id is not None:
            if not re.fullmatch(r"[0-9]{1,19}", last_event_id) or int(last_event_id) > 2**53 - 1:
                raise HTTPException(422, "INVALID_EVENT_CURSOR")
            after = int(last_event_id)
        upstream = client()
        try:
            response = await upstream.send(
                upstream.build_request(
                    "GET", f"/runs/{config.run_id}/events", headers={"Last-Event-ID": str(after)}
                ),
                stream=True,
            )
            if response.status_code != 200 or not response.headers.get(
                "content-type", ""
            ).startswith("text/event-stream"):
                await response.aclose()
                raise HTTPException(502, "OBSERVER_UNAVAILABLE")
        except Exception as exc:
            await upstream.aclose()
            if isinstance(exc, httpx.TransportError):
                raise HTTPException(502, "OBSERVER_UNAVAILABLE") from exc
            raise

        async def stream() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    if await request.is_disconnected():
                        break
                    yield chunk
            except httpx.TransportError:
                yield b'event: bridge_error\ndata: {"error":"OBSERVER_UNAVAILABLE"}\n\n'
            finally:
                await response.aclose()
                await upstream.aclose()

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
                "Cross-Origin-Resource-Policy": "same-origin",
            },
        )

    return router
