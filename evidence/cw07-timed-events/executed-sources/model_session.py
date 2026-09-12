#!/usr/bin/env python3
"""Own a fresh Medusa gateway/seller session and hand off buyer-only execution inputs.

No model invocation is performed here. Default preflight creates no clients or world.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import threading
import time
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from contract_spike import ROOT, Spike
from operating_fixture import prepare, start_gateway, start_seller
from stock_smoke import export_run

from rehearsal.agents.runner import read_settings
from rehearsal.commerce.model_runner import attest, digest, write
from rehearsal.evaluation.condition_events import static_case, validate_case
from rehearsal.evaluation.medusa import verify_medusa
from rehearsal.experiments.frozen import FrozenPolicy, freeze
from rehearsal.experiments.policy import Policy
from rehearsal.operating.client import OperatingClient
from rehearsal.operating.local import ORIGIN, check_port, stop


class Session:
    def __init__(self, policy_path=None, fixture=False, case=None):
        self.case = deepcopy(case)
        if case is not None:
            validate_case(case)
        self.fixture = fixture
        self.policy_path = policy_path
        self.spike = None
        self.path = None
        self.run = None
        self.buyer = None
        self.processes = []
        self.record = {
            "schema": "rehearsal-model-session-v1",
            "state": "INITIALIZING",
            "purpose": "sdk-fixture-session" if fixture else "configured-model-session",
            "model_calls_by_controller": 0,
            "transaction_status": "NOT_VERIFIED",
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.closed = False

    def save(self):
        if self.path:
            write(self.path / "session.json", self.record)

    def start(self):
        check_port(18001)  # Reject another owner before creating fixtures.
        if self.policy_path:
            FrozenPolicy.load(self.policy_path, ROOT)
        self.spike = Spike()
        self.path = self.spike.directory / "model-session"
        self.path.mkdir(mode=0o700)
        self.record.update(
            session_id=self.spike.run_id,
            controller_pid=os.getpid(),
            source_sha256={
                name: digest(ROOT / name)
                for name in (
                    "scripts/commerce/model_session.py",
                    "scripts/commerce/operating_fixture.py",
                    "scripts/commerce/stock_smoke.py",
                    "scripts/commerce/contract_spike.py",
                )
            },
        )
        if self.case is not None:
            self.record["source_sha256"]["scripts/commerce/case_fixture.py"] = digest(
                ROOT / "scripts/commerce/case_fixture.py"
            )
        if self.case and self.case.get("events"):
            self.record["source_sha256"]["scripts/commerce/event_fixture.py"] = digest(
                ROOT / "scripts/commerce/event_fixture.py"
            )
        self.save()
        directory, credentials, config, self.fixtures = (
            prepare(self.spike, case=static_case(self.case))
            if self.case is not None
            else prepare(self.spike)
        )
        run_id = next(iter(config["runs"]))
        self.run = config["runs"][run_id]
        target = self.path / "policy.json"
        if self.policy_path:
            with target.open("xb") as output:
                output.write(self.policy_path.read_bytes())
            frozen = FrozenPolicy.load(target, ROOT)
        else:
            frozen = freeze(Policy(), target, ROOT)
        target.chmod(0o600)
        self.processes.append(start_seller(directory))
        self.processes.append(start_gateway(directory))
        buyer_token = credentials["runs"][run_id]["buyer"]
        self.buyer = OperatingClient(ORIGIN, run_id, buyer_token, timeout=10)
        initial = self.buyer.observe_world()
        if initial["tick"] >= self.run["binding"]["goal"]["deadline_tick"]:
            raise RuntimeError("Fresh session expired during startup")
        config_path = self.path / "buyer-config.json"
        write(
            config_path,
            {
                "run_id": run_id,
                "buyer_token": buyer_token,
                "expected_goal": self.run["binding"]["goal"],
                "expected_budget": self.run["binding"]["budget"],
                "policy_path": "policy.json",
            },
        )
        config_path.chmod(0o600)
        self.record.update(
            state="READY",
            ready_at=datetime.now(UTC).isoformat(),
            run_id=run_id,
            frozen_id=frozen.identifier,
            ready_at_tick=initial["tick"],
            deadline_tick=self.run["binding"]["goal"]["deadline_tick"],
            buyer_config="buyer-config.json",
            policy_sha256=digest(target),
            child_pids=[p.pid for p in self.processes],
        )
        if self.case is not None:
            self.capture_conditions()
        self.save()
        return self.path

    def capture_conditions(self):
        from case_fixture import capture

        if self.case is None:
            raise ValueError("Session has no declared static case")
        artifact, verdict = capture(self)
        name = "conditions-" + uuid.uuid4().hex + ".json"
        write(self.path / name, artifact)
        self.record.update(
            conditions_path=name,
            conditions_sha256=digest(self.path / name),
            initial_conditions=verdict,
        )
        self.save()
        return self.path / name

    def wait(self, stopping):
        while not stopping.wait(0.2):
            if (self.path / "STOP").exists():
                return "OPERATOR_STOP_FILE"
            from event_fixture import tick_events

            tick_events(self)
            marker = self.path / "REFRESH_CONDITIONS"
            if marker.exists():
                try:
                    fresh = self.capture_conditions()
                    self.record["refresh_result"] = {"path": str(fresh), "status": "VERIFIED"}
                except Exception as exc:
                    self.record["refresh_result"] = {
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                    }
                finally:
                    marker.unlink()
                    self.save()
            if any(p.poll() is not None for p in self.processes):
                raise RuntimeError("Owned session service exited")
        return "OPERATOR_SIGNAL"

    def close(self, reason):
        if self.closed:
            return
        self.closed = True
        self.record.update(state="STOPPING", stop_reason=reason)
        errors = []
        try:
            self.save()
        except OSError as exc:
            errors.append("save:" + type(exc).__name__)
        snapshot = None
        if self.buyer:
            try:
                snapshot = self.buyer.observe_world()
            except Exception as exc:
                errors.append("snapshot:" + type(exc).__name__)
        # Always stop every owned child, even if export or an earlier stop fails.
        for process in reversed(self.processes):
            try:
                stop(process)
            except Exception as exc:
                errors.append("stop:" + type(exc).__name__)
        if self.run and self.path and self.spike:
            try:
                # Capture clock after quiescing; a stale earlier snapshot is not the export clock.
                import time

                from rehearsal.commerce.seller import read_rows

                binding = json.loads(
                    read_rows(Path(self.run["directory"]) / "medusa.sqlite3", "binding")[0]["data"]
                )
                tick = max(0, int(time.time() - binding["started_at"]))
                evidence = export_run(self.spike, self.run, {"tick": tick})
                if self.case and self.case.get("events"):
                    from event_fixture import export_events

                    evidence["condition_events"] = export_events(self)
                evidence["scope"] = "model-session-independent-export-at-operator-stop"
                write(self.path / "evidence.json", evidence)
                selection = {
                    "run_id": self.run["binding"]["run_id"],
                    "expected_goal": self.run["binding"]["goal"],
                    "expected_budget": self.run["binding"]["budget"],
                    "artifact_path": "evidence.json",
                    "sha256": digest(self.path / "evidence.json"),
                }
                write(self.path / "selection.json", selection)
                verdict = verify_medusa(
                    evidence, selection["expected_goal"], selection["expected_budget"]
                )
                self.record.update(transaction_status=verdict["status"], verdict=verdict)
                execution = ROOT / ".local/commerce-model" / selection["run_id"]
                if (execution / "execution-manifest.json").is_file():
                    review = attest(execution, self.path / "selection.json")
                    write(self.path / "attestation.json", review)
                    self.record["execution_attestation"] = (
                        "VERIFIED" if review["success"] else "NOT_SUCCESSFUL"
                    )
                else:
                    self.record["execution_attestation"] = "NOT_READY"
            except Exception as exc:
                errors.append("export:" + type(exc).__name__)
                self.record["transaction_status"] = "NOT_VERIFIED"
        if self.buyer:
            try:
                self.buyer.close()
            except Exception as exc:
                errors.append("buyer_close:" + type(exc).__name__)
        if self.spike:
            try:
                self.spike.save()
            except Exception as exc:
                errors.append("spike_save:" + type(exc).__name__)
            for client in self.spike.clients.values():
                try:
                    client.close()
                except Exception as exc:
                    errors.append("client_close:" + type(exc).__name__)
        exited = all(p.poll() is not None for p in self.processes)
        self.record.update(
            state="STOPPED" if exited else "CLEANUP_FAILED",
            cleanup_errors=errors,
            owned_children_exited=exited,
            stopped_at=datetime.now(UTC).isoformat(),
        )
        if snapshot is not None:
            self.record["last_snapshot"] = snapshot
        self.save()


def request_stop(path):
    path = path.resolve()
    base = (ROOT / ".local/commerce").resolve()
    if not path.is_relative_to(base) or path.name != "model-session":
        raise ValueError("Stop requires an owned session directory")
    record = json.loads((path / "session.json").read_text())
    if (
        record.get("schema") != "rehearsal-model-session-v1"
        or record.get("session_id") != path.parent.name
    ):
        raise ValueError("Invalid session record")
    # A stop request is not proof the process is live or that shutdown completed.
    try:
        descriptor = os.open(path / "STOP", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if (path / "STOP").is_symlink() or not (path / "STOP").is_file():
            raise ValueError("Invalid stop marker") from None
    else:
        os.close(descriptor)
    print("Stop requested; inspect session state and live process/port evidence for completion.")


def request_refresh(path):
    path = path.resolve()
    base = (ROOT / ".local/commerce").resolve()
    if not path.is_relative_to(base) or path.name != "model-session":
        raise ValueError("Refresh requires an owned session directory")
    record = json.loads((path / "session.json").read_text())
    if (
        record.get("schema") != "rehearsal-model-session-v1"
        or record.get("session_id") != path.parent.name
        or not record.get("conditions_path")
    ):
        raise ValueError("No declared-case session")
    previous = record["conditions_path"]
    marker = path / "REFRESH_CONDITIONS"
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        fresh = json.loads((path / "session.json").read_text())
        if fresh.get("conditions_path") != previous:
            print(path / fresh["conditions_path"])
            return 0
        if not marker.exists() and fresh.get("refresh_result", {}).get("status") == "FAILED":
            raise RuntimeError("Condition refresh failed; inspect the session record")
        time.sleep(0.1)
    print("Refresh is still pending; no process liveness or capture success inferred.")
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--serve", action="store_true")
    modes.add_argument("--fixture-serve", action="store_true")
    modes.add_argument("--stop", type=Path)
    modes.add_argument("--refresh-conditions", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--case", type=Path)
    args = parser.parse_args()
    if args.refresh_conditions:
        if args.policy or args.case:
            parser.error("Refresh accepts only a session directory")
        return request_refresh(args.refresh_conditions)
    if args.stop:
        if args.policy or args.case:
            parser.error("Stop accepts no policy or case")
        request_stop(args.stop)
        return 0
    case = json.loads(args.case.read_text()) if args.case else None
    if case is not None:
        validate_case(case)
    if args.policy:
        FrozenPolicy.load(args.policy, ROOT)
    if not args.fixture_serve:
        try:
            read_settings(ROOT)
        except ValueError as exc:
            print(str(exc))
            return 2
    if not (args.serve or args.fixture_serve):
        print("PASS: settings only; no clients, external clock, services or model calls.")
        return 0
    os.umask(0o077)
    stopping = threading.Event()
    original_handlers = {
        sig: signal.signal(sig, lambda *_: stopping.set())
        for sig in (signal.SIGINT, signal.SIGTERM)
    }
    session = (
        Session(args.policy, args.fixture_serve, case=case)
        if case is not None
        else Session(args.policy, args.fixture_serve)
    )
    reason, failed = "START_FAILURE", False
    try:
        path = session.start()
        print(f"READY: buyer configuration {path / 'buyer-config.json'}", flush=True)
        if session.record.get("conditions_path"):
            print(f"Conditions: {path / session.record['conditions_path']}", flush=True)
        print(
            "Operating clock is advancing. This controller invokes no model. "
            "Ctrl+C stops owned services.",
            flush=True,
        )
        reason = session.wait(stopping)
    except Exception as exc:
        failed = True
        reason = type(exc).__name__
        print(f"Session failed: {reason}; inspect private session record.", flush=True)
    finally:
        try:
            session.close(reason)
        finally:
            for sig, handler in original_handlers.items():
                signal.signal(sig, handler)
    if session.path:
        print(
            f"{session.record['state']}: {session.path}; databases and reservations retained.",
            flush=True,
        )
    return (
        1
        if failed
        or session.record.get("cleanup_errors")
        or not session.record.get("owned_children_exited")
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
