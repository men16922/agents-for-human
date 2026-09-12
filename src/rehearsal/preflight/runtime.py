"""AgentCore preflight runtime with a separate role and no transaction permissions."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from strands.models import BedrockModel

from rehearsal.agents.metering import RateCard
from rehearsal.serverless.control import Control
from rehearsal.serverless.domain import Json, Rejected, canonical
from rehearsal.serverless.metering import DurableLedger

from .cloud import get_json
from .planner import plan_and_measure


def run(run_id: str) -> Json:
    if not run_id.startswith("preview-"):
        raise Rejected("INVALID_PREFLIGHT_RUN")
    session = boto3.Session(region_name=os.environ["AWS_REGION"])
    config = Config(retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=120)
    control = Control(session.client("dynamodb", config=config), os.environ["CONTROL_TABLE"])
    meta = control.claim(run_id)
    if meta["method"] != "PREFLIGHT":
        raise Rejected("INVALID_PREFLIGHT_RUN")
    s3 = session.client("s3", config=config)
    bucket = os.environ["ARTIFACTS_BUCKET"]
    with tempfile.TemporaryDirectory(prefix="preflight-") as folder:
        ledger = DurableLedger(
            Path(folder) / "usage.sqlite3",
            run_id,
            os.environ["MODEL_ID"],
            RateCard("0.30", "2.50", "0.075", "0", os.environ["RATE_SOURCE"]),
            500_000,
            24000,
            1024,
            "live-model",
            max_calls=18,
            max_total_tokens=300000,
            max_tool_calls=24,
        )
        ledger.bind(control, s3, bucket, run_id)
        control.publish(run_id, "runtime", {"phase": "PLANNING_AND_SIMULATING"})
        model = BedrockModel(
            model_id=os.environ["MODEL_ID"],
            boto_session=session,
            boto_client_config=config,
            max_tokens=1024,
            use_native_token_count=False,
        )
        result = asyncio.run(
            plan_and_measure(model, ledger, run_id, get_json(session, run_id, "input.json"))
        )
        s3.put_object(
            Bucket=bucket,
            Key=f"runs/{run_id}/runtime/preflight.json",
            Body=canonical(result).encode(),
            ContentType="application/json",
        )
        control.publish(
            run_id,
            "runtime",
            {
                "phase": "FINISHED",
                "runtime_status": result["runtime_status"],
                "usage": ledger.report(),
                "proposed_supplier": result["proposed_supplier"],
            },
        )
    return {"run_id": run_id, "status": result["runtime_status"]}
