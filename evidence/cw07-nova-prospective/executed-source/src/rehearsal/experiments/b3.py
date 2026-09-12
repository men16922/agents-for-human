"""Explicit B3 accounting rehearsal: initial buyer, independent review, candidate buyer."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from strands.models.model import Model

from rehearsal.agents.metering import RateCard, UsageLedger
from rehearsal.agents.runner import ModelSettings, bedrock_model, read_settings
from rehearsal.world import World
from rehearsal.world.storage import ContractError, Json, canonical, identifier

from .model_experiment import model_experiment, verify_attribution
from .policy import Policy
from .review import review_policy
from .review_runner import ReviewFixture


class BuyerFixture(ReviewFixture):
    """Known deterministic SDK tool sequence, not a learned purchasing policy."""

    def __init__(self, policy: Policy):
        super().__init__()
        self.policy = policy

    def get_config(self) -> dict[str, Any]:
        return {"model_id": "offline-b3-fixture"}

    async def stream(
        self, messages: Any, tool_specs: Any = None, system_prompt: Any = None, **kwargs: Any
    ) -> Any:
        assert canonical(self.policy.__dict__) in system_prompt
        index = self.calls
        self.calls += 1
        results = []
        for message in messages:
            for block in message["content"]:
                if "toolResult" in block:
                    content = block["toolResult"]["content"][0]
                    try:
                        results.append(content.get("json") or json.loads(content.get("text", "{}")))
                    except (ValueError, TypeError):
                        results.append({})
        steps = ["observe_world"] + ["get_quotes"] * (
            6 if self.policy.refresh_quote_before_order else 3
        )
        steps += ["create_order"]
        if self.policy.refresh_quote_before_order:
            orders = [r for r in results if isinstance(r, dict) and "due_tick" in r]
            waits = math.ceil(orders[-1]["lead_ticks"] / self.policy.wait_ticks) if orders else 3
            steps += ["authorize_payment"] + ["wait_for_updates"] * waits + ["get_inventory"]
        name = steps[index] if index < len(steps) else ""
        data: Json = {}
        if name == "get_quotes":
            data = {"supplier": ["A", "B", "C"][(index - 1) % 3], "items": {"tent": 3, "light": 6}}
        elif name == "create_order":
            quotes = {
                r["supplier"]: r
                for r in results
                if isinstance(r, dict) and "amount" in r and "supplier" in r
            }
            chosen = min(quotes.values(), key=lambda r: r["amount"])
            data = {"quote_id": chosen["id"], "idempotency_key": "fixture-buy"}
        elif name == "authorize_payment":
            data = {"order_id": results[-1]["id"], "idempotency_key": "fixture-pay"}
        elif name == "wait_for_updates":
            data = {"ticks": self.policy.wait_ticks}
        yield {"messageStart": {"role": "assistant"}}
        if name:
            yield {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {"toolUse": {"toolUseId": f"call-{index}", "name": name}},
                }
            }
            yield {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"toolUse": {"input": json.dumps(data)}},
                }
            }
        else:
            yield {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"text": "Known SDK fixture ended; inspect independent evidence."},
                }
            }
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "tool_use" if name else "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
                "metrics": {"latencyMs": 1},
            }
        }


class ReviewerFixture(ReviewFixture):
    def get_config(self) -> dict[str, Any]:
        return {"model_id": "offline-b3-fixture"}

    def answer(self, messages: Any) -> str:
        value = json.loads(super().answer(messages))
        payload = json.loads(messages[-1]["content"][0]["text"])
        if value["decision"] == "keep" and any(
            e["independent_verdict"]["status"] != "COMPLETE" for e in payload["experiments"]
        ):
            value["reason"] = "Known evidence remains incomplete; no further fixture revision."
        return json.dumps(value)


def run_b3(
    buyer_factory: Callable[[Policy], Model],
    reviewer_factory: Callable[[int], Model],
    settings: ModelSettings,
    directory: Path,
    scenario: Json,
    scope: str,
) -> Json:
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    parent = World(directory / "parent")
    parent.create_run("parent", scenario, environment="operating-test")
    original = parent.snapshot("parent")
    ledger = UsageLedger(
        directory / "usage.sqlite3",
        "b3-session",
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
        "scope": scope,
        "status": "STARTED",
        "promoted": False,
        "efficacy_verified": False,
        "held_out_evaluation_verified": False,
    }
    models: list[Model] = []

    def fresh(model: Model) -> Model:
        if any(model is old for old in models):
            raise ContractError("B3_MODEL_INSTANCE_REUSED")
        models.append(model)
        return model

    def buy(policy: Policy, destination: Path, eid: str, role: str) -> Path:
        model_experiment(
            parent,
            "parent",
            destination,
            eid,
            policy,
            scenario,
            fresh(buyer_factory(policy)),
            settings,
            ledger,
            role,
            scope,
        )
        return destination / "experiment.json"

    try:
        initial_policy = Policy(refresh_quote_before_order=False)
        initial = buy(initial_policy, directory / "initial", "initial", "buyer_initial")
        report["initial_artifact_sha256"] = hashlib.sha256(initial.read_bytes()).hexdigest()
        verify_attribution(json.loads(initial.read_text()), ledger, "buyer_initial")
        review = review_policy(
            lambda number: fresh(reviewer_factory(number)),
            settings,
            directory / "review",
            initial_policy,
            {"initial": initial},
            lambda policy, destination, eid: buy(policy, destination, eid, "buyer_candidate"),
            scope=scope,
            shared_ledger=ledger,
            model_reevaluator=True,
        )
        report["review_report_sha256"] = hashlib.sha256(
            (directory / "review/report.json").read_bytes()
        ).hexdigest()
        report["status"] = review["status"]
        if "error" in review:
            report["error"] = review["error"]
    except Exception as exc:
        report["status"] = "REJECTED" if isinstance(exc, ContractError) else "ERROR"
        report["error"] = exc.code if isinstance(exc, ContractError) else type(exc).__name__
    finally:
        report["usage"] = ledger.report()
        report["parent_unchanged"] = parent.snapshot("parent") == original
        if not report["parent_unchanged"]:
            report.update(status="REJECTED", error="PARENT_WORLD_CHANGED")
        root = Path(__file__).resolve().parents[3]
        report["source_hashes"] = {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                Path(__file__).with_name("model_experiment.py"),
                Path(__file__).with_name("review.py"),
                Path(__file__).with_name("policy.py"),
                Path(__file__).with_name("review_runner.py"),
                root / "src/rehearsal/agents/runner.py",
                root / "src/rehearsal/agents/metering.py",
                root / "src/rehearsal/agents/executor.py",
                root / "src/rehearsal/world/fork.py",
                root / "src/rehearsal/evaluation/verifier.py",
            ]
        }
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline-fixture", action="store_true")
    mode.add_argument(
        "--execute", action="store_true", help="Call paid buyer/reviewer on the known practice case"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.offline_fixture:
        settings = ModelSettings(
            "offline",
            "offline",
            "offline-b3-fixture",
            RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
            100000,
            max_model_calls=32,
        )
    else:
        try:
            settings = read_settings(root)
        except ValueError as exc:
            print(str(exc))
            return 2
        if not args.execute:
            print("PASS: B3 settings parsed; no AWS client or model call. Rates unverified.")
            return 0
    os.umask(0o077)
    directory = root / ".local/experiments" / identifier("b3")
    report = run_b3(
        (lambda p: BuyerFixture(p))
        if args.offline_fixture
        else (lambda _: bedrock_model(settings)),
        (lambda _: ReviewerFixture())
        if args.offline_fixture
        else (lambda _: bedrock_model(settings)),
        settings,
        directory,
        json.loads((root / "scenarios/normal-v1.json").read_text()),
        "offline-scripted-model" if args.offline_fixture else "live-model",
    )
    print(f"{report['status']}: {directory}; no promotion or efficacy claim.")
    if args.offline_fixture and report["status"] == "CANDIDATE_EVALUATED_NOT_PROMOTED":
        candidate = json.loads(
            (directory / "review/round-1/reexperiment/experiment.json").read_text()
        )
        if candidate["verdict"]["status"] != "COMPLETE":
            print("FAIL: known fixture candidate did not deliver the goal")
            return 1
    return 0 if report["status"] in {"CANDIDATE_EVALUATED_NOT_PROMOTED", "NO_CHANGE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
