"""Frozen known-case pilot roster and B0 runs; missing model arms remain explicit.

This does not implement B2/B3 evaluation or turn SDK fixtures into model results.
Every planned cell remains in the report, including absent/corrupt/unfinished runs.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from rehearsal.agents.executor import purchasing_tools
from rehearsal.evaluation.verifier import verify, verify_export
from rehearsal.experiments.baseline import ToolPort, run_baseline
from rehearsal.experiments.frozen import freeze
from rehearsal.experiments.policy import Policy
from rehearsal.world import World
from rehearsal.world.storage import Json, canonical, identifier

METHODS = ("B0", "B1", "B2", "B3")
SOURCES = (
    "src/rehearsal/evaluation/pilot.py",
    "src/rehearsal/evaluation/verifier.py",
    "src/rehearsal/experiments/baseline.py",
    "src/rehearsal/experiments/frozen.py",
    "src/rehearsal/experiments/policy.py",
    "src/rehearsal/agents/executor.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def save(path: Path, value: Json) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def known_cases(root: Path) -> dict[str, Json]:
    normal = json.loads((root / "scenarios/normal-v1.json").read_text())
    cases = {name: deepcopy(normal) for name in ("normal", "higher-price", "partial", "impossible")}
    cases["higher-price"]["suppliers"]["A"]["items"]["tent"]["price"] = 100
    for supplier in cases["partial"]["suppliers"]:
        for item in ("tent", "light"):
            if (supplier, item) not in {("A", "tent"), ("B", "light")}:
                cases["partial"]["suppliers"][supplier]["items"][item]["stock"] = 0
    for supplier in cases["impossible"]["suppliers"].values():
        supplier["items"]["tent"]["stock"] = 0
    cases["supplier-prose"] = json.loads(
        (root / "scenarios/untrusted-supplier-v1.json").read_text()
    )
    for name, scenario in cases.items():
        scenario["scenario_version"] = f"known-pilot-{name}-v1"
    return cases


def prepare(directory: Path, root: Path) -> Json:
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    frozen = freeze(Policy(), directory / "policy.json", root)
    cases = known_cases(root)
    plan: Json = {
        "schema": "rehearsal-known-pilot-v1",
        "scope": "known-cases-not-held-out-or-model-efficacy",
        "cases": cases,
        "methods": list(METHODS),
        "repeats": 1,
        "planned_cells": len(cases) * len(METHODS),
        "limits": {
            "max_tool_calls": 80,
            "max_model_calls": 32,
            "max_total_tokens": 100000,
            "max_seconds": 180,
        },
        "policy_sha256": digest(directory / "policy.json"),
        "frozen_policy_id": frozen.identifier,
        "source_hashes": {name: digest(root / name) for name in SOURCES},
        "model_rates_and_spend_authorized": False,
        "case_partition": "known-pilot-only",
    }
    plan["id"] = "pilot-" + fingerprint(plan)
    with (directory / "plan.json").open("x") as output:
        output.write(json.dumps(plan, indent=2) + "\n")
    return plan


def run_b0(directory: Path, root: Path) -> Json:
    from rehearsal.experiments.frozen import FrozenPolicy

    plan = load_plan(directory)
    if any(digest(root / name) != expected for name, expected in plan["source_hashes"].items()):
        raise ValueError("Pilot execution sources changed after freeze")
    frozen = FrozenPolicy.load(directory / "policy.json", root)
    for name, scenario in plan["cases"].items():
        slot = directory / f"{name}-B0"
        slot.mkdir(mode=0o700)  # Never overwrite or silently retry an existing cell.
        run_id = name + "-B0"
        record: Json = {
            "plan_id": plan["id"],
            "case": name,
            "method": "B0",
            "run_id": run_id,
            "scope": "B0-fixed-rule-not-model",
            "execution_status": "STARTED",
            "scenario_sha256": fingerprint(scenario),
            "frozen_id": frozen.identifier,
            "model_calls": 0,
            "model_cost_micro_usd": 0,
        }
        save(slot / "result.json", record)
        try:
            world = World(slot)
            world.create_run(run_id, scenario, policy_version=frozen.identifier)
            port = ToolPort(
                purchasing_tools(world, run_id),
                plan["limits"]["max_tool_calls"],
                plan["limits"]["max_seconds"],
            )
            result = run_baseline(frozen, port, run_id)
            save(slot / "execution.json", result)
            record.update(
                execution_status=result["status"],
                reason=result["reason"],
                tool_calls=len(port.trace),
                execution_sha256=digest(slot / "execution.json"),
            )
            verdict = verify(slot, run_id, scenario, export_to=slot / "evidence.json")
            record.update(verdict=verdict.as_dict(), evidence_sha256=digest(slot / "evidence.json"))
        except Exception as exc:
            record.update(execution_status="ERROR", error_type=type(exc).__name__)
        finally:
            save(slot / "result.json", record)
    report = summarize(directory)
    save(directory / "report.json", report)
    return report


def load_plan(directory: Path) -> Json:
    plan: Json = json.loads((directory / "plan.json").read_text())
    if (
        plan["schema"] != "rehearsal-known-pilot-v1"
        or plan["id"] != "pilot-" + fingerprint({k: v for k, v in plan.items() if k != "id"})
        or plan["methods"] != list(METHODS)
        or plan["planned_cells"] != len(plan["cases"]) * len(METHODS)
        or digest(directory / "policy.json") != plan["policy_sha256"]
    ):
        raise ValueError("Pilot plan or policy integrity mismatch")
    return plan


def summarize(directory: Path) -> Json:
    """Recompute B0 ledger verdicts. Model cells cannot be imported as B0 successes."""
    plan = load_plan(directory)
    cells: list[Json] = []
    for name, scenario in plan["cases"].items():
        for method in METHODS:
            slot = directory / f"{name}-{method}"
            cell: Json = {
                "case": name,
                "method": method,
                "status": "NOT_RUN",
                "goal_complete": False,
                "spent": None,
                "reserved": None,
                "model_calls": None,
                "model_cost_micro_usd": None,
                "tool_calls": None,
            }
            cells.append(cell)
            if not (slot / "result.json").exists():
                cell["reason"] = {
                    "B0": "NO_EXECUTION_RECORD",
                    "B1": "REAL_MODEL_RUN_PENDING",
                    "B2": "SIMULATION_EXECUTOR_PENDING",
                    "B3": "FROZEN_POLICY_EVALUATION_PENDING",
                }[method]
                continue
            cell["status"] = "INVALID_EVIDENCE"
            try:
                record = json.loads((slot / "result.json").read_text())
                if (
                    method != "B0"
                    or record["scope"] != "B0-fixed-rule-not-model"
                    or record["plan_id"] != plan["id"]
                    or record["case"] != name
                    or record["method"] != method
                    or record["run_id"] != f"{name}-{method}"
                    or record["scenario_sha256"] != fingerprint(scenario)
                    or record["frozen_id"] != plan["frozen_policy_id"]
                    or record["model_calls"] != 0
                    or record["model_cost_micro_usd"] != 0
                ):
                    raise ValueError("Cell identity/accounting mismatch")
                cell.update(model_calls=0, model_cost_micro_usd=0)
                if record["execution_status"] in {"STARTED", "ERROR"}:
                    cell.update(status=record["execution_status"], reason=record.get("error_type"))
                    continue
                if (
                    digest(slot / "evidence.json") != record["evidence_sha256"]
                    or digest(slot / "execution.json") != record["execution_sha256"]
                ):
                    raise ValueError("Cell artifact hash mismatch")
                evidence = json.loads((slot / "evidence.json").read_text())
                execution = json.loads((slot / "execution.json").read_text())
                if (
                    evidence["run_id"] != record["run_id"]
                    or evidence["scenario"] != scenario
                    or evidence["tables"]["runs"][0]["id"] != record["run_id"]
                    or json.loads(evidence["tables"]["runs"][0]["metadata"])["policy_version"]
                    != plan["frozen_policy_id"]
                    or execution["frozen_id"] != plan["frozen_policy_id"]
                    or execution["status"] != record["execution_status"]
                    or record["tool_calls"] != len(execution["trace"])
                    or len(execution["trace"]) > plan["limits"]["max_tool_calls"]
                ):
                    raise ValueError("Cell execution contract mismatch")
                verdict = verify_export(slot / "evidence.json").as_dict()
                if verdict != record["verdict"]:
                    raise ValueError("Saved verdict disagrees with independent evidence")
                cell.update(
                    status=verdict["status"],
                    execution_status=record["execution_status"],
                    goal_complete=verdict["status"] == "COMPLETE",
                    spent=verdict["spent"],
                    reserved=verdict["reserved"],
                    reason=record.get("reason"),
                    tool_calls=record["tool_calls"],
                )
            except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
                cell.update(
                    status="INVALID_EVIDENCE",
                    reason=type(exc).__name__,
                    model_calls=None,
                    model_cost_micro_usd=None,
                )
    return {
        "plan_id": plan["id"],
        "scope": plan["scope"],
        "cells": cells,
        "planned_cells": plan["planned_cells"],
        "status_counts": dict(Counter(c["status"] for c in cells)),
        "methods": {
            method: {
                "planned": len(plan["cases"]),
                "execution_records": sum(
                    c["method"] == method and c["status"] != "NOT_RUN" for c in cells
                ),
                "independent_complete": sum(
                    c["method"] == method and c["goal_complete"] for c in cells
                ),
                "status_counts": dict(Counter(c["status"] for c in cells if c["method"] == method)),
                "spent_observed": sum(c["spent"] or 0 for c in cells if c["method"] == method),
                "spending_unavailable_cells": sum(
                    c["method"] == method and c["spent"] is None for c in cells
                ),
            }
            for method in METHODS
        },
        "comparison_complete": all(
            c["status"] not in {"NOT_RUN", "STARTED", "INVALID_EVIDENCE"} for c in cells
        ),
        "model_efficacy_verified": False,
        "held_out_evaluation_verified": False,
        "developer_time_savings_verified": False,
    }


def main() -> None:
    os.umask(0o077)
    root = Path(__file__).resolve().parents[3]
    directory = root / ".local/evaluation" / identifier("pilot")
    prepare(directory, root)
    report = run_b0(directory, root)
    print(f"Known B0 pilot: {report['status_counts']}; evidence {directory}")
    actual = {c["case"]: (c["status"], c["spent"]) for c in report["cells"] if c["method"] == "B0"}
    expected = {
        "normal": ("COMPLETE", 310),
        "higher-price": ("COMPLETE", 380),
        "partial": ("COMPLETE", 360),
        "impossible": ("INCOMPLETE", 0),
        "supplier-prose": ("COMPLETE", 310),
    }
    if actual != expected:
        raise RuntimeError("Known pilot outcomes differ; retained failures require inspection")
    print("B1/B2/B3 remain unexecuted; no model comparison, held-out or user-efficiency claim.")


if __name__ == "__main__":
    main()
