import copy
import importlib.util
import json
import os
import signal
import stat
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[2]


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts/commerce"))
    spec = importlib.util.spec_from_file_location(
        "model_session_test", ROOT / "scripts/commerce/model_session.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def setup(module, tmp_path, monkeypatch):
    base = tmp_path / ".local/commerce/cw00-test"
    original = json.loads((ROOT / "evidence/cw05-metered-http/evidence.json").read_text())
    run_id = original["binding"]["run_id"]
    initial = {
        "tick": 0,
        "run_id": run_id,
        "goal": original["binding"]["goal"],
        "balance": {"budget": 500, "spent": 0, "reserved": 0, "available": 500},
        "inventory": {"tent": 0, "light": 0},
    }
    children = [SimpleNamespace(pid=101, exit=None), SimpleNamespace(pid=102, exit=None)]
    for child in children:
        child.poll = lambda child=child: child.exit
    stops = []

    def stop(child):
        stops.append(child.pid)
        child.exit = 0

    class Spike:
        def __init__(self):
            self.run_id = "cw00-test"
            self.directory = base
            base.mkdir(parents=True)
            self.clients = {"one": SimpleNamespace(close=lambda: None)}

        def save(self):
            pass

    class Buyer:
        def __init__(self, *args, **kwargs):
            pass

        def observe_world(self):
            return copy.deepcopy(initial)

        def close(self):
            pass

    def prepare(spike):
        return (
            base,
            {"runs": {run_id: {"buyer": "buyer-private-token", "control": "do-not-forward"}}},
            {"runs": {run_id: {"directory": str(base), "binding": original["binding"]}}},
            {},
        )

    # Keep real freeze source roots; only the stop-command path is overridden in that test.
    monkeypatch.setattr(module, "check_port", lambda p: None)
    monkeypatch.setattr(module, "Spike", Spike)
    monkeypatch.setattr(module, "prepare", prepare)
    monkeypatch.setattr(module, "start_seller", lambda p: children[0])
    monkeypatch.setattr(module, "start_gateway", lambda p: children[1])
    monkeypatch.setattr(module, "OperatingClient", Buyer)
    monkeypatch.setattr(module, "stop", stop)
    monkeypatch.setattr(
        "rehearsal.commerce.seller.read_rows", lambda *a: [{"data": '{"started_at":0}'}]
    )
    monkeypatch.setattr(module, "export_run", lambda *a: copy.deepcopy(original))
    return module, base, children, stops, initial


def test_default_missing_settings_never_create_a_session(module, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        module,
        "read_settings",
        lambda _: (_ for _ in ()).throw(ValueError("Missing model settings")),
    )
    monkeypatch.setattr(module, "Session", lambda *a: pytest.fail("session constructed"))
    monkeypatch.setattr(sys, "argv", ["model_session", "--serve"])
    assert module.main() == 2
    assert "Missing model settings" in capsys.readouterr().out


def test_valid_preflight_creates_no_client_or_clock(module, monkeypatch):
    monkeypatch.setattr(module, "read_settings", lambda _: object())
    monkeypatch.setattr(module, "Session", lambda *a: pytest.fail("session constructed"))
    monkeypatch.setattr(sys, "argv", ["model_session"])
    assert module.main() == 0


def test_session_hands_off_only_private_buyer_inputs_and_stops_owned_children(setup):
    module, base, _, stops, _ = setup
    session = module.Session(fixture=True)
    path = session.start()
    config = json.loads((path / "buyer-config.json").read_text())
    assert set(config) == {
        "run_id",
        "buyer_token",
        "expected_goal",
        "expected_budget",
        "policy_path",
    }
    assert config["buyer_token"] == "buyer-private-token"
    assert stat.S_IMODE((path / "buyer-config.json").stat().st_mode) == 0o600
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert "private-token" not in (path / "session.json").read_text()
    session.close("TEST_STOP")
    assert stops == [102, 101]
    assert session.record["state"] == "STOPPED" and session.record["owned_children_exited"]
    assert session.record["execution_attestation"] == "NOT_READY"
    assert (path / "selection.json").is_file()
    session.close("AGAIN")
    assert stops == [102, 101] and base.exists()


def test_stop_marker_is_idempotent_and_does_not_follow_symlinks(setup, monkeypatch, tmp_path):
    module, _, _, _, _ = setup
    path = module.Session(fixture=True).start()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    module.request_stop(path)
    module.request_stop(path)
    (path / "STOP").unlink()
    other = tmp_path / "other.txt"
    other.write_text("preserve")
    (path / "STOP").symlink_to(other)
    before = other.stat().st_mtime_ns
    with pytest.raises(ValueError, match="Invalid stop"):
        module.request_stop(path)
    assert other.read_text() == "preserve" and other.stat().st_mtime_ns == before
    with pytest.raises(ValueError, match="owned"):
        module.request_stop(tmp_path)


def test_child_exit_is_detected_and_remaining_child_is_stopped(setup):
    module, _, children, stops, _ = setup
    session = module.Session(fixture=True)
    session.start()
    children[1].exit = 1
    with pytest.raises(RuntimeError, match="service exited"):
        session.wait(threading.Event())
    session.close("CHILD_FAILED")
    assert stops == [102, 101] and session.record["owned_children_exited"]


def test_export_failure_still_stops_every_child_and_keeps_record(setup, monkeypatch):
    module, _, _, stops, _ = setup
    session = module.Session(fixture=True)
    path = session.start()
    monkeypatch.setattr(
        module, "export_run", lambda *a: (_ for _ in ()).throw(RuntimeError("failure"))
    )
    session.close("TEST_STOP")
    record = json.loads((path / "session.json").read_text())
    assert stops == [102, 101] and record["state"] == "STOPPED"
    assert record["transaction_status"] == "NOT_VERIFIED"
    assert record["cleanup_errors"] == ["export:RuntimeError"]


def test_partial_start_failure_stops_already_started_seller(setup, monkeypatch):
    module, _, _, stops, _ = setup
    session = module.Session(fixture=True)
    monkeypatch.setattr(
        module, "start_gateway", lambda *a: (_ for _ in ()).throw(RuntimeError("startup"))
    )
    with pytest.raises(RuntimeError):
        session.start()
    session.close("START_FAILURE")
    assert stops == [101] and session.record["state"] == "STOPPED"


def test_metadata_write_failure_cannot_prevent_child_cleanup(setup, monkeypatch):
    module, _, _, stops, _ = setup
    session = module.Session(fixture=True)
    session.start()
    monkeypatch.setattr(session, "save", lambda: (_ for _ in ()).throw(OSError("unwritable")))
    with pytest.raises(OSError):
        session.close("TEST_STOP")
    assert stops == [102, 101] and session.record["owned_children_exited"]


def test_cleanup_failure_does_not_claim_children_are_stopped(setup, monkeypatch, capsys):
    module, base, _, _, _ = setup
    monkeypatch.setattr(sys, "argv", ["model_session", "--fixture-serve"])
    monkeypatch.setattr(module.Session, "wait", lambda *a: "TEST_STOP")
    monkeypatch.setattr(module, "stop", lambda child: (_ for _ in ()).throw(OSError("not stopped")))
    assert module.main() == 1
    record = json.loads((base / "model-session/session.json").read_text())
    assert record["state"] == "CLEANUP_FAILED" and not record["owned_children_exited"]
    assert "CLEANUP_FAILED:" in capsys.readouterr().out


def test_repeated_signals_during_shutdown_do_not_interrupt_owned_cleanup(setup, monkeypatch):
    module, _, _, stops, _ = setup
    before = signal.getsignal(signal.SIGINT)
    monkeypatch.setattr(sys, "argv", ["model_session", "--fixture-serve"])
    monkeypatch.setattr(module.Session, "wait", lambda *a: "TEST_STOP")
    original = module.stop

    def interrupted(child):
        os.kill(os.getpid(), signal.SIGINT)
        original(child)

    monkeypatch.setattr(module, "stop", interrupted)
    assert module.main() == 0
    assert stops == [102, 101]
    assert signal.getsignal(signal.SIGINT) == before


def test_shutdown_preserves_unknown_reservation_from_retained_race_evidence(setup, monkeypatch):
    module, _, _, _, _ = setup
    session = module.Session(fixture=True)
    path = session.start()
    original = (ROOT / "evidence/cw05-race/race-evidence-0.json").read_bytes()
    evidence = json.loads(original)
    session.run["binding"] = copy.deepcopy(evidence["binding"])
    monkeypatch.setattr(module, "export_run", lambda *a: copy.deepcopy(evidence))
    session.close("OPERATOR_STOP")
    assert session.record["transaction_status"] == "UNKNOWN"
    assert session.record["verdict"]["reserved"] == 310
    saved = json.loads((path / "evidence.json").read_text())
    assert saved["tables"] == evidence["tables"]
    assert (ROOT / "evidence/cw05-race/race-evidence-0.json").read_bytes() == original


def test_unsupported_session_case_is_rejected_before_bootstrap(module, monkeypatch):
    case = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    case["events"] = []
    monkeypatch.setattr(module, "Spike", lambda: pytest.fail("bootstrap"))
    with pytest.raises(ValueError, match="explicit timed events required"):
        module.Session(case=case)


def test_declared_case_is_applied_before_child_start_and_capture(setup, monkeypatch):
    module, base, _, _, _ = setup
    case = json.loads((ROOT / "scenarios/normal-v1.json").read_text())
    original = module.prepare
    seen = []

    def prepare(spike, case=None):
        seen.append(copy.deepcopy(case))
        return original(spike)

    def capture(session):
        assert seen == [case]
        assert len(session.processes) == 2
        session.record["conditions_path"] = "conditions-in-test.json"

    monkeypatch.setattr(module, "prepare", prepare)
    monkeypatch.setattr(module.Session, "capture_conditions", capture)
    session = module.Session(fixture=True, case=case)
    session.start()
    assert session.record["conditions_path"] == "conditions-in-test.json"
    assert "scripts/commerce/case_fixture.py" in session.record["source_sha256"]
    session.close("test")


def test_refresh_request_is_serviced_by_the_session_without_restarting_it(
    setup, monkeypatch, capsys
):
    module, base, _, _, _ = setup
    session = module.Session(fixture=True)
    session.start()
    session.record["conditions_path"] = "conditions-old.json"
    session.save()
    stopping = threading.Event()
    captured = []

    def capture():
        path = session.path / "conditions-new.json"
        captured.append(path)
        session.record["conditions_path"] = path.name
        session.save()
        stopping.set()
        return path

    monkeypatch.setattr(session, "capture_conditions", capture)
    monkeypatch.setattr(module, "ROOT", base.parents[2])
    worker = threading.Thread(target=session.wait, args=(stopping,))
    worker.start()
    try:
        assert module.request_refresh(session.path) == 0
        assert len(captured) == 1 and str(captured[0]) in capsys.readouterr().out
    finally:
        stopping.set()
        worker.join(5)
        session.close("test")
    assert not worker.is_alive()
    assert not (session.path / "REFRESH_CONDITIONS").exists()
