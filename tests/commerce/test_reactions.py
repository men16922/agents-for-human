import asyncio
import copy
import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from rehearsal.agents.metering import RateCard
from rehearsal.agents.runner import ModelSettings
from rehearsal.commerce.change_inbox import ChangeInbox, meaning
from rehearsal.commerce.model_runner import execute_http
from rehearsal.commerce.observations import ObservationJournal
from rehearsal.commerce.reaction import Reactions, ReactionSettings
from rehearsal.experiments.frozen import freeze
from rehearsal.experiments.policy import Policy
from rehearsal.experiments.review_runner import ReviewFixture
from rehearsal.operating.client import OperatingClient
from rehearsal.world.storage import ContractError

ROOT = Path(__file__).parents[2]


def snapshot(tick=0):
    return {
        "run_id": "reactive",
        "goal": {"items": {"tent": 3}, "recipient": "venue", "deadline_tick": 60},
        "tick": tick,
        "clock_mode": "operating-one-second-ticks",
        "inventory": {"tent": 0},
        "balance": {"budget": 500, "spent": 0, "reserved": 0, "available": 500},
        "suppliers": ["A", "B"],
        "commerce": {
            "receipt_status": "OBSERVED",
            "catalog": {
                "source": "medusa-store-sales-channel",
                "status": "OBSERVED",
                "offers": [
                    {
                        "supplier": s,
                        "item": "tent",
                        "status": "OBSERVED",
                        "stock": 10,
                        "unit_price": p,
                        "currency": "usd",
                        "inventory_managed": True,
                        "backorder": False,
                    }
                    for s, p in [("A", 60), ("B", 70)]
                ],
            },
            "orders": {"status": "OBSERVED", "total": 0, "truncated": False, "items": []},
        },
    }


def publish(journal, value):
    journal.record("reactive", value, 1000 + value["tick"])
    journal.publish(1000 + value["tick"])


def test_clock_only_and_collection_order_do_not_request_replanning(tmp_path):
    journal = ObservationJournal(tmp_path / "journal", ["reactive"])
    inbox = ChangeInbox("reactive", lambda s: s)
    initial = snapshot()
    publish(journal, initial)
    inbox.ingest(journal.read("reactive", 0, 1000))
    inbox.acknowledge(initial, inbox.capture())
    later = snapshot(1)
    later["suppliers"].reverse()
    later["commerce"]["catalog"]["offers"].reverse()
    assert meaning(initial) == meaning(later)
    publish(journal, later)
    inbox.ingest(journal.read("reactive", inbox.cursor(), 1001))
    assert not inbox.changed.is_set() and inbox.report()["version"] == 2


def test_processing_keeps_newest_change_and_delayed_duplicate_never_rolls_it_back(tmp_path):
    journal = ObservationJournal(tmp_path / "journal", ["reactive"])
    inbox = ChangeInbox("reactive", lambda s: s)
    initial = snapshot()
    publish(journal, initial)
    inbox.ingest(journal.read("reactive", 0, 1000))
    captured = inbox.capture()
    changed = snapshot(1)
    changed["commerce"]["catalog"]["offers"][0]["stock"] = 0
    publish(journal, changed)
    first = journal.read("reactive", inbox.cursor(), 1001)
    inbox.ingest(first)
    newest = copy.deepcopy(changed)
    newest["tick"] = 2
    newest["commerce"]["catalog"]["offers"][1]["unit_price"] = 80
    publish(journal, newest)
    inbox.ingest(journal.read("reactive", inbox.cursor(), 1002))
    inbox.acknowledge(initial, captured)
    assert inbox.changed.is_set() and inbox.latest == newest
    eid = first["events"][0]["event"]["event_id"]
    journal.replay("reactive", eid, 1003, copies=2)
    journal.publish(1003)
    inbox.ingest(journal.read("reactive", inbox.cursor(), 1003))
    assert inbox.latest == newest and inbox.report()["counts"]["duplicate"] == 2
    inbox.acknowledge(newest, inbox.capture())
    assert not inbox.changed.is_set()


