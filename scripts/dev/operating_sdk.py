"""Explicit real-HTTP SDK smoke with a test-only scripted model; never AWS."""

from __future__ import annotations

import json
import os
import runpy
from pathlib import Path

from rehearsal.agents.executor import Limits, agent_for_tools
from rehearsal.evaluation.verifier import verify
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN, prepare, start, stop
from rehearsal.operating.tools import purchasing_http_tools


def main() -> None:
    os.umask(0o077)
    root = Path(__file__).resolve().parents[2]
    scripted = runpy.run_path(str(root / "tests/agents/test_executor.py"))["ScriptedModel"]

    class HttpScripted(scripted):
        async def stream(self, *args, **kwargs):
            async for event in super().stream(*args, **kwargs):
                delta = event.get("contentBlockDelta", {}).get("delta", {}).get("toolUse", {})
                if delta.get("input") == json.dumps({"ticks": 10}):
                    delta["input"] = json.dumps({"ticks": 3})
                yield event

    directory, credentials, scenario = prepare(root, True)
    process = start(directory)
    client = OperatingClient(ORIGIN, "buyer-one", credentials["runs"]["buyer-one"]["buyer"])
    try:
        limits = Limits()
        result = agent_for_tools(HttpScripted(), purchasing_http_tools(client), limits)(
            "Complete the event-supplies goal."
        )
        usage = dict(result.metrics.accumulated_usage)
        snapshot = client.observe_world()
    finally:
        client.close()
        stop(process)
    verdict = verify(directory, "buyer-one", scenario, export_to=directory / "sdk-evidence.json")
    assert verdict.status == "COMPLETE", verdict
    report = {
        "scope": "real-loopback-server-with-offline-scripted-Strands-model",
        "model_calls_fixture": limits.model_calls,
        "tool_calls": limits.tool_calls,
        "fixture_usage": usage,
        "snapshot": snapshot,
        "verdict": verdict.as_dict(),
    }
    (directory / "sdk-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: SDK -> HTTP tools -> independent worker -> delivery; evidence {directory}")


if __name__ == "__main__":
    main()
