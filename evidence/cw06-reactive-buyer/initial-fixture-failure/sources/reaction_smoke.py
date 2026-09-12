#!/usr/bin/env python3
"""Known delayed SDK decision with scheduled actual stock loss and a reactive HTTP buyer."""

import asyncio
import json
import os
import threading
import time

from model_session import ROOT, Session

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.commerce.model_runner import attest, digest, execute_http, write
from rehearsal.commerce.reaction import ReactionSettings
from rehearsal.evaluation.condition_events import verify_events
from rehearsal.evaluation.conditions import verify_conditions
from rehearsal.experiments.frozen import freeze
from rehearsal.experiments.policy import Policy
from rehearsal.experiments.review_runner import ReviewFixture
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN
from rehearsal.world.storage import identifier


class DelayedBuyer(ReviewFixture):
    """Scripted A-to-B recovery, not a model's learned policy or judgment."""

    delayed_call = None

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        index = self.calls
        self.calls += 1
        results, snapshots = [], []
        for message in messages:
            for block in message["content"]:
                if "toolResult" in block:
                    content = block["toolResult"]["content"][0]
                    try:
                        results.append(content.get("json") or json.loads(content.get("text", "{}")))
                    except (TypeError, ValueError):
                        pass
                elif "text" in block:
                    try:
                        value = json.loads(block["text"])
                        if value.get("kind") == "public_condition_update":
                            snapshots.append(value["snapshot"])
                    except (TypeError, ValueError, AttributeError):
                        pass
        quotes = {r["supplier"]: r for r in results if isinstance(r, dict) and "quote_version" in r}
        orders = [r for r in results if isinstance(r, dict) and "due_tick" in r]
        name, data = "", {}
        if index in (0, 2):
            name = "get_quotes"
            data = {"supplier": "A" if index == 0 else "B", "items": {"tent": 3, "light": 6}}
        elif index in (1, 3):
            if index == 1:
                started = time.time()
                await asyncio.sleep(12)
                self.delayed_call = {"started_at": started, "finished_at": time.time()}
            name = "create_order"
            supplier = "A" if index == 1 else "B"
            data = {"quote_id": quotes[supplier]["id"], "idempotency_key": "fixture-" + supplier}
        elif index == 4:
            name = "authorize_payment"
            data = {"order_id": orders[-1]["id"], "idempotency_key": "fixture-payment-B"}
        elif not snapshots or snapshots[-1]["inventory"] != {"tent": 3, "light": 6}:
            name, data = "wait_for_updates", {"ticks": 5}
        yield {"messageStart": {"role": "assistant"}}
        if name:
            yield {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {"toolUse": {"toolUseId": f"reaction-{index}", "name": name}},
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
                    "delta": {"text": "Known reactive fixture ended."},
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


class RecordedClient(OperatingClient):
    def __init__(self, config, directory):
        super().__init__(ORIGIN, config["run_id"], config["buyer_token"], timeout=10)
        self.path = directory / "buyer-http.jsonl"
        self.lock = threading.Lock()

    def request(self, method, path, body=None):
        record = {"method": method, "path": path, "started_at": time.time(), "body": body}
        try:
            value = super().request(method, path, body)
            # Public observations are retained by the runner. HTTP audit needs no response body.
            return value
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            raise
        finally:
            record["finished_at"] = time.time()
            with self.lock, self.path.open("a") as output:
                output.write(json.dumps(record) + "\n")


def main():
    os.umask(0o077)
    path = ROOT / ".local/evaluation" / identifier("reaction")
    path.mkdir(mode=0o700)
    case = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    case["goal"]["deadline_tick"] = 90
    case["events"] = [
        {
            "id": "stock",
            "kind": "stock",
            "at_tick": 10,
            "max_lateness_ticks": 2,
            "supplier": "A",
            "item": "tent",
            "value": 0,
        }
    ]
    frozen = freeze(Policy(), path / "policy.json", ROOT)
    write(path / "case.json", case)
    session = client = worker = None
    stop = threading.Event()
    report = {"passed": False, "real_model_calls": 0, "model_efficacy_verified": False}
    try:
        session = Session(path / "policy.json", fixture=True, case=case)
        sp = session.start()
        report["session"] = str(sp.relative_to(ROOT))
        worker = threading.Thread(target=session.wait, args=(stop,))
        worker.start()
        config = json.loads((sp / "buyer-config.json").read_text())
        initial = json.loads((sp / session.record["conditions_path"]).read_text())
        verified = verify_conditions(initial, case, config["run_id"])
        write(path / "conditions.json", initial)
        client = RecordedClient(config, path)
        settings = ModelSettings(
            "offline",
            "offline",
            "offline-review-fixture",
            RateCard("1", "2", "0", "0", "fictional SDK fixture rates"),
            100000,
            max_model_calls=32,
            max_tool_calls=32,
        )
        model = DelayedBuyer()
        result = execute_http(
            model,
            settings,
            client,
            path / "execution",
            config["expected_goal"],
            config["expected_budget"],
            frozen,
            "offline-scripted-model",
            initial_condition={
                "sha256": digest(path / "conditions.json"),
                "verification": verified,
            },
            reaction_settings=ReactionSettings(8),
        )
        report["delayed_model_call"] = model.delayed_call
        report["runtime"] = result
        stop.set()
        worker.join(5)
        assert not worker.is_alive()
        session.close("REACTION_SMOKE_FINISHED")
        reviewed = attest(path / "execution", sp / "selection.json")
        report["attestation"] = reviewed
        assert reviewed["success"] and reviewed["evidence_review"]["verdict"]["spent"] == 380
        selected = json.loads((sp / "selection.json").read_text())
        evidence = json.loads((sp / selected["artifact_path"]).read_text())
        report["events"] = verify_events(
            evidence["condition_events"],
            case,
            evidence["binding"],
            verified["capture_end_tick"],
            evidence["captured_at_tick"],
        )
        assert report["events"]["status"] == "VERIFIED"
        assert report["events"]["events"][0]["end_tick"] <= result["event_execution_end"]["tick"]
        audit = [
            json.loads(line)
            for line in (path / "execution/observations.jsonl").read_text().splitlines()
        ]
        during = [
            r
            for r in audit
            if r["kind"] == "journal"
            and model.delayed_call["started_at"] <= r["at"] <= model.delayed_call["finished_at"]
            and any(
                o["supplier"] == "A" and o["item"] == "tent" and o["stock"] == 0
                for d in r["value"]["events"]
                for o in d["event"]["snapshot"]["commerce"]["catalog"]["offers"]
            )
        ]
        assert during, "No changed stock observed while the model was pending"
        blocked = [r for r in audit if r["kind"] == "effect_blocked"]
        assert blocked and blocked[0]["value"]["reason"] == "OBSERVATION_CHANGED_REPLAN"
        requests = [
            json.loads(line) for line in (path / "buyer-http.jsonl").read_text().splitlines()
        ]
        posts = [r for r in requests if r["method"] == "POST"]
        assert len([r for r in posts if r["path"] == "orders"]) == 1
        assert len([r for r in posts if r["path"] == "payments"]) == 1
        report.update(
            passed=True,
            changed_journal_batches_during_model=len(during),
            actual_order_posts=1,
            actual_payment_posts=1,
        )
    finally:
        stop.set()
        if worker:
            worker.join(5)
        if session:
            session.close("REACTION_SMOKE_CLEANUP")
        if client:
            client.close()
        write(path / "smoke.json", report)
        print(f"{'PASS' if report['passed'] else 'FAIL'} observed-change reaction: {path}")


if __name__ == "__main__":
    main()