def test_retention_reset_is_a_newest_state_and_run_scope_is_checked(tmp_path):
    journal = ObservationJournal(tmp_path / "journal", ["reactive"], retention=1)
    inbox = ChangeInbox("reactive", lambda s: s)
    for tick in range(4):
        publish(journal, snapshot(tick))
    batch = journal.read("reactive", 0, 1003)
    assert batch["reset"]
    inbox.ingest(batch)
    assert inbox.latest == snapshot(3) and inbox.cursor() == 4
    wrong = copy.deepcopy(batch)
    wrong["snapshot_event"]["snapshot"]["run_id"] = "another"
    with pytest.raises(ContractError):
        inbox.ingest(wrong)
    assert inbox.latest == snapshot(3)


class ChangingFixture(ReviewFixture):
    def __init__(self, change, wait_for_poll, missing_usage=False):
        super().__init__()
        self.change, self.wait_for_poll = change, wait_for_poll
        self.missing_usage = missing_usage
        self.contexts = []

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        index = self.calls
        self.calls += 1
        self.contexts.append(copy.deepcopy(messages))
        if index == 1:
            self.change()
            deadline = time.monotonic() + 3
            while not self.wait_for_poll.is_set() and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert self.wait_for_poll.is_set(), "Background consumer did not progress during model"
        steps = [
            ("get_quotes", {"supplier": "A", "items": {"tent": 3}}),
            ("create_order", {"quote_id": "quote-A", "idempotency_key": "old-plan"}),
            ("get_quotes", {"supplier": "B", "items": {"tent": 3}}),
            ("create_order", {"quote_id": "quote-B", "idempotency_key": "new-plan"}),
            ("authorize_payment", {"order_id": "order-B", "idempotency_key": "pay-B"}),
            ("observe_world", {}),
        ]
        name, data = steps[index] if index < len(steps) else ("", {})
        yield {"messageStart": {"role": "assistant"}}
        if name:
            yield {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {"toolUse": {"toolUseId": f"fixture-{index}", "name": name}},
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
                    "delta": {"text": "Known scripted replan ended."},
                }
            }
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "tool_use" if name else "end_turn"}}
        if not self.missing_usage:
            yield {
                "metadata": {
                    "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
                    "metrics": {"latencyMs": 1},
                }
            }


@pytest.fixture
def reactive(tmp_path):
    journal = ObservationJournal(tmp_path / "journal", ["reactive"])
    value = snapshot()
    publish(journal, value)
    lock = threading.RLock()
    observed = threading.Event()
    posts = []

    def change():
        with lock:
            value["tick"] = 1
            value["commerce"]["catalog"]["offers"][0]["stock"] = 0
            publish(journal, value)

    def handler(request):
        assert request.headers["Authorization"] == "Bearer local-reactive-buyer"
        with lock:
            path = request.url.path.rsplit("/", 1)[-1]
            if path == "observations":
                result = journal.read(
                    "reactive", int(request.url.params["after"]), 1000 + value["tick"]
                )
                if value["tick"] == 1:
                    observed.set()
                return httpx.Response(200, json=result)
            if path == "snapshot":
                return httpx.Response(200, json=copy.deepcopy(value))
            body = json.loads(request.content)
            posts.append((path, body))
            if path == "quotes":
                return httpx.Response(
                    200,
                    json={
                        "id": "quote-" + body["supplier"],
                        "supplier": body["supplier"],
                        "items": body["items"],
                        "amount": 210,
                        "expires_tick": 50,
                    },
                )
            if path == "orders":
                assert body["quote_id"] == "quote-B", "Stale plan reached the backend"
                order = {
                    "id": "order-B",
                    "run_id": "reactive",
                    "supplier": "B",
                    "items": {"tent": 3},
                    "amount": 210,
                    "status": "ACCEPTED",
                    "payment_status": "NOT_STARTED",
                    "created_tick": value["tick"],
                }
                value["commerce"]["orders"].update(total=1, items=[order])
                publish(journal, value)
                return httpx.Response(200, json=order)
            assert path == "payments"
            value["inventory"]["tent"] = 3
            value["balance"].update(spent=210, available=290)
            value["commerce"]["orders"]["items"][0].update(
                status="DELIVERED", payment_status="SETTLED"
            )
            publish(journal, value)
            return httpx.Response(200, json={"status": "SETTLED"})

    client = OperatingClient("http://127.0.0.1:18001", "reactive", "local-reactive-buyer")
    client.http.close()
    client.http = httpx.Client(
        base_url="http://127.0.0.1:18001",
        headers={"Authorization": "Bearer local-reactive-buyer"},
        transport=httpx.MockTransport(handler),
    )
    settings = ModelSettings(
        "offline",
        "offline",
        "offline-review-fixture",
        RateCard("1", "2", "0", "0", "fictional"),
        100000,
        max_model_calls=16,
        max_tool_calls=16,
    )
    policy = freeze(Policy(), tmp_path / "policy.json", ROOT)

    def run(max_replans=8, missing_usage=False, factory=ChangingFixture, **limits):
        model = factory(change, observed, missing_usage)
        report = execute_http(
            model,
            replace(settings, **limits),
            client,
            tmp_path / "execution",
            value["goal"],
            500,
            policy,
            "offline-scripted-model",
            reaction_settings=ReactionSettings(max_replans),
        )
        return report, model

    yield run, posts, tmp_path / "execution", value, client
    client.close()


