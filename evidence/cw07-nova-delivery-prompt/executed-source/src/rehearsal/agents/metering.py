"""Durable per-call usage and estimated cost, including failed/unknown calls.

Price values are explicit run inputs, never a built-in claim about provider prices.
Admission uses the SDK's input estimate and output limit, so the USD threshold is
an admission guard, not a guarantee of the final provider invoice.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any

from strands.hooks import AfterModelCallEvent, BeforeModelCallEvent, BeforeToolCallEvent
from strands.models.model import Model


@dataclass(frozen=True)
class RateCard:
    input_usd_per_million: str
    output_usd_per_million: str
    cache_read_usd_per_million: str
    cache_write_usd_per_million: str
    source: str

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            if key != "source" and (not Decimal(value).is_finite() or Decimal(value) < 0):
                raise ValueError(f"Invalid rate: {key}")
        if not self.source.strip():
            raise ValueError("An explicit rate source is required")

    def micro_usd(self, usage: dict[str, int]) -> int:
        # USD / million tokens equals micro-USD / token. Round upward only once.
        fields = {
            "inputTokens": self.input_usd_per_million,
            "outputTokens": self.output_usd_per_million,
            "cacheReadInputTokens": self.cache_read_usd_per_million,
            "cacheWriteInputTokens": self.cache_write_usd_per_million,
        }
        amount = Decimal(0)
        for name, rate in fields.items():
            quantity = usage.get(name, 0)
            if type(quantity) is not int or quantity < 0:
                raise ValueError(f"Invalid usage: {name}")
            amount += Decimal(rate) * quantity
        return int(amount.to_integral_value(rounding=ROUND_CEILING))


SCHEMA = """
CREATE TABLE IF NOT EXISTS model_runs (
    run_id TEXT PRIMARY KEY, model_id TEXT NOT NULL, rates TEXT NOT NULL,
    budget_micro_usd INTEGER NOT NULL, input_limit INTEGER NOT NULL,
    output_limit INTEGER NOT NULL, scope TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES model_runs(run_id),
    status TEXT NOT NULL, projected_input_tokens INTEGER NOT NULL,
    reserved_micro_usd INTEGER NOT NULL, estimated_micro_usd INTEGER,
    usage TEXT, error_type TEXT,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at TEXT,
    CHECK(status IN ('STARTED','RECORDED','USAGE_UNKNOWN','ERROR'))
);
CREATE TABLE IF NOT EXISTS model_limits (
    run_id TEXT PRIMARY KEY REFERENCES model_runs(run_id), max_calls INTEGER
);
CREATE TABLE IF NOT EXISTS model_call_context (
    call_id INTEGER PRIMARY KEY REFERENCES model_calls(id),
    role TEXT NOT NULL, execution_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_admission_rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES model_runs(run_id),
    role TEXT NOT NULL, execution_id TEXT NOT NULL, reason TEXT NOT NULL,
    rejected_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS session_constraints (
    run_id TEXT PRIMARY KEY REFERENCES model_runs(run_id),
    max_total_tokens INTEGER, max_tool_calls INTEGER
);
CREATE TABLE IF NOT EXISTS tool_admissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES model_runs(run_id),
    role TEXT NOT NULL, execution_id TEXT NOT NULL, tool_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ADMITTED','REJECTED')), reason TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
"""


class UsageLedger:
    def __init__(
        self,
        path: Path,
        run_id: str,
        model_id: str,
        rates: RateCard,
        budget_micro_usd: int,
        input_limit: int,
        output_limit: int,
        scope: str = "live-model",
        *,
        max_calls: int | None = None,
        max_total_tokens: int | None = None,
        max_tool_calls: int | None = None,
    ):
        for value in (budget_micro_usd, input_limit, output_limit):
            if type(value) is not int or value <= 0:
                raise ValueError("Budget and token limits must be positive integers")
        if scope not in {"live-model", "offline-scripted-model"}:
            raise ValueError("Invalid accounting scope")
        if max_calls is not None and (type(max_calls) is not int or max_calls <= 0):
            raise ValueError("Invalid shared model call limit")
        for optional_limit in (max_total_tokens, max_tool_calls):
            if optional_limit is not None and (
                type(optional_limit) is not int or optional_limit <= 0
            ):
                raise ValueError("Invalid shared token/tool limit")
        self.path, self.run_id, self.rates = path, run_id, rates
        self.budget = budget_micro_usd
        self.max_calls = max_calls
        self.max_total_tokens, self.max_tool_calls = max_total_tokens, max_tool_calls
        self.input_limit, self.output_limit = input_limit, output_limit
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            config = (
                run_id,
                model_id,
                json.dumps(asdict(rates), sort_keys=True),
                budget_micro_usd,
                input_limit,
                output_limit,
                scope,
            )
            old = db.execute("SELECT * FROM model_runs WHERE run_id=?", (run_id,)).fetchone()
            if old is not None and tuple(old) != config:
                raise ValueError("Existing usage run configuration cannot change")
            db.execute("INSERT OR IGNORE INTO model_runs VALUES(?,?,?,?,?,?,?)", config)
            limit = db.execute(
                "SELECT max_calls FROM model_limits WHERE run_id=?", (run_id,)
            ).fetchone()
            if limit is not None and limit[0] != max_calls:
                raise ValueError("Existing model call limit cannot change")
            db.execute("INSERT OR IGNORE INTO model_limits VALUES(?,?)", (run_id, max_calls))
            constraints = db.execute(
                "SELECT max_total_tokens,max_tool_calls FROM session_constraints WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if constraints is not None and tuple(constraints) != (max_total_tokens, max_tool_calls):
                raise ValueError("Existing session constraints cannot change")
            if (
                constraints is None
                and old is not None
                and (max_total_tokens is not None or max_tool_calls is not None)
            ):
                raise ValueError("Cannot retrofit session constraints on an existing run")
            db.execute(
                "INSERT OR IGNORE INTO session_constraints VALUES(?,?,?)",
                (run_id, max_total_tokens, max_tool_calls),
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(
        self,
        projected_input: int | None,
        *,
        role: str = "executor",
        execution_id: str | None = None,
    ) -> tuple[int | None, str | None]:
        execution_id = execution_id or self.run_id
        if role not in {
            "executor",
            "reviewer",
            "buyer_initial",
            "buyer_candidate",
            "simulation_agent",
            "buyer_evaluation",
        } or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", execution_id):
            raise ValueError("Invalid usage attribution")
        reason = None
        if type(projected_input) is not int or projected_input < 0:
            reason = "INPUT_ESTIMATE_UNAVAILABLE"
        elif projected_input > self.input_limit:
            reason = "INPUT_TOKEN_LIMIT"
        # Reserve the full admitted input cap, not just the current estimate.
        # Cache write can cost more than ordinary input; use the maximum input rate.
        input_rate = max(
            Decimal(self.rates.input_usd_per_million),
            Decimal(self.rates.cache_read_usd_per_million),
            Decimal(self.rates.cache_write_usd_per_million),
        )
        estimate = int(
            (
                input_rate * self.input_limit
                + Decimal(self.rates.output_usd_per_million) * self.output_limit
            ).to_integral_value(rounding=ROUND_CEILING)
        )
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT status,reserved_micro_usd,estimated_micro_usd,usage "
                "FROM model_calls WHERE run_id=?",
                (self.run_id,),
            ).fetchall()
            consumed = sum(r["estimated_micro_usd"] or 0 for r in rows)
            tokens = sum(sum(json.loads(r["usage"]).values()) for r in rows if r["usage"])
            if reason is None:
                if any(r["status"] != "RECORDED" for r in rows):
                    reason = "PRIOR_USAGE_UNRESOLVED"
                elif self.max_calls is not None and len(rows) >= self.max_calls:
                    reason = "MODEL_CALL_LIMIT"
                elif consumed + estimate > self.budget:
                    reason = "ESTIMATED_COST_LIMIT"
                elif self.max_total_tokens is not None and (
                    tokens + self.input_limit + self.output_limit > self.max_total_tokens
                ):
                    reason = "TOTAL_TOKEN_LIMIT"
            if reason:
                db.execute(
                    "INSERT INTO model_admission_rejections(run_id,role,execution_id,reason) "
                    "VALUES(?,?,?,?)",
                    (self.run_id, role, execution_id, reason),
                )
                return None, reason
            cursor = db.execute(
                "INSERT INTO model_calls(run_id,status,projected_input_tokens,"
                "reserved_micro_usd) VALUES(?,'STARTED',?,?)",
                (self.run_id, projected_input, estimate),
            )
            assert cursor.lastrowid is not None
            db.execute(
                "INSERT INTO model_call_context VALUES(?,?,?)",
                (cursor.lastrowid, role, execution_id),
            )
            return cursor.lastrowid, None

    def admit_tool(
        self, role: str, execution_id: str, name: str, cancellation: str | None = None
    ) -> str | None:
        """Count admitted attempts, including tool errors; never store arguments/secrets."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT COUNT(*) FROM tool_admissions WHERE run_id=? AND status='ADMITTED'",
                (self.run_id,),
            ).fetchone()[0]
            reason = cancellation
            if reason is None and self.max_tool_calls is not None and count >= self.max_tool_calls:
                reason = "SHARED_TOOL_CALL_LIMIT"
            db.execute(
                "INSERT INTO tool_admissions(run_id,role,execution_id,tool_name,status,reason) "
                "VALUES(?,?,?,?,?,?)",
                (
                    self.run_id,
                    role,
                    execution_id,
                    name,
                    "REJECTED" if reason else "ADMITTED",
                    reason,
                ),
            )
            return reason

    def finish(self, call_id: int, usage: dict[str, Any] | None, error: str | None = None) -> None:
        status, cost, normalized = "USAGE_UNKNOWN", None, None
        if error:
            status = "ERROR"
        elif usage is not None and {"inputTokens", "outputTokens"}.issubset(usage):
            try:
                normalized = {
                    k: usage.get(k, 0)
                    for k in (
                        "inputTokens",
                        "outputTokens",
                        "cacheReadInputTokens",
                        "cacheWriteInputTokens",
                    )
                }
                cost = self.rates.micro_usd(normalized)
                status = "RECORDED"
            except (ValueError, TypeError):
                error = "INVALID_USAGE"
                normalized = None
        with self.connect() as db:
            changed = db.execute(
                "UPDATE model_calls SET status=?,estimated_micro_usd=?,usage=?,"
                "error_type=?,finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                "WHERE id=? AND run_id=? AND status='STARTED'",
                (
                    status,
                    cost,
                    json.dumps(normalized) if normalized is not None else None,
                    error,
                    call_id,
                    self.run_id,
                ),
            ).rowcount
            if changed != 1:
                raise ValueError("Usage call is missing or already finalized")

    def report(self) -> dict[str, Any]:
        with self.connect() as db:
            config = dict(
                db.execute("SELECT * FROM model_runs WHERE run_id=?", (self.run_id,)).fetchone()
            )
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT c.*,a.role,a.execution_id FROM model_calls c "
                    "LEFT JOIN model_call_context a ON a.call_id=c.id "
                    "WHERE c.run_id=? ORDER BY c.id",
                    (self.run_id,),
                )
            ]
            rejections = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM model_admission_rejections WHERE run_id=? ORDER BY id",
                    (self.run_id,),
                )
            ]
            tool_rows = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM tool_admissions WHERE run_id=? ORDER BY id", (self.run_id,)
                )
            ]
        recorded = sum(r["estimated_micro_usd"] or 0 for r in rows)
        unresolved = sum(r["reserved_micro_usd"] for r in rows if r["status"] != "RECORDED")
        tokens = sum(sum(json.loads(r["usage"]).values()) for r in rows if r["usage"])
        return {
            "config": config,
            "calls": rows,
            "admission_rejections": rejections,
            "tool_admissions": tool_rows,
            "admitted_tool_calls": sum(r["status"] == "ADMITTED" for r in tool_rows),
            "max_tool_calls": self.max_tool_calls,
            "max_total_tokens": self.max_total_tokens,
            "recorded_total_tokens": tokens,
            "unresolved_reserved_tokens": sum(
                self.input_limit + self.output_limit for r in rows if r["status"] != "RECORDED"
            ),
            "estimated_token_budget_exceeded": (
                self.max_total_tokens is not None and tokens > self.max_total_tokens
            ),
            "recorded_micro_usd": recorded,
            "unresolved_reserved_micro_usd": unresolved,
            "all_usage_recorded": all(r["status"] == "RECORDED" for r in rows),
            "estimated_budget_exceeded": recorded > self.budget,
            "billing_verified": False,
            "max_model_calls": self.max_calls,
            "role_usage": {
                role: {
                    "scope": config["scope"],
                    "model_calls": sum((r["role"] or "unattributed") == role for r in rows),
                    "admission_rejections": sum(r["role"] == role for r in rejections),
                    "admitted_tool_calls": sum(
                        r["role"] == role and r["status"] == "ADMITTED" for r in tool_rows
                    ),
                    "rejected_tool_calls": sum(
                        r["role"] == role and r["status"] == "REJECTED" for r in tool_rows
                    ),
                    "status_counts": {
                        status: sum(
                            (r["role"] or "unattributed") == role and r["status"] == status
                            for r in rows
                        )
                        for status in ("STARTED", "RECORDED", "USAGE_UNKNOWN", "ERROR")
                    },
                    "recorded_tokens": {
                        key: sum(
                            json.loads(r["usage"])[key]
                            for r in rows
                            if (r["role"] or "unattributed") == role and r["status"] == "RECORDED"
                        )
                        for key in (
                            "inputTokens",
                            "outputTokens",
                            "cacheReadInputTokens",
                            "cacheWriteInputTokens",
                        )
                    },
                    "recorded_micro_usd": sum(
                        r["estimated_micro_usd"] or 0
                        for r in rows
                        if (r["role"] or "unattributed") == role
                    ),
                    "unresolved_reserved_micro_usd": sum(
                        r["reserved_micro_usd"]
                        for r in rows
                        if (r["role"] or "unattributed") == role and r["status"] != "RECORDED"
                    ),
                }
                for role in sorted(
                    {r["role"] or "unattributed" for r in rows}
                    | {r["role"] for r in rejections}
                    | {r["role"] for r in tool_rows}
                )
            },
        }


