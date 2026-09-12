"""Recompute a selected local export, returning only a bounded public summary.

The locally selected manifest pins bytes, run, goal and budget independently.
A digest identifies a local artifact; it is not proof of an external signature.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from rehearsal.evaluation.medusa import verify_medusa

MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
SAFE_INTEGER = 2**53 - 1


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


def read_json(path: Path, limit: int) -> tuple[bytes, dict[str, Any]]:
    with path.open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Size limit")
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("Object required")
    return raw, value


def integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= SAFE_INTEGER:
        raise ValueError("Invalid integer")
    return value


def goal(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"items", "deadline_tick", "recipient"}:
        raise ValueError("Invalid goal")
    items = value["items"]
    if not isinstance(items, dict) or not 1 <= len(items) <= 30:
        raise ValueError("Invalid items")
    for key, quantity in items.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key):
            raise ValueError("Invalid item")
        integer(quantity, 1)
    integer(value["deadline_tick"], 1)
    if not isinstance(value["recipient"], str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,64}", value["recipient"]
    ):
        raise ValueError("Invalid recipient")
    return value


def review_export(manifest_path: Path | None, observer_run: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "UNCONFIGURED",
        "reason": "EVIDENCE_NOT_CONFIGURED",
        "run_id": observer_run,
        "artifact": None,
        "verdict": None,
        "checked_at": time.time(),
        "historical": True,
    }
    if manifest_path is None:
        return result
    result.update(status="PENDING", reason="EVIDENCE_NOT_READY")
    try:
        _, manifest = read_json(manifest_path, 16 * 1024)
    except FileNotFoundError:
        return result
    except (OSError, ValueError, RecursionError):
        return result | {"status": "REJECTED", "reason": "INVALID_EVIDENCE_SELECTION"}
    try:
        if set(manifest) != {
            "run_id",
            "expected_goal",
            "expected_budget",
            "artifact_path",
            "sha256",
        }:
            raise ValueError("Invalid selection")
        expected_goal = goal(manifest["expected_goal"])
        budget = integer(manifest["expected_budget"], 1)
        if not isinstance(manifest["sha256"], str) or not re.fullmatch(
            r"[a-f0-9]{64}", manifest["sha256"]
        ):
            raise ValueError("Invalid digest")
        path = Path(manifest["artifact_path"])
        if not path.is_absolute():
            path = manifest_path.parent / path
    except (KeyError, TypeError, ValueError):
        return result | {"status": "REJECTED", "reason": "INVALID_EVIDENCE_SELECTION"}
    if observer_run is None or manifest["run_id"] != observer_run:
        return result | {"status": "REJECTED", "reason": "EVIDENCE_RUN_MISMATCH"}
    try:
        raw, evidence = read_json(path, MAX_ARTIFACT_BYTES)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != manifest["sha256"]:
            return result | {"status": "REJECTED", "reason": "EVIDENCE_HASH_MISMATCH"}
        if evidence["binding"]["run_id"] != observer_run:
            return result | {"status": "REJECTED", "reason": "EVIDENCE_RUN_MISMATCH"}
        tick = integer(evidence["captured_at_tick"])
        # Do not read any saved verdict or success flag from the artifact.
        verdict = verify_medusa(evidence, expected_goal, budget)
        if verdict["status"] not in {"COMPLETE", "INCOMPLETE", "FAILED", "UNKNOWN"}:
            raise ValueError("Invalid verdict")
        public: dict[str, Any] = {
            "status": verdict["status"],
            "scope": verdict.get("scope"),
            "errors": verdict["errors"][:50],
        }
        if "spent" in verdict:
            public.update(
                spent=integer(verdict["spent"]),
                reserved=integer(verdict["reserved"]),
                received_on_time={
                    key: integer(verdict["received_on_time"].get(key, 0))
                    for key in expected_goal["items"]
                },
            )
        verifier_hash = hashlib.sha256(
            Path(__file__).with_name("evaluation").joinpath("medusa.py").read_bytes()
        ).hexdigest()
        return result | {
            "status": "VERIFIED",
            "reason": None,
            "verdict": public,
            "artifact": {
                "sha256": digest,
                "bytes": len(raw),
                "captured_at_tick": tick,
                "run_id": observer_run,
                "goal": expected_goal,
                "budget": budget,
            },
            "verifier": {"name": "verify_medusa", "sha256": verifier_hash},
        }
    except FileNotFoundError:
        return result
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
        return result | {"status": "REJECTED", "reason": "INVALID_EVIDENCE"}


def evidence_routes(manifest_path: Path | None, observer_run: str | None) -> APIRouter:
    router = APIRouter(prefix="/observer")

    @router.get("/evidence")
    def evidence() -> JSONResponse:
        return JSONResponse(
            review_export(manifest_path, observer_run),
            headers={
                "Cache-Control": "no-store",
                "Cross-Origin-Resource-Policy": "same-origin",
            },
        )

    return router
