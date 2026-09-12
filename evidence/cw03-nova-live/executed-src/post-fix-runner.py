"""Explicitly configured CW03 execution. Preflight never creates an AWS client."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from strands.hooks import AfterToolCallEvent
from strands.models.model import Model

from rehearsal.evaluation.verifier import verify
from rehearsal.experiments.frozen import FrozenPolicy
from rehearsal.experiments.policy import policy_prompt
from rehearsal.world import World
from rehearsal.world.storage import Json, identifier

from .executor import SYSTEM_PROMPT, Limits, agent_for_tools, purchasing_tools
from .metering import MeterHooks, RateCard, UsageLedger


@dataclass(frozen=True)
class ModelSettings:
    profile: str
    region: str
    model_id: str
    rates: RateCard
    budget_micro_usd: int
    input_limit: int = 8000
    output_limit: int = 1024
    max_model_calls: int = 12
    max_tool_calls: int = 24
    timeout_seconds: int = 120
    max_total_tokens: int = 100000

    def __post_init__(self) -> None:
        if not all(v.strip() for v in (self.profile, self.region, self.model_id)):
            raise ValueError("Explicit profile, region and model ID are required")
        for name in (
            "budget_micro_usd",
            "input_limit",
            "output_limit",
            "max_model_calls",
            "max_tool_calls",
            "timeout_seconds",
            "max_total_tokens",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    @classmethod
    def from_values(cls, values: dict[str, str]) -> ModelSettings:
        names = (
            "AWS_PROFILE",
            "AWS_REGION",
            "REHEARSAL_MODEL_ID",
            "REHEARSAL_MODEL_BUDGET_USD",
            "REHEARSAL_PRICE_INPUT",
            "REHEARSAL_PRICE_OUTPUT",
            "REHEARSAL_PRICE_CACHE_READ",
            "REHEARSAL_PRICE_CACHE_WRITE",
            "REHEARSAL_RATE_SOURCE",
        )
        missing = [name for name in names if not values.get(name, "").strip()]
        if missing:
            raise ValueError("Missing model settings: " + ", ".join(missing))
        try:
            usd = Decimal(values["REHEARSAL_MODEL_BUDGET_USD"])
            if not usd.is_finite() or usd <= 0:
                raise ValueError("Model budget must be finite and positive")
            micro_usd = int(usd * 1_000_000)
            rates = RateCard(
                values["REHEARSAL_PRICE_INPUT"],
                values["REHEARSAL_PRICE_OUTPUT"],
                values["REHEARSAL_PRICE_CACHE_READ"],
                values["REHEARSAL_PRICE_CACHE_WRITE"],
                values["REHEARSAL_RATE_SOURCE"],
            )
            optional = {
                field: int(values.get(env, str(default)))
                for field, env, default in (
                    ("input_limit", "REHEARSAL_MAX_INPUT_TOKENS", 8000),
                    ("output_limit", "REHEARSAL_MAX_OUTPUT_TOKENS", 1024),
                    ("max_model_calls", "REHEARSAL_MAX_MODEL_CALLS", 12),
                    ("max_tool_calls", "REHEARSAL_MAX_TOOL_CALLS", 24),
                    ("timeout_seconds", "REHEARSAL_MODEL_TIMEOUT_SECONDS", 120),
                    ("max_total_tokens", "REHEARSAL_MAX_TOTAL_TOKENS", 100000),
                )
            }
            return cls(
                values["AWS_PROFILE"],
                values["AWS_REGION"],
                values["REHEARSAL_MODEL_ID"],
                rates,
                micro_usd,
                **optional,
            )
        except (InvalidOperation, OverflowError) as exc:
            raise ValueError("Invalid decimal model budget or rate") from exc


def read_settings(root: Path) -> ModelSettings:
    values: dict[str, str] = {}
    path = root / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                key, separator, value = line.partition("=")
                if separator:
                    values[key.strip()] = value.strip()
    # Empty ambient variables do not erase explicitly configured repository values.
    values.update(
        {
            k: v
            for k, v in os.environ.items()
            if v and (k in {"AWS_PROFILE", "AWS_REGION"} or k.startswith("REHEARSAL_"))
        }
    )
    return ModelSettings.from_values(values)


def bedrock_model(settings: ModelSettings) -> Model:
    # Client construction can resolve credentials. It happens only after --execute.
    import boto3  # type: ignore[import-untyped]
    from botocore.config import Config  # type: ignore[import-untyped]
    from strands.models import BedrockModel

    session = boto3.Session(profile_name=settings.profile, region_name=settings.region)
    return BedrockModel(
        model_id=settings.model_id,
        boto_session=session,
        boto_client_config=Config(
            retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=60
        ),
        max_tokens=settings.output_limit,
        use_native_token_count=False,
    )


def execute(
    model: Model,
    settings: ModelSettings,
    directory: Path,
    scenario: Json,
    run_id: str,
    scope: str,
    frozen: FrozenPolicy | None = None,
    *,
    shared_ledger: UsageLedger | None = None,
    role: str = "executor",
) -> Json:
    """Run once, retaining usage and independent evidence even after failure."""
    if model.get_config().get("model_id") != settings.model_id:
        raise ValueError("Model ID does not match the configured rate/run record")
    if frozen:
        frozen.check()
    if shared_ledger is not None:
        from rehearsal.experiments.model_experiment import validate_shared_ledger

        validate_shared_ledger(shared_ledger, settings, scope)
        if any(c["execution_id"] == run_id for c in shared_ledger.report()["calls"]):
            raise ValueError("Execution accounting ID already used")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    world = World(directory)
    world.create_run(
        run_id, scenario, policy_version=frozen.identifier if frozen else "single-executor-v1"
    )
    ledger = shared_ledger or UsageLedger(
        directory / "usage.sqlite3",
        run_id,
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
    meter = MeterHooks(ledger, role=role, execution_id=run_id)
    limits = Limits(settings.max_model_calls, settings.max_tool_calls)
    agent = agent_for_tools(
        model,
        purchasing_tools(world, run_id),
        limits,
        meter,
        policy=frozen.policy if frozen else None,
    )
    prompt = policy_prompt(SYSTEM_PROMPT, frozen.policy) if frozen else SYSTEM_PROMPT
    tool_trace: list[Json] = []

    def after_tool(event: AfterToolCallEvent) -> None:
        # Store tool facts only; do not export provider reasoning content.
        entry: Json = {
            "tool_use": event.tool_use,
            "result": event.result,
            "error_type": type(event.exception).__name__ if event.exception else None,
        }
        tool_trace.append(entry)
        with (directory / "tools.jsonl").open("a") as output:
            output.write(json.dumps(entry) + "\n")

    agent.add_hook(after_tool)
    report: Json = {
        "scope": scope,
        "run_id": run_id,
        "model_id": settings.model_id,
        "settings": asdict(settings),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "frozen_id": frozen.identifier if frozen else None,
        "runtime_status": "STARTED",
        "error_type": None,
    }
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    async def invoke() -> Any:
        return await asyncio.wait_for(
            agent.invoke_async(
                "Complete the event-supplies goal using your tools. "
                "Report actual delivery and spending."
            ),
            timeout=settings.timeout_seconds,
        )

    try:
        result = asyncio.run(invoke())
        report["provider_stop_reason"] = result.stop_reason
        report["runtime_status"] = "COMPLETED" if result.stop_reason == "end_turn" else "INCOMPLETE"
        report["final_response"] = str(result)
        report["sdk_usage"] = dict(result.metrics.accumulated_usage)
    except Exception as exc:
        report["runtime_status"] = "ERROR"
        report["error_type"] = type(exc).__name__
    finally:
        report["stop_reason"] = meter.stop_reason or limits.stop_reason
        if report["stop_reason"]:
            report["runtime_status"] = "LIMITED"
        report["usage"] = ledger.report()
        report["execution_usage"] = [
            c for c in report["usage"]["calls"] if c["execution_id"] == run_id
        ]
        report["accounting_role"] = role
        report["tool_calls"] = len(tool_trace)
        report["verdict"] = verify(
            directory, run_id, scenario, export_to=directory / "evidence.json"
        ).as_dict()
        report["success"] = (
            report["runtime_status"] == "COMPLETED"
            and report["verdict"]["status"] == "COMPLETE"
            and bool(report["execution_usage"])
            and report["usage"]["all_usage_recorded"]
            and not report["usage"]["estimated_budget_exceeded"]
            and not report["usage"]["estimated_token_budget_exceeded"]
        )
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Invoke the configured paid model")
    parser.add_argument("--policy", type=Path, help="Immutable policy manifest to verify and apply")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    frozen = FrozenPolicy.load(args.policy, root) if args.policy else None
    try:
        settings = read_settings(root)
    except ValueError as exc:
        print(str(exc))
        return 2
    if not args.execute:
        print("PASS: model settings are structurally valid. No AWS client or model call was made.")
        print(
            "Rates and permissions still require live verification; cost admission uses estimates."
        )
        return 0
    os.umask(0o077)
    model = bedrock_model(settings)
    run_id = identifier("cw03")
    directory = root / ".local/model" / run_id
    scenario = json.loads((root / "scenarios/normal-v1.json").read_text())
    report = execute(model, settings, directory, scenario, run_id, "live-model", frozen)
    print(f"{report['runtime_status']}: goal={report['verdict']['status']}; evidence={directory}")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
