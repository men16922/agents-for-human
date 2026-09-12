"""Run-authenticated purchasing HTTP surface over Medusa, without admin credentials."""

import asyncio
import contextlib
import fcntl
import hashlib
import json
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field, StrictInt

from rehearsal.operating.server import (
    Controls,
    DelayBody,
    Grant,
    OrderBody,
    PaymentBody,
    QuoteBody,
    StrictBody,
)
from rehearsal.world.storage import ContractError, Json

from .gateway import Binding, MedusaGateway, StoreAPI
from .observations import ObservationJournal
from .observer import Observer, sse_frames
from .response_faults import ResponseFaults


class NotificationBody(StrictBody):
    delay_ms: StrictInt = Field(default=0, ge=0, le=5000)
    copies: StrictInt = Field(default=1, ge=1, le=3)


class ScheduledNotificationBody(NotificationBody):
    event_id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    kind: Literal["delivery_notification", "notification_replay"]
    source_event: str | None = Field(
        default=None, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$"
    )


class ScheduledResponseBody(StrictBody):
    event_id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    delay_ms: StrictInt = Field(ge=1, le=5000)


class ReplayBody(NotificationBody):
    event_id: str = Field(min_length=1, max_length=100)


def seller_health(directory: Path) -> Json:
    try:
        value: Json = json.loads((directory / "seller-status.json").read_text())
        healthy = (
            value["state"] == "running"
            and not value["errors"]
            and 0 <= time.time() - value["updated_at"] < 5
            and value["worker_cycles"] > 0
        )
        return {
            "status": "ok" if healthy else "unavailable",
            "worker_cycles": value["worker_cycles"],
            "scope": "medusa-purchasing-http-and-separate-seller",
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {
            "status": "unavailable",
            "worker_cycles": 0,
            "scope": "medusa-purchasing-http-and-separate-seller",
        }


def create_app(
    config: Json | None = None,
    gateways: dict[str, MedusaGateway] | None = None,
    *,
    start_observer: bool = True,
) -> FastAPI:
    if config is None:
        filename = os.environ.get("REHEARSAL_MEDUSA_CONFIG")
        if not filename:
            raise RuntimeError("Missing REHEARSAL_MEDUSA_CONFIG")
        config = json.loads(Path(filename).read_text())
    directory = Path(config["directory"])
    grants = {digest: Grant(**g) for digest, g in config["grants"].items()}
    if any(
        g.run_id not in config["runs"] or g.role not in {"buyer", "observer", "control"}
        for g in grants.values()
    ):
        raise ValueError("Invalid Medusa grants")
    if gateways is None:
        gateways = {}
        for run_id, run in config["runs"].items():
            if run_id != run["binding"]["run_id"]:
                raise ValueError("Run binding mismatch")
            api = StoreAPI(run["store_token"], run["publishable_key"])
            gateways[run_id] = MedusaGateway(Path(run["directory"]), Binding(**run["binding"]), api)
    backends = gateways
    if set(backends) != set(config["runs"]):
        raise ValueError("Missing run backend")
    controls = Controls(directory / "controls.sqlite3")
    response_faults = ResponseFaults(directory / "response-faults.sqlite3")
    journal = ObservationJournal(
        directory / "observations.sqlite3",
        list(backends),
        retention=config.get("observation_retention", 1000),
    )
    observer = Observer(journal, backends)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with contextlib.ExitStack() as cleanup:
            lock = cleanup.enter_context((directory / "observer.lock").open("a+"))
            for backend in backends.values():
                cleanup.callback(backend.store.close)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            task = asyncio.create_task(observer.serve()) if start_observer else None
            try:
                yield
            finally:
                if task is not None:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    app = FastAPI(title="Rehearsal Medusa purchasing gateway", lifespan=lifespan)
    app.state.observer = observer

    def authorize(run_id: str, authorization: Annotated[str | None, Header()] = None) -> Grant:
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(401, "AUTHENTICATION_REQUIRED")
        grant = grants.get(hashlib.sha256(authorization[7:].encode()).hexdigest())
        if grant is None:
            raise HTTPException(401, "INVALID_CREDENTIAL")
        if grant.run_id != run_id:
            raise HTTPException(403, "RUN_SCOPE_DENIED")
        return grant

    def buyer(grant: Annotated[Grant, Depends(authorize)]) -> Grant:
        if grant.role != "buyer":
            raise HTTPException(403, "BUYER_ROLE_REQUIRED")
        if seller_health(directory)["status"] != "ok":
            raise HTTPException(503, "SELLER_UNAVAILABLE")
        return grant

    def reader(grant: Annotated[Grant, Depends(authorize)]) -> Grant:
        if grant.role not in {"buyer", "observer"}:
            raise HTTPException(403, "READER_ROLE_REQUIRED")
        return grant

    def control(grant: Annotated[Grant, Depends(authorize)]) -> Grant:
        if grant.role != "control":
            raise HTTPException(403, "CONTROL_ROLE_REQUIRED")
        return grant

    @app.exception_handler(ContractError)
    async def contract_error(request: Request, exc: ContractError) -> JSONResponse:
        return JSONResponse(
            status_code=404 if exc.code == "NOT_FOUND" else 409, content={"error": exc.code}
        )

    @app.exception_handler(httpx.TransportError)
    async def transport_error(request: Request, exc: httpx.TransportError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"error": "MEDUSA_UNAVAILABLE"})

    @app.get("/health")
    def health() -> JSONResponse:
        value = seller_health(directory)
        return JSONResponse(status_code=200 if value["status"] == "ok" else 503, content=value)

    @app.get("/runs/{run_id}/snapshot")
    def snapshot(
        run_id: str,
        grant: Annotated[Grant, Depends(reader)],
        details: bool = False,
    ) -> Json:
        return backends[run_id].observe_world(include_details=details or grant.role == "observer")

    @app.get("/runs/{run_id}/observations")
    def observations(
        run_id: str,
        grant: Annotated[Grant, Depends(reader)],
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> Json:
        return observer.read(run_id, after, limit)

    @app.get("/runs/{run_id}/events")
    async def events(
        run_id: str,
        request: Request,
        grant: Annotated[Grant, Depends(reader)],
        after: Annotated[int, Query(ge=0)] = 0,
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        if last_event_id is not None:
            if (
                not last_event_id.isascii()
                or not last_event_id.isdecimal()
                or len(last_event_id) > 19
            ):
                raise HTTPException(422, "INVALID_EVENT_CURSOR")
            after = int(last_event_id)
        # Validate cursor before sending HTTP 200; subsequent reads handle retention resets.
        initial = await asyncio.to_thread(observer.read, run_id, after)

        async def stream() -> AsyncIterator[str]:
            batch = initial
            while not await request.is_disconnected():
                for frame in sse_frames(batch):
                    yield frame
                await asyncio.sleep(0.5)
                batch = await asyncio.to_thread(observer.read, run_id, batch["next_cursor"])

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/runs/{run_id}/quotes")
    def quote(run_id: str, body: QuoteBody, grant: Annotated[Grant, Depends(buyer)]) -> Json:
        return backends[run_id].get_quotes(body.supplier, body.items)

    @app.post("/runs/{run_id}/orders")
    def order(run_id: str, body: OrderBody, grant: Annotated[Grant, Depends(buyer)]) -> Json:
        return backends[run_id].create_order(body.quote_id, body.idempotency_key)

    @app.get("/runs/{run_id}/orders/{order_id}")
    def get_order(run_id: str, order_id: str, grant: Annotated[Grant, Depends(reader)]) -> Json:
        return backends[run_id].get_order(order_id)

    @app.post("/runs/{run_id}/payments")
    async def payment(
        run_id: str, body: PaymentBody, grant: Annotated[Grant, Depends(buyer)]
    ) -> Json:
        value = await asyncio.to_thread(
            backends[run_id].authorize_payment, body.order_id, body.idempotency_key
        )
        scheduled = response_faults.consume(
            run_id, body.order_id, value["status"], time.time(), backends[run_id].tick()
        )
        delay = scheduled["delay_ms"] if scheduled else controls.consume_delay(run_id)
        try:
            if delay:
                await asyncio.sleep(delay / 1000)
        except BaseException:
            if scheduled:
                response_faults.finish(
                    run_id,
                    scheduled["event_id"],
                    time.time(),
                    backends[run_id].tick(),
                    interrupted=True,
                )
            raise
        if scheduled:
            response_faults.finish(
                run_id, scheduled["event_id"], time.time(), backends[run_id].tick()
            )
        return value

    @app.get("/runs/{run_id}/payments/{order_id}")
    def get_payment(run_id: str, order_id: str, grant: Annotated[Grant, Depends(reader)]) -> Json:
        return backends[run_id].get_payment(order_id)

    @app.post("/admin/runs/{run_id}/faults/scheduled-payment-response")
    def scheduled_response(
        run_id: str, body: ScheduledResponseBody, grant: Annotated[Grant, Depends(control)]
    ) -> Json:
        return response_faults.arm(
            run_id, body.event_id, body.delay_ms, backends[run_id].tick(), time.time()
        )

    @app.post("/admin/runs/{run_id}/faults/payment-response-delay")
    def delay(run_id: str, body: DelayBody, grant: Annotated[Grant, Depends(control)]) -> Json:
        controls.set_delay(run_id, body.delay_ms)
        return {"armed": True}

    @app.post("/admin/runs/{run_id}/faults/scheduled-notification")
    def scheduled_notification(
        run_id: str, body: ScheduledNotificationBody, grant: Annotated[Grant, Depends(control)]
    ) -> Json:
        return journal.arm_scheduled(
            run_id,
            body.event_id,
            body.kind,
            body.delay_ms,
            body.copies,
            body.source_event,
            backends[run_id].tick(),
            time.time(),
        )

    @app.post("/admin/runs/{run_id}/faults/delivery-notification")
    def notification_fault(
        run_id: str,
        body: NotificationBody,
        grant: Annotated[Grant, Depends(control)],
    ) -> Json:
        journal.arm_delivery(run_id, body.delay_ms, body.copies)
        return {"armed": True}

    @app.post("/admin/runs/{run_id}/faults/replay-notification")
    def replay_notification(
        run_id: str,
        body: ReplayBody,
        grant: Annotated[Grant, Depends(control)],
    ) -> Json:
        journal.replay(run_id, body.event_id, time.time(), body.delay_ms, body.copies)
        return {"queued": True}

    return app
