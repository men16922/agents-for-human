"""AgentCore HTTP entrypoint. IAM infrastructure fixes the experiment and budget."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from fastapi import FastAPI, HTTPException
from strands.hooks import AfterToolCallEvent
from strands.models import BedrockModel

from rehearsal.agents.executor import Limits, agent_for_tools
from rehearsal.agents.metering import MeterHooks, RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.experiments.b2 import run_b2
from rehearsal.experiments.b3 import run_b3
from rehearsal.experiments.baseline import ToolPort, run_baseline
from rehearsal.experiments.frozen import freeze
from rehearsal.experiments.policy import Policy

from .control import Control
from .domain import Json, canonical, identifier
from .metering import DurableLedger
from .scenarios import scenario_for
from .tools import purchasing_tools

app = FastAPI()
busy = threading.Lock()


def run(run_id: str) -> Json:
    if os.environ.get("RUNTIME_MODE") == "preflight":
        from rehearsal.preflight.runtime import run as preview

        return preview(run_id)
    session = boto3.Session(region_name=os.environ["AWS_REGION"])
    config = Config(retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=120)
    control = Control(session.client("dynamodb", config=config), os.environ["CONTROL_TABLE"])
    # A durable claim rejects a second invocation, including a duplicate runtime session.
    meta = control.claim(run_id)
    method = meta["method"]
    s3 = session.client("s3", config=config)
    client = session.client("lambda", config=config)
    settings = ModelSettings(
        "agentcore-execution-role",
        os.environ["AWS_REGION"],
        os.environ["MODEL_ID"],
        RateCard("0.30", "2.50", "0.075", "0", os.environ["RATE_SOURCE"]),
        500_000,
        input_limit=24000,
        output_limit=1024,
        max_model_calls=60,
        max_tool_calls=120,
        max_total_tokens=500000,
        timeout_seconds=120,
    )

    def model() -> BedrockModel:
        return BedrockModel(
            model_id=settings.model_id,
            boto_session=session,
            boto_client_config=config,
            max_tokens=settings.output_limit,
            use_native_token_count=False,
        )

    report: Json = {
        "scope": "AWS-AgentCore-DynamoDB",
        "method": method,
        "run_id": run_id,
        "phase": "STARTING",
        "runtime_status": "STARTED",
        "learning_status": "NONE",
        "model_efficacy_verified": False,
    }
    with tempfile.TemporaryDirectory(prefix="rehearsal-") as temp:
        folder = Path(temp)
        ledger = DurableLedger(
            folder / "usage.sqlite3",
            run_id,
            settings.model_id,
            settings.rates,
            settings.budget_micro_usd,
            settings.input_limit,
            settings.output_limit,
            "live-model",
            max_calls=settings.max_model_calls,
            max_total_tokens=settings.max_total_tokens,
            max_tool_calls=settings.max_tool_calls,
        )
        trace: list[Json] = []
        try:
            ledger.bind(control, s3, os.environ["ARTIFACTS_BUCKET"], run_id)
            policy = Policy()
            if method in {"B2", "B3"}:
                report["phase"] = "LEARNING"
                control.publish(run_id, "runtime", report)
                training = scenario_for("price-change")
                # Existing isolated practice worlds use a virtual clock, not the cloud seller clock.
                training["scenario_version"] = "serverless-known-practice"
                training["events"][0]["at_tick"] = 2
                if method == "B2":
                    learned = run_b2(
                        model(),
                        settings,
                        folder / "learning",
                        training,
                        "live-model",
                        shared_ledger=ledger,
                    )
                    selection = learned
                else:
                    learned = run_b3(
                        lambda _: model(),
                        lambda _: model(),
                        settings,
                        folder / "learning",
                        training,
                        "live-model",
                        shared_ledger=ledger,
                    )
                    source = folder / "learning/review/report.json"
                    selection = json.loads(source.read_text()) if source.exists() else {}
                report["learning_status"] = learned["status"]
                if learned["status"] not in {"CANDIDATE_EVALUATED_NOT_PROMOTED", "NO_CHANGE"}:
                    raise ValueError("LEARNING_REJECTED")
                if not learned["parent_unchanged"] or not ledger.report()["all_usage_recorded"]:
                    raise ValueError("LEARNING_EVIDENCE_UNRESOLVED")
                policy = Policy.parse(
                    selection.get("candidate_policy") or selection["initial_policy"]
                )
                report["learning"] = {
                    "status": learned["status"],
                    "selected_policy": asdict(policy),
                    "proves_improvement": False,
                }
            root = Path(__file__).resolve().parents[3]
            frozen = freeze(policy, folder / "policy.json", root)
            report.update(phase="BUYING", policy=asdict(policy), frozen_id=frozen.identifier)
            control.publish(run_id, "runtime", report)
            tools = purchasing_tools(client, os.environ["COMMERCE_FUNCTION"], run_id)
            port = ToolPort(tools, settings.max_tool_calls, 120)
            # Seller workflow alone activates the external experiment after learning.
            ready_by = time.monotonic() + 30
            while port.call("observe_world")["tick"] == 0:
                if time.monotonic() > ready_by:
                    raise TimeoutError("Seller activation not observed")
                time.sleep(1)
            if method == "B0":
                result = run_baseline(frozen, port, "cloud-baseline")
                trace = port.trace
                report.update(runtime_status=result["status"], stop_reason=result["reason"])
            else:
                meter = MeterHooks(ledger, role="buyer_evaluation", execution_id="cloud-evaluation")
                limits = Limits(settings.max_model_calls, settings.max_tool_calls)
                agent = agent_for_tools(model(), tools, limits, meter, policy=policy)

                def after_tool(event: AfterToolCallEvent) -> None:
                    trace.append(
                        {
                            "tool": event.tool_use,
                            "result": event.result,
                            "error": type(event.exception).__name__ if event.exception else None,
                        }
                    )
                    s3.put_object(
                        Bucket=os.environ["ARTIFACTS_BUCKET"],
                        Key=f"runs/{run_id}/tools.json",
                        Body=canonical(trace).encode(),
                    )

                agent.add_hook(after_tool)

                async def invoke() -> Any:
                    return await asyncio.wait_for(
                        agent.invoke_async(
                            "Deliver the fixed goal using your purchasing tools. The independent "
                            "seller runs on wall time. Report only confirmed delivery and spending."
                        ),
                        timeout=120,
                    )

                model_result = asyncio.run(invoke())
                report.update(
                    runtime_status="COMPLETED"
                    if model_result.stop_reason == "end_turn"
                    else "INCOMPLETE",
                    final_response=str(model_result),
                    stop_reason=meter.stop_reason,
                )
        except Exception as exc:
            report.update(runtime_status="ERROR", error=type(exc).__name__, reason=str(exc)[:150])
        finally:
            report.update(phase="FINISHED", usage=ledger.report(), tool_calls=len(trace))
            (folder / "report.json").write_text(canonical(report))
            (folder / "tools.json").write_text(canonical(trace))
            for file in folder.rglob("*"):
                if file.is_file():
                    s3.put_object(
                        Bucket=os.environ["ARTIFACTS_BUCKET"],
                        Key=f"runs/{run_id}/runtime/{file.relative_to(folder).as_posix()}",
                        Body=file.read_bytes(),
                    )
            control.publish(run_id, "runtime", report)
    return {"run_id": run_id, "status": report["runtime_status"]}


@app.get("/ping")
def ping() -> Json:
    return {"status": "HealthyBusy" if busy.locked() else "Healthy"}


@app.post("/invocations")
def invocations(payload: Json) -> Json:
    if set(payload) != {"run_id"}:
        raise HTTPException(status_code=400, detail="Expected a server-selected run ID")
    run_id = identifier(payload["run_id"])
    if not busy.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Runtime already executing")
    try:
        return run(run_id)
    finally:
        busy.release()
