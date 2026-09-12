"""Metered frozen-policy buyer over loopback HTTP; transaction proof is a later read-only step."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from strands.hooks import AfterToolCallEvent, BeforeModelCallEvent, BeforeToolCallEvent
from strands.models.model import Model

from rehearsal.agents.executor import SYSTEM_PROMPT, Limits, agent_for_tools
from rehearsal.agents.metering import MeterHooks, UsageLedger
from rehearsal.agents.runner import ModelSettings, bedrock_model, read_settings
from rehearsal.commerce.learning_budget import B3Carryover, BudgetCarryover
from rehearsal.commerce.reaction import Reactions, ReactionSettings
from rehearsal.evaluation.conditions import verify_start
from rehearsal.evidence_view import MAX_ARTIFACT_BYTES, goal, integer, read_json, review_export
from rehearsal.experiments.baseline import ToolPort, run_baseline
from rehearsal.experiments.frozen import FrozenPolicy
from rehearsal.experiments.policy import policy_prompt
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.tools import purchasing_http_tools
from rehearsal.world.storage import ContractError, Json

ROOT = Path(__file__).resolve().parents[3]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unchanged(path: Path, sha: str) -> bool:
    try:
        return digest(path) == sha
    except OSError:
        return False


def write(path: Path, value: Json) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


class ContractClient(OperatingClient):
    """Check the operator-selected run/goal/budget before writes, without planning purchases."""

    def __init__(self, client: OperatingClient, spec: Json, meter: MeterHooks):
        self.delegate = client
        self.http, self.run_id = client.http, client.run_id
        self.spec, self.meter = spec, meter
        self.scope_reads = 0
        self.reactions: Reactions | None = None

    def checked(self, snapshot: Json) -> Json:
        try:
            goal(snapshot["goal"])
            integer(snapshot["balance"]["budget"], 1)
        except (KeyError, TypeError, ValueError):
            self.meter.stop_reason = "HTTP_RUN_CONTRACT_CHANGED"
            raise ContractError("HTTP_RUN_CONTRACT_CHANGED") from None
        if (
            snapshot.get("run_id") != self.run_id
            or snapshot.get("goal") != self.spec["expected_goal"]
            or snapshot.get("balance", {}).get("budget") != self.spec["expected_budget"]
            or snapshot.get("clock_mode") != "operating-one-second-ticks"
        ):
            self.meter.stop_reason = "HTTP_RUN_CONTRACT_CHANGED"
            raise ContractError("HTTP_RUN_CONTRACT_CHANGED")
        return snapshot

    def request(self, method: str, path: str, body: Json | None = None) -> Json:
        if self.meter.stop_reason:
            raise ContractError(self.meter.stop_reason)
        if method == "POST":
            self.scope_reads += 1
            self.checked(self.delegate.request("GET", "snapshot"))
            if self.reactions and path in {"orders", "payments"}:
                self.reactions.guard_effect(path, body or {})
        value = self.delegate.request(method, path, body)
        if self.reactions and method == "POST" and path == "quotes":
            self.reactions.quotes[value["id"]] = value
            self.reactions.quote_basis[value["id"]] = self.reactions.basis
        return self.checked(value) if method == "GET" and path == "snapshot" else value


def execute_fixed(
    frozen: FrozenPolicy,
    settings: ModelSettings,
    client: ContractClient,
    meter: MeterHooks,
    guard: Callable[[], None],
    record: Callable[[Json], None],
) -> Json:
    class RecordedPort(ToolPort):
        def call(self, name: str, **arguments: object) -> Json:
            guard()
            reason = meter.ledger.admit_tool(meter.role, client.run_id, name, meter.stop_reason)
            if reason:
                meter.stop_reason = reason
                raise ContractError(reason)
            entry: Json = {
                "tool_use": {
                    "name": name,
                    "input": arguments,
                    "toolUseId": f"fixed-{len(self.trace) + 1}",
                },
                "error_type": None,
            }
            try:
                value = super().call(name, **arguments)
                entry["result"] = {"status": "success", "content": [{"json": value}]}
                return value
            except Exception as exc:
                entry.update(
                    error_type=type(exc).__name__,
                    result={"status": "error", "content": [{"text": str(exc)}]},
                )
                raise
            finally:
                record(entry)

    port = RecordedPort(
        purchasing_http_tools(client), settings.max_tool_calls, settings.timeout_seconds
    )
    return run_baseline(frozen, port, client.run_id)


def execute_http(
    model: Model | None,
    settings: ModelSettings,
    client: OperatingClient,
    directory: Path,
    expected_goal: Json,
    expected_budget: int,
    frozen: FrozenPolicy,
    scope: str,
    *,
    carryover: BudgetCarryover | None = None,
    initial_condition: Json | None = None,
    reaction_settings: ReactionSettings | None = None,
) -> Json:
    goal(expected_goal)
    integer(expected_budget, 1)
    if scope not in {"offline-scripted-model", "live-model"}:
        raise ValueError("Invalid execution scope")
    if (model is None) != bool(carryover and carryover.method == "B0"):
        raise ValueError("B0 requires no model; model arms require a configured model")
    if model is not None and model.get_config().get("model_id") != settings.model_id:
        raise ValueError("Model ID mismatch")
    if reaction_settings is not None and model is None:
        raise ValueError("Observation replanning requires a model arm")
    frozen.check()
    if frozen.learning_evidence and carryover is None:
        raise ContractError("LEARNING_BUDGET_REQUIRED")
    if carryover:
        from rehearsal.experiments.model_experiment import validate_shared_ledger

        validate_shared_ledger(carryover.ledger, settings, scope)
        carryover.check()
        if frozen.identifier != carryover.frozen.identifier:
            raise ContractError(f"{carryover.method}_FROZEN_LEARNING_MISMATCH")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    if carryover:
        carryover.claim(client.run_id, directory)
    spec: Json = {
        "schema": "rehearsal-http-model-run-v1",
        "executor_kind": "B0-fixed-rule" if model is None else "model",
        "method": carryover.method if carryover else "B1",
        "run_id": client.run_id,
        "expected_goal": expected_goal,
        "expected_budget": expected_budget,
        "frozen_id": frozen.identifier,
        "policy": asdict(frozen.policy),
        "prompt_sha256": hashlib.sha256(
            policy_prompt(SYSTEM_PROMPT, frozen.policy).encode()
        ).hexdigest(),
        "scope": scope,
        "settings": asdict(settings),
        "initial_condition": initial_condition,
        "reaction_settings": asdict(reaction_settings) if reaction_settings else None,
        "learning_budget": {
            "session_id": carryover.ledger.run_id,
            "learning_artifact_hashes": carryover.hashes,
            "frozen_sha256": carryover.policy_sha,
            "planned_external_runs": 1,
        }
        if carryover
        else None,
        "source_hashes": {
            str(p.relative_to(ROOT)): digest(p)
            for p in sorted((ROOT / "src/rehearsal").rglob("*.py"))
        },
    }
    write(directory / "spec.json", spec)
    spec_sha = digest(directory / "spec.json")
    ledger = (
        carryover.ledger
        if carryover
        else UsageLedger(
            directory / "usage.sqlite3",
            client.run_id,
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
    )

    reactions: Reactions | None = None

    class TransferMeter(MeterHooks):
        def before(self, event: BeforeModelCallEvent) -> None:
            if carryover:
                try:
                    carryover.check()
                except (ContractError, OSError) as exc:
                    self.stop_reason = (
                        exc.code
                        if isinstance(exc, ContractError)
                        else f"{carryover.method}_LEARNING_ARTIFACT_CHANGED"
                    )
            if reactions and not event.cancel and not self.stop_reason:
                try:
                    added = reactions.before_model(event)
                    projected = event.projected_input_tokens
                    adjusted = replace(
                        event,
                        projected_input_tokens=None if projected is None else projected + added,
                    )
                    super().before(adjusted)
                    event.cancel = adjusted.cancel
                    return
                except Exception as exc:
                    self.stop_reason = (
                        exc.code if isinstance(exc, ContractError) else "OBSERVATION_READ_FAILED"
                    )
            super().before(event)

    meter = TransferMeter(
        ledger, role="buyer_evaluation" if carryover else "executor", execution_id=client.run_id
    )
    bounded = ContractClient(client, spec, meter)
    limits = Limits(settings.max_model_calls, settings.max_tool_calls)
    trace: list[Json] = []
    report: Json = {
        "scope": scope,
        "run_id": client.run_id,
        "runtime_status": "STARTED",
        "spec_sha256": spec_sha,
        "frozen_id": frozen.identifier,
        "transaction_status": "NOT_VERIFIED",
        "success": False,
        "model_efficacy_verified": False,
    }
    write(directory / "report.json", report)
    try:
        initial = bounded.observe_world()
        if (
            initial["balance"]["spent"]
            or initial["balance"]["reserved"]
            or any(initial["inventory"].values())
            or initial["tick"] >= expected_goal["deadline_tick"]
        ):
            raise ContractError("FRESH_EXTERNAL_RUN_REQUIRED")
        report["initial_snapshot"] = initial
        if initial_condition is not None:
            verify_start(initial_condition["verification"], initial)
        write(directory / "report.json", report)
        if reaction_settings:
            reactions = Reactions(client, bounded.checked, reaction_settings, directory)
            bounded.reactions = reactions
            reactions.start()

        def record(entry: Json) -> None:
            trace.append(entry)
            with (directory / "tools.jsonl").open("a") as output:
                output.write(json.dumps(entry) + "\n")

        def guard() -> None:
            if carryover:
                carryover.check()
            if not unchanged(directory / "spec.json", spec_sha) or any(
                not unchanged(ROOT / name, sha) for name, sha in spec["source_hashes"].items()
            ):
                raise ContractError("EXECUTION_INPUT_CHANGED")

        if model is None:
            result_fixed = execute_fixed(frozen, settings, bounded, meter, guard, record)
            report["baseline"] = result_fixed
            report["runtime_status"] = (
                "COMPLETED" if result_fixed["status"] == "GOAL_OBSERVED" else "INCOMPLETE"
            )
        else:
            agent = agent_for_tools(
                model, purchasing_http_tools(bounded), limits, meter, frozen.policy
            )

            def before_tool(event: BeforeToolCallEvent) -> None:
                if carryover:
                    try:
                        carryover.check()
                    except (ContractError, OSError) as exc:
                        meter.stop_reason = (
                            exc.code
                            if isinstance(exc, ContractError)
                            else f"{carryover.method}_LEARNING_ARTIFACT_CHANGED"
                        )
                        event.cancel_tool = meter.stop_reason
                if not unchanged(directory / "spec.json", spec_sha) or any(
                    not unchanged(ROOT / name, sha) for name, sha in spec["source_hashes"].items()
                ):
                    meter.stop_reason = "EXECUTION_INPUT_CHANGED"
                    event.cancel_tool = meter.stop_reason

            agent.add_hook(before_tool)

            def after_tool(event: AfterToolCallEvent) -> None:
                entry: Json = {
                    "tool_use": event.tool_use,
                    "result": event.result,
                    "error_type": type(event.exception).__name__ if event.exception else None,
                }
                record(entry)

            agent.add_hook(after_tool)

            async def invoke() -> Any:
                async def work() -> Any:
                    prompt = (
                        "Complete your event-supplies goal using your tools. "
                        "Report actual delivery and spending."
                    )
                    while True:
                        result = await agent.invoke_async(prompt)
                        if (
                            not reactions
                            or result.stop_reason != "end_turn"
                            or meter.stop_reason
                            or limits.stop_reason
                        ):
                            return result
                        # Remain receptive while an unfinished external goal is progressing.
                        # Clock-only frames do not invoke a model. All calls reuse this agent,
                        # the same meter/limits and any carried-over learning budget.
                        while True:
                            captured = reactions.inbox.capture()
                            snapshot = reactions.fresh()
                            if all(
                                snapshot["inventory"].get(k, 0) >= n
                                for k, n in expected_goal["items"].items()
                            ):
                                return result
                            if snapshot["tick"] >= expected_goal["deadline_tick"]:
                                report["reaction_stop"] = "DEADLINE"
                                return result
                            if reactions.inbox.changed.is_set():
                                # A fresh read can supersede a delayed journal observation.
                                from rehearsal.commerce.change_inbox import meaning

                                if meaning(snapshot) != reactions.basis:
                                    break
                                reactions.inbox.acknowledge(snapshot, captured)
                            await asyncio.sleep(0.5)
                        prompt = (
                            "Public purchasing conditions changed while your goal was unfinished. "
                            "Reconcile existing orders and UNKNOWN payments, then reassess the "
                            "remaining goal using the current observation and your tools."
                        )

                return await asyncio.wait_for(work(), timeout=settings.timeout_seconds)

            result = asyncio.run(invoke())
            report["runtime_status"] = (
                "COMPLETED"
                if result.stop_reason == "end_turn" and not report.get("reaction_stop")
                else "INCOMPLETE"
            )
            report["final_response"] = str(result)
    except Exception as exc:
        report.update(runtime_status="ERROR", error_type=type(exc).__name__)
        if isinstance(exc, ContractError):
            report["error_code"] = exc.code
    finally:
        if reactions:
            reactions.close()
            report["reactions"] = reactions.report()
            report["observations_sha256"] = (
                digest(reactions.path) if reactions.path.exists() else None
            )
        if (
            initial_condition
            and initial_condition["verification"].get("first_event_tick") is not None
        ):
            try:
                report["event_execution_end"] = bounded.observe_world()
            except Exception:
                report["event_execution_end"] = None
        report["payment_transport_events"] = list(getattr(client, "transport_events", []))
        report["stop_reason"] = meter.stop_reason or limits.stop_reason
        if report["stop_reason"]:
            report["runtime_status"] = "LIMITED"
        report["usage"] = ledger.report()
        rows = [c for c in report["usage"]["calls"] if c["execution_id"] == client.run_id]
        report["execution_usage"] = {
            "calls": rows,
            "recorded_micro_usd": sum(c["estimated_micro_usd"] or 0 for c in rows),
            "recorded_total_tokens": sum(
                sum(json.loads(c["usage"]).values()) for c in rows if c["usage"]
            ),
            "unresolved_reserved_micro_usd": sum(
                c["reserved_micro_usd"] for c in rows if c["status"] != "RECORDED"
            ),
            "tool_admissions": [
                c for c in report["usage"]["tool_admissions"] if c["execution_id"] == client.run_id
            ],
        }
        report["tool_calls"] = len(trace)
        report["scope_check_reads"] = bounded.scope_reads
        # Scope checks are wrapper GETs, not additional model-selected tools or hidden planning.
        report["runtime_accounted"] = (
            report["runtime_status"] == "COMPLETED"
            and (bool(rows) if model is not None else bool(trace) and not report["usage"]["calls"])
            and report["usage"]["all_usage_recorded"]
            and not report["usage"]["estimated_budget_exceeded"]
            and not report["usage"]["estimated_token_budget_exceeded"]
        )
        if not unchanged(directory / "spec.json", spec_sha) or any(
            not unchanged(ROOT / p, sha) for p, sha in spec["source_hashes"].items()
        ):
            report.update(
                runtime_status="ERROR",
                error_code="EXECUTION_INPUT_CHANGED",
                runtime_accounted=False,
            )
        if carryover:
            try:
                carryover.check()
            except (ContractError, OSError) as exc:
                report.update(
                    runtime_status="ERROR",
                    runtime_accounted=False,
                    error_code=exc.code
                    if isinstance(exc, ContractError)
                    else f"{carryover.method}_LEARNING_ARTIFACT_CHANGED",
                )
            carryover.finish(report["runtime_status"])
            report["learning_budget"] = carryover.accounting()
        report["tools_sha256"] = digest(directory / "tools.jsonl") if trace else None
        write(directory / "report.json", report)
        write(
            directory / "execution-manifest.json",
            {
                "scope": "local-artifact-integrity-not-an-external-signature",
                "spec_sha256": spec_sha,
                "report_sha256": digest(directory / "report.json"),
                "tools_sha256": report["tools_sha256"],
                "observations_sha256": report.get("observations_sha256"),
            },
        )
    return report


def attest(directory: Path, selection: Path) -> Json:
    """Read-only independent verification; never submit/retry a purchase or call a model."""
    _, report = read_json(directory / "report.json", MAX_ARTIFACT_BYTES)
    _, spec = read_json(directory / "spec.json", MAX_ARTIFACT_BYTES)
    _, sealed = read_json(directory / "execution-manifest.json", 16 * 1024)
    _, chosen = read_json(selection, 16 * 1024)
    if (
        sealed["report_sha256"] != digest(directory / "report.json")
        or sealed["spec_sha256"] != digest(directory / "spec.json")
        or sealed["tools_sha256"] != report["tools_sha256"]
        or report["spec_sha256"] != digest(directory / "spec.json")
        or report["run_id"] != spec["run_id"]
        or report["frozen_id"] != spec["frozen_id"]
        or chosen.get("expected_goal") != spec["expected_goal"]
        or chosen.get("expected_budget") != spec["expected_budget"]
        or sealed.get("observations_sha256") != report.get("observations_sha256")
    ):
        raise ValueError("Execution/evidence contract mismatch")
    if (
        report.get("observations_sha256") is not None
        and digest(directory / "observations.jsonl") != report["observations_sha256"]
    ):
        raise ValueError("Execution observations changed")
    review = review_export(selection, spec["run_id"])
    orders = set()
    trace_path = directory / "tools.jsonl"
    if report["tools_sha256"] is not None:
        if digest(trace_path) != report["tools_sha256"]:
            raise ValueError("Tool trace changed")
        for line in trace_path.read_text().splitlines():
            record = json.loads(line)
            if (
                record["tool_use"]["name"] == "create_order"
                and record["result"]["status"] == "success"
            ):
                content = record["result"]["content"][0]
                result = content.get("json") or json.loads(content.get("text", "{}"))
                orders.add(result["id"])
    attributed = False
    if review["status"] == "VERIFIED":
        evidence_path = Path(chosen["artifact_path"])
        if not evidence_path.is_absolute():
            evidence_path = selection.parent / evidence_path
        raw, evidence = read_json(evidence_path, MAX_ARTIFACT_BYTES)
        if hashlib.sha256(raw).hexdigest() != chosen["sha256"]:
            raise ValueError("Selected evidence changed during attestation")
        attributed = (
            orders == {p["id"] for p in evidence["tables"]["purchases"]}
            and bool(orders)
            and evidence["captured_at_tick"] >= report.get("initial_snapshot", {}).get("tick", 0)
        )
    return {
        "scope": report["scope"],
        "run_id": spec["run_id"],
        "frozen_id": spec["frozen_id"],
        "report_sha256": digest(directory / "report.json"),
        "evidence_review": review,
        "orders_match_execution": attributed,
        "transaction_verified": review["status"] == "VERIFIED"
        and review["verdict"]["status"] == "COMPLETE",
        "success": bool(report.get("runtime_accounted"))
        and attributed
        and review["status"] == "VERIFIED"
        and review["verdict"]["status"] == "COMPLETE",
        "model_efficacy_verified": False,
    }


def configuration(path: Path) -> Json:
    _, value = read_json(path, 16 * 1024)
    if set(value) != {"run_id", "buyer_token", "expected_goal", "expected_budget", "policy_path"}:
        raise ValueError("Only buyer credentials and explicit execution inputs are accepted")
    if not isinstance(value["run_id"], str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,128}", value["run_id"]
    ):
        raise ValueError("Invalid run ID")
    if not isinstance(value["buyer_token"], str) or not value["buyer_token"].strip():
        raise ValueError("Buyer token required")
    goal(value["expected_goal"])
    integer(value["expected_budget"], 1)
    policy = Path(value["policy_path"])
    if not policy.is_absolute():
        policy = path.parent / policy
    value["policy_path"] = str(policy)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-replans", type=int, help="Enable observed-change reactions (1..32)")
    parser.add_argument("--learning", type=Path, help="Completed B3 directory; reuse its budget")
    parser.add_argument("--attest", type=Path, metavar="RUN_DIRECTORY")
    parser.add_argument("--evidence-selection", type=Path)
    args = parser.parse_args()
    if args.attest:
        if (
            args.execute
            or args.config
            or args.learning
            or args.max_replans is not None
            or not args.evidence_selection
        ):
            parser.error("Attestation requires only a run directory and evidence selection")
        result = attest(args.attest, args.evidence_selection)
        print(json.dumps(result, indent=2))
        return 0 if result["success"] else 1
    if not args.config or args.evidence_selection:
        parser.error("A buyer-only execution configuration is required")
    config = configuration(args.config)
    reaction_settings = ReactionSettings(args.max_replans) if args.max_replans is not None else None
    frozen = FrozenPolicy.load(Path(config["policy_path"]), ROOT)
    if frozen.learning_evidence and not args.learning:
        raise ContractError("LEARNING_BUDGET_REQUIRED")
    try:
        settings = read_settings(ROOT)
    except ValueError as exc:
        print(str(exc))
        return 2
    carryover = (
        B3Carryover(args.learning, Path(config["policy_path"]), settings, "live-model")
        if args.learning
        else None
    )
    if not args.execute:
        print("PASS: configuration only; no HTTP request, AWS client or model call.")
        return 0
    os.umask(0o077)
    directory = ROOT / ".local/commerce-model" / config["run_id"]
    if directory.exists():
        raise FileExistsError("Existing execution retained; no automatic retry")
    client = OperatingClient("http://127.0.0.1:18001", config["run_id"], config["buyer_token"])
    try:
        report = execute_http(
            bedrock_model(settings),
            settings,
            client,
            directory,
            config["expected_goal"],
            config["expected_budget"],
            frozen,
            "live-model",
            carryover=carryover,
            reaction_settings=reaction_settings,
        )
    finally:
        client.close()
    print(f"Runtime {report['runtime_status']}; transaction NOT_VERIFIED; evidence: {directory}")
    return 0 if report["runtime_accounted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
