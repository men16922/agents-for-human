"""Prospective external comparison admissions; each arm retains its original cell budget.

B0 uses fixed rules, B1 skips learning, B2 learns with one Agent and B3 uses peer review.
Transaction proof does not prove supplier-condition matching.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from strands.models.model import Model

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import bedrock_model, read_settings
from rehearsal.commerce.learning_budget import (
    BudgetCarryover,
    prepare_unlearned,
    reopen,
)
from rehearsal.commerce.learning_budget import prepare as freeze_learning
from rehearsal.commerce.model_runner import attest, configuration, execute_http
from rehearsal.commerce.reaction import ReactionSettings
from rehearsal.evaluation import batch
from rehearsal.evaluation.condition_events import validate_case, verify_events
from rehearsal.evaluation.conditions import verify_conditions, verify_start
from rehearsal.evaluation.frozen_run import digest
from rehearsal.evidence_view import MAX_ARTIFACT_BYTES, goal, integer, read_json
from rehearsal.experiments.b2 import run_b2
from rehearsal.experiments.b3 import run_b3
from rehearsal.experiments.policy import Policy
from rehearsal.operating.client import OperatingClient
from rehearsal.world.storage import Json, identifier

ROOT = Path(__file__).resolve().parents[3]


def manifest_for(directory: Path, *, execution: bool = False) -> Json:
    manifest = batch.load(directory)
    if manifest.get("evaluation_environment") != "external-medusa":
        raise ValueError("External evaluation roster required")
    for case in manifest["cases"].values():
        validate_case(case)
        goal({k: v for k, v in case["goal"].items() if k != "budget"})
        integer(case["goal"]["budget"], 1)
    if execution:
        current = {
            str(p.relative_to(ROOT)): digest(p) for p in (ROOT / "src/rehearsal").rglob("*.py")
        }
        if current != manifest["source_hashes"]:
            raise ValueError("External batch execution source changed")
    return manifest


def selected(directory: Path, manifest: Json, cell_id: str) -> Json:
    row = next((r for r in batch.rows(directory, manifest) if r["id"] == cell_id), None)
    if row is None or row["method"] not in {"B0", "B1", "B2", "B3"}:
        raise ValueError("An explicit comparison cell is required")
    return row


def refresh_reservation(directory: Path, cell: Json, usage: Json, manifest: Json) -> None:
    recorded = usage["recorded_micro_usd"]
    with sqlite3.connect(directory / "batch.sqlite3") as db:
        db.execute("BEGIN IMMEDIATE")
        changed = db.execute(
            "UPDATE cells SET recorded=?,reserved=?,usage_resolved=? "
            "WHERE id=? AND status='RUNNING'",
            (
                recorded,
                max(
                    (0 if cell["method"] == "B0" else manifest["settings"]["budget_micro_usd"])
                    - recorded,
                    0,
                ),
                int(usage["all_usage_recorded"]),
                cell["id"],
            ),
        ).rowcount
        if changed != 1:
            raise ValueError("External attempt is no longer active")


def learn(directory: Path, cell_id: str, factory: Callable[[str, Policy], Model]) -> Json:
    manifest = manifest_for(directory, execution=True)
    selected(directory, manifest, cell_id)
    if "INVALID_EVIDENCE" in summarize(directory)["status_counts"]:
        raise ValueError("Prior external evidence is invalid")
    cell, reason = batch.claim(directory, manifest, cell_id)
    if cell is None:
        raise ValueError(reason or "Cell already attempted; no automatic retry")
    path = directory / "runs" / cell_id
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    settings = batch.settings_from(manifest["settings"])
    spec = {
        "batch_id": manifest["id"],
        "cell": cell_id,
        "method": cell["method"],
        "scope": manifest["scope"],
        "settings": manifest["settings"],
        "training": manifest["training"],
        "case": manifest["cases"][cell["case_id"]],
    }
    if "external_reactions" in manifest:
        spec["reaction_settings"] = manifest["external_reactions"][cell["method"]]
    batch.write(path / "batch-spec.json", spec)
    report: Json = {
        "status": "LEARNING",
        "total_usage": {},
        "batch_spec_sha256": digest(path / "batch-spec.json"),
        "external_transaction_verified": False,
        "condition_alignment_verified": False,
    }
    batch.write(path / "report.json", report)
    try:
        if cell["method"] in {"B0", "B1"}:
            learning = prepare_unlearned(
                path / "learning", settings, manifest["scope"], cell["method"]
            )
        elif cell["method"] == "B2":
            learning = run_b2(
                factory("simulation", Policy(refresh_quote_before_order=False)),
                settings,
                path / "learning",
                deepcopy(manifest["training"]),
                manifest["scope"],
            )
        else:
            learning = run_b3(
                lambda p: factory("buyer", p),
                lambda _: factory("reviewer", Policy()),
                settings,
                path / "learning",
                deepcopy(manifest["training"]),
                manifest["scope"],
            )
        report.update(learning_status=learning["status"], total_usage=learning["usage"])
        frozen = freeze_learning(
            path / "learning", path / "policy.json", settings, manifest["scope"], cell["method"]
        )
        report.update(
            status="WAITING_EXTERNAL",
            frozen_id=frozen.identifier,
            frozen_sha256=digest(path / "policy.json"),
        )
        refresh_reservation(directory, cell, learning["usage"], manifest)
    except Exception as exc:
        report.update(status="LEARNING_FAILED", error_type=type(exc).__name__)
        batch.write(path / "report.json", report)
        batch.finish(directory, cell, report)
        return report
    batch.write(path / "report.json", report)
    return report


def execute(
    directory: Path,
    cell_id: str,
    model: Model | None,
    client: OperatingClient,
    *,
    condition_path: Path | None = None,
) -> Json:
    manifest = manifest_for(directory, execution=True)
    cell = selected(directory, manifest, cell_id)
    path = directory / "runs" / cell_id
    report: Json = json.loads((path / "report.json").read_text())
    if cell["status"] != "RUNNING" or report["status"] != "WAITING_EXTERNAL":
        raise ValueError("A waiting external attempt is required")
    check_spec(path, manifest, cell, report)
    settings = batch.settings_from(manifest["settings"])
    if (model is None) != (cell["method"] == "B0"):
        raise ValueError("B0 has no model; every model arm requires one")
    carry = BudgetCarryover(
        path / "learning", path / "policy.json", settings, manifest["scope"], cell["method"]
    )
    case = manifest["cases"][cell["case_id"]]
    condition = None
    if case.get("events") and condition_path is None:
        raise ValueError("Timed cases require initial condition evidence")
    if condition_path is not None:
        raw, value = read_json(condition_path, MAX_ARTIFACT_BYTES)
        verified = verify_conditions(value, case, client.run_id)
        verify_start(verified, client.observe_world())
        with (path / "conditions.json").open("xb") as output:
            output.write(raw)
        condition = {"sha256": hashlib.sha256(raw).hexdigest(), "verification": verified}
        report["conditions_sha256"] = condition["sha256"]
    # Save before invocation: process death stays in the denominator and holds the cap.
    report.update(status="EXTERNAL_RUNNING", external_run_id=client.run_id)
    batch.write(path / "report.json", report)
    result = execute_http(
        model,
        settings,
        client,
        path / "execution",
        deepcopy({k: v for k, v in case["goal"].items() if k != "budget"}),
        case["goal"]["budget"],
        carry.frozen,
        manifest["scope"],
        carryover=carry,
        initial_condition=condition,
        reaction_settings=batch.reaction_for(manifest, cell["method"]),
    )
    report.update(
        status="AWAITING_EVIDENCE",
        total_usage=result["usage"],
        runtime_status=result["runtime_status"],
    )
    refresh_reservation(directory, cell, result["usage"], manifest)
    batch.write(path / "report.json", report)
    return report


def check_spec(path: Path, manifest: Json, cell: Json, report: Json) -> None:
    spec = json.loads((path / "batch-spec.json").read_text())
    expected = {
        "batch_id": manifest["id"],
        "cell": cell["id"],
        "method": cell["method"],
        "scope": manifest["scope"],
        "settings": manifest["settings"],
        "training": manifest["training"],
        "case": manifest["cases"][cell["case_id"]],
    }
    if "external_reactions" in manifest:
        expected["reaction_settings"] = manifest["external_reactions"][cell["method"]]
    if spec != expected or digest(path / "batch-spec.json") != report["batch_spec_sha256"]:
        raise ValueError("External cell contract changed")


def review_result(
    path: Path, manifest: Json, cell: Json, selection: Path, report_override: Json | None = None
) -> Json:
    report: Json = report_override or json.loads((path / "report.json").read_text())
    check_spec(path, manifest, cell, report)
    spec = json.loads((path / "execution/spec.json").read_text())
    runtime = json.loads((path / "execution/report.json").read_text())
    case = manifest["cases"][cell["case_id"]]
    reaction = batch.reaction_for(manifest, cell["method"])
    declared_reaction = asdict(reaction) if reaction else None
    if (
        spec["expected_goal"] != {k: v for k, v in case["goal"].items() if k != "budget"}
        or spec["expected_budget"] != case["goal"]["budget"]
        or spec["settings"] != manifest["settings"]
        or spec["scope"] != manifest["scope"]
        or spec.get("method", "B3") != cell["method"]
        or (cell["method"] == "B0" and spec.get("executor_kind") != "B0-fixed-rule")
        or spec["source_hashes"] != manifest["source_hashes"]
        or spec["frozen_id"] != report["frozen_id"]
        or digest(path / "policy.json") != report["frozen_sha256"]
        or runtime["run_id"] != report["external_run_id"]
        or runtime["usage"] != report["total_usage"]
        or spec.get("reaction_settings") != declared_reaction
    ):
        raise ValueError("External runtime contract mismatch")
    observed_reaction = runtime.get("reactions")
    if observed_reaction is not None and (
        reaction is None
        or observed_reaction["settings"] != declared_reaction
        or not 0 <= integer(observed_reaction["replans"]) <= reaction.max_replans
    ):
        raise ValueError("External reaction execution differs from the roster")
    reaction_verified = bool(
        reaction
        and observed_reaction is not None
        and observed_reaction["worker_stopped"] is True
        and runtime.get("observations_sha256")
        and runtime.get("runtime_accounted")
    )
    if reaction and runtime.get("runtime_accounted") and not reaction_verified:
        raise ValueError("Completed reaction execution lacks sealed observations")
    historical = json.loads((path / "learning/report.json").read_text())["usage"]
    policy = json.loads((path / "policy.json").read_text())
    for name, sha in policy["learning_evidence"].items():
        if digest(path / "learning" / name) != sha:
            raise ValueError("Learning artifact changed")
    for key in ("calls", "tool_admissions", "admission_rejections"):
        rows = runtime["usage"][key]
        if rows[: len(historical[key])] != historical[key] or any(
            r["role"] != "buyer_evaluation" or r["execution_id"] != runtime["run_id"]
            for r in rows[len(historical[key]) :]
        ):
            raise ValueError("External usage attribution mismatch")
    rates = RateCard(**manifest["settings"]["rates"])
    usage = runtime["usage"]
    if sum(
        rates.micro_usd(json.loads(c["usage"])) for c in usage["calls"] if c["status"] == "RECORDED"
    ) != usage["recorded_micro_usd"] or usage["all_usage_recorded"] != all(
        c["status"] == "RECORDED" for c in usage["calls"]
    ):
        raise ValueError("External usage total mismatch")
    attestation = attest(path / "execution", selection)
    if "external_reactions" in manifest:
        attestation["reaction_settings"] = declared_reaction
        attestation["reaction_execution_verified"] = reaction_verified
    if report.get("conditions_sha256"):
        raw, conditions = read_json(path / "conditions.json", MAX_ARTIFACT_BYTES)
        verification = verify_conditions(conditions, case, runtime["run_id"])
        if hashlib.sha256(raw).hexdigest() != report["conditions_sha256"] or spec.get(
            "initial_condition"
        ) != {"sha256": report["conditions_sha256"], "verification": verification}:
            raise ValueError("Initial condition proof changed")
        verify_start(verification, runtime["initial_snapshot"])
        _, chosen = read_json(selection, 16 * 1024)
        final_path = Path(chosen["artifact_path"])
        if not final_path.is_absolute():
            final_path = selection.parent / final_path
        final_raw, final_evidence = read_json(final_path, MAX_ARTIFACT_BYTES)
        if (
            hashlib.sha256(final_raw).hexdigest() != chosen["sha256"]
            or final_evidence["binding"] != conditions["binding_record"]["config"]
        ):
            raise ValueError("Final run binding differs from the initial condition proof")
        attestation["initial_conditions_verified"] = True
        attestation["condition_scope"] = verification["scope"]
        if case.get("events"):
            if (
                any(
                    e["kind"] in {"delivery_notification", "notification_replay"}
                    for e in case["events"]
                )
                and final_evidence["condition_events"].get("clock_started_at")
                != conditions["binding_record"]["started_at"]
            ):
                raise ValueError("Notification clock anchor differs from the initial raw binding")
            event_review = verify_events(
                final_evidence["condition_events"],
                case,
                final_evidence["binding"],
                verification["capture_end_tick"],
                final_evidence["captured_at_tick"],
            )
            end = runtime.get("event_execution_end")
            event_review["within_execution"] = (
                bool(end)
                and end["run_id"] == runtime["run_id"]
                and all(
                    runtime["initial_snapshot"]["tick"]
                    <= e["begin_tick"]
                    <= e["end_tick"]
                    <= end["tick"]
                    for e in event_review["events"]
                )
            )
            if not event_review["within_execution"]:
                event_review["status"] = "INCOMPLETE"
            response_events = [
                e for e in event_review["events"] if e.get("kind") == "payment_response_delay"
            ]
            if response_events:
                from rehearsal.evaluation.response_conditions import timeout_observed

                event_review["client_timeouts_verified"] = all(
                    timeout_observed(
                        e, runtime["run_id"], runtime.get("payment_transport_events", [])
                    )
                    for e in response_events
                )
                if not event_review["client_timeouts_verified"]:
                    event_review["status"] = "INCOMPLETE"
            attestation["event_review"] = event_review
            attestation["condition_scope"] = event_review["scope"]
    elif spec.get("initial_condition") is not None:
        raise ValueError("Initial condition proof omitted")
    return attestation


def settle(directory: Path, cell_id: str, selection: Path) -> Json:
    manifest = manifest_for(directory)
    cell = selected(directory, manifest, cell_id)
    path = directory / "runs" / cell_id
    report: Json = json.loads((path / "report.json").read_text())
    if cell["status"] != "RUNNING" or report["status"] not in {
        "AWAITING_EVIDENCE",
        "EXTERNAL_RUNNING",
    }:
        raise ValueError("A completed runtime awaiting evidence is required")
    # A sealed HTTP report proves that runner finished its invocation. A phase label,
    # PID file or elapsed time alone cannot release the reservation or trigger a retry.
    runtime = json.loads((path / "execution/report.json").read_text())
    actual_usage = reopen(
        path / "learning",
        batch.settings_from(manifest["settings"]),
        manifest["scope"],
        cell["method"],
    ).report()
    if runtime["usage"] != actual_usage:
        raise ValueError("External durable usage differs from the sealed runtime")
    report.update(total_usage=actual_usage, runtime_status=runtime["runtime_status"])
    verdict = review_result(path, manifest, cell, selection, report_override=report)
    if verdict["evidence_review"]["status"] != "VERIFIED":
        raise ValueError("Independent external evidence is not verified")
    # Copy only the selected raw artifact, never credentials or the session directory.
    chosen = json.loads(selection.read_text())
    artifact = Path(chosen["artifact_path"])
    if not artifact.is_absolute():
        artifact = selection.parent / artifact
    raw = artifact.read_bytes()
    if hashlib.sha256(raw).hexdigest() != chosen["sha256"]:
        raise ValueError("External evidence changed before retention")
    (path / "external-evidence.json").write_bytes(raw)
    chosen["artifact_path"] = "external-evidence.json"
    batch.write(path / "selection.json", chosen)
    verdict = review_result(path, manifest, cell, path / "selection.json", report_override=report)
    batch.write(path / "attestation.json", verdict)
    report.update(
        status="EXTERNAL_VERIFIED" if verdict["success"] else "EXTERNAL_INCOMPLETE",
        external_transaction_verified=verdict["success"],
        condition_alignment_verified=verdict.get("initial_conditions_verified", False)
        and verdict.get("event_review", {"status": "VERIFIED"})["status"] == "VERIFIED",
        condition_note=verdict.get("condition_scope", "Supplier conditions unverified"),
    )
    batch.write(path / "report.json", report)
    batch.finish(directory, cell, report)
    return summarize(directory)


def summarize(directory: Path) -> Json:
    manifest = manifest_for(directory)
    records = batch.rows(directory, manifest)
    cells = []
    for row in records:
        cell = {
            "id": row["id"],
            "method": row["method"],
            "status": row["status"],
            "recorded_micro_usd": row["recorded"],
            "held_micro_usd": row["reserved"],
            "usage_resolved": bool(row["usage_resolved"]),
            "external_transaction_verified": False,
            "condition_alignment_verified": False,
        }
        if "external_reactions" in manifest:
            cell.update(
                reaction_settings=manifest["external_reactions"][row["method"]],
                reaction_execution_verified=False,
            )
        path = directory / "runs" / row["id"]
        if row["status"] != "NOT_RUN":
            try:
                report: Json = json.loads((path / "report.json").read_text())
                check_spec(path, manifest, row, report)
                cell["status"] = report["status"]
                if row["status"] == "FINISHED":
                    if batch.artifact_hashes(path) != json.loads(row["artifact_hashes"]):
                        raise ValueError("Retained external artifacts changed")
                    usage = report["total_usage"]
                    resolved = bool(usage) and usage.get("all_usage_recorded") is True
                    held = (
                        0
                        if resolved
                        else max(
                            (
                                0
                                if row["method"] == "B0"
                                else manifest["settings"]["budget_micro_usd"]
                            )
                            - row["recorded"],
                            0,
                        )
                    )
                    if (
                        usage.get("recorded_micro_usd", 0) != row["recorded"]
                        or resolved != bool(row["usage_resolved"])
                        or row["reserved"] != held
                    ):
                        raise ValueError("Durable external cost changed")
                    if report["status"] in {"EXTERNAL_VERIFIED", "EXTERNAL_INCOMPLETE"}:
                        verdict = review_result(path, manifest, row, path / "selection.json")
                        cell["external_transaction_verified"] = verdict["success"]
                        if "external_reactions" in manifest:
                            cell["reaction_execution_verified"] = verdict[
                                "reaction_execution_verified"
                            ]
                        cell["condition_alignment_verified"] = (
                            verdict.get("initial_conditions_verified", False)
                            and verdict.get("event_review", {"status": "VERIFIED"})["status"]
                            == "VERIFIED"
                        )
            except (OSError, ValueError, KeyError, TypeError, IndexError):
                cell.update(status="INVALID_EVIDENCE", external_transaction_verified=False)
                if "external_reactions" in manifest:
                    cell["reaction_execution_verified"] = False
        cells.append(cell)
    return {
        **(
            {"external_reactions": manifest["external_reactions"]}
            if "external_reactions" in manifest
            else {}
        ),
        "batch_id": manifest["id"],
        "scope": manifest["scope"],
        "planned": len(cells),
        "cells": cells,
        "status_counts": dict(Counter(c["status"] for c in cells)),
        "recorded_micro_usd": sum(r["recorded"] for r in records),
        "held_micro_usd": sum(r["reserved"] for r in records),
        "batch_budget_micro_usd": manifest["batch_budget_micro_usd"],
        "model_efficacy_verified": False,
        "held_out_evaluation_verified": False,
        "methods": {
            m: {
                "planned": sum(c["method"] == m for c in cells),
                "transaction_verified": sum(
                    c["method"] == m and c["external_transaction_verified"] for c in cells
                ),
                "condition_verified": sum(
                    c["method"] == m and c["condition_alignment_verified"] for c in cells
                ),
                **(
                    {
                        "reaction_execution_verified": sum(
                            c["method"] == m and c["reaction_execution_verified"] for c in cells
                        )
                    }
                    if "external_reactions" in manifest
                    else {}
                ),
            }
            for m in manifest["methods"]
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--learn", type=Path)
    modes.add_argument("--execute", type=Path)
    modes.add_argument("--settle", type=Path)
    modes.add_argument("--report", type=Path)
    parser.add_argument("--cell")
    parser.add_argument("--buyer-config", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--conditions", type=Path)
    parser.add_argument("--batch-budget-usd")
    parser.add_argument("--cases", type=Path, help="Explicit training/cases JSON")
    parser.add_argument(
        "--max-replans", type=int, help="Prepare identical model-arm reactions (1..32)"
    )
    args = parser.parse_args()
    if args.max_replans is not None and not args.prepare:
        parser.error("--max-replans is frozen at --prepare; execution cannot override it")
    if args.report:
        print(json.dumps(summarize(args.report), indent=2))
        return 0
    os.umask(0o077)
    if args.prepare:
        if not args.cases:
            parser.error("--prepare requires an explicit --cases JSON")
        try:
            settings = read_settings(ROOT)
        except ValueError as exc:
            print(str(exc))
            return 2
        amount = Decimal(args.batch_budget_usd or "0")
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Explicit positive total model budget required")
        dataset = json.loads(args.cases.read_text())
        training, cases = dataset["training"], dataset["cases"]
        for case in cases.values():
            validate_case(case)
        directory = ROOT / ".local/evaluation" / identifier("external")
        batch.prepare(
            directory,
            training,
            cases,
            1,
            settings,
            int(amount * 1000000),
            "live-model",
            evaluation_environment="external-medusa",
            external_reactions=ReactionSettings(args.max_replans)
            if args.max_replans is not None
            else None,
        )
        print(f"Prepared external roster: {directory}; no HTTP/AWS/model call.")
        return 0
    if not args.cell:
        parser.error("An explicit --cell is required")
    if args.settle:
        if not args.selection:
            parser.error("--settle requires --selection")
        print(json.dumps(settle(args.settle, args.cell, args.selection), indent=2))
        return 0
    directory = args.learn or args.execute
    manifest = manifest_for(directory, execution=True)
    if manifest["scope"] != "live-model":
        raise ValueError("Paid CLI requires a live-model roster")
    settings = batch.settings_from(manifest["settings"])
    if asdict(read_settings(ROOT)) != manifest["settings"]:
        raise ValueError("Current settings differ from the frozen roster")
    if args.learn:
        result = learn(directory, args.cell, lambda k, p: bedrock_model(settings))
    else:
        if not args.buyer_config:
            parser.error("--execute requires --buyer-config")
        config = configuration(args.buyer_config)
        cell_path = directory / "runs" / args.cell
        if digest(Path(config["policy_path"])) != digest(cell_path / "policy.json"):
            raise ValueError("Session policy differs from the selected batch cell")
        with_client = OperatingClient(
            "http://127.0.0.1:18001", config["run_id"], config["buyer_token"]
        )
        try:
            result = execute(
                directory,
                args.cell,
                None
                if selected(directory, manifest, args.cell)["method"] == "B0"
                else bedrock_model(settings),
                with_client,
                condition_path=args.conditions,
            )
        finally:
            with_client.close()
    print(f"External cell: {result['status']}; {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
