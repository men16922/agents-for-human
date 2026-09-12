"""Metered purchasing on an isolated fork with a declared, known price-change fixture."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from strands.hooks import AfterToolCallEvent
from strands.models.model import Model

from rehearsal.agents.executor import Limits, agent_for_tools, purchasing_tools
from rehearsal.agents.metering import MeterHooks, UsageLedger
from rehearsal.agents.runner import ModelSettings
from rehearsal.evaluation.verifier import verify
from rehearsal.world import World
from rehearsal.world.fork import fork_world
from rehearsal.world.storage import ContractError, Json, canonical

from .policy import Policy


def validate_shared_ledger(ledger: UsageLedger, settings: ModelSettings, scope: str) -> None:
    config = ledger.report()["config"]
    expected = {
        "model_id": settings.model_id,
        "rates": json.dumps(asdict(settings.rates), sort_keys=True),
        "budget_micro_usd": settings.budget_micro_usd,
        "input_limit": settings.input_limit,
        "output_limit": settings.output_limit,
        "scope": scope,
    }
    if (
        any(config[k] != v for k, v in expected.items())
        or ledger.max_calls != settings.max_model_calls
        or ledger.max_total_tokens != settings.max_total_tokens
        or ledger.max_tool_calls != settings.max_tool_calls
    ):
        raise ContractError("SHARED_USAGE_CONFIG_MISMATCH")


def verify_attribution(artifact: Json, ledger: UsageLedger, role: str) -> None:
    report = ledger.report()
    rows = [r for r in report["calls"] if r["execution_id"] == artifact["experiment_id"]]
    accounting = artifact.get("accounting", {})
    rejections = [
        r
        for r in report["admission_rejections"]
        if r["execution_id"] == artifact["experiment_id"] and r["role"] == role
    ]
    if not rows and rejections and artifact.get("stop_reason") == rejections[-1]["reason"]:
        raise ContractError(rejections[-1]["reason"])
    if (
        not rows
        or any(r["role"] != role for r in rows)
        or accounting.get("session_id") != ledger.run_id
        or accounting.get("scope") != report["config"]["scope"]
        or artifact.get("accounting_scope") != report["config"]["scope"]
        or accounting.get("call_ids") != [r["id"] for r in rows]
        or accounting.get("calls_sha256") != hashlib.sha256(canonical(rows).encode()).hexdigest()
    ):
        raise ContractError("EXPERIMENT_USAGE_MISMATCH")
    if any(r["status"] != "RECORDED" for r in rows):
        raise ContractError("EXPERIMENT_USAGE_UNRESOLVED")
    if report["estimated_token_budget_exceeded"]:
        raise ContractError("TOTAL_TOKEN_LIMIT")
    if artifact.get("runtime_status") != "COMPLETED" or artifact.get("stop_reason"):
        raise ContractError(artifact.get("stop_reason") or "EXPERIMENT_RUNTIME_INCOMPLETE")


def model_experiment(
    parent: World,
    parent_run_id: str,
    directory: Path,
    experiment_id: str,
    policy: Policy,
    scenario: Json,
    model: Model,
    settings: ModelSettings,
    ledger: UsageLedger,
    role: str,
    scope: str,
) -> Json:
    validate_shared_ledger(ledger, settings, scope)
    if role not in {"buyer_initial", "buyer_candidate"}:
        raise ContractError("INVALID_PURCHASING_ROLE")
    if model.get_config().get("model_id") != settings.model_id:
        raise ContractError("PURCHASING_MODEL_ID_MISMATCH")
    if any(c["execution_id"] == experiment_id for c in ledger.report()["calls"]):
        raise ContractError("EXPERIMENT_ACCOUNTING_ID_REUSED")
    child, manifest = fork_world(parent, parent_run_id, directory, experiment_id, policy.version)
    if any(e["event_type"].startswith("order.") for e in child.shop.events(experiment_id)):
        raise ContractError("COUNTEREXAMPLE_REQUIRES_PREPURCHASE_SNAPSHOT")
    limits = Limits(settings.max_model_calls, settings.max_tool_calls)
    meter = MeterHooks(ledger, role=role, execution_id=experiment_id)
    agent = agent_for_tools(model, purchasing_tools(child, experiment_id), limits, meter, policy)
    trace: list[Json] = []
    changed = False

    def after_tool(event: AfterToolCallEvent) -> None:
        nonlocal changed
        trace.append(
            {
                "tool_use": event.tool_use,
                "result": event.result,
                "error_type": type(event.exception).__name__ if event.exception else None,
            }
        )
        # Operator-controlled known challenge; never exposed as a purchasing tool.
        if (
            not changed
            and event.tool_use["name"] == "get_quotes"
            and event.result.get("status") == "success"
        ):
            child.shop.change_price(experiment_id, "A", "tent", 100)
            changed = True

    agent.add_hook(after_tool)
    report: Json = {
        "experiment_id": experiment_id,
        "policy_version": policy.version,
        "policy": asdict(policy),
        "snapshot_sha256": manifest["snapshot_sha256"],
        "scope": "model-purchasing-known-counterexample",
        "accounting_scope": scope,
        "runtime_status": "STARTED",
        "stop_reason": None,
        "tool_trace": trace,
        "challenge": "A tent becomes 100 after first successful quote",
        "held_out": False,
        "model_efficacy_verified": False,
    }

    async def invoke() -> Any:
        return await asyncio.wait_for(
            agent.invoke_async("Complete the event-supplies goal using your tools."),
            settings.timeout_seconds,
        )

    try:
        result = asyncio.run(invoke())
        report["runtime_status"] = "COMPLETED" if result.stop_reason == "end_turn" else "INCOMPLETE"
    except Exception as exc:
        report.update(runtime_status="ERROR", error_type=type(exc).__name__)
    finally:
        report["stop_reason"] = meter.stop_reason or limits.stop_reason
        if report["stop_reason"]:
            report["runtime_status"] = "LIMITED"
        report["challenge_applied"] = changed
        rows = [r for r in ledger.report()["calls"] if r["execution_id"] == experiment_id]
        report["accounting"] = {
            "session_id": ledger.run_id,
            "scope": scope,
            "call_ids": [r["id"] for r in rows],
            "calls_sha256": hashlib.sha256(canonical(rows).encode()).hexdigest(),
        }
        evidence = directory / "evidence.json"
        report["verdict"] = verify(directory, experiment_id, scenario, export_to=evidence).as_dict()
        report["evidence_sha256"] = hashlib.sha256(evidence.read_bytes()).hexdigest()
        (directory / "experiment.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
