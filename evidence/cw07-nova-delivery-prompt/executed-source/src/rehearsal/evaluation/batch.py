"""Frozen evaluation roster, durable admissions and independent full-denominator reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from strands.models.model import Model

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings, bedrock_model, read_settings
from rehearsal.commerce.reaction import ReactionSettings
from rehearsal.evaluation.frozen_run import METHODS, condition_id, digest, fixture_factory, run_cell
from rehearsal.evaluation.verifier import verify_export
from rehearsal.experiments.policy import Policy
from rehearsal.world.storage import Json, canonical, identifier

SCHEMA = """
CREATE TABLE cells (
 id TEXT PRIMARY KEY, case_id TEXT NOT NULL, method TEXT NOT NULL, repeat INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('NOT_RUN','RUNNING','FINISHED')),
 reserved INTEGER NOT NULL DEFAULT 0, recorded INTEGER NOT NULL DEFAULT 0,
 usage_resolved INTEGER NOT NULL DEFAULT 0, result_status TEXT, artifact_hashes TEXT,
 started_at TEXT, finished_at TEXT
);
"""


def write(path: Path, value: Json) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def settings_from(value: Json) -> ModelSettings:
    return ModelSettings(**(value | {"rates": RateCard(**value["rates"])}))


def validate_reactions(manifest: Json) -> None:
    if "external_reactions" not in manifest:
        return  # Historical manifests specify the original non-reactive execution.
    policy = manifest["external_reactions"]
    if (
        manifest.get("evaluation_environment") != "external-medusa"
        or not isinstance(policy, dict)
        or set(policy) != set(METHODS)
        or policy["B0"] is not None
    ):
        raise ValueError("Invalid external reaction policy")
    for value in policy.values():
        if value is not None:
            if not isinstance(value, dict) or set(value) != {"max_replans"}:
                raise ValueError("Explicit bounded reaction settings required")
            ReactionSettings(**value)
    if len({canonical(policy[m]) for m in ("B1", "B2", "B3")}) != 1:
        raise ValueError("Model comparison arms require identical reaction settings")


def reaction_for(manifest: Json, method: str) -> ReactionSettings | None:
    validate_reactions(manifest)
    if method not in METHODS:
        raise ValueError("Unknown reaction method")
    value = manifest.get("external_reactions", {}).get(method)
    return ReactionSettings(**value) if value is not None else None


def prepare(
    directory: Path,
    training: Json,
    cases: dict[str, Json],
    repeats: int,
    settings: ModelSettings,
    batch_budget: int,
    scope: str,
    *,
    evaluation_environment: str = "practice",
    external_reactions: ReactionSettings | None = None,
) -> Json:
    if evaluation_environment not in {"practice", "external-medusa"}:
        raise ValueError("Invalid evaluation environment")
    if external_reactions is not None and (
        not isinstance(external_reactions, ReactionSettings)
        or evaluation_environment != "external-medusa"
    ):
        raise ValueError("Reaction settings require external Medusa evaluation")
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError("Repeats must be 1 through 10")
    if type(batch_budget) is not int or batch_budget <= 0:
        raise ValueError("Explicit positive batch budget required")
    if (
        not cases
        or len(cases) > 100
        or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", k) for k in cases)
    ):
        raise ValueError("Invalid evaluation cases")
    fingerprints = [condition_id(c) for c in cases.values()]
    if len(set(fingerprints)) != len(cases) or condition_id(training) in fingerprints:
        raise ValueError("Evaluation conditions duplicate training or another case")
    if scope not in {"offline-scripted-model", "live-model"}:
        raise ValueError("Invalid evaluation scope")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    root = Path(__file__).resolve().parents[3]
    cells = [
        {"id": f"{case}-{method}-r{n}", "case_id": case, "method": method, "repeat": n}
        for case in cases
        for n in range(1, repeats + 1)
        for method in METHODS
    ]
    manifest: Json = {
        "schema": "rehearsal-evaluation-batch-v1",
        "scope": scope,
        "dataset_kind": "explicit-known-conditions",
        "evaluation_environment": evaluation_environment,
        "held_out": False,
        "training": training,
        "cases": cases,
        "repeats": repeats,
        "methods": list(METHODS),
        "cells": cells,
        "planned": len(cells),
        "settings": asdict(settings),
        "batch_budget_micro_usd": batch_budget,
        "source_hashes": {
            str(p.relative_to(root)): digest(p)
            for p in sorted((root / "src/rehearsal").rglob("*.py"))
        },
    }
    if evaluation_environment == "external-medusa":
        manifest["external_reactions"] = {
            m: asdict(external_reactions) if external_reactions and m != "B0" else None
            for m in METHODS
        }
    validate_reactions(manifest)
    manifest["id"] = "batch-" + hashlib.sha256(canonical(manifest).encode()).hexdigest()
    write(directory / "manifest.json", manifest)
    with sqlite3.connect(directory / "batch.sqlite3") as db:
        db.executescript(SCHEMA)
        db.executemany(
            "INSERT INTO cells(id,case_id,method,repeat,status) VALUES(?,?,?,?,'NOT_RUN')",
            [(c["id"], c["case_id"], c["method"], c["repeat"]) for c in cells],
        )
    return manifest


def load(directory: Path) -> Json:
    value: Json = json.loads((directory / "manifest.json").read_text())
    if (
        value.get("evaluation_environment", "practice") not in {"practice", "external-medusa"}
        or type(value.get("repeats")) is not int
        or not 1 <= value["repeats"] <= 10
        or not isinstance(value.get("cases"), dict)
        or not 1 <= len(value["cases"]) <= 100
        or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", k) for k in value["cases"])
        or value.get("scope") not in {"offline-scripted-model", "live-model"}
        or type(value.get("batch_budget_micro_usd")) is not int
        or value["batch_budget_micro_usd"] <= 0
    ):
        raise ValueError("Invalid batch manifest constraints")
    settings_from(value["settings"])
    validate_reactions(value)
    fingerprints = [condition_id(c) for c in value["cases"].values()]
    if (
        len(set(fingerprints)) != len(fingerprints)
        or condition_id(value["training"]) in fingerprints
    ):
        raise ValueError("Batch condition partition mismatch")
    expected = (
        "batch-"
        + hashlib.sha256(
            canonical({k: v for k, v in value.items() if k != "id"}).encode()
        ).hexdigest()
    )
    expected_cells = [
        {"id": f"{case}-{method}-r{n}", "case_id": case, "method": method, "repeat": n}
        for case in value["cases"]
        for n in range(1, value["repeats"] + 1)
        for method in METHODS
    ]
    if (
        value["schema"] != "rehearsal-evaluation-batch-v1"
        or value["id"] != expected
        or value["cells"] != expected_cells
        or value["planned"] != len(expected_cells)
        or value["methods"] != list(METHODS)
    ):
        raise ValueError("Batch manifest integrity mismatch")
    return value


def rows(directory: Path, manifest: Json) -> list[Json]:
    with sqlite3.connect(
        (directory / "batch.sqlite3").resolve().as_uri() + "?mode=ro", uri=True
    ) as db:
        db.row_factory = sqlite3.Row
        result = [dict(r) for r in db.execute("SELECT * FROM cells ORDER BY rowid")]
    if [{k: r[k] for k in ("id", "case_id", "method", "repeat")} for r in result] != manifest[
        "cells"
    ]:
        raise ValueError("Batch roster was changed")
    if any(type(r[k]) is not int or r[k] < 0 for r in result for k in ("reserved", "recorded")):
        raise ValueError("Invalid durable batch cost")
    return result


def claim(
    directory: Path, manifest: Json, cell_id: str | None = None
) -> tuple[Json | None, str | None]:
    records = rows(directory, manifest)
    if cell_id is not None and not any(r["id"] == cell_id for r in records):
        raise ValueError("Unknown batch cell")
    with sqlite3.connect(directory / "batch.sqlite3", timeout=10) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        pending = db.execute("SELECT * FROM cells ORDER BY rowid").fetchall()
        if any(r["status"] == "RUNNING" for r in pending):
            return None, "UNRESOLVED_ATTEMPT"
        if any(r["status"] == "FINISHED" and not r["usage_resolved"] for r in pending):
            return None, "UNRESOLVED_USAGE"
        used = sum(r["recorded"] + r["reserved"] for r in pending)
        row = next(
            (
                r
                for r in pending
                if r["status"] == "NOT_RUN" and (cell_id is None or r["id"] == cell_id)
            ),
            None,
        )
        if row is None:
            return None, None
        reservation = 0 if row["method"] == "B0" else manifest["settings"]["budget_micro_usd"]
        if used + reservation > manifest["batch_budget_micro_usd"]:
            return None, "BATCH_COST_LIMIT"
        db.execute(
            "UPDATE cells SET status='RUNNING',reserved=?,"
            "started_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (reservation, row["id"]),
        )
        return dict(row), None


def artifact_hashes(path: Path) -> dict[str, str]:
    return {
        str(p.relative_to(path)): digest(p)
        for p in sorted(path.rglob("*"))
        if p.is_file() and p.suffix in {".json", ".txt", ".jsonl"}
    }


def finish(directory: Path, cell: Json, result: Json) -> None:
    usage = result.get("total_usage", {})
    recorded = usage.get("recorded_micro_usd", 0)
    resolved = bool(usage) and usage.get("all_usage_recorded") is True
    if type(recorded) is not int or recorded < 0:
        raise ValueError("Invalid recorded batch cost")
    hashes = artifact_hashes(directory / "runs" / cell["id"])
    with sqlite3.connect(directory / "batch.sqlite3") as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT status,reserved,recorded FROM cells WHERE id=?", (cell["id"],)
        ).fetchone()
        if row is None or row[0] != "RUNNING":
            raise ValueError("Attempt not running")
        held = 0 if resolved else max(row[1] + row[2] - recorded, 0)
        db.execute(
            "UPDATE cells SET status='FINISHED',recorded=?,reserved=?,usage_resolved=?,"
            "result_status=?,artifact_hashes=?,"
            "finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (recorded, held, int(resolved), result["status"], json.dumps(hashes), cell["id"]),
        )


def run_pending(
    directory: Path, factory: Callable[[str, Policy], Model], max_cells: int | None = None
) -> Json:
    manifest = load(directory)
    if manifest.get("evaluation_environment", "practice") != "practice":
        raise ValueError("External roster requires the external-batch controller")
    root = Path(__file__).resolve().parents[3]
    allowed = {str(p.relative_to(root)) for p in (root / "src/rehearsal").rglob("*.py")}
    if set(manifest["source_hashes"]) != allowed:
        raise ValueError("Batch source set changed")
    if any(digest(root / p) != sha for p, sha in manifest["source_hashes"].items()):
        raise ValueError("Batch execution source changed")
    if "INVALID_EVIDENCE" in summarize(directory)["status_counts"]:
        raise ValueError("Prior batch evidence is invalid")
    if max_cells is not None and (type(max_cells) is not int or max_cells <= 0):
        raise ValueError("max_cells must be positive")
    completed = 0
    stop = None
    while max_cells is None or completed < max_cells:
        cell, stop = claim(directory, manifest)
        if cell is None:
            break
        path = directory / "runs" / cell["id"]
        started_ns = time.perf_counter_ns()
        try:
            result = run_cell(
                cell["method"],
                factory,
                settings_from(manifest["settings"]),
                path,
                deepcopy(manifest["training"]),
                deepcopy(manifest["cases"][cell["case_id"]]),
                manifest["scope"],
            )
        except Exception as exc:
            # No automatic retry or free-cost assumption when a runner fails to retain usage.
            path.mkdir(parents=True, exist_ok=True)
            result = {"status": "ERROR", "error": type(exc).__name__}
            write(path / "batch-error.json", result)
        finished_ns = time.perf_counter_ns()
        write(
            path / "timing.json",
            {
                "basis": "single-process-monotonic-cell-total",
                "started_ns": started_ns,
                "finished_ns": finished_ns,
                "duration_ns": finished_ns - started_ns,
            },
        )
        finish(directory, cell, result)
        completed += 1
    report = summarize(directory)
    report["stop_reason"] = stop
    write(directory / "report.json", report)
    return report


def audit(directory: Path, manifest: Json, row: Json) -> Json:
    value: Json = {
        "id": row["id"],
        "case": row["case_id"],
        "method": row["method"],
        "repeat": row["repeat"],
        "status": row["status"],
        "goal_complete": False,
        "spent": None,
        "reserved_credits": None,
        "recorded_micro_usd": row["recorded"],
        "unresolved_reserved_micro_usd": row["reserved"],
        "usage_resolved": bool(row["usage_resolved"]),
        "recorded_total_tokens": None,
        "token_usage_complete": False,
        "duration_ns": None,
    }
    if row["status"] != "FINISHED":
        return value
    path = directory / "runs" / row["id"]
    try:
        hashes = json.loads(row["artifact_hashes"])
        if not hashes or artifact_hashes(path) != hashes:
            raise ValueError("Artifacts changed")
        if "timing.json" in hashes:
            timing = json.loads((path / "timing.json").read_text())
            if (
                timing.get("basis") != "single-process-monotonic-cell-total"
                or any(
                    type(timing.get(k)) is not int or timing[k] < 0
                    for k in ("started_ns", "finished_ns", "duration_ns")
                )
                or timing["finished_ns"] - timing["started_ns"] != timing["duration_ns"]
            ):
                raise ValueError("Invalid cell timing")
            value["duration_ns"] = timing["duration_ns"]
        if "batch-error.json" in hashes:
            value.update(
                status="ERROR", reason=json.loads((path / "batch-error.json").read_text())["error"]
            )
            return value
        report = json.loads((path / "report.json").read_text())
        spec = json.loads((path / "spec.json").read_text())
        if (
            report["method"] != row["method"]
            or report["scope"] != manifest["scope"]
            or spec["method"] != row["method"]
            or spec["scope"] != manifest["scope"]
            or spec["settings"] != manifest["settings"]
            or spec["training_condition"] != manifest["training"]
            or spec["evaluation_condition"] != manifest["cases"][row["case_id"]]
            or report["status"] != row["result_status"]
            or report["spec_sha256"] != digest(path / "spec.json")
            or any(
                manifest["source_hashes"].get(name) != sha
                for name, sha in spec["source_hashes"].items()
            )
        ):
            raise ValueError("Cell contract mismatch")
        usage = report.get("total_usage", {})
        rates = RateCard(**manifest["settings"]["rates"])
        measured = sum(
            rates.micro_usd(json.loads(c["usage"]))
            for c in usage.get("calls", [])
            if c["status"] == "RECORDED"
        )
        resolved = bool(usage) and usage.get("all_usage_recorded") is True
        tokens = 0
        for call in usage.get("calls", []):
            if call["status"] == "RECORDED":
                counts = json.loads(call["usage"])
                if set(counts) != {
                    "inputTokens", "outputTokens", "cacheReadInputTokens", "cacheWriteInputTokens"
                } or any(type(n) is not int or n < 0 for n in counts.values()):
                    raise ValueError("Invalid token usage")
                tokens += sum(counts.values())
        if usage.get("recorded_total_tokens", tokens) != tokens:
            raise ValueError("Token total mismatch")
        if (
            measured != row["recorded"]
            or usage.get("recorded_micro_usd", 0) != measured
            or resolved != bool(row["usage_resolved"])
            or (resolved and row["reserved"] != 0)
        ):
            raise ValueError("Usage total mismatch")
        value.update(
            status=report["status"],
            reason=report.get("error"),
            model_calls=len(usage.get("calls", [])),
            tool_calls=report.get("total_tool_calls"),
            recorded_total_tokens=tokens if usage else None,
            token_usage_complete=resolved,
        )
        if report["status"] in {"EVALUATED", "EVALUATION_INCOMPLETE"}:
            evidence = json.loads((path / "evaluation/evidence.json").read_text())
            verdict = verify_export(path / "evaluation/evidence.json").as_dict()
            policy = json.loads((path / "policy.json").read_text())
            if (
                evidence["scenario"] != manifest["cases"][row["case_id"]]
                or verdict != report["verdict"]
                or evidence["run_id"] != "evaluation"
                or policy["id"] != report["frozen_id"]
                or json.loads(evidence["tables"]["runs"][0]["metadata"])["policy_version"]
                != policy["id"]
                or digest(path / "policy.json") != report["frozen_sha256"]
            ):
                raise ValueError("Independent evaluation mismatch")
            value.update(
                goal_complete=verdict["status"] == "COMPLETE",
                spent=verdict["spent"],
                reserved_credits=verdict["reserved"],
                verdict_status=verdict["status"],
            )
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        value.update(
            status="INVALID_EVIDENCE", goal_complete=False, reason=type(exc).__name__,
            recorded_total_tokens=None, token_usage_complete=False, duration_ns=None,
        )
    return value


def summarize(directory: Path) -> Json:
    manifest = load(directory)
    if manifest.get("evaluation_environment", "practice") != "practice":
        raise ValueError("External roster requires the external-batch report")
    records = rows(directory, manifest)
    cells = [audit(directory, manifest, r) for r in records]
    recorded = sum(r["recorded"] for r in records)
    held = sum(r["reserved"] for r in records)
    return {
        "batch_id": manifest["id"],
        "scope": manifest["scope"],
        "held_out_evaluation_verified": False,
        "model_efficacy_verified": False,
        "planned": len(cells),
        "cells": cells,
        "status_counts": dict(Counter(c["status"] for c in cells)),
        "recorded_micro_usd": recorded,
        "unresolved_reserved_micro_usd": held,
        "batch_budget_micro_usd": manifest["batch_budget_micro_usd"],
        "estimated_budget_exceeded": recorded > manifest["batch_budget_micro_usd"],
        "all_cells_resolved": all(
            c["status"] not in {"NOT_RUN", "RUNNING", "INVALID_EVIDENCE"} and c["usage_resolved"]
            for c in cells
        ),
        "methods": {
            method: {
                "planned": sum(c["method"] == method for c in cells),
                "goal_complete": sum(c["method"] == method and c["goal_complete"] for c in cells),
                "status_counts": dict(Counter(c["status"] for c in cells if c["method"] == method)),
                "recorded_micro_usd": sum(
                    c["recorded_micro_usd"] for c in cells if c["method"] == method
                ),
                "spending_unavailable_cells": sum(
                    c["method"] == method and c["spent"] is None for c in cells
                ),
            }
            for method in METHODS
        },
    }


def generated_known_cases(root: Path, count: int = 20) -> tuple[Json, dict[str, Json]]:
    training = json.loads((root / "scenarios/normal-v1.json").read_text())
    cases = {}
    for index in range(count):
        scenario = deepcopy(training)
        scenario["scenario_version"] = f"known-grid-{index + 1:02d}-v1"
        scenario["suppliers"]["A"]["items"]["tent"]["stock"] = 0
        scenario["suppliers"]["B"]["items"]["tent"]["price"] = 70 + 5 * (index % 5)
        scenario["suppliers"]["B"]["lead_ticks"] = 10 + 5 * (index // 5)
        cases[f"case-{index + 1:02d}"] = scenario
    return training, cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--offline-fixture", action="store_true")
    modes.add_argument("--prepare-live", action="store_true")
    modes.add_argument("--execute", type=Path, metavar="BATCH_DIRECTORY")
    modes.add_argument("--report", type=Path, metavar="BATCH_DIRECTORY")
    parser.add_argument("--batch-budget-usd")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.report:
        report = summarize(args.report)
        print(json.dumps(report, indent=2))
        return 0
    if args.execute:
        manifest = load(args.execute)
        if manifest["scope"] != "live-model":
            parser.error("Paid execution requires a live-model batch")
        settings = settings_from(manifest["settings"])
        report = run_pending(args.execute, lambda kind, p: bedrock_model(settings))
        print(report["status_counts"], report["stop_reason"])
        return 0 if report["all_cells_resolved"] else 1
    if args.offline_fixture:
        settings = ModelSettings(
            "offline",
            "offline",
            "offline-evaluation-fixture",
            RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
            100000,
            max_model_calls=48,
            max_tool_calls=48,
        )
        budget = 500000
    else:
        try:
            settings = read_settings(root)
            amount = Decimal(args.batch_budget_usd or "0")
            if not amount.is_finite() or amount <= 0:
                raise ValueError("Explicit finite batch budget required")
            budget = int(amount * 1000000)
        except (ValueError, InvalidOperation) as exc:
            print(str(exc))
            return 2
    os.umask(0o077)
    directory = root / ".local/evaluation" / identifier("batch")
    training, cases = generated_known_cases(root)
    manifest = prepare(
        directory,
        training,
        cases,
        args.repeats,
        settings,
        budget,
        "offline-scripted-model" if args.offline_fixture else "live-model",
    )
    if args.prepare_live:
        print(f"Prepared {manifest['planned']} cells: {directory}; no AWS client or model calls.")
        return 0
    report = run_pending(directory, fixture_factory)
    print(f"Known fixture batch: {report['status_counts']}; {directory}")
    print("No real-model, held-out or review-efficacy claim.")
    return 0 if report["all_cells_resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
