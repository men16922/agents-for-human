"""Read-only deployed IAM checks and independent export audit of one preview run."""

import argparse
import json
from pathlib import Path

import boto3

from rehearsal.preflight.report import build_report
from rehearsal.serverless.control import Control
from rehearsal.serverless.domain import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    s = boto3.Session(profile_name="q-user", region_name="us-west-2")
    assert s.client("sts").get_caller_identity()["Account"] == "908601828278"
    folder = Path("evidence/preflight")
    folder.mkdir(exist_ok=True)
    resources = s.client("cloudformation").list_stack_resources(
        StackName="rehearsal-serverless-app"
    )["StackResourceSummaries"]
    ids = {r["LogicalResourceId"]: r["PhysicalResourceId"] for r in resources}
    iam = s.client("iam")
    role = iam.get_role(RoleName=ids["PreviewAgentRole"])["Role"]["Arn"]
    bucket = "rehearsal-serverless-artifacts-908601828278-us-west-2"
    prefix = f"arn:aws:s3:::{bucket}/runs/preview-example/"
    checks = []
    for action, resource, expected in [
        (
            "lambda:InvokeFunction",
            "arn:aws:lambda:us-west-2:908601828278:function:rehearsal-serverless-commerce",
            "implicitDeny",
        ),
        (
            "lambda:InvokeFunction",
            "arn:aws:lambda:us-west-2:908601828278:function:rehearsal-serverless-seller",
            "implicitDeny",
        ),
        (
            "dynamodb:PutItem",
            "arn:aws:dynamodb:us-west-2:908601828278:table/rehearsal-serverless-commerce",
            "implicitDeny",
        ),
        ("s3:PutObject", prefix + "input.json", "implicitDeny"),
        ("s3:PutObject", prefix + "impact-report.json", "implicitDeny"),
        ("s3:PutObject", prefix + "impact-evidence.json", "implicitDeny"),
        ("s3:PutObject", prefix + "runtime/preflight.json", "allowed"),
        ("s3:GetObject", prefix + "input.json", "allowed"),
    ]:
        result = iam.simulate_principal_policy(
            PolicySourceArn=role, ActionNames=[action], ResourceArns=[resource]
        )["EvaluationResults"][0]
        assert result["EvalDecision"] == expected, result
        checks.append({"action": action, "resource": resource, "decision": result["EvalDecision"]})
    (folder / "iam.json").write_text(
        json.dumps(
            {"scope": "AWS IAM policy simulation", "checks": checks, "passed": True}, indent=2
        )
        + "\n"
    )
    print("IAM policy simulation: 8 checks passed", flush=True)
    if not args.run_id:
        return
    run_id = args.run_id
    assert run_id.startswith("preview-")
    target = folder / run_id
    target.mkdir(exist_ok=True)
    s3 = s.client("s3")
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=f"runs/{run_id}/"
    ):
        for item in page.get("Contents", []):
            p = target / item["Key"].split("/", 2)[2]
            p.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, item["Key"], str(p))
    report = json.loads((target / "impact-report.json").read_text())
    raw = json.loads((target / "runtime/preflight.json").read_text())
    frozen = json.loads((target / "input.json").read_text())
    rebuilt = build_report(
        run_id,
        frozen,
        raw["artifacts"],
        proposed_supplier=raw["proposed_supplier"],
        generated_at=report["generated_at"],
        model_usage=raw["usage"],
    )
    for k in ["plans", "coverage", "snapshot", "recommended_supplier", "proposed_supplier"]:
        assert rebuilt[k] == report[k], k
    assert report["report_sha256"] == digest(
        {k: v for k, v in report.items() if k != "report_sha256"}
    )
    db = s.client("dynamodb")
    control = Control(db, "rehearsal-serverless-control")
    meta = control.get(run_id)
    assert meta["finalized"] and meta["status"] == "REPORT_READY"
    assert raw["usage"]["all_usage_recorded"] and raw["usage"]["recorded_micro_usd"] <= 500000
    commerce = db.query(
        TableName="rehearsal-serverless-commerce",
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": "RUN#" + run_id}},
        ConsistentRead=True,
    )
    assert commerce["Count"] == 0
    outputs = json.loads(Path(".local/serverless-deploy/outputs.json").read_text())
    workflow = s.client("stepfunctions").describe_execution(
        executionArn=outputs["PreviewWorkflowArn"].replace(":stateMachine:", ":execution:")
        + ":"
        + run_id
    )
    assert workflow["status"] == "SUCCEEDED"
    recorded = db.get_item(
        TableName=control.table,
        Key={"pk": {"S": "DECISION#" + run_id}, "sk": {"S": "FINAL"}},
        ConsistentRead=True,
    ).get("Item")
    budget = db.get_item(
        TableName=control.table,
        Key={"pk": {"S": "GLOBAL"}, "sk": {"S": "BUDGET"}},
        ConsistentRead=True,
    )["Item"]
    assert budget["active"]["N"] == "0"
    for name, data in [
        ("control", meta),
        ("workflow", workflow),
        ("budget", budget),
        ("decision", recorded),
    ]:
        (target / (name + ".json")).write_text(json.dumps(data, indent=2, default=str) + "\n")
    audit = {
        "run_id": run_id,
        "scope": "Actual AWS Nova planning; synthetic transaction simulation",
        "report_sha256": report["report_sha256"],
        "verified_cells": report["coverage"]["verified"],
        "model_calls": len(raw["usage"]["calls"]),
        "recorded_micro_usd": raw["usage"]["recorded_micro_usd"],
        "commerce_table_rows": commerce["Count"],
        "workflow_status": workflow["status"],
        "runtime_stop_confirmed_by_finalizer": report["runtime_session_stopped"],
        "remaining_micro_usd": int(budget["remaining"]["N"]),
        "active": 0,
        "passed": True,
    }
    (target / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit))


if __name__ == "__main__":
    main()
