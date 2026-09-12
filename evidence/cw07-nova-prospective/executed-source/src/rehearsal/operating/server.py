"""Authenticated run-scoped HTTP boundary with a model-independent clock worker."""

import asyncio
import contextlib
import fcntl
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from rehearsal.world import OperatingClock, World
from rehearsal.world.storage import ContractError, Json


@dataclass(frozen=True)
class Grant:
    run_id: str
    role: str


@dataclass(frozen=True)
class ServerSettings:
    directory: Path
    grants: dict[str, Grant]
    runs: list[str]

    @classmethod
    def load(cls, path: Path) -> "ServerSettings":
        values = json.loads(path.read_text())
        grants = {token_hash: Grant(**grant) for token_hash, grant in values["grants"].items()}
        if any(
            g.role not in {"buyer", "observer", "control"} or g.run_id not in values["runs"]
            for g in grants.values()
        ):
            raise ValueError("Invalid server grants")
        return cls(Path(values["directory"]), grants, values["runs"])


class Controls:
    """Persistent clock anchors and one-shot response fault plans, never agent data."""

    def __init__(self, path: Path):
        self.path = path
        with contextlib.closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS clocks(run_id TEXT PRIMARY KEY, "
                "base_tick INTEGER NOT NULL, wall_anchor REAL NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS faults(run_id TEXT PRIMARY KEY, "
                "payment_delay_ms INTEGER NOT NULL)"
            )

    def resumed_tick(self, run_id: str, persisted_tick: int) -> int:
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO clocks VALUES(?,?,?)", (run_id, persisted_tick, time.time())
            )
            value = db.execute("SELECT * FROM clocks WHERE run_id=?", (run_id,)).fetchone()
        return max(persisted_tick, int(value[1]) + int(max(0, time.time() - float(value[2]))))

    def set_delay(self, run_id: str, delay: int) -> None:
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO faults VALUES(?,?) ON CONFLICT(run_id) "
                "DO UPDATE SET payment_delay_ms=excluded.payment_delay_ms",
                (run_id, delay),
            )

    def consume_delay(self, run_id: str) -> int:
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            value = db.execute(
                "SELECT payment_delay_ms FROM faults WHERE run_id=?", (run_id,)
            ).fetchone()
            db.execute("DELETE FROM faults WHERE run_id=?", (run_id,))
            return int(value[0]) if value else 0


class Worker:
    def __init__(self, world: World, settings: ServerSettings, controls: Controls):
        self.world, self.settings, self.controls = world, settings, controls
        self.clocks = {
            r: OperatingClock(controls.resumed_tick(r, world.shop.run(r)["tick"]))
            for r in settings.runs
        }
        self.error: str | None = None
        self.cycles = 0

    def step(self) -> None:
        for run_id, clock in self.clocks.items():
            # Advance first so newly received settlements are not backdated across restarts.
            self.world.shop.advance(run_id, clock.now())
            for event in self.world.payments.events(run_id):
                if event["event_type"] == "payment.reserved":
                    self.world.settle_payment(run_id, event["aggregate_id"])
            self.world.synchronize(run_id)
        self.cycles += 1

    async def serve(self) -> None:
        try:
            while True:
                step = asyncio.create_task(asyncio.to_thread(self.step))
                try:
                    await asyncio.shield(step)
                except asyncio.CancelledError:
                    await step  # Keep the process lock until the SQLite work has stopped.
                    raise
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = type(exc).__name__


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuoteBody(StrictBody):
    supplier: str = Field(min_length=1, max_length=100)
    items: dict[str, StrictInt]


class OrderBody(StrictBody):
    quote_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=200)


class PaymentBody(StrictBody):
    order_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=200)


class PriceBody(StrictBody):
    price: StrictInt = Field(gt=0)


class DelayBody(StrictBody):
    delay_ms: StrictInt = Field(ge=1, le=2000)


