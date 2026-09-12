"""Exercise local setup boundaries with isolated files and a real occupied socket."""

import importlib.util
import json
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("rehearsal_local", ROOT / "scripts/dev/local.py")
assert spec and spec.loader
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


def test_init_preserves_existing_secrets(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(local, "ROOT", tmp_path)
    local.init_env()
    path = tmp_path / ".env"
    original = path.read_bytes()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    local.init_env()
    assert path.read_bytes() == original
    output = capsys.readouterr().out
    assert all(
        value not in output
        for value in [
            line.split("=", 1)[1]
            for line in original.decode().splitlines()
            if line.startswith(("JWT_SECRET=", "COOKIE_SECRET="))
        ]
    )


def test_local_runtime_uses_own_db_and_excludes_inherited_cloud_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "ROOT", tmp_path)
    local.init_env()
    monkeypatch.setenv("DATABASE_URL", "postgres://other-project/private")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fixture-do-not-use")
    monkeypatch.setenv("AWS_PROFILE", "unrelated-profile")
    env = local.environment()
    assert "@127.0.0.1:55432/rehearsal" in env["DATABASE_URL"]
    assert "other-project" not in env["DATABASE_URL"]
    assert "AWS_ACCESS_KEY_ID" not in env
    assert "AWS_PROFILE" not in env
    assert env["MEDUSA_FF_RBAC"] == "false"


def test_occupied_port_fails_without_touching_its_owner():
    with socket.socket() as owner:
        owner.bind(("127.0.0.1", 0))
        owner.listen()
        port = owner.getsockname()[1]
        with pytest.raises(SystemExit, match="in use"):
            local.check_ports((port,))
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass


def test_doctor_fails_when_installation_is_missing(tmp_path):
    (tmp_path / "scripts/dev").mkdir(parents=True)
    (tmp_path / "dev").mkdir()
    doctor = tmp_path / "scripts/dev/doctor.py"
    doctor.write_bytes((ROOT / "scripts/dev/doctor.py").read_bytes())
    (tmp_path / "dev/toolchain.json").write_text(
        json.dumps({"python": "3.12.13", "node": "22.23.2"})
    )
    result = subprocess.run([sys.executable, str(doctor)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "missing" in result.stderr
    assert "PASS" not in result.stdout


def test_dev_cleanup_stops_both_process_groups_during_repeated_interrupts():
    # A subprocess keeps the test runner's own signal handlers untouched.
    probe = r"""
import importlib.util, os, signal, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
spec = importlib.util.spec_from_file_location("local", Path("scripts/dev/local.py"))
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)
children = [subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                            start_new_session=True) for _ in range(2)]
original_popen = local.subprocess.Popen
original_terminate = local.terminate
pending = iter(children)
local.subprocess.Popen = lambda *a, **kw: next(pending)
local.check_ports = lambda ports: None
local.environment = lambda: dict(os.environ)
local.wait_http = lambda *a, **kw: "OK"
def interrupt(_):
    raise KeyboardInterrupt()
local.time = SimpleNamespace(sleep=interrupt)
def second_interrupt(child):
    os.kill(os.getpid(), signal.SIGINT)
    original_terminate(child)
local.terminate = second_interrupt
try:
    try:
        local.dev()
    except KeyboardInterrupt:
        pass
    assert all(child.poll() is not None for child in children), "surviving child process"
finally:
    local.subprocess.Popen = original_popen
    for child in children:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
        child.wait()
"""
    result = subprocess.run(
        [sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
