"""One explicit comparison-arm-to-HTTP handoff retaining the original durable admission budget.

The frozen policy seals historical learning artifacts. A durable one-slot roster retains
interrupted and zero-call external attempts; it does not authorize automatic retries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from rehearsal.agents.metering import UsageLedger
from rehearsal.agents.runner import ModelSettings, read_settings
from rehearsal.experiments.frozen import FrozenPolicy, freeze
from rehearsal.experiments.model_experiment import validate_shared_ledger
from rehearsal.experiments.policy import Policy
from rehearsal.world.storage import ContractError, Json

ROOT = Path(__file__).resolve().parents[3]
ROWS = ("calls", "tool_admissions", "admission_rejections")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifacts(directory: Path) -> dict[str, Path]:
    return {
        str(p.relative_to(directory)): p
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p.suffix in {".json", ".txt"}
    }


def reopen(directory: Path, settings: ModelSettings, scope: str, method: str = "B3") -> UsageLedger:
    if method not in {"B0", "B1", "B2", "B3"}:
        raise ValueError("Invalid comparison method")
    path = directory / "usage.sqlite3"
    # Read-only inspection first: a missing/empty/wrong ledger must never become a new budget.
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        found = db.execute("SELECT run_id FROM model_runs").fetchall()
        if found != [(method.lower() + "-session",)]:
            raise ContractError(f"{method}_USAGE_LEDGER_REQUIRED")
    return UsageLedger(
        path,
        method.lower() + "-session",
        settings.model_id,
        settings.rates,
        settings.budget_micro_usd,
        settings.input_limit,
        settings.output_limit,
        scope,
        max_calls=settings.max_model_calls,
        max_total_tokens=settings.max_total_tokens,
        max_tool_calls=settings.max_tool_calls,
    )


def learning_inputs(directory: Path, method: str = "B3") -> tuple[Json, Policy, dict[str, Path]]:
    if method not in {"B0", "B1", "B2", "B3"}:
        raise ValueError("Invalid comparison method")
    report = json.loads((directory / "report.json").read_text())
    if method in {"B0", "B1"}:
        if (
            report.get("method") != method
            or report["status"] != "NOT_REQUIRED"
            or any(report["usage"][key] for key in ROWS)
            or report["policy"] != asdict(Policy())
        ):
            raise ContractError("UNLEARNED_PREPARATION_CHANGED")
        if any(sha(ROOT / p) != expected for p, expected in report["source_hashes"].items()):
            raise ContractError("PREPARATION_SOURCE_CHANGED")
        return report, Policy(), artifacts(directory)
    if (
        report["status"] not in {"CANDIDATE_EVALUATED_NOT_PROMOTED", "NO_CHANGE"}
        or not report["parent_unchanged"]
        or not report["usage"]["calls"]
        or not report["usage"]["all_usage_recorded"]
    ):
        raise ContractError(f"{method}_LEARNING_NOT_READY")
    if not report["source_hashes"] or any(
        sha(ROOT / p) != expected for p, expected in report["source_hashes"].items()
    ):
        raise ContractError(f"{method}_LEARNING_SOURCE_CHANGED")
    if method == "B3" and (
        sha(directory / "initial/experiment.json") != report["initial_artifact_sha256"]
        or sha(directory / "review/report.json") != report["review_report_sha256"]
    ):
        raise ContractError(f"{method}_LEARNING_ARTIFACT_CHANGED")
    selection = (
        json.loads((directory / "review/report.json").read_text()) if method == "B3" else report
    )
    policy = Policy.parse(selection.get("candidate_policy") or selection["initial_policy"])
    return report, policy, artifacts(directory)


def prepare(
    directory: Path, output: Path, settings: ModelSettings, scope: str, method: str = "B3"
) -> FrozenPolicy:
    if output.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Keep frozen handoff outside immutable learning artifacts")
    report, policy, paths = learning_inputs(directory, method)
    ledger = reopen(directory, settings, scope, method)
    validate_shared_ledger(ledger, settings, scope)
    if ledger.report() != report["usage"]:
        raise ContractError(f"{method}_LEARNING_USAGE_CHANGED")
    return freeze(policy, output, ROOT, paths)


class BudgetCarryover:
    def __init__(
        self,
        directory: Path,
        policy_path: Path,
        settings: ModelSettings,
        scope: str,
        method: str = "B3",
    ):
        self.method = method
        self.directory, self.policy_path = directory.resolve(), policy_path.resolve()
        self.policy_sha = sha(policy_path)
        self.frozen = FrozenPolicy.load(policy_path, ROOT)
        manifest = json.loads(policy_path.read_text())
        report, policy, paths = learning_inputs(directory, method)
        self.hashes = {name: sha(p) for name, p in paths.items()}
        if self.hashes != manifest["learning_evidence"] or policy != self.frozen.policy:
            raise ContractError(f"{self.method}_FROZEN_LEARNING_MISMATCH")
        self.baseline = report["usage"]
        self.ledger = reopen(directory, settings, scope, method)
        validate_shared_ledger(self.ledger, settings, scope)
        self.execution_id: str | None = None
        self.check()
        if self.accounting()["attempted_external_runs"]:
            raise ContractError(f"{self.method}_EXTERNAL_ATTEMPT_ALREADY_RETAINED")

    def check(self) -> None:
        self.frozen.check()
        if (
            sha(self.policy_path) != self.policy_sha
            or {name: sha(p) for name, p in artifacts(self.directory).items()} != self.hashes
        ):
            raise ContractError(f"{self.method}_LEARNING_ARTIFACT_CHANGED")
        current = self.ledger.report()
        if self.method == "B0" and current["calls"]:
            raise ContractError("B0_MODEL_CALL_FORBIDDEN")
        for key in ROWS:
            original = self.baseline[key]
            if current[key][: len(original)] != original or any(
                r["role"] != "buyer_evaluation" or r["execution_id"] != self.execution_id
                for r in current[key][len(original) :]
            ):
                raise ContractError(f"{self.method}_LEARNING_USAGE_CHANGED")
        if not current["all_usage_recorded"]:
            raise ContractError(f"{self.method}_USAGE_UNRESOLVED")

    def claim(self, execution_id: str, output: Path) -> None:
        self.check()
        if any(r["execution_id"] == execution_id for key in ROWS for r in self.baseline[key]):
            raise ContractError(f"{self.method}_EXECUTION_ID_REUSED")
        with self.ledger.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS http_transfer ("
                "session_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, "
                "directory TEXT NOT NULL, frozen_id TEXT NOT NULL, state TEXT NOT NULL)"
            )
            try:
                db.execute(
                    "INSERT INTO http_transfer VALUES(?,?,?,?,?)",
                    (
                        self.ledger.run_id,
                        execution_id,
                        str(output.resolve()),
                        self.frozen.identifier,
                        "STARTED",
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ContractError(f"{self.method}_EXTERNAL_ATTEMPT_ALREADY_RETAINED") from exc
        self.execution_id = execution_id

    def finish(self, status: str) -> None:
        with self.ledger.connect() as db:
            db.execute(
                "UPDATE http_transfer SET state=? WHERE session_id=? AND execution_id=?",
                (status, self.ledger.run_id, self.execution_id),
            )

    def accounting(self) -> Json:
        with self.ledger.connect() as db:
            exists = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='http_transfer'"
            ).fetchone()
            row = db.execute("SELECT * FROM http_transfer").fetchone() if exists else None
        return {
            "method": self.method,
            "planned_external_runs": 1,
            "attempted_external_runs": int(row is not None),
            "external_state": dict(row) if row else {"state": "NOT_RUN"},
            "learning_usage": self.baseline,
            "total_usage": self.ledger.report(),
            "model_efficacy_verified": False,
            "held_out_evaluation_verified": False,
        }


# Existing B3 callers keep the same default and explicit receipt checks.
B3Carryover = BudgetCarryover


def prepare_unlearned(directory: Path, settings: ModelSettings, scope: str, method: str) -> Json:
    if method not in {"B0", "B1"}:
        raise ValueError("Only B0/B1 skip learning")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    ledger = UsageLedger(
        directory / "usage.sqlite3",
        method.lower() + "-session",
        settings.model_id,
        settings.rates,
        settings.budget_micro_usd,
        settings.input_limit,
        settings.output_limit,
        scope,
        max_calls=settings.max_model_calls,
        max_total_tokens=settings.max_total_tokens,
        max_tool_calls=settings.max_tool_calls,
    )
    report: Json = {
        "method": method,
        "status": "NOT_REQUIRED",
        "scope": scope,
        "policy": asdict(Policy()),
        "usage": ledger.report(),
        "source_hashes": {str(Path(__file__).relative_to(ROOT)): sha(Path(__file__))},
        "model_efficacy_verified": False,
    }
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--policy-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        settings = read_settings(ROOT)
    except ValueError as exc:
        print(str(exc))
        return 2
    frozen = prepare(args.learning, args.policy_output, settings, "live-model")
    print(f"Prepared {frozen.identifier}; no HTTP/AWS/model invocation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
