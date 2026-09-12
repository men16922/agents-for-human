import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "scripts/commerce"))
    return importlib.import_module("reaction_ui_smoke")


class Service:
    def __init__(self, exit_code=None):
        self.exit_code = exit_code

    def poll(self):
        return self.exit_code


def test_operator_interrupt_finishes_only_the_inspection_window(demo, tmp_path, monkeypatch):
    def interrupt(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(demo.time, "sleep", interrupt)
    result = demo.inspect_live(tmp_path, [Service()], [], 0)
    assert result["state"] == "FINISHED" and result["reason"] == "OPERATOR_INTERRUPT"
    assert not result["human_participation_measured"] and result["real_model_calls"] == 0
    assert json.loads((tmp_path / "inspection.json").read_text()) == result


def test_bounded_window_uses_monotonic_time(demo, tmp_path, monkeypatch):
    times = iter((10, 10.5, 11))
    monkeypatch.setattr(demo.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(demo.time, "sleep", lambda _: None)
    result = demo.inspect_live(tmp_path, [Service()], [], 1)
    assert result["reason"] == "BOUNDED_WINDOW_FINISHED"


@pytest.mark.parametrize("kind", ["api", "worker"])
def test_exited_service_cannot_leave_a_successful_inspection_record(demo, tmp_path, kind):
    with pytest.raises(RuntimeError, match="service exited"):
        demo.inspect_live(
            tmp_path, [Service(1 if kind == "api" else None)],
            ["gateway failed"] if kind == "worker" else [], 1,
        )
    record = json.loads((tmp_path / "inspection.json").read_text())
    assert record["state"] == "FAILED" and record["reason"] == "SERVICE_FAILURE"


@pytest.mark.parametrize("seconds", [-1, 3601, True])
def test_invalid_window_does_not_create_an_inspection_record(demo, tmp_path, seconds):
    with pytest.raises(ValueError):
        demo.inspect_live(tmp_path, [Service()], [], seconds)
    assert not (tmp_path / "inspection.json").exists()