class ObservedModel(Model):
    """Retain provider usage before the SDK fills missing counts with zero."""

    def __init__(self, provider: Model):
        self.provider = provider
        self.raw_usage: dict[str, Any] | None = None

    def update_config(self, **kwargs: Any) -> None:
        self.provider.update_config(**kwargs)

    def get_config(self) -> Any:
        return self.provider.get_config()

    async def count_tokens(self, *args: Any, **kwargs: Any) -> Any:
        return await self.provider.count_tokens(*args, **kwargs)

    async def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        # The rehearsal runners use ordinary streaming plus explicit output parsing.
        raise NotImplementedError("Usage-observed structured output is not supported")
        yield

    async def stream(self, *args: Any, **kwargs: Any) -> Any:
        self.raw_usage = None
        async for chunk in self.provider.stream(*args, **kwargs):
            if "metadata" in chunk:
                usage = chunk["metadata"].get("usage")
                self.raw_usage = dict(usage) if isinstance(usage, dict) else None
            yield chunk


class MeterHooks:
    def __init__(
        self, ledger: UsageLedger, *, role: str = "executor", execution_id: str | None = None
    ):
        self.ledger = ledger
        self.role, self.execution_id = role, execution_id
        self.active: int | None = None
        self.lock = threading.Lock()
        self.stop_reason: str | None = None
        self.observed_model: ObservedModel | None = None

    def observe(self, model: Model) -> ObservedModel:
        self.observed_model = ObservedModel(model)
        return self.observed_model

    def before_tool(self, event: BeforeToolCallEvent) -> None:
        reason = self.ledger.admit_tool(
            self.role,
            self.execution_id or self.ledger.run_id,
            event.tool_use["name"],
            str(event.cancel_tool) if event.cancel_tool else None,
        )
        if reason:
            event.cancel_tool = reason
            self.stop_reason = reason

    def before(self, event: BeforeModelCallEvent) -> None:
        # A prior limit hook may have canceled before a model invocation was made.
        if event.cancel:
            return
        if self.stop_reason:
            event.cancel = self.stop_reason
            return
        with self.lock:
            self.active, reason = self.ledger.reserve(
                event.projected_input_tokens, role=self.role, execution_id=self.execution_id
            )
            if reason:
                self.stop_reason = reason
                event.cancel = reason

    def after(self, event: AfterModelCallEvent) -> None:
        with self.lock:
            call_id, self.active = self.active, None
            if call_id is None:
                return  # SDK also emits AfterModelCall for canceled calls.
            usage = None
            if self.observed_model is not None:
                usage = self.observed_model.raw_usage
            elif event.stop_response is not None:
                sdk_usage = event.stop_response.message.get("metadata", {}).get("usage")
                usage = dict(sdk_usage) if sdk_usage is not None else None
            self.ledger.finish(
                call_id,
                dict(usage) if usage is not None else None,
                type(event.exception).__name__ if event.exception else None,
            )
