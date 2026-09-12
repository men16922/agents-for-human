#!/usr/bin/env python3
"""Deploy the reviewed Rehearsal stacks; requires an explicit --execute flag.

Pinned ARM64 dependencies must already exist; see infra/serverless/README.md.
Existing budget rows are never reset or increased by deployment.
"""

import argparse
import json
import mimetypes
import subprocess
import time
from datetime import datetime
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local/serverless-deploy"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--profile", default="q-user")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--initialize-budget", action="store_true")
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    if session.client("sts").get_caller_identity()["Account"] != "908601828278":
        raise RuntimeError("This reviewed deployment targets AWS account 908601828278")
    if args.region != "us-west-2":
        raise RuntimeError("The reviewed region is us-west-2")
    LOCAL.mkdir(parents=True, exist_ok=True)
    cfn = session.client("cloudformation")

    def stack(name, template, parameters=None):
        data = {
            "StackName": name,
            "TemplateBody": json.dumps(json.loads(template), separators=(",", ":")),
            "Parameters": [
                {"ParameterKey": k, "ParameterValue": v} for k, v in (parameters or {}).items()
            ],
            "Capabilities": ["CAPABILITY_IAM"],
            "DisableRollback": True,
        }
        cfn.validate_template(TemplateBody=data["TemplateBody"])
        try:
            previous = cfn.describe_stacks(StackName=name)["Stacks"][0]
        except cfn.exceptions.ClientError as exc:
            if "does not exist" not in str(exc):
                raise
            previous = None
        if previous:
            if {"Key": "Project", "Value": "rehearsal-serverless"} not in previous["Tags"]:
                raise RuntimeError("Refusing to update an unrelated stack")
            try:
                cfn.update_stack(**data)
            except cfn.exceptions.ClientError as exc:
                if "No updates are to be performed" not in str(exc):
                    raise
        else:
            cfn.create_stack(**data, Tags=[{"Key": "Project", "Value": "rehearsal-serverless"}])
        while True:
            info = cfn.describe_stacks(StackName=name)["Stacks"][0]
            status = info["StackStatus"]
            print(name, status, flush=True)
            if status in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
                return {x["OutputKey"]: x["OutputValue"] for x in info.get("Outputs", [])}
            if not status.endswith("IN_PROGRESS"):
                raise RuntimeError("Stack requires review: " + status)
            time.sleep(15)

    base = stack("rehearsal-serverless-base", (ROOT / "infra/serverless/base.json").read_text())
    subprocess.run(["python3", "scripts/dev/serverless_template.py"], cwd=ROOT, check=True)
    subprocess.run(["python3", "scripts/dev/serverless_package.py"], cwd=ROOT, check=True)
    manifest = json.loads((LOCAL / "package.json").read_text())
    s3 = session.client("s3")
    key = "packages/" + manifest["sha256"] + ".zip"
    try:
        version = s3.head_object(Bucket=base["ArtifactsBucket"], Key=key)["VersionId"]
    except s3.exceptions.ClientError as exc:
        if exc.response["Error"]["Code"] != "404":
            raise
        version = s3.put_object(
            Bucket=base["ArtifactsBucket"], Key=key, Body=(LOCAL / "code.zip").read_bytes()
        )["VersionId"]
    params = {
        k: base[k] for k in ["ArtifactsBucket", "SiteBucket", "CommerceTable", "ControlTable"]
    }
    params.update(CodeKey=key, CodeVersion=version)
    (LOCAL / "application-params.json").write_text(json.dumps(params, indent=2) + "\n")
    out = stack(
        "rehearsal-serverless-app", (ROOT / "infra/serverless/application.json").read_text(), params
    )
    (LOCAL / "outputs.json").write_text(json.dumps(out, indent=2) + "\n")
    from rehearsal.preflight.contracts import catalog
    from rehearsal.serverless.domain import canonical, digest

    db = session.client("dynamodb")
    for case in ["family-camping", "no-tents"]:
        source = catalog(case)
        try:
            db.put_item(
                TableName=base["ControlTable"],
                Item={
                    "pk": {"S": "SOURCE#" + case},
                    "sk": {"S": "CATALOG"},
                    "body": {"S": canonical(source)},
                    "digest": {"S": digest(source)},
                    "revision": {"N": str(source["revision"])},
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except db.exceptions.ConditionalCheckFailedException:
            print("Existing source revision preserved:", case, flush=True)
    if args.initialize_budget:
        db = session.client("dynamodb")
        expires = int(datetime.fromisoformat("2026-10-10T00:00:00+00:00").timestamp())
        try:
            db.put_item(
                TableName=base["ControlTable"],
                Item={
                    "pk": {"S": "GLOBAL"},
                    "sk": {"S": "BUDGET"},
                    "remaining": {"N": "4000000"},
                    "active": {"N": "0"},
                    "runs_left": {"N": "40"},
                    "closes_at": {"N": str(expires)},
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except db.exceptions.ConditionalCheckFailedException:
            print("Existing budget preserved", flush=True)
    subprocess.run(
        [
            "scripts/dev/with-env.sh",
            "env",
            "VITE_DEPLOYMENT=serverless",
            "npm",
            "run",
            "build",
            "--workspace",
            "web",
            "--",
            "--outDir",
            "dist-cloud",
        ],
        cwd=ROOT,
        check=True,
    )
    for file in (ROOT / "web/dist-cloud").rglob("*"):
        if file.is_file():
            key = file.relative_to(ROOT / "web/dist-cloud").as_posix()
            s3.put_object(
                Bucket=base["SiteBucket"],
                Key=key,
                Body=file.read_bytes(),
                ContentType=mimetypes.guess_type(str(file))[0] or "application/octet-stream",
                CacheControl="no-cache"
                if key == "index.html"
                else "public,max-age=31536000,immutable",
            )
    session.client("cloudfront").create_invalidation(
        DistributionId=out["DistributionId"],
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/index.html"]},
            "CallerReference": "rehearsal-" + str(time.time_ns()),
        },
    )
    logs = session.client("logs")
    for runtime_key in ["RuntimeArn", "PreviewRuntimeArn"]:
        runtime_id = out[runtime_key].rsplit("/", 1)[-1]
        for group in logs.describe_log_groups(
            logGroupNamePrefix="/aws/bedrock-agentcore/runtimes/" + runtime_id
        )["logGroups"]:
            logs.put_retention_policy(logGroupName=group["logGroupName"], retentionInDays=7)
    print(out["Url"])


if __name__ == "__main__":
    main()
