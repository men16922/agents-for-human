"""Durable, globally bounded admission and per-run lifecycle; no user-set budgets."""

from __future__ import annotations

import time
from typing import Any

from .domain import Json, Rejected, canonical, digest, identifier

METHODS = ("B0", "B1", "B2", "B3")
CASES = ("normal", "stock-change", "price-change", "unavailable", "untrusted-supplier")
PER_RUN_MICRO_USD = 500_000


class Control:
    def __init__(self, client: Any, table: str):
        self.client, self.table = client, table

    @staticmethod
    def key(run_id: str) -> Json:
        return {"pk": {"S": "RUN#" + identifier(run_id)}, "sk": {"S": "CONTROL"}}

    def get(self, run_id: str) -> Json | None:
        response = self.client.get_item(
            TableName=self.table, Key=self.key(run_id), ConsistentRead=True
        )
        if "Item" not in response:
            return None
        from boto3.dynamodb.types import TypeDeserializer  # type: ignore[import-untyped]

        decoder = TypeDeserializer()
        return {k: decoder.deserialize(v) for k, v in response["Item"].items()}

    def admit(self, request_id: str, method: str, case: str, scenario: Json) -> Json:
        identifier(request_id)
        preview = method == "PREFLIGHT" and case in {"family-camping", "no-tents"}
        if not preview and (method not in METHODS or case not in CASES):
            raise Rejected("UNKNOWN_EXPERIMENT")
        run_id = ("preview-" if preview else "rehearsal-") + digest(request_id)[:32]
        previous = self.get(run_id)
        if previous:
            if previous["method"] != method or previous["case"] != case:
                raise Rejected("IDEMPOTENCY_CONFLICT")
            return previous
        reserve = 0 if method == "B0" else PER_RUN_MICRO_USD
        now = int(time.time())
        meta = {
            **self.key(run_id),
            "run_id": {"S": run_id},
            "method": {"S": method},
            "case": {"S": case},
            "scenario": {"S": canonical(scenario)},
            "status": {"S": "QUEUED"},
            "created_at": {"N": str(now)},
            "deadline_at": {"N": str(now + 600)},
            "reservation": {"N": str(reserve)},
            "session_id": {"S": run_id},
            "started": {"BOOL": False},
            "finalized": {"BOOL": False},
        }
        try:
            self.client.transact_write_items(
                ClientRequestToken=digest([run_id, method, case, now])[:32],
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self.table,
                            "Key": {"pk": {"S": "GLOBAL"}, "sk": {"S": "BUDGET"}},
                            "UpdateExpression": "SET remaining = remaining - :r, active = :one, "
                            "runs_left = runs_left - :one",
                            "ConditionExpression": "remaining >= :r AND active = :zero "
                            "AND runs_left > :zero AND closes_at > :now",
                            "ExpressionAttributeValues": {
                                ":r": {"N": str(reserve)},
                                ":one": {"N": "1"},
                                ":zero": {"N": "0"},
                                ":now": {"N": str(now)},
                            },
                        }
                    },
                    {
                        "Put": {
                            "TableName": self.table,
                            "Item": meta,
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                ],
            )
        except Exception as exc:
            previous = self.get(run_id)
            if previous and previous["method"] == method and previous["case"] == case:
                return previous
            if getattr(exc, "response", {}).get("Error", {}).get("Code") == (
                "TransactionCanceledException"
            ):
                raise Rejected("DEMO_BUSY_OR_LIMIT_REACHED") from exc
            raise
        created = self.get(run_id)
        assert created is not None
        return created

    def claim(self, run_id: str) -> Json:
        self.client.update_item(
            TableName=self.table,
            Key=self.key(run_id),
            UpdateExpression="SET started = :yes, #s = :running",
            ConditionExpression="started = :no AND finalized = :no AND deadline_at > :now "
            "AND (attribute_not_exists(closing) OR closing = :no)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":yes": {"BOOL": True},
                ":no": {"BOOL": False},
                ":running": {"S": "RUNNING"},
                ":now": {"N": str(int(time.time()))},
            },
        )
        meta = self.get(run_id)
        assert meta is not None
        return meta

    def publish(self, run_id: str, name: str, value: Json) -> None:
        if name not in {"progress", "runtime", "verification"}:
            raise ValueError("Invalid published field")
        self.client.update_item(
            TableName=self.table,
            Key=self.key(run_id),
            UpdateExpression="SET #field = :body",
            ConditionExpression="attribute_exists(pk) AND finalized = :no",
            ExpressionAttributeNames={"#field": name},
            ExpressionAttributeValues={":body": {"S": canonical(value)}, ":no": {"BOOL": False}},
        )

    def close(self, run_id: str) -> None:
        """Fence all in-flight commerce commits before independent final audit."""
        self.client.update_item(
            TableName=self.table,
            Key=self.key(run_id),
            UpdateExpression="SET closing = :yes",
            ConditionExpression="attribute_exists(pk) AND finalized = :no",
            ExpressionAttributeValues={":yes": {"BOOL": True}, ":no": {"BOOL": False}},
        )

    def finalize(self, run_id: str, cost: int | None, status: str) -> None:
        meta = self.get(run_id)
        if not meta or meta["finalized"]:
            return
        # Unknown usage retains the entire admitted reservation. Never refund from a timeout.
        reservation = int(meta["reservation"])
        if cost is not None and (type(cost) is not int or cost < 0):
            raise ValueError("Invalid cost")
        refund = reservation - cost if cost is not None else 0
        self.client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": self.table,
                        "Key": self.key(run_id),
                        "UpdateExpression": "SET finalized = :yes, #s = :status, "
                        "recorded_cost = :cost, "
                        "unresolved_reservation = :reserved",
                        "ConditionExpression": "finalized = :no",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":yes": {"BOOL": True},
                            ":no": {"BOOL": False},
                            ":status": {"S": status},
                            ":cost": {"N": str(cost or 0)},
                            ":reserved": {"N": str(reservation if cost is None else 0)},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": self.table,
                        "Key": {"pk": {"S": "GLOBAL"}, "sk": {"S": "BUDGET"}},
                        "UpdateExpression": "SET remaining = remaining + :refund, active = :zero",
                        "ConditionExpression": "active = :one",
                        "ExpressionAttributeValues": {
                            ":refund": {"N": str(refund)},
                            ":zero": {"N": "0"},
                            ":one": {"N": "1"},
                        },
                    }
                },
            ]
        )
