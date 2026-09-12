import json
from pathlib import Path

import pytest

from rehearsal.evaluation.pilot import digest, prepare, run_b0, save, summarize

ROOT = Path(__file__).parents[2]


@pytest.fixture
def pilot(tmp_path):
    directory = tmp_path / "pilot"
    prepare(directory, ROOT)
    return directory


def test_roster_exists_before_calls_and_retains_all_absent_arms(pilot):
    report = summarize(pilot)
    assert report["planned_cells"] == 20
    assert report["status_counts"] == {"NOT_RUN": 20}
    assert len(report["cells"]) == 20
    assert all(m["planned"] == 5 for m in report["methods"].values())
    assert all(m["spending_unavailable_cells"] == 5 for m in report["methods"].values())
    assert not report["comparison_complete"]


def test_real_b0_cases_preserve_impossible_case_and_missing_model_arms(pilot):
    result = run_b0(pilot, ROOT)
    assert result == summarize(pilot)
    assert result["status_counts"] == {"COMPLETE": 4, "NOT_RUN": 15, "INCOMPLETE": 1}
    assert result["methods"]["B0"]["independent_complete"] == 4
    assert result["methods"]["B0"]["execution_records"] == 5
    assert result["methods"]["B0"]["planned"] == 5
    assert result["methods"]["B0"]["spending_unavailable_cells"] == 0
    cases = {c["case"]: c for c in result["cells"] if c["method"] == "B0"}
    assert cases["impossible"]["spent"] == 0
    assert cases["impossible"]["reason"] == "NO_EXECUTABLE_QUOTE"
    assert cases["normal"]["spent"] == 310
    assert cases["higher-price"]["spent"] == 380
    assert cases["partial"]["spent"] == 360
    assert not result["comparison_complete"]
    assert not result["model_efficacy_verified"]
    assert not result["held_out_evaluation_verified"]
    with pytest.raises(FileExistsError):
        run_b0(pilot, ROOT)


@pytest.mark.parametrize("damage", ["delete", "edit", "cross-run", "verdict", "wrong-scenario"])
def test_saved_success_cannot_hide_missing_or_modified_evidence(pilot, damage):
    run_b0(pilot, ROOT)
    slot = pilot / "normal-B0"
    evidence = slot / "evidence.json"
    record = json.loads((slot / "result.json").read_text())
    if damage == "delete":
        evidence.unlink()
    elif damage == "edit":
        evidence.write_text("{}")
    elif damage == "verdict":
        record["verdict"]["spent"] = 0
    else:
        raw = json.loads(evidence.read_text())
        if damage == "cross-run":
            raw["run_id"] = "different"
        else:
            raw["scenario"]["goal"]["budget"] += 1
        save(evidence, raw)
        record["evidence_sha256"] = digest(evidence)
    save(slot / "result.json", record)
    report = summarize(pilot)
    assert report["planned_cells"] == 20
    assert report["status_counts"]["INVALID_EVIDENCE"] == 1
    assert report["methods"]["B0"]["independent_complete"] == 3
    assert report["methods"]["B0"]["spending_unavailable_cells"] == 1


def test_crash_and_error_slots_remain_in_execution_denominator(pilot):
    run_b0(pilot, ROOT)
    for name, state in [("normal", "STARTED"), ("partial", "ERROR")]:
        path = pilot / f"{name}-B0/result.json"
        record = json.loads(path.read_text())
        record["execution_status"] = state
        save(path, record)
    report = summarize(pilot)
    assert report["status_counts"]["STARTED"] == report["status_counts"]["ERROR"] == 1
    assert report["methods"]["B0"]["execution_records"] == 5
    assert report["methods"]["B0"]["independent_complete"] == 2
    assert report["methods"]["B0"]["spending_unavailable_cells"] == 2


def test_model_arm_cannot_be_populated_with_renamed_b0_success(pilot):
    run_b0(pilot, ROOT)
    target = pilot / "normal-B3"
    target.mkdir()
    record = json.loads((pilot / "normal-B0/result.json").read_text())
    record.update(method="B3", run_id="normal-B3")
    save(target / "result.json", record)
    report = summarize(pilot)
    assert report["methods"]["B3"]["status_counts"] == {"INVALID_EVIDENCE": 1, "NOT_RUN": 4}
    assert report["methods"]["B3"]["independent_complete"] == 0


def test_frozen_plan_tampering_fails_instead_of_shrinking_the_denominator(pilot):
    path = pilot / "plan.json"
    plan = json.loads(path.read_text())
    del plan["cases"]["impossible"]
    save(path, plan)
    with pytest.raises(ValueError, match="integrity mismatch"):
        summarize(pilot)
