"""Serve reverified real retained exports; reject tampering and scope mismatch."""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rehearsal.evidence_view import MAX_ARTIFACT_BYTES, evidence_routes, review_export

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evidence/cw06-observer/observer-evidence.json"
RUN = "cw00-3f3dac1b04a9-buyer"
GOAL = {"items": {"tent": 3, "light": 6}, "deadline_tick": 120, "recipient": "venue"}


def select(tmp_path, evidence=None, **changes):
    raw = SOURCE.read_bytes() if evidence is None else json.dumps(evidence).encode()
    artifact = tmp_path / "evidence.json"
    artifact.write_bytes(raw)
    manifest = {
        "run_id": RUN,
        "expected_goal": GOAL,
        "expected_budget": 500,
        "artifact_path": "evidence.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    manifest.update(changes)
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(manifest))
    return path, artifact


def test_real_export_recomputed_without_saved_success_and_private_fields(tmp_path):
    path, artifact = select(tmp_path)
    app = FastAPI()
    app.include_router(evidence_routes(path, RUN))
    with TestClient(app) as client:
        response = client.get("/observer/evidence?path=/etc/passwd&run_id=another")
        result = response.json()
        assert response.headers["cache-control"] == "no-store"
        assert result["status"] == "VERIFIED"
        assert result["verdict"]["status"] == "COMPLETE"
        assert result["verdict"]["spent"] == 380
        assert result["verdict"]["received_on_time"] == {"tent": 3, "light": 6}
        assert result["artifact"]["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
        for private in (str(tmp_path), "customer_id", "external_orders", "shipping_address"):
            assert private not in response.text
        assert client.post("/observer/evidence").status_code == 405


@pytest.mark.parametrize("run", [None, "another"])
def test_selection_cannot_override_bound_run(tmp_path, run):
    path, _ = select(tmp_path)
    assert review_export(path, run)["reason"] == "EVIDENCE_RUN_MISMATCH"


def test_missing_config_artifact_and_removed_file_never_keep_previous_success(tmp_path):
    assert review_export(None, RUN)["status"] == "UNCONFIGURED"
    assert review_export(tmp_path / "missing", RUN)["status"] == "PENDING"
    path, artifact = select(tmp_path)
    assert review_export(path, RUN)["verdict"]["status"] == "COMPLETE"
    artifact.unlink()
    assert review_export(path, RUN)["status"] == "PENDING"
    assert review_export(path, RUN)["verdict"] is None


def test_modified_bytes_need_explicit_new_digest(tmp_path):
    path, artifact = select(tmp_path)
    artifact.write_bytes(artifact.read_bytes() + b"\n")
    result = review_export(path, RUN)
    assert result["reason"] == "EVIDENCE_HASH_MISMATCH"
    assert result["verdict"] is None


@pytest.mark.parametrize("mutation", ["budget", "goal", "run", "capture", "quantity", "receipt"])
def test_rehashing_tampered_evidence_does_not_make_it_complete(tmp_path, mutation):
    evidence = json.loads(SOURCE.read_text())
    evidence["verdict"] = {"status": "COMPLETE"}
    evidence["passed"] = True
    if mutation == "budget":
        evidence["binding"]["budget"] = 600
    elif mutation == "goal":
        evidence["binding"]["goal"]["items"]["tent"] = 1
    elif mutation == "run":
        evidence["binding"]["run_id"] = "other"
    elif mutation == "capture":
        evidence["external_orders"][0]["payment_collections"][0]["payments"][0]["captures"] = []
    elif mutation == "quantity":
        evidence["external_orders"][0]["items"][0]["detail"]["delivered_quantity"] = 0
    elif mutation == "receipt":
        evidence["tables"]["purchases"][0]["received_tick"] = None
    path, _ = select(tmp_path, evidence)
    result = review_export(path, RUN)
    assert result["verdict"] is None or result["verdict"]["status"] != "COMPLETE"


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_budget": True},
        {"expected_budget": 2**53},
        {"expected_budget": 0},
        {"expected_goal": {"items": {}, "deadline_tick": 120, "recipient": "venue"}},
        {"sha256": "not a digest"},
        {"artifact_path": None},
        {"url": "https://example.invalid"},
    ],
)
def test_invalid_selection_has_no_filesystem_or_exception_detail(tmp_path, changes):
    path, _ = select(tmp_path, **changes)
    result = review_export(path, RUN)
    assert result["reason"] == "INVALID_EVIDENCE_SELECTION"
    assert str(tmp_path) not in json.dumps(result)


@pytest.mark.parametrize(
    "raw",
    [
        b"[]",
        b'{"binding":null}',
        b'{"x":1,"x":2}',
        b'{"binding":{},"captured_at_tick":true}',
        b"x" * (MAX_ARTIFACT_BYTES + 1),
    ],
)
def test_malformed_artifact_is_not_success(tmp_path, raw):
    path, artifact = select(tmp_path, sha256=hashlib.sha256(raw).hexdigest())
    artifact.write_bytes(raw)
    result = review_export(path, RUN)
    assert result["status"] == "REJECTED"
    assert result["verdict"] is None


def test_valid_schema_but_incomplete_export_is_unknown(tmp_path):
    evidence = json.loads(SOURCE.read_text())
    del evidence["external_orders"][0]["items"]
    path, _ = select(tmp_path, evidence)
    result = review_export(path, RUN)
    assert result["status"] == "VERIFIED"
    assert result["verdict"]["status"] == "UNKNOWN"


def test_selection_refresh_revalidates_expected_goal_and_ignores_saved_verdict(tmp_path):
    evidence = json.loads(SOURCE.read_text())
    path, _ = select(tmp_path, evidence)
    assert review_export(path, RUN)["verdict"]["status"] == "COMPLETE"
    manifest = json.loads(path.read_text())
    manifest["expected_goal"]["items"]["tent"] = 4
    path.write_text(json.dumps(manifest))
    assert review_export(path, RUN)["verdict"]["status"] == "FAILED"
