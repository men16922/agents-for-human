"""Local health and optional read-only observer view. No transaction commands."""

import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from rehearsal.evidence_view import evidence_routes
from rehearsal.execution_view import execution_routes
from rehearsal.observer_view import ObserverSettings, observer_routes


class Health(BaseModel):
    status: str = "ok"
    phase: str = "development-foundation"
    model_calls_enabled: bool = False


def create_app() -> FastAPI:
    app = FastAPI(title="Rehearsal observation view", version="0.1.0")
    config_path = os.environ.get("REHEARSAL_OBSERVER_CONFIG")
    settings = ObserverSettings.load(Path(config_path)) if config_path else None
    app.include_router(observer_routes(settings))
    evidence_path = os.environ.get("REHEARSAL_EVIDENCE_CONFIG")
    app.include_router(
        evidence_routes(
            Path(evidence_path).resolve() if evidence_path else None,
            settings.run_id if settings else None,
        )
    )
    execution_path = os.environ.get("REHEARSAL_EXECUTION_CONFIG")
    app.include_router(
        execution_routes(
            Path(execution_path).resolve() if execution_path else None,
            settings.run_id if settings else None,
        )
    )

    @app.get("/health", response_model=Health)
    def health() -> Health:
        return Health()

    return app


app = create_app()
