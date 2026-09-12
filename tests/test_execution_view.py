"""Actual retained SDK/Medusa records through a read-only public projection."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rehearsal.execution_view import MAX_ARTIFACT_BYTES, execution_routes, review_execution

ROOT = Path(__file__).resolve().parents[1]
RETAINED = ROOT / "evidence/cw07-reactive-comparison/runs"


def write(path, value):
    path.write_text(json.dumps(value))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(tmp_path, method="B1"):
    directory = tmp_path / "execution"
    shutil.copytree(RETAINED / f"changed-{method}-r1/execution", directory)
    spec = json.loads((directory / "spec.json").read_text())
    chosen = {k: spec[k] for k in ("run_id", "expected_goal", "expected_budget")}
    chosen.update(execution_path="execution", spec_sha256=digest(directory / "spec.json"))
    selection = tmp_path / "selection.json"
    write(selection, chosen)
    return selection, directory, spec["run_id"]


def reseal(directory):
    report_path = directory / "report.json"
    report = json.loads(report_path.read_text())
    report["spec_sha256"] = digest(directory / "spec.json")
    report["observations_sha256"] = digest(directory / "observations.jsonl")
    write(report_path, report)
    path = directory / "execution-manifest.json"
    seal = json.loads(path.read_text())
    seal.update(
        report_sha256=digest(report_path),
        spec_sha256=report["spec_sha256"],
        observations_sha256=report["observations_sha256"],
    )
    write(path, seal)


@pytest.mark.parametrize("method", ["B0", "B1", "B2", "B3"])
def test_retained_four_arms_replay_without_claiming_trade_or_model_success(tmp_path, method):
    selection, _, run = select(tmp_path, method)
    result = review_execution(selection, run)
    assert result["status"] == "SEALED"
    execution = result["execution"]
    assert execution["runtime_status"] == "COMPLETED"
    assert execution["reaction_limit"] == (None if method == "B0" else 8)
    assert execution["audit"]["replans"] == (0 if method == "B0" else 5)
    assert execution["audit"]["blocked_effects"] == (0 if method == "B0" else 1)
    assert result["transaction_verified"] is result["model_efficacy_verified"] is False


def test_api_ignores_browser_paths_is_read_only_and_projects_no_private_payloads(tmp_path):
    selection, directory, run = select(tmp_path)
    report_path = directory / "report.json"
    report = json.loads(report_path.read_text())
    report.update(final_response="SECRET_MODEL_TEXT", error_type="SECRET_ERROR")
    write(report_path, report)
    reseal(directory)
    app = FastAPI()
    app.include_router(execution_routes(selection, run))
    with TestClient(app) as client:
        response = client.get("/observer/execution?path=/etc/passwd&run_id=other")
        assert response.json()["status"] == "SEALED"
        assert response.headers["cache-control"] == "no-store"
        for private in (
            str(tmp_path),
            "SECRET",
            "source_hashes",
            "customer_id",
            "final_response",
            "instruction",
            "supplier",
            "policy",
            "usage",
        ):
            assert private not in response.text
        assert client.post("/observer/execution", json={"path": "/etc/passwd"}).status_code == 405


@pytest.mark.parametrize("name", ["spec.json", "report.json", "observations.jsonl", "tools.jsonl"])
def test_changed_or_missing_sealed_bytes_clear_summary(tmp_path, name):
    selection, directory, run = select(tmp_path)
    path = directory / name
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    assert review_execution(selection, run)["status"] == "REJECTED"
    path.unlink()
    assert review_execution(selection, run)["execution"] is None


@pytest.mark.parametrize("run", [None, "other-run"])
def test_selection_must_match_current_observer(tmp_path, run):
    selection, _, _ = select(tmp_path)
    assert review_execution(selection, run)["reason"] == "EXECUTION_RUN_MISMATCH"


@pytest.mark.parametrize(
    "change",
    [
        {"expected_budget": True},
        {"expected_budget": 2**53},
        {"expected_budget": 501},
        {"expected_goal": {}},
        {"execution_path": None},
        {"spec_sha256": "invalid"},
        {"url": "https://example.invalid"},
    ],
)
def test_invalid_selection_or_scope_returns_no_details(tmp_path, change):
    selection, _, run = select(tmp_path)
    value = json.loads(selection.read_text()) | change
    write(selection, value)
    result = review_execution(selection, run)
    assert result["status"] == "REJECTED"
    assert result["execution"] is None
    assert str(tmp_path) not in json.dumps(result)


def test_unsealed_finished_report_and_partial_tail_remain_provisional(tmp_path):
    selection, directory, run = select(tmp_path)
    (directory / "execution-manifest.json").unlink()
    path = directory / "observations.jsonl"
    path.write_bytes(path.read_bytes() + b'{"kind":"decision_basis","value":')
    result = review_execution(selection, run)
    assert result["status"] == "PROVISIONAL"
    assert result["execution"]["runtime_status"] is None
    assert result["execution"]["stop_reason"] is None
    assert result["execution"]["audit"]["partial_tail"] is True
    assert result["execution"]["audit"]["replans"] == 5
    # A stopped/crashed writer is not promoted to currently running by file age or STARTED.
    report = json.loads((directory / "report.json").read_text())
    report["runtime_status"] = "STARTED"
    write(directory / "report.json", report)
    assert review_execution(selection, run)["status"] == "PROVISIONAL"


@pytest.mark.parametrize("mutation", ["cross_run", "goal", "replan", "counter", "worker", "tail"])
def test_resealing_bad_semantics_does_not_bypass_replay(tmp_path, mutation):
    selection, directory, run = select(tmp_path)
    path = directory / "observations.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    basis = next(row for row in rows if row["kind"] == "decision_basis")["value"]
    if mutation == "cross_run":
        basis["snapshot"]["run_id"] = "other-run"
    elif mutation == "goal":
        basis["snapshot"]["goal"]["items"]["tent"] = 4
    elif mutation == "replan":
        basis["replan"] = True
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    report_path = directory / "report.json"
    report = json.loads(report_path.read_text())
    if mutation == "counter":
        report["reactions"]["blocked_effects"] = 0
    elif mutation == "worker":
        report["reactions"]["worker_stopped"] = False
    elif mutation == "tail":
        path.write_bytes(path.read_bytes()[:-1])
    write(report_path, report)
    reseal(directory)
    assert review_execution(selection, run)["status"] == "REJECTED"


@pytest.mark.parametrize(
    "raw", [b"{}\n", b'{"kind":1,"kind":2}\n', b"[]\n", b"x" * (MAX_ARTIFACT_BYTES + 1)]
)
def test_bad_audit_never_reaches_ui_even_without_seal(tmp_path, raw):
    selection, directory, run = select(tmp_path)
    (directory / "execution-manifest.json").unlink()
    (directory / "observations.jsonl").write_bytes(raw)
    assert review_execution(selection, run)["status"] == "REJECTED"


def test_stop_reason_is_fixed_code_and_report_text_never_leaks(tmp_path):
    selection, directory, run = select(tmp_path)
    path = directory / "report.json"
    for reason, expected in (
        ("OBSERVATION_REPLAN_LIMIT", "OBSERVATION_REPLAN_LIMIT"),
        ("SECRET-CREDENTIAL", "OTHER"),
    ):
        report = json.loads(path.read_text())
        report.update(runtime_status="LIMITED", stop_reason=reason)
        write(path, report)
        reseal(directory)
        result = review_execution(selection, run)
        assert result["status"] == "SEALED"
        assert result["execution"]["stop_reason"] == expected
        assert "SECRET" not in json.dumps(result)


def test_no_selection_or_report_has_no_fabricated_counts(tmp_path):
    assert review_execution(None, None)["status"] == "UNCONFIGURED"
    assert review_execution(tmp_path / "absent.json", None)["status"] == "PENDING"
    selection, directory, run = select(tmp_path)
    (directory / "execution-manifest.json").unlink()
    (directory / "report.json").unlink()
    assert review_execution(selection, run)["status"] == "PENDING"
