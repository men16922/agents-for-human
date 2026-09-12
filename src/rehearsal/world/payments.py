"""Synthetic credit ledger. Each budget transition and outbox event is atomic."""

from __future__ import annotations

from pathlib import Path

from .storage import ContractError, Database, Json, canonical, emit, identifier, integer, row

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    run_id TEXT PRIMARY KEY, budget INTEGER NOT NULL CHECK(budget>=0),
    spent INTEGER NOT NULL DEFAULT 0 CHECK(spent>=0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved>=0), metadata TEXT NOT NULL,
    CHECK(spent+reserved<=budget)
);
CREATE TABLE IF NOT EXISTS intents (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES accounts(run_id),
    order_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, recipient TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount>0), status TEXT NOT NULL,
    version INTEGER NOT NULL, created_tick INTEGER NOT NULL, settled_tick INTEGER,
    UNIQUE(run_id,idempotency_key), UNIQUE(run_id,order_id),
    CHECK(status IN ('RESERVED','SETTLED'))
);
"""


class PaymentLedger(Database):
    def __init__(self, path: Path):
        super().__init__(path, SCHEMA)

    def create_account(self, run_id: str, budget: int, metadata: Json) -> None:
        integer(budget)
        with self.transaction() as db:
            existing = db.execute("SELECT * FROM accounts WHERE run_id=?", (run_id,)).fetchone()
            if existing:
                if existing["budget"] != budget or existing["metadata"] != canonical(metadata):
                    raise ContractError("RUN_CONFLICT")
                return
            db.execute(
                "INSERT INTO accounts(run_id,budget,metadata) VALUES(?,?,?)",
                (run_id, budget, canonical(metadata)),
            )
            emit(db, run_id, "payments", run_id, 1, 0, "account.created", {"budget": budget})

    def balance(self, run_id: str) -> Json:
        with self.connect() as db:
            result = row(db, "SELECT * FROM accounts WHERE run_id=?", (run_id,))
        return result | {"available": result["budget"] - result["spent"] - result["reserved"]}

    def reserve(
        self,
        run_id: str,
        order_id: str,
        key: str,
        recipient: str,
        amount: int,
        tick: int,
    ) -> Json:
        """Trusted payment service input, resolved from a canonical server-side order."""
        integer(amount, 1)
        integer(tick)
        if not key or not recipient:
            raise ContractError("INVALID_INTENT")
        with self.transaction() as db:
            account = row(db, "SELECT * FROM accounts WHERE run_id=?", (run_id,))
            prior = db.execute(
                "SELECT * FROM intents WHERE run_id=? AND idempotency_key=?", (run_id, key)
            ).fetchone()
            if prior:
                if (prior["order_id"], prior["recipient"], prior["amount"]) != (
                    order_id,
                    recipient,
                    amount,
                ):
                    raise ContractError("IDEMPOTENCY_CONFLICT")
                return dict(prior)
            if db.execute(
                "SELECT 1 FROM intents WHERE run_id=? AND order_id=?", (run_id, order_id)
            ).fetchone():
                raise ContractError("ORDER_ALREADY_HAS_INTENT")
            if account["spent"] + account["reserved"] + amount > account["budget"]:
                raise ContractError("BUDGET_EXCEEDED")
            pid = identifier("pay")
            db.execute("UPDATE accounts SET reserved=reserved+? WHERE run_id=?", (amount, run_id))
            db.execute(
                "INSERT INTO intents VALUES(?,?,?,?,?,?,'RESERVED',1,?,NULL)",
                (pid, run_id, order_id, key, recipient, amount, tick),
            )
            result = row(db, "SELECT * FROM intents WHERE id=?", (pid,))
            emit(db, run_id, "payments", pid, 1, tick, "payment.reserved", result)
            return result

    def get(self, run_id: str, intent_id: str) -> Json:
        with self.connect() as db:
            return row(db, "SELECT * FROM intents WHERE run_id=? AND id=?", (run_id, intent_id))

    def for_order(self, run_id: str, order_id: str) -> Json:
        with self.connect() as db:
            return row(
                db, "SELECT * FROM intents WHERE run_id=? AND order_id=?", (run_id, order_id)
            )

    def settle(self, run_id: str, intent_id: str, tick: int) -> Json:
        """Seller/payment worker operation; never inferred from a client timeout."""
        integer(tick)
        with self.transaction() as db:
            intent = row(db, "SELECT * FROM intents WHERE run_id=? AND id=?", (run_id, intent_id))
            if intent["status"] == "SETTLED":
                return intent
            if tick < intent["created_tick"]:
                raise ContractError("CLOCK_REVERSED")
            db.execute(
                "UPDATE accounts SET reserved=reserved-?,spent=spent+? WHERE run_id=?",
                (intent["amount"], intent["amount"], run_id),
            )
            db.execute(
                "UPDATE intents SET status='SETTLED',version=2,settled_tick=? WHERE id=?",
                (tick, intent_id),
            )
            result = row(db, "SELECT * FROM intents WHERE id=?", (intent_id,))
            emit(db, run_id, "payments", intent_id, 2, tick, "payment.settled", result)
            return result
