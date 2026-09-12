"""Explicit CW04 review invocation; default is settings-only preflight."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from strands.models.model import Model

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings, bedrock_model, read_settings
from rehearsal.world import World
from rehearsal.world.storage import Json, identifier

from .policy import Policy
from .rehearse import experiment
from .review import review_policy


class ReviewFixture(Model):
    """Deterministic SDK fixture for plumbing; never a model judgment result."""

    def __init__(self) -> None:
        self.calls = 0

    def update_config(self, **kwargs: Any) -> None:
        pass

    def get_config(self) -> dict[str, Any]:
        return {"model_id": "offline-review-fixture"}

    async def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError
        yield

    def answer(self, messages: Any) -> str:
        payload = json.loads(messages[-1]["content"][0]["text"])
        policy = Policy.parse(payload["policy"])
        revise = not policy.refresh_quote_before_order
        return json.dumps(
            {
                "decision": "revise" if revise else "keep",
                "reason": "Known stale quote requires refresh."
                if revise
                else "Known case passed; no new evidence for a change.",
                "counterexamples": [payload["experiments"][0]["experiment_id"]] if revise else [],
                "candidate_policy": asdict(Policy()) if revise else None,
            }
        )

    async def stream(
        self, messages: Any, tool_specs: Any = None, system_prompt: Any = None, **kwargs: Any
    ) -> Any:
        self.calls += 1
        yield {"messageStart": {"role": "assistant"}}
        yield {
            "contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": self.answer(messages)}}
        }
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
                "metrics": {"latencyMs": 1},
            }
        }


def known_review(directory: Path, settings: ModelSettings, offline: bool) -> Json:
    scenario = json.loads(
        (Path(__file__).resolve().parents[3] / "scenarios/normal-v1.json").read_text()
    )
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    parent = World(directory / "parent")
    parent.create_run("parent", scenario, environment="operating-test")
    snapshot = parent.snapshot("parent")
    before = Policy(refresh_quote_before_order=False)
    experiment(parent, "parent", directory / "before", "before", before, scenario)

    def reevaluate(policy: Policy, destination: Path, eid: str) -> Path:
        experiment(parent, "parent", destination, eid, policy, scenario)
        return destination / "experiment.json"

    report = review_policy(
        lambda _: ReviewFixture() if offline else bedrock_model(settings),
        settings,
        directory / "review",
        before,
        {"before": directory / "before/experiment.json"},
        reevaluate,
        scope="offline-scripted-model" if offline else "live-model",
    )
    assert parent.snapshot("parent") == snapshot, "Reviewer/reexperiment changed the source world"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--offline-fixture", action="store_true")
    modes.add_argument(
        "--execute",
        action="store_true",
        help="Call configured paid reviewer; reevaluator is scripted",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.offline_fixture:
        settings = ModelSettings(
            "offline",
            "offline",
            "offline-review-fixture",
            RateCard("1", "2", "0", "0", "fictional offline fixture rates"),
            100000,
            input_limit=8000,
            output_limit=1024,
        )
    else:
        try:
            settings = read_settings(root)
        except ValueError as exc:
            print(str(exc))
            return 2
        if not args.execute:
            print(
                "PASS: reviewer settings parsed. No AWS client/model call; "
                "rates/permissions unverified."
            )
            return 0
    os.umask(0o077)
    directory = root / ".local/experiments" / identifier("cw04_review")
    report = known_review(directory, settings, args.offline_fixture)
    print(f"{report['status']}: {directory}; no policy promotion or efficacy claim.")
    return 0 if report["status"] in {"CANDIDATE_EVALUATED_NOT_PROMOTED", "NO_CHANGE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