def create_app(settings: ServerSettings | None = None, start_worker: bool = True) -> FastAPI:
    if settings is None:
        filename = os.environ.get("REHEARSAL_OPERATING_CONFIG")
        if not filename:
            raise RuntimeError(
                "Missing REHEARSAL_OPERATING_CONFIG; use the scoped operating runner"
            )
        settings = ServerSettings.load(Path(filename))
    world = World(settings.directory)
    controls = Controls(settings.directory / "controls.sqlite3")
    worker = Worker(world, settings, controls)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        lock = (settings.directory / "worker.lock").open("a")
        try:
            if start_worker:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                task = asyncio.create_task(worker.serve())
            yield
        finally:
            if start_worker and "task" in locals():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            lock.close()

    app = FastAPI(title="Rehearsal operating sandbox", lifespan=lifespan)
    app.state.world, app.state.worker = world, worker

    def authorize(run_id: str, authorization: Annotated[str | None, Header()] = None) -> Grant:
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(401, "AUTHENTICATION_REQUIRED")
        token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
        grant = settings.grants.get(token_hash)
        if grant is None:
            raise HTTPException(401, "INVALID_CREDENTIAL")
        if grant.run_id != run_id:
            raise HTTPException(403, "RUN_SCOPE_DENIED")
        return grant

    def buyer(grant: Annotated[Grant, Depends(authorize)]) -> Grant:
        if grant.role != "buyer":
            raise HTTPException(403, "BUYER_ROLE_REQUIRED")
        if worker.error:
            raise HTTPException(503, "WORKER_UNAVAILABLE")
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

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse(
            status_code=503 if worker.error else 200,
            content={
                "status": "failed" if worker.error else "ok",
                "scope": "local-operating-sandbox",
                "worker_cycles": worker.cycles,
            },
        )

    @app.get("/runs/{run_id}/snapshot")
    def snapshot(run_id: str, grant: Annotated[Grant, Depends(reader)]) -> Json:
        snapshot = world.snapshot(run_id)
        balance = snapshot["balance"]
        return {
            "run_id": run_id,
            "goal": snapshot["goal"],
            "tick": snapshot["tick"],
            "clock_mode": "operating-one-second-ticks",
            "balance": {k: balance[k] for k in ("budget", "spent", "reserved", "available")},
            "inventory": snapshot["inventory"],
            "suppliers": sorted({o["supplier"] for o in world.shop.offers(run_id)}),
        }

    @app.post("/runs/{run_id}/quotes")
    def quote(run_id: str, body: QuoteBody, grant: Annotated[Grant, Depends(buyer)]) -> Json:
        return world.shop.quote(run_id, body.supplier, body.items)

    @app.post("/runs/{run_id}/orders")
    def create_order(run_id: str, body: OrderBody, grant: Annotated[Grant, Depends(buyer)]) -> Json:
        return world.shop.create_order(run_id, body.quote_id, body.idempotency_key)

    @app.get("/runs/{run_id}/orders/{order_id}")
    def get_order(run_id: str, order_id: str, grant: Annotated[Grant, Depends(reader)]) -> Json:
        return world.shop.order(run_id, order_id)

    @app.post("/runs/{run_id}/payments")
    async def payment(
        run_id: str, body: PaymentBody, grant: Annotated[Grant, Depends(buyer)]
    ) -> Json:
        result = await asyncio.to_thread(
            world.authorize_payment, run_id, body.order_id, body.idempotency_key
        )
        delay = controls.consume_delay(run_id)
        if delay:
            await asyncio.sleep(delay / 1000)
        return result

    @app.get("/runs/{run_id}/payments/{order_id}")
    def get_payment(run_id: str, order_id: str, grant: Annotated[Grant, Depends(reader)]) -> Json:
        world.shop.order(run_id, order_id)
        return world.payments.for_order(run_id, order_id)

    @app.post("/admin/runs/{run_id}/offers/{supplier}/{item}/price")
    def price(
        run_id: str,
        supplier: str,
        item: str,
        body: PriceBody,
        grant: Annotated[Grant, Depends(control)],
    ) -> Json:
        world.shop.change_price(run_id, supplier, item, body.price)
        return {"changed": True}

    @app.post("/admin/runs/{run_id}/faults/payment-response-delay")
    def response_delay(
        run_id: str, body: DelayBody, grant: Annotated[Grant, Depends(control)]
    ) -> Json:
        controls.set_delay(run_id, body.delay_ms)
        return {"armed": True}

    return app
