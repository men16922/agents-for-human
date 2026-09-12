#!/usr/bin/env python3
"""Scoped local environment commands. Never connect to cloud or place orders."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = [
    "docker",
    "compose",
    "--project-name",
    "rehearsal-dev",
    "--env-file",
    str(ROOT / ".env"),
    "-f",
    str(ROOT / "dev/compose.yaml"),
]
SECRET_KEYS = ("POSTGRES_PASSWORD", "REDIS_PASSWORD", "JWT_SECRET", "COOKIE_SECRET")


def init_env() -> None:
    target = ROOT / ".env"
    if target.exists():
        print("Existing .env preserved.")
        return
    with open(target, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as out:
        out.write("# Generated for loopback-only local development; do not publish.\n")
        for key in SECRET_KEYS:
            out.write(f"{key}={secrets.token_hex(32)}\n")
        out.write("AWS_PROFILE=\nAWS_REGION=\nREHEARSAL_MODEL_ID=\n")
    print("Created private .env with independent local secrets; no AWS credentials added.")


def environment() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.is_file():
        raise SystemExit("Missing .env. Run make init-env.")
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise SystemExit("Malformed .env line; use simple KEY=value entries.")
        values[key] = value
    if any(not values.get(k) or values[k].startswith("generated-") for k in SECRET_KEYS):
        raise SystemExit("Local secret values are missing. See docs/DEVELOPMENT.md.")
    # The isolated test DB URLs are fixed, not inherited from another workspace.
    env = dict(os.environ)
    for key in (
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "DATABASE_URL",
        "REDIS_URL",
    ):
        env.pop(key, None)
    env.update({key: values[key] for key in SECRET_KEYS})
    env.update(
        {
            "DATABASE_URL": f"postgres://rehearsal:{values['POSTGRES_PASSWORD']}@127.0.0.1:55432/rehearsal",
            "REDIS_URL": f"redis://:{values['REDIS_PASSWORD']}@127.0.0.1:56379/0",
            "MEDUSA_DISABLE_TELEMETRY": "true",
            "MEDUSA_FF_RBAC": "false",
            "DO_NOT_TRACK": "1",
            "AWS_EC2_METADATA_DISABLED": "true",
            "NODE_ENV": "development",
        }
    )
    return env


def run(command: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def check_ports(ports: tuple[int, ...]) -> None:
    for port in ports:
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as exc:
                raise SystemExit(
                    f"Port {port} is in use. Stop its owner; no process was killed."
                ) from exc


def wait_http(url: str, child: subprocess.Popen[bytes], timeout: float = 120) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError(f"Service exited with {child.returncode}; inspect .local/logs/.")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return response.read().decode()
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Service readiness timeout: {url}; inspect .local/logs/.")


@contextmanager
def uninterrupted_cleanup() -> Iterator[None]:
    # make/uv can forward another SIGINT while the first interrupt is being cleaned up.
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def terminate(child: subprocess.Popen[bytes]) -> None:
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)


def commerce(smoke: bool) -> None:
    env = environment()
    check_ports((19000,))
    child = None
    logs = ROOT / ".local/logs"
    logs.mkdir(parents=True, exist_ok=True)
    try:
        run(COMPOSE + ["up", "-d", "--wait", "--wait-timeout", "90"], env)
        for task in ("medusa:build", "medusa:migrate"):
            with (logs / (task.replace(":", "-") + ".log")).open("wb") as output:
                subprocess.run(
                    ["npm", "run", task],
                    cwd=ROOT,
                    env=env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            print(f"PASS: {task}; details in .local/logs/.", flush=True)
        with (logs / "medusa.log").open("wb") as output:
            child = subprocess.Popen(
                ["npm", "run", "medusa:start"],
                cwd=ROOT,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            body = wait_http("http://127.0.0.1:19000/health", child)
            print("Medusa health: HTTP 200; independent local database migrated.", flush=True)
            if smoke:
                report = {
                    "scope": "local-environment-only",
                    "medusa_health": 200,
                    "health_body": body,
                    "orders_executed": 0,
                    "model_calls": 0,
                }
                (ROOT / ".local/commerce-smoke.json").write_text(
                    json.dumps(report, indent=2) + "\n"
                )
            else:
                print(
                    "Medusa: http://127.0.0.1:19000 · Ctrl+C stops the local services.",
                    flush=True,
                )
                child.wait()
    finally:
        with uninterrupted_cleanup():
            if child is not None:
                terminate(child)
            run(COMPOSE + ["down"], env)  # Preserve named data volumes.


def dev() -> None:
    check_ports((18000, 15173))
    env = environment()
    children = []
    try:
        for command in (
            [
                "uv",
                "run",
                "--offline",
                "--no-sync",
                "uvicorn",
                "rehearsal.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                "18000",
                "--reload",
            ],
            ["npm", "run", "dev:web"],
        ):
            children.append(subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True))
        wait_http("http://127.0.0.1:18000/health", children[0], 30)
        wait_http("http://127.0.0.1:15173", children[1], 30)
        print("Development shell: http://127.0.0.1:15173 · Ctrl+C stops both services.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise RuntimeError("A development process exited; stopping the remaining owned process.")
    finally:
        with uninterrupted_cleanup():
            for child in children:
                terminate(child)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init-env", "dev", "commerce", "commerce-smoke"])
    args = parser.parse_args()
    try:
        if args.command == "init-env":
            init_env()
        elif args.command == "dev":
            dev()
        else:
            commerce(smoke=args.command == "commerce-smoke")
    except KeyboardInterrupt:
        print("\nStopped owned local processes; no volumes deleted.")


if __name__ == "__main__":
    main()
