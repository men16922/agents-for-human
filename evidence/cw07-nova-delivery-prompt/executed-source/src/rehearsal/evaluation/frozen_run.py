"""Known-condition learning -> frozen policy -> fresh evaluation with one budget.

Offline runs use deterministic SDK fixtures and never populate the real-model pilot.
A paid invocation is restricted to one explicitly selected arm and one budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from strands.models.model import Model

from rehearsal.agents.executor import purchasing_tools
from rehearsal.agents.metering import RateCard, UsageLedger
from rehearsal.agents.runner import ModelSettings, bedrock_model, execute, read_settings
from rehearsal.evaluation.verifier import verify, verify_export
from rehearsal.experiments.b2 import SimulationFixture, run_b2
from rehearsal.experiments.b3 import BuyerFixture, ReviewerFixture, run_b3
from rehearsal.experiments.baseline import ToolPort, run_baseline
from rehearsal.experiments.frozen import FrozenPolicy, freeze
from rehearsal.experiments.policy import Policy
from rehearsal.world import World
from rehearsal.world.storage import ContractError, Json, canonical, identifier

METHODS = ("B0", "B1", "B2", "B3")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unchanged(path: Path, expected: str) -> bool:
    try:
        return digest(path) == expected
    except OSError:
        return False


def condition_id(scenario: Json) -> str:
    # A new label or seed alone is not a different deterministic starting condition.
    return hashlib.sha256(
        canonical(
            {k: v for k, v in scenario.items() if k not in {"scenario_version", "seed"}}
        ).encode()
    ).hexdigest()


def ledger_for(directory: Path, method: str, settings: ModelSettings, scope: str) -> UsageLedger:
    folder = directory / "learning" if method in {"B2", "B3"} else directory
    return UsageLedger(
        folder / "usage.sqlite3",
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


def run_cell(
    method: str,
    model_factory: Callable[[str, Policy], Model],
    settings: ModelSettings,
    directory: Path,
    training: Json,
    evaluation: Json,
    scope: str,
) -> Json:
    if method not in METHODS:
        raise ContractError("INVALID_COMPARISON_METHOD")
    if condition_id(training) == condition_id(evaluation):
        raise ContractError("EVALUATION_CONDITION_REUSED")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    root = Path(__file__).resolve().parents[3]
    spec: Json = {
        "method": method,
        "training_condition": training,
        "evaluation_condition": evaluation,
        "training_condition_id": condition_id(training),
        "evaluation_condition_id": condition_id(evaluation),
        "settings": asdict(settings),
        "scope": scope,
        "held_out": False,
        "purpose": "known-condition-frozen-evaluation-plumbing",
        "source_hashes": {
            str(p.relative_to(root)): digest(p)
            for p in (
                Path(__file__),
                root / "src/rehearsal/agents/runner.py",
                root / "src/rehearsal/agents/executor.py",
                root / "src/rehearsal/agents/metering.py",
                root / "src/rehearsal/experiments/b2.py",
                root / "src/rehearsal/experiments/b3.py",
                root / "src/rehearsal/experiments/frozen.py",
                root / "src/rehearsal/evaluation/verifier.py",
            )
        },
    }
    (directory / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    spec_sha = digest(directory / "spec.json")
    report: Json = {
        "method": method,
        "scope": scope,
        "status": "STARTED",
        "spec_sha256": spec_sha,
        "promoted": False,
        "model_efficacy_verified": False,
        "held_out_evaluation_verified": False,
        "evaluation_status": "NOT_RUN",
        "learning_status": "NOT_REQUIRED" if method in {"B0", "B1"} else "NOT_RUN",
    }
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    models: list[Model] = []
    meter: UsageLedger | None = None
    learning_paths: dict[str, Path] = {}
    frozen_sha: str | None = None

    def fresh(kind: str, policy: Policy) -> Model:
        model = model_factory(kind, policy)
        if any(model is old for old in models):
            raise ContractError("EVALUATION_MODEL_CONTEXT_REUSED")
        models.append(model)
        return model

    try:
        policy = Policy()  # B0/B1 keep the robust fixed input, not a weakened server boundary.
        if method in {"B2", "B3"}:
            if method == "B2":
                learning = run_b2(
                    fresh("simulation", Policy(refresh_quote_before_order=False)),
                    settings,
                    directory / "learning",
                    deepcopy(training),
                    scope,
                )
                selection = learning
            else:
                learning = run_b3(
                    lambda p: fresh("buyer", p),
                    lambda _: fresh("reviewer", Policy()),
                    settings,
                    directory / "learning",
                    deepcopy(training),
                    scope,
                )
                selection_path = directory / "learning/review/report.json"
                selection = (
                    json.loads(selection_path.read_text()) if selection_path.exists() else {}
                )
            report["learning_status"] = learning["status"]
            meter = ledger_for(directory, method, settings, scope)
            report["learning_usage"] = meter.report()
            if learning["status"] not in {"CANDIDATE_EVALUATED_NOT_PROMOTED", "NO_CHANGE"}:
                raise ContractError("LEARNING_NOT_READY")
            if not learning["parent_unchanged"] or not meter.report()["all_usage_recorded"]:
                raise ContractError("LEARNING_EVIDENCE_UNRESOLVED")
            policy = Policy.parse(selection.get("candidate_policy") or selection["initial_policy"])
            learning_paths = {
                str(p.relative_to(directory / "learning")): p
                for p in (directory / "learning").rglob("*")
                if p.suffix in {".json", ".txt"}
            }
        else:
            meter = ledger_for(directory, method, settings, scope)
            report["learning_usage"] = meter.report()
        learning_hashes = {name: digest(p) for name, p in learning_paths.items()}
        frozen = freeze(policy, directory / "policy.json", root, learning_paths)
        frozen_sha = digest(directory / "policy.json")
        report.update(
            frozen_id=frozen.identifier,
            frozen_sha256=frozen_sha,
            selected_policy=asdict(policy),
            learning_artifact_hashes=learning_hashes,
        )
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        if method == "B0":
            target = directory / "evaluation"
            world = World(target)
            world.create_run("evaluation", deepcopy(evaluation), policy_version=frozen.identifier)
            port = ToolPort(
                purchasing_tools(world, "evaluation"),
                settings.max_tool_calls,
                settings.timeout_seconds,
            )
            execution = run_baseline(frozen, port, "evaluation")
            baseline_verdict = verify(
                target, "evaluation", evaluation, export_to=target / "evidence.json"
            )
            evaluation_result: Json = {
                "scope": "B0-fixed-rule-not-model",
                "verdict": baseline_verdict.as_dict(),
                "execution_status": execution["status"],
                "frozen_id": frozen.identifier,
                "tool_calls": len(port.trace),
                "trace": execution["trace"],
                "success": execution["status"] == "GOAL_OBSERVED"
                and baseline_verdict.status == "COMPLETE",
            }
            (target / "report.json").write_text(json.dumps(evaluation_result, indent=2) + "\n")
        else:
            model = fresh("evaluation", policy)
            # Re-read the immutable file after the factory and before a paid call.
            if not unchanged(directory / "policy.json", frozen_sha):
                raise ContractError("FROZEN_POLICY_FILE_CHANGED")
            FrozenPolicy.load(directory / "policy.json", root)
            evaluation_result = execute(
                model,
                settings,
                directory / "evaluation",
                deepcopy(evaluation),
                "evaluation",
                scope,
                frozen,
                shared_ledger=meter,
                role="buyer_evaluation",
            )
        report["evaluation_status"] = evaluation_result.get(
            "runtime_status", evaluation_result.get("execution_status")
        )
        report["evaluation_report_sha256"] = digest(directory / "evaluation/report.json")
        verdict = verify_export(directory / "evaluation/evidence.json").as_dict()
        if verdict != evaluation_result["verdict"]:
            raise ContractError("EVALUATION_VERDICT_MISMATCH")
        if any(digest(p) != learning_hashes[name] for name, p in learning_paths.items()):
            raise ContractError("LEARNING_ARTIFACT_CHANGED")
        frozen.check()
        report.update(
            verdict=verdict,
            evaluation_tool_calls=evaluation_result["tool_calls"],
            status="EVALUATED" if evaluation_result["success"] else "EVALUATION_INCOMPLETE",
        )
    except Exception as exc:
        report.update(
            status="REJECTED" if isinstance(exc, ContractError) else "ERROR",
            error=exc.code if isinstance(exc, ContractError) else type(exc).__name__,
        )
    finally:
        if meter is not None:
            report["total_usage"] = meter.report()
            rows = [r for r in report["total_usage"]["calls"] if r["role"] == "buyer_evaluation"]
            report["evaluation_usage"] = {
                "calls": rows,
                "recorded_micro_usd": sum(r["estimated_micro_usd"] or 0 for r in rows),
                "unresolved_reserved_micro_usd": sum(
                    r["reserved_micro_usd"] for r in rows if r["status"] != "RECORDED"
                ),
            }
            report["total_tool_calls"] = report["total_usage"]["admitted_tool_calls"] + (
                report.get("evaluation_tool_calls", 0) if method == "B0" else 0
            )
        if not unchanged(directory / "spec.json", spec_sha):
            report.update(status="REJECTED", error="EVALUATION_SPEC_CHANGED")
        elif any(not unchanged(root / p, sha) for p, sha in spec["source_hashes"].items()):
            report.update(status="REJECTED", error="EVALUATION_SOURCE_CHANGED")
        if frozen_sha is not None and not unchanged(directory / "policy.json", frozen_sha):
            report.update(status="REJECTED", error="FROZEN_POLICY_FILE_CHANGED")
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


class EvaluationBuyer(BuyerFixture):
    def get_config(self) -> Json:
        return {"model_id": "offline-evaluation-fixture"}


class EvaluationReviewer(ReviewerFixture):
    def get_config(self) -> Json:
        return {"model_id": "offline-evaluation-fixture"}


class EvaluationSimulation(SimulationFixture):
    def get_config(self) -> Json:
        return {"model_id": "offline-evaluation-fixture"}


def fixture_factory(kind: str, policy: Policy) -> Model:
    if kind == "simulation":
        return EvaluationSimulation()
    if kind == "reviewer":
        return EvaluationReviewer()
    return EvaluationBuyer(policy)


def known_pair(root: Path) -> tuple[Json, Json]:
    training = json.loads((root / "scenarios/normal-v1.json").read_text())
    evaluation = deepcopy(training)
    evaluation["scenario_version"] = "known-evaluation-a-stockout-v1"
    evaluation["suppliers"]["A"]["items"]["tent"]["stock"] = 0
    return training, evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline-fixture", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--method", choices=METHODS)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
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
        methods = [args.method] if args.method else list(METHODS)
    else:
        try:
            settings = read_settings(root)
        except ValueError as exc:
            print(str(exc))
            return 2
        if not args.execute:
            print("PASS: frozen-evaluation settings only; no AWS client or model call.")
            return 0
        if args.method not in {"B1", "B2", "B3"}:
            parser.error("--execute requires one explicit model arm (--method B1/B2/B3)")
        methods = [args.method]
    os.umask(0o077)
    directory = root / ".local/evaluation" / identifier("frozen")
    directory.mkdir(parents=True, exist_ok=False)
    training, evaluation = known_pair(root)
    reports = [
        run_cell(
            method,
            fixture_factory if args.offline_fixture else lambda k, p: bedrock_model(settings),
            settings,
            directory / method,
            training,
            evaluation,
            "offline-scripted-model" if args.offline_fixture else "live-model",
        )
        for method in methods
    ]
    (directory / "report.json").write_text(
        json.dumps({"scope": "known-condition-only", "methods": reports}, indent=2) + "\n"
    )
    print(f"Frozen evaluation: {[(r['method'], r['status']) for r in reports]}; {directory}")
    print("No held-out evaluation, policy promotion, or model-efficacy claim.")
    return 0 if all(r["status"] == "EVALUATED" for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
