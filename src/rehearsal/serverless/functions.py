"""Lambda entrypoints. Each role is deployed as a distinct function and IAM role."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from .control import CASES, METHODS, Control
from .domain import Json, Rejected, canonical, identifier, observation
from .scenarios import scenario_for
from .store import Conflict, DynamoStore
from .verifier import verify


def clients() -> tuple[Any, Control, DynamoStore]:
    session = boto3.Session()
    db = session.client("dynamodb", config=Config(retries={"total_max_attempts": 1}))
    return (
        session,
        Control(db, os.environ["CONTROL_TABLE"]),
        DynamoStore(db, os.environ["COMMERCE_TABLE"], os.environ["CONTROL_TABLE"]),
    )


def api(event: Json, session: Any, control: Control, store: DynamoStore) -> Json:
    if event["rawPath"].startswith("/api/preflights"):
        from rehearsal.preflight.cloud import api as preflight_api

        return preflight_api(event, session, control)
    method = event["requestContext"]["http"]["method"]
    path = event["rawPath"]
    result: Json
    status = 200
    if method == "GET" and path == "/api/config":
        result = {
            "methods": list(METHODS),
            "scenarios": list(CASES),
            "scope": "AWS serverless synthetic transaction rehearsal",
            "model": "Amazon Nova 2 Lite",
            "max_parallel": 1,
            "per_model_run_budget_usd": 0.50,
        }
    elif method == "POST" and path == "/api/experiments":
        if event.get("isBase64Encoded") or len(event.get("body") or "") > 1024:
            raise Rejected("INVALID_BODY")
        try:
            body = json.loads(event.get("body") or "{}")
        except (ValueError, TypeError):
            raise Rejected("INVALID_BODY") from None
        if not isinstance(body, dict) or set(body) != {"request_id", "method", "scenario"}:
            raise Rejected("INVALID_ARGUMENTS")
        if any(not isinstance(v, str) for v in body.values()):
            raise Rejected("INVALID_ARGUMENTS")
        scenario = scenario_for(body["scenario"])
        meta = control.admit(body["request_id"], body["method"], body["scenario"], scenario)
        if meta["status"] == "QUEUED":
            # Standard-workflow name/input are stable; a retried API request never starts a
            # second run. A lost response is reconciled using this exact execution name.
            session.client("stepfunctions").start_execution(
                stateMachineArn=os.environ["WORKFLOW_ARN"],
                name=meta["run_id"],
                input=canonical({"run_id": meta["run_id"]}),
            )
        result, status = {"run_id": meta["run_id"], "status": meta["status"]}, 202
    elif method == "GET" and path.startswith("/api/experiments/"):
        run_id = identifier(path.removeprefix("/api/experiments/"))
        found = control.get(run_id)
        if not found:
            raise Rejected("RUN_NOT_FOUND")
        meta = found
        result = {k: meta[k] for k in ["run_id", "method", "case", "status", "finalized"]}
        result["created_at"] = int(meta["created_at"])
        for name in ["progress", "runtime", "verification"]:
            if name in meta:
                value = json.loads(meta[name])
                if name in {"runtime", "progress"}:
                    usage = value.get("usage", {})
                    # Do not expose internal settings, paths, model prose or supplier text.
                    result[name] = {
                        k: value[k]
                        for k in [
                            "phase",
                            "runtime_status",
                            "learning_status",
                            "policy",
                            "tool_calls",
                        ]
                        if k in value
                    }
                    result[name]["usage"] = {
                        "model_calls": len(usage.get("calls", [])),
                        "recorded_micro_usd": usage.get("recorded_micro_usd", 0),
                        "unresolved_reserved_micro_usd": usage.get(
                            "unresolved_reserved_micro_usd", 0
                        ),
                        "recorded_total_tokens": usage.get("recorded_total_tokens", 0),
                        "role_usage": usage.get("role_usage", {}),
                    }
                else:
                    result[name] = value
        try:
            state = store.load(run_id)
            result["snapshot"] = observation(state, int(time.time()))
            result["events"] = [
                e
                for r in store.journal(run_id, state["version"])
                for e in r["entries"]
                if e["kind"] not in {"CREATED", "QUOTED"}
            ][-20:]
        except Rejected as exc:
            if str(exc) != "RUN_NOT_FOUND":
                raise
    else:
        result, status = {"error": "NOT_FOUND"}, 404
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": canonical(result),
    }


def seller(event: Json, control: Control, store: DynamoStore) -> Json:
    run_id = identifier(event["run_id"])
    meta = control.get(run_id)
    if not meta:
        raise Rejected("RUN_NOT_FOUND")
    scenario = json.loads(meta["scenario"])
    now = int(time.time())
    if event.get("operation") == "bootstrap":
        try:
            store.create(run_id, scenario, now)
        except Conflict:
            existing = store.load(run_id)
            if existing["goal"] != scenario["goal"]:
                raise Rejected("INITIAL_STATE_MISMATCH") from None
        return {"run_id": run_id}
    runtime = json.loads(meta.get("runtime", "{}"))
    state = store.load(run_id)
    phase = runtime.get("phase")
    if state["started_at"] is None and phase == "BUYING":
        store.command(run_id, "activate", {}, now, actor="seller")
    store.command(run_id, "advance", {}, now, actor="seller")
    state = store.load(run_id)
    pending = any(o["status"] in {"AUTHORIZED", "PAID"} for o in state["orders"].values())
    finished = phase == "FINISHED" and not pending
    expired = now >= int(meta["deadline_at"])
    return {"run_id": run_id, "done": finished or expired}


def invoke(event: Json, session: Any, control: Control) -> Json:
    run_id = identifier(event["run_id"])
    meta = control.get(run_id)
    if not meta:
        raise Rejected("RUN_NOT_FOUND")
    config = Config(connect_timeout=20, read_timeout=540, retries={"total_max_attempts": 1})
    client = session.client("bedrock-agentcore", config=config)
    # No automatic paid-runtime retries after ambiguous transport failures.
    response = client.invoke_agent_runtime(
        agentRuntimeArn=os.environ["RUNTIME_ARN"],
        runtimeSessionId=meta["session_id"],
        payload=canonical({"run_id": run_id}).encode(),
        contentType="application/json",
    )
    for _ in response["response"].iter_chunks():
        pass
    return {"run_id": run_id}


def finalize(event: Json, session: Any, control: Control, store: DynamoStore) -> Json:
    run_id = identifier(event["run_id"])
    meta = control.get(run_id)
    if not meta:
        raise Rejected("RUN_NOT_FOUND")
    if meta["finalized"]:
        return {"run_id": run_id, "status": meta["status"]}
    control.close(run_id)
    client = session.client("bedrock-agentcore")
    stop_confirmed = False
    try:
        client.stop_runtime_session(
            agentRuntimeArn=os.environ["RUNTIME_ARN"], runtimeSessionId=meta["session_id"]
        )
        stop_confirmed = True
    except client.exceptions.ResourceNotFoundException:
        stop_confirmed = True
    # An unsuccessful stop propagates: do not free the slot while an agent may still execute.
    failure = event.get("failure") or event.get("workflow", {}).get("failure") or {}
    try:
        state = store.load(run_id)
        records = store.journal(run_id, state["version"])
        verdict = verify(state, records, run_id, json.loads(meta["scenario"]))
    except Rejected as exc:
        if str(exc) != "RUN_NOT_FOUND":
            raise
        state, records = {}, []
        verdict = {"status": "INVALID", "run_id": run_id, "errors": ["MISSING_COMMERCE_GENESIS"]}
    meta = control.get(run_id)
    assert meta is not None
    runtime = json.loads(meta.get("runtime", "{}"))
    usage = runtime.get("usage", {})
    known = runtime.get("phase") == "FINISHED" and usage.get("all_usage_recorded") is True
    cost = int(usage["recorded_micro_usd"]) if known else None
    if not meta["started"]:
        # The durable claim precedes every model call, so no claim proves no paid invocation.
        known, cost = True, 0
    report = {
        "verdict": verdict,
        "runtime_status": runtime.get("runtime_status", "UNKNOWN"),
        "runtime_session_stop_requested": stop_confirmed,
        "usage_known": known,
        "recorded_micro_usd": cost,
        "scope": "AWS-DynamoDB-independent-journal-not-Medusa",
        "execution_error": failure.get("Error"),
    }
    artifact = {"state": state, "journal": records, "verification": report}
    session.client("s3").put_object(
        Bucket=os.environ["ARTIFACTS_BUCKET"],
        Key=f"runs/{run_id}/commerce-evidence.json",
        Body=canonical(artifact).encode(),
        ContentType="application/json",
    )
    control.publish(run_id, "verification", report)
    status = "COMPLETE" if verdict["status"] == "COMPLETE" else "INCOMPLETE"
    if (
        not known
        or failure
        or verdict["status"] == "INVALID"
        or runtime.get("runtime_status") not in {"COMPLETED", "GOAL_OBSERVED"}
    ):
        status = "REVIEW_REQUIRED"
    control.finalize(run_id, cost, status)
    return {"run_id": run_id, "status": status}


def handler(event: Json, context: Any) -> Json:
    session, control, store = clients()
    role = os.environ["FUNCTION_ROLE"]
    try:
        if role == "api":
            return api(event, session, control, store)
        if role == "commerce":
            if set(event) != {"run_id", "action", "args"}:
                raise Rejected("INVALID_ARGUMENTS")
            run_id = identifier(event["run_id"])
            meta = control.get(run_id)
            if not meta or meta["finalized"]:
                raise Rejected("RUN_NOT_ACTIVE")
            result = store.command(run_id, event["action"], event["args"], int(time.time()))
            return {"ok": True, "result": result}
        if role == "seller":
            return seller(event, control, store)
        if role == "invoke":
            return invoke(event, session, control)
        if role == "previewinvoke":
            return invoke(event, session, control)
        if role == "previewfinalize":
            from rehearsal.preflight.cloud import finalize as preflight_finalize

            return preflight_finalize(event, session, control)
        if role == "finalize":
            return finalize(event, session, control, store)
        raise RuntimeError("Unknown function role")
    except Rejected as exc:
        if role == "api":
            return {
                "statusCode": 409,
                "headers": {"content-type": "application/json"},
                "body": canonical({"error": str(exc)}),
            }
        if role == "commerce":
            return {"ok": False, "error": str(exc)}
        raise