def test_sdk_waiting_model_sees_change_rejects_stale_post_and_replans_with_shared_meter(reactive):
    run, posts, directory, _, _ = reactive
    result, model = run()
    assert result["runtime_status"] == "COMPLETED" and result["runtime_accounted"]
    assert result["reactions"]["blocked_effects"] == 1
    assert result["reactions"]["replans"] == 3
    assert result["reactions"]["worker_stopped"]
    assert [b["quote_id"] for p, b in posts if p == "orders"] == ["quote-B"]
    assert len([p for p, _ in posts if p == "payments"]) == 1
    assert "OBSERVATION_CHANGED_REPLAN" in json.dumps(model.contexts[2])
    update = json.loads(model.contexts[2][-1]["content"][-1]["text"])
    assert update["snapshot"]["commerce"]["catalog"]["offers"][0]["stock"] == 0
    usage = result["usage"]
    assert len(usage["calls"]) == model.calls == 7 and usage["recorded_micro_usd"] == 196
    assert usage["calls"][0]["projected_input_tokens"] > 1500
    assert all(c["execution_id"] == "reactive" for c in usage["calls"])
    assert "local-reactive-buyer" not in (directory / "observations.jsonl").read_text()
    assert not result["success"] and result["transaction_status"] == "NOT_VERIFIED"


def test_replan_limit_prevents_next_model_and_payment_but_keeps_ledger(reactive):
    run, posts, _, _, _ = reactive
    result, model = run(max_replans=1)
    assert result["stop_reason"] == "OBSERVATION_REPLAN_LIMIT"
    assert result["runtime_status"] == "LIMITED" and model.calls == 4
    assert not any(p == "payments" for p, _ in posts)
    assert result["usage"]["recorded_micro_usd"] == 112


def test_reactions_do_not_reset_existing_model_call_limit(reactive):
    run, posts, _, _, _ = reactive
    result, model = run(max_model_calls=2)
    assert result["stop_reason"] == "MODEL_CALL_LIMIT" and model.calls == 2
    assert not any(p in {"payments", "orders"} for p, _ in posts)


def test_missing_usage_keeps_reservation_and_prevents_replanning(reactive):
    run, posts, _, _, _ = reactive
    result, model = run(missing_usage=True)
    assert model.calls == 1 and not result["runtime_accounted"]
    assert result["usage"]["calls"][0]["status"] == "USAGE_UNKNOWN"
    assert result["execution_usage"]["unresolved_reserved_micro_usd"] > 0
    assert not any(p in {"payments", "orders"} for p, _ in posts)


@pytest.mark.parametrize("value", [0, -1, 33, True, 1.5])
def test_replan_settings_are_bounded(value):
    with pytest.raises((ValueError, ContractError)):
        ReactionSettings(value)


