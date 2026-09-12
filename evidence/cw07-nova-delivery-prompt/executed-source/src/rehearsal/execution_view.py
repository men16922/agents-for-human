"""Bounded, read-only reaction records. Integrity is not transaction/model success."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from rehearsal.commerce.change_inbox import ChangeInbox
from rehearsal.evidence_view import (
    MAX_ARTIFACT_BYTES,
    goal,
    integer,
    read_json,
    unique_object,
)
from rehearsal.world.storage import ContractError

REASONS = frozenset(
    {
        "OBSERVATION_DEADLINE_REACHED",
        "OBSERVATION_REPLAN_LIMIT",
        "OBSERVATION_CHANGED_REPLAN",
        "OBSERVATION_UNAVAILABLE_RECHECK",
        "QUOTE_EXPIRED_RECHECK",
        "QUOTE_BASIS_CHANGED_RECHECK",
        "OBSERVATION_READ_FAILED",
        "OBSERVATION_UNAVAILABLE",
        "OBSERVATION_STALE",
        "DEADLINE",
        "MODEL_CALL_LIMIT",
        "COST_LIMIT",
        "TOKEN_LIMIT",
        "TOOL_CALL_LIMIT",
        "USAGE_UNKNOWN",
        "PRIOR_USAGE_UNRESOLVED",
        "INPUT_ESTIMATE_UNAVAILABLE",
        "INPUT_TOKEN_LIMIT",
        "ESTIMATED_COST_LIMIT",
        "TOTAL_TOKEN_LIMIT",
        "HTTP_RUN_CONTRACT_CHANGED",
        "EXECUTION_INPUT_CHANGED",
        "FRESH_EXTERNAL_RUN_REQUIRED",
    }
)
TERMINAL = {"COMPLETED", "INCOMPLETE", "ERROR", "LIMITED"}


def code(value: Any) -> str | None:
    return (
        None if value is None else value if isinstance(value, str) and value in REASONS else "OTHER"
    )


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def binary(path: Path) -> bytes:
    with path.open("rb") as source:
        raw = source.read(MAX_ARTIFACT_BYTES + 1)
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError("Size limit")
    return raw


def audit_summary(raw: bytes, spec: dict[str, Any], sealed: bool) -> dict[str, Any]:
    """Replay only complete audit rows; never forward supplier prose or model output."""

    def checked(snapshot: dict[str, Any]) -> dict[str, Any]:
        goal(snapshot["goal"])
        integer(snapshot["balance"]["budget"], 1)
        if (
            snapshot["goal"] != spec["expected_goal"]
            or snapshot["balance"]["budget"] != spec["expected_budget"]
        ):
            raise ValueError("Scope mismatch")
        return snapshot

    inbox = ChangeInbox(spec["run_id"], checked)
    partial = bool(raw and not raw.endswith(b"\n"))
    if sealed and partial:
        raise ValueError("Incomplete sealed audit")
    lines = raw.split(b"\n")[:-1]
    if len(lines) > 50_000:
        raise ValueError("Row limit")
    basis = None
    blocks = rechecks = errors = 0
    recent: list[dict[str, Any]] = []
    for line in lines:
        row = json.loads(line, object_pairs_hook=unique_object)
        if not isinstance(row, dict) or set(row) != {"kind", "at", "value"}:
            raise ValueError("Invalid row")
        at = row["at"]
        if type(at) not in (int, float) or not 0 <= at <= 2**53 - 1:
            raise ValueError("Invalid timestamp")
        value, kind = row["value"], row["kind"]
        if not isinstance(value, dict):
            raise ValueError("Invalid value")
        if kind == "journal":
            inbox.ingest(value)
            continue
        event: dict[str, Any] = {"kind": kind, "at": at}
        if kind in {"decision_basis", "effect_blocked", "effect_rechecked"}:
            snapshot = inbox.validate(value["snapshot"])
            tick = integer(snapshot["tick"])
            event["tick"] = tick
            if kind == "decision_basis":
                replan = integer(value["replan"])
                if replan != (0 if basis is None else basis["replan"] + 1):
                    raise ValueError("Invalid replan sequence")
                basis = {"tick": tick, "replan": replan}
                event["replan"] = replan
            else:
                if value["path"] not in {"orders", "payments"}:
                    raise ValueError("Invalid effect")
                event["effect"] = value["path"]
                if kind == "effect_blocked":
                    blocks += 1
                    event["reason"] = code(value["reason"])
                else:
                    rechecks += 1
        elif kind == "read_error":
            errors += 1
            event["reason"] = "OBSERVATION_UNAVAILABLE"
        else:
            raise ValueError("Unknown record")
        recent.append(event)
        recent = recent[-12:]
    return {
        "basis": basis,
        "replans": basis["replan"] if basis else 0,
        "blocked_effects": blocks,
        "effect_rechecks": rechecks,
        "read_errors": errors,
        "cursor": integer(inbox.projection.cursor),
        "version": integer(inbox.projection.version),
        "partial_tail": partial,
        "rows": len(lines),
        "recent": recent,
    }


def review_execution(selection: Path | None, observer_run: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "UNCONFIGURED",
        "reason": "EXECUTION_NOT_CONFIGURED",
        "run_id": observer_run,
        "checked_at": time.time(),
        "execution": None,
        "read_only": True,
        "transaction_verified": False,
        "model_efficacy_verified": False,
    }
    if selection is None:
        return result
    result.update(status="PENDING", reason="EXECUTION_NOT_READY")
    try:
        _, selected = read_json(selection, 16 * 1024)
        if set(selected) != {
            "run_id",
            "expected_goal",
            "expected_budget",
            "execution_path",
            "spec_sha256",
        }:
            raise ValueError("Invalid selection")
        goal(selected["expected_goal"])
        integer(selected["expected_budget"], 1)
        if not isinstance(selected["spec_sha256"], str) or not re.fullmatch(
            r"[a-f0-9]{64}", selected["spec_sha256"]
        ):
            raise ValueError("Invalid hash")
        directory = Path(selected["execution_path"])
        if not directory.is_absolute():
            directory = selection.parent / directory
        if observer_run is None or selected["run_id"] != observer_run:
            return result | {"status": "REJECTED", "reason": "EXECUTION_RUN_MISMATCH"}
    except FileNotFoundError:
        return result
    except (OSError, ValueError, TypeError, RecursionError):
        return result | {"status": "REJECTED", "reason": "INVALID_EXECUTION_SELECTION"}
    sealed = None
    try:
        try:
            _, sealed = read_json(directory / "execution-manifest.json", 16 * 1024)
        except FileNotFoundError:
            pass
        spec_raw, spec = read_json(directory / "spec.json", MAX_ARTIFACT_BYTES)
        goal(spec["expected_goal"])
        integer(spec["expected_budget"], 1)
        if sha(spec_raw) != selected["spec_sha256"]:
            raise ValueError("Input hash mismatch")
        if spec["schema"] != "rehearsal-http-model-run-v1" or any(
            spec[k] != selected[k] for k in ("run_id", "expected_goal", "expected_budget")
        ):
            raise ValueError("Input scope mismatch")
        settings = spec.get("reaction_settings")
        maximum = None
        if settings is not None:
            if not isinstance(settings, dict) or set(settings) != {"max_replans"}:
                raise ValueError("Invalid settings")
            maximum = integer(settings["max_replans"], 1)
            if maximum > 32 or spec["executor_kind"] != "model":
                raise ValueError("Invalid reaction arm")
        report_raw, report = read_json(directory / "report.json", MAX_ARTIFACT_BYTES)
        if (
            report["spec_sha256"] != sha(spec_raw)
            or report["run_id"] != observer_run
            or report["frozen_id"] != spec["frozen_id"]
            or report["runtime_status"] not in TERMINAL | {"STARTED"}
        ):
            raise ValueError("Invalid report binding")
        try:
            raw = binary(directory / "observations.jsonl")
        except FileNotFoundError:
            raw = b""
        if settings is None and raw:
            raise ValueError("Unexpected reactions")
        audit = audit_summary(raw, spec, sealed is not None)
        if maximum is not None and audit["replans"] > maximum:
            raise ValueError("Replan limit mismatch")
        if sealed is not None:
            if (
                sealed["spec_sha256"] != sha(spec_raw)
                or sealed["report_sha256"] != sha(report_raw)
                or sealed["tools_sha256"] != report["tools_sha256"]
                or sealed.get("observations_sha256") != report.get("observations_sha256")
                or report.get("observations_sha256") != (sha(raw) if raw else None)
                or report["runtime_status"] not in TERMINAL
            ):
                raise ValueError("Seal mismatch")
            tools = binary(directory / "tools.jsonl") if report["tools_sha256"] else b""
            if report["tools_sha256"] != (sha(tools) if tools else None):
                raise ValueError("Tool trace mismatch")
            reactions = report.get("reactions")
            if reactions is not None:
                if (
                    settings is None
                    or reactions["settings"] != settings
                    or reactions["worker_stopped"] is not True
                    or type(reactions["replans"]) is not int
                    or type(reactions["blocked_effects"]) is not int
                    or reactions["replans"] != audit["replans"]
                    or reactions["blocked_effects"] != audit["blocked_effects"]
                    or reactions["inbox"]["cursor"] != audit["cursor"]
                    or reactions["inbox"]["version"] != audit["version"]
                ):
                    raise ValueError("Reaction summary mismatch")
            elif raw or (settings is not None and report["runtime_status"] == "COMPLETED"):
                raise ValueError("Missing reaction summary")
        return result | {
            "status": "SEALED" if sealed is not None else "PROVISIONAL",
            "reason": None,
            "execution": {
                "goal": spec["expected_goal"],
                "budget": spec["expected_budget"],
                "spec_sha256": sha(spec_raw),
                "reaction_limit": maximum,
                "runtime_status": report["runtime_status"] if sealed is not None else None,
                "stop_reason": code(
                    report.get("stop_reason")
                    or report.get("reaction_stop")
                    or report.get("error_code")
                )
                if sealed is not None
                else None,
                "audit": audit,
            },
        }
    except FileNotFoundError:
        return (
            result
            if sealed is None
            else result | {"status": "REJECTED", "reason": "INVALID_EXECUTION_RECORD"}
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RecursionError,
        ContractError,
    ):
        return result | {"status": "REJECTED", "reason": "INVALID_EXECUTION_RECORD"}


def execution_routes(selection: Path | None, observer_run: str | None) -> APIRouter:
    router = APIRouter(prefix="/observer")

    @router.get("/execution")
    def execution() -> JSONResponse:
        return JSONResponse(
            review_execution(selection, observer_run),
            headers={
                "Cache-Control": "no-store",
                "Cross-Origin-Resource-Policy": "same-origin",
            },
        )

    return router
