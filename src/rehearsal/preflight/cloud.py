"""Server-owned source, independent report finalization and atomic decision export."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from rehearsal.serverless.control import Control
from rehearsal.serverless.domain import Json, Rejected, canonical, digest, identifier

from .contracts import catalog, expected_decision, snapshot
from .report import build_report


def source_key(case: str) -> Json:
    catalog(case)  # Validate the allowed server-owned request IDs.
    return {"pk": {"S": "SOURCE#" + case}, "sk": {"S": "CATALOG"}}


def read_source(control: Control, case: str) -> Json:
    item = control.client.get_item(
        TableName=control.table,
        Key=source_key(case),
        ConsistentRead=True,
    ).get("Item")
    if not item:
        raise Rejected("SOURCE_NOT_CONFIGURED")
    source: Json = json.loads(item["body"]["S"])
    if digest(source) != item["digest"]["S"] or str(source["revision"]) != item["revision"]["N"]:
        raise Rejected("SOURCE_INTEGRITY_FAILED")
    return source


def get_json(session: Any, run_id: str, suffix: str) -> Json:
    response = session.client("s3").get_object(
        Bucket=os.environ["ARTIFACTS_BUCKET"],
        Key=f"runs/{run_id}/{suffix}",
    )
    value: Json = json.loads(response["Body"].read())
    return value


def body_of(event: Json, fields: set[str]) -> Json:
    if event.get("isBase64Encoded") or len(event.get("body") or "") > 1024:
        raise Rejected("INVALID_BODY")
    try:
        body = json.loads(event.get("body") or "{}")
    except (ValueError, TypeError):
        raise Rejected("INVALID_BODY") from None
    if (
        not isinstance(body, dict)
        or set(body) != fields
        or any(not isinstance(v, str) for v in body.values())
    ):
        raise Rejected("INVALID_ARGUMENTS")
    return body


def decision(
    control: Control,
    report: Json,
    case: str,
    body: Json,
    now: int,
) -> Json:
    """Source condition and final decision commit share one DynamoDB transaction."""
    if body["report_sha256"] != report["report_sha256"]:
        raise Rejected("REPORT_BINDING_MISMATCH")
    if body["action"] not in {"accept", "decline"}:
        raise Rejected("INVALID_DECISION")
    run_id = report["report_id"]
    key = {"pk": {"S": "DECISION#" + run_id}, "sk": {"S": "FINAL"}}
    binding = digest(body)

    def previous() -> Json | None:
        item = control.client.get_item(
            TableName=control.table,
            Key=key,
            ConsistentRead=True,
        ).get("Item")
        if item:
            if item["binding"]["S"] != binding:
                raise Rejected("DECISION_ALREADY_RECORDED")
            # Idempotent read of a historical brief, not renewed authorization.
            value: Json = json.loads(item["body"]["S"])
            return value
        return None

    prior = previous()
    if prior:
        return prior
    source = read_source(control, case)
    if body["action"] == "accept":
        brief = expected_decision(report, body["plan_sha256"], source, now)
    else:
        brief = {
            "report_id": run_id,
            "report_sha256": report["report_sha256"],
            "decision": "DECLINED",
            "recorded_at": now,
            "external_orders_created": 0,
        }
    brief["brief_sha256"] = digest(brief)
    try:
        control.client.transact_write_items(
            TransactItems=[
                {
                    "ConditionCheck": {
                        "TableName": control.table,
                        "Key": source_key(case),
                        "ConditionExpression": "digest = :hash AND revision = :rev",
                        "ExpressionAttributeValues": {
                            ":hash": {"S": digest(source)},
                            ":rev": {"N": str(source["revision"])},
                        },
                    }
                },
                {
                    "ConditionCheck": {
                        "TableName": control.table,
                        "Key": control.key(run_id),
                        "ConditionExpression": "finalized = :yes",
                        "ExpressionAttributeValues": {":yes": {"BOOL": True}},
                    }
                },
                {
                    "Put": {
                        "TableName": control.table,
                        "Item": {**key, "binding": {"S": binding}, "body": {"S": canonical(brief)}},
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                },
            ]
        )
    except Exception as exc:
        prior = previous()
        if prior:
            return prior
        if getattr(exc, "response", {}).get("Error", {}).get("Code") == (
            "TransactionCanceledException"
        ):
            raise Rejected("SOURCE_OR_DECISION_CHANGED_RELOAD_REQUIRED") from exc
        raise
    return brief


def api(event: Json, session: Any, control: Control) -> Json:
    method = event["requestContext"]["http"]["method"]
    path = event["rawPath"]
    status = 200
    result: Json
    if method == "GET" and path == "/api/preflights/config":
        result = {
            "requests": [catalog(c)["intent"] | {"id": c} for c in ["family-camping", "no-tents"]],
            "model": "Amazon Nova 2 Lite",
            "external_transactions_enabled": False,
        }
    elif method == "POST" and path == "/api/preflights":
        body = body_of(event, {"request_id", "scenario"})
        source = read_source(control, body["scenario"])
        meta = control.admit(
            body["request_id"],
            "PREFLIGHT",
            body["scenario"],
            snapshot(source, int(time.time())),
        )
        # Immutable input, outside model-writable prefixes. Retry uses original admitted snapshot.
        s3 = session.client("s3")
        try:
            s3.put_object(
                Bucket=os.environ["ARTIFACTS_BUCKET"],
                Key=f"runs/{meta['run_id']}/input.json",
                Body=meta["scenario"].encode(),
                ContentType="application/json",
                IfNoneMatch="*",
            )
        except s3.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
                raise
        if meta["status"] == "QUEUED":
            session.client("stepfunctions").start_execution(
                stateMachineArn=os.environ["PREVIEW_WORKFLOW_ARN"],
                name=meta["run_id"],
                input=canonical({"run_id": meta["run_id"]}),
            )
        result, status = {"run_id": meta["run_id"], "status": meta["status"]}, 202
    elif path.startswith("/api/preflights/"):
        parts = path.removeprefix("/api/preflights/").split("/")
        run_id = identifier(parts[0])
        found = control.get(run_id)
        if not found or found["method"] != "PREFLIGHT":
            raise Rejected("RUN_NOT_FOUND")
        meta = found
        if method == "POST" and len(parts) == 2 and parts[1] == "decision":
            if not meta["finalized"]:
                raise Rejected("REPORT_NOT_READY")
            body = body_of(event, {"action", "report_sha256", "plan_sha256"})
            result = decision(
                control,
                get_json(session, run_id, "impact-report.json"),
                meta["case"],
                body,
                int(time.time()),
            )
        elif method == "GET" and len(parts) == 2 and parts[1] == "evidence":
            if not meta["finalized"]:
                raise Rejected("REPORT_NOT_READY")
            result = get_json(session, run_id, "impact-evidence.json")
        elif method == "GET" and len(parts) == 1:
            runtime = json.loads(meta.get("runtime", "{}"))
            usage = runtime.get("usage") or json.loads(meta.get("progress", "{}")).get("usage", {})
            result = {
                "run_id": run_id,
                "status": meta["status"],
                "finalized": meta["finalized"],
                "phase": runtime.get("phase", "QUEUED"),
                "created_at": int(meta["created_at"]),
                "usage": {
                    "model_calls": len(usage.get("calls", [])),
                    "recorded_micro_usd": usage.get("recorded_micro_usd", 0),
                },
            }
            if meta["finalized"]:
                result["report"] = get_json(session, run_id, "impact-report.json")
                recorded = control.client.get_item(
                    TableName=control.table,
                    Key={"pk": {"S": "DECISION#" + run_id}, "sk": {"S": "FINAL"}},
                    ConsistentRead=True,
                ).get("Item")
                result["decision"] = json.loads(recorded["body"]["S"]) if recorded else None
        else:
            result, status = {"error": "NOT_FOUND"}, 404
    else:
        result, status = {"error": "NOT_FOUND"}, 404
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": canonical(result),
    }


def finalize(event: Json, session: Any, control: Control) -> Json:
    run_id = identifier(event["run_id"])
    meta = control.get(run_id)
    if not meta or meta["method"] != "PREFLIGHT":
        raise Rejected("RUN_NOT_FOUND")
    if meta["finalized"]:
        return {"run_id": run_id, "status": meta["status"]}
    control.close(run_id)
    client = session.client("bedrock-agentcore")
    try:
        client.stop_runtime_session(
            agentRuntimeArn=os.environ["RUNTIME_ARN"],
            runtimeSessionId=meta["session_id"],
        )
    except client.exceptions.ResourceNotFoundException:
        pass
    value = get_json(session, run_id, "input.json")
    raw: Json = {}
    try:
        raw = get_json(session, run_id, "runtime/preflight.json")
    except session.client("s3").exceptions.NoSuchKey:
        pass
    usage = raw.get("usage", {})
    known = usage.get("all_usage_recorded") is True
    cost = int(usage["recorded_micro_usd"]) if known else None
    if not meta["started"]:
        cost = 0
    report = build_report(
        run_id,
        value,
        raw.get("artifacts", []),
        proposed_supplier=raw.get("proposed_supplier"),
        generated_at=int(time.time()),
        model_usage=usage,
    )
    failure = event.get("workflow", {}).get("failure")
    if raw.get("runtime_status") != "COMPLETED" or not known or failure:
        report.update(status="REVIEW_REQUIRED", decision="DO_NOT_EXECUTE")
        for plan in report["plans"]:
            plan["eligible_for_handoff"] = False
        report["recommended_supplier"] = None
    report["runtime_session_stopped"] = True
    report["runtime_status"] = raw.get("runtime_status", "UNKNOWN")
    report["report_sha256"] = digest({k: v for k, v in report.items() if k != "report_sha256"})
    s3 = session.client("s3")
    for suffix, data in [
        ("impact-report.json", report),
        (
            "impact-evidence.json",
            {
                "report": report,
                "artifacts": raw.get("artifacts", []),
                "agent_trace": raw.get("agent_trace", []),
            },
        ),
    ]:
        s3.put_object(
            Bucket=os.environ["ARTIFACTS_BUCKET"],
            Key=f"runs/{run_id}/{suffix}",
            Body=canonical(data).encode(),
            ContentType="application/json",
        )
    control.publish(run_id, "verification", {"report_sha256": report["report_sha256"]})
    control.finalize(run_id, cost, report["status"])
    return {"run_id": run_id, "status": report["status"]}