@pytest.mark.parametrize(
    "damage,reason",
    [
        ("clock", "QUOTE_EXPIRED_RECHECK"),
        ("basis", "QUOTE_BASIS_CHANGED_RECHECK"),
        ("unknown", "OBSERVATION_UNAVAILABLE_RECHECK"),
        ("deadline", "OBSERVATION_DEADLINE_REACHED"),
        ("stock", "OBSERVATION_CHANGED_REPLAN"),
    ],
)
def test_effect_recheck_rejects_expired_old_basis_unknown_and_changed_state(
    reactive, damage, reason
):
    _, posts, directory, value, client = reactive
    directory.mkdir()
    control = Reactions(client, lambda s: s, ReactionSettings(), directory)
    control.basis = meaning(value)
    control.quotes["old"] = {"expires_tick": 10}
    control.quote_basis["old"] = control.basis
    if damage == "clock":
        value["tick"] = 10
    elif damage == "basis":
        control.quote_basis["old"] = "older-decision"
    elif damage == "unknown":
        value["commerce"]["receipt_status"] = "UNAVAILABLE"
        control.basis = meaning(value)
    elif damage == "deadline":
        value["tick"] = 60
    else:
        value["commerce"]["catalog"]["offers"][0]["stock"] = 0
    with pytest.raises(ContractError, match=reason):
        control.guard_effect("orders", {"quote_id": "old"})
    assert posts == [] and control.blocked_effects == 1


def test_model_observation_audit_tamper_fails_attestation_before_export_lookup(reactive):
    from rehearsal.commerce.model_runner import attest

    run, _, directory, value, _ = reactive
    run()
    selected = directory / "selection.json"
    selected.write_text(json.dumps({"expected_goal": value["goal"], "expected_budget": 500}))
    with (directory / "observations.jsonl").open("a") as output:
        output.write(" ")
    with pytest.raises(ValueError, match="observations changed"):
        attest(directory, selected)


def test_semantic_event_after_end_turn_wakes_same_agent_and_existing_ledger(reactive):
    run, posts, _, value, _ = reactive

    class EndsEarly(ChangingFixture):
        async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
            self.calls += 1
            self.contexts.append(copy.deepcopy(messages))
            if self.calls == 1:

                async def later():
                    await asyncio.sleep(0.05)
                    self.change()  # Independent fixture world mutation after end_turn.

                self.task = asyncio.create_task(later())
            else:
                # Synthetic seller completion only terminates this wakeup test; no trade proof.
                value["inventory"]["tent"] = 3
            yield {"messageStart": {"role": "assistant"}}
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "Waiting."}}}
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "end_turn"}}
            yield {
                "metadata": {
                    "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
                    "metrics": {"latencyMs": 1},
                }
            }

    report, model = run(factory=EndsEarly, timeout_seconds=4)
    assert report["runtime_status"] == "COMPLETED" and model.calls == 2
    assert len(model.contexts[1]) > len(model.contexts[0])
    assert report["reactions"]["replans"] == 1
    assert len(report["usage"]["calls"]) == 2 and report["usage"]["recorded_micro_usd"] == 56
    assert model.task.done() and posts == [] and not report["success"]


def test_early_end_turn_with_only_clock_progress_does_not_call_model_again(reactive):
    run, posts, _, value, _ = reactive

    class EndsAtClock(ChangingFixture):
        async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
            self.calls += 1

            async def ticks():
                value["tick"] = 1
                await asyncio.sleep(0.7)
                value["tick"] = 60

            self.task = asyncio.create_task(ticks())
            yield {"messageStart": {"role": "assistant"}}
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "Waiting."}}}
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "end_turn"}}
            yield {
                "metadata": {
                    "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
                    "metrics": {"latencyMs": 1},
                }
            }

    report, model = run(factory=EndsAtClock, timeout_seconds=4)
    assert report["runtime_status"] == "INCOMPLETE" and model.calls == 1
    assert report["reaction_stop"] == "DEADLINE" and report["reactions"]["replans"] == 0
    assert model.task.done() and posts == []
