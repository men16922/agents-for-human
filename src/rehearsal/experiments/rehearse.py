"""Known CW04 counterexample plumbing; not measured model Peer Review."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import cast

from rehearsal.agents.executor import purchasing_tools
from rehearsal.evaluation.verifier import verify, verify_export
from rehearsal.world import World
from rehearsal.world.fork import fork_world
from rehearsal.world.storage import ContractError, Json, identifier

from .policy import Policy, record_revision


def experiment(
    parent: World,
    parent_run_id: str,
    directory: Path,
    experiment_id: str,
    policy: Policy,
    scenario: Json,
) -> Json:
    """Apply a data policy through the same purchasing tools as the SDK executor."""
    child, manifest = fork_world(parent, parent_run_id, directory, experiment_id, policy.version)
    if any(e["event_type"].startswith("order.") for e in child.shop.events(experiment_id)):
        raise ContractError("COUNTEREXAMPLE_REQUIRES_PREPURCHASE_SNAPSHOT")
    tools = {t.tool_name: t for t in purchasing_tools(child, experiment_id)}
    observed = cast(Callable[..., Json], tools["observe_world"])()
    trace: list[Json] = []
    rejection = None

    def call(name: str, **arguments: object) -> Json:
        result = cast(Callable[..., Json], tools[name])(**arguments)
        trace.append({"tool": name, "arguments": arguments, "result": result})
        return result

    def quotes() -> list[Json]:
        return [
            call("get_quotes", supplier=supplier, items=observed["goal"]["items"])
            for supplier in observed["suppliers"][: policy.max_quote_candidates]
        ]

    try:
        candidates = quotes()
        # Administrator-controlled known counterexample, never a purchasing tool.
        child.shop.change_price(experiment_id, "A", "tent", 100)
        if policy.refresh_quote_before_order:
            candidates = quotes()
        field = "amount" if policy.supplier_preference == "lowest_total" else "lead_ticks"
        selected = min(candidates, key=lambda q: (q[field], q["supplier"]))
        order = call("create_order", quote_id=selected["id"], idempotency_key="supplies")
        call("authorize_payment", order_id=order["id"], idempotency_key="payment")
        while child.shop.run(experiment_id)["tick"] < observed["goal"]["deadline_tick"]:
            state = call("get_inventory")
            if all(
                state["received"].get(item, 0) >= qty
                for item, qty in observed["goal"]["items"].items()
            ):
                break
            call(
                "wait_for_updates",
                ticks=min(policy.wait_ticks, observed["goal"]["deadline_tick"] - state["tick"]),
            )
    except ContractError as exc:
        rejection = exc.code
        trace.append({"rejected": exc.code})
    child.advance(experiment_id, observed["goal"]["deadline_tick"])
    evidence_path = directory / "evidence.json"
    verdict = verify(directory, experiment_id, scenario, export_to=evidence_path)
    assert verify_export(evidence_path) == verdict
    report = {
        "experiment_id": experiment_id,
        "policy_version": policy.version,
        "policy": asdict(policy),
        "snapshot_sha256": manifest["snapshot_sha256"],
        "scope": "known-scripted-counterexample-not-model-review",
        "rejection": rejection,
        "verdict": verdict.as_dict(),
        "tool_trace": trace,
        "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
    }
    (directory / "experiment.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    directory = root / ".local/experiments" / identifier("cw04")
    scenario = json.loads((root / "scenarios/normal-v1.json").read_text())
    parent = World(directory / "parent")
    parent.create_run("parent", scenario, environment="operating-test")
    baseline, revised = Policy(refresh_quote_before_order=False), Policy()
    before = experiment(parent, "parent", directory / "before", "before", baseline, scenario)
    review = {
        "review_id": "known-price-change-review",
        "round": 1,
        "reviewer_kind": "scripted-fixture",
        "counterexamples": ["before"],
        "reason": "The quote went stale; refresh candidate quotes before creating the order.",
    }
    revision_path = record_revision(
        directory / "revisions",
        baseline,
        revised,
        review,
        {"before": directory / "before/experiment.json"},
    )
    after = experiment(parent, "parent", directory / "after", "after", revised, scenario)
    assert before["snapshot_sha256"] == after["snapshot_sha256"]
    assert before["verdict"]["status"] == "FAILED" and before["rejection"] == "STALE_QUOTE"
    assert after["verdict"]["status"] == "COMPLETE" and after["verdict"]["spent"] == 380
    report = {
        "scope": "CW04-known-scripted-policy-reexperiment-not-Peer-Review-effect",
        "before": before["experiment_id"],
        "before_experiment_sha256": hashlib.sha256(
            (directory / "before/experiment.json").read_bytes()
        ).hexdigest(),
        "after_experiment_sha256": hashlib.sha256(
            (directory / "after/experiment.json").read_bytes()
        ).hexdigest(),
        "snapshot_sha256": before["snapshot_sha256"],
        "after": after["experiment_id"],
        "revision_sha256": hashlib.sha256(revision_path.read_bytes()).hexdigest(),
        "policy_diff": json.loads(revision_path.read_text())["diff"],
        "reexperiment_status": "KNOWN_CASE_PASSED_NOT_PROMOTED",
        "parent_unchanged": parent.shop.run("parent")["tick"] == 0
        and parent.payments.balance("parent")["spent"] == 0,
    }
    assert report["parent_unchanged"]
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: fork -> counterexample -> policy diff -> reexperiment. Evidence: {directory}")


if __name__ == "__main__":
    main()
