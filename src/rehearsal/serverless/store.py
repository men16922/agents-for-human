"""DynamoDB state plus immutable journal in one conditional transaction."""

from __future__ import annotations

import json
from typing import Any

from .domain import Json, Rejected, canonical, digest, identifier, initial, transition


class Conflict(RuntimeError):
    pass


class DynamoStore:
    def __init__(self, client: Any, table: str, control_table: str | None = None):
        self.client, self.table, self.control_table = client, table, control_table

    @staticmethod
    def key(run_id: str, sk: str) -> Json:
        return {"pk": {"S": "RUN#" + identifier(run_id)}, "sk": {"S": sk}}

    def load(self, run_id: str) -> Json:
        item = self.client.get_item(
            TableName=self.table, Key=self.key(run_id, "STATE"), ConsistentRead=True
        ).get("Item")
        if not item:
            raise Rejected("RUN_NOT_FOUND")
        return json.loads(item["body"]["S"])  # type: ignore[no-any-return]

    def create(self, run_id: str, scenario: Json, now: int) -> Json:
        state = initial(run_id, scenario, now)
        record = {
            "version": 0,
            "run_id": run_id,
            "at": now,
            "entries": [{"kind": "CREATED", "scenario": scenario}],
            "previous_sha256": None,
            "state_sha256": digest(state),
        }
        self._commit(state, record, None)
        return state

    def command(
        self, run_id: str, action: str, args: Json, now: int, *, actor: str = "buyer"
    ) -> Any:
        for _ in range(6):
            before = self.load(run_id)
            after, result, entries = transition(before, action, args, now, actor=actor)
            if not entries:
                return result
            record = {
                "version": after["version"],
                "run_id": run_id,
                "at": now,
                "entries": entries,
                "previous_sha256": digest(before),
                "state_sha256": digest(after),
            }
            try:
                self._commit(after, record, before["version"])
                return result
            except Conflict:
                continue
        raise Rejected("CONCURRENT_UPDATE_RETRY")

    def _commit(self, state: Json, event: Json, expected: int | None) -> None:
        item = {
            **self.key(state["run_id"], "STATE"),
            "version": {"N": str(state["version"])},
            "body": {"S": canonical(state)},
        }
        put: Json = {
            "TableName": self.table,
            "Item": item,
            "ConditionExpression": "attribute_not_exists(pk)",
        }
        if expected is not None:
            put.update(
                ConditionExpression="#v = :v",
                ExpressionAttributeNames={"#v": "version"},
                ExpressionAttributeValues={":v": {"N": str(expected)}},
            )
        # No retries for uncertain transport/service errors. A caller reconciles by reading
        # and reusing the same order/payment key; a failed response never releases a reservation.
        try:
            self.client.transact_write_items(
                ClientRequestToken=digest(event)[:32],
                TransactItems=[
                    {"Put": put},
                    {
                        "Put": {
                            "TableName": self.table,
                            "Item": {
                                **self.key(state["run_id"], f"EVENT#{state['version']:06d}"),
                                "body": {"S": canonical(event)},
                            },
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                ]
                + (
                    [
                        {
                            "ConditionCheck": {
                                "TableName": self.control_table,
                                "Key": self.key(state["run_id"], "CONTROL"),
                                "ConditionExpression": (
                                    "attribute_exists(pk) AND finalized = :no AND "
                                    "(attribute_not_exists(closing) OR closing = :no)"
                                ),
                                "ExpressionAttributeValues": {":no": {"BOOL": False}},
                            }
                        }
                    ]
                    if self.control_table
                    else []
                ),
            )
        except Exception as exc:
            response = getattr(exc, "response", {})
            reasons = response.get("CancellationReasons", [])
            if (
                self.control_table
                and len(reasons) == 3
                and reasons[2].get("Code") == "ConditionalCheckFailed"
            ):
                raise Rejected("RUN_CLOSED") from exc
            if response.get("Error", {}).get("Code") == "TransactionCanceledException" and any(
                reason.get("Code") == "ConditionalCheckFailed" for reason in reasons
            ):
                raise Conflict("State version already changed") from exc
            raise

    def journal(self, run_id: str, version: int) -> list[Json]:
        records: list[Json] = []
        query: Json = {
            "TableName": self.table,
            "ConsistentRead": True,
            "KeyConditionExpression": "pk = :pk AND sk BETWEEN :lo AND :hi",
            "ExpressionAttributeValues": {
                ":pk": {"S": "RUN#" + identifier(run_id)},
                ":lo": {"S": "EVENT#000000"},
                ":hi": {"S": f"EVENT#{version:06d}"},
            },
        }
        while True:
            page = self.client.query(**query)
            records.extend(json.loads(item["body"]["S"]) for item in page["Items"])
            if not page.get("LastEvaluatedKey"):
                return records
            query["ExclusiveStartKey"] = page["LastEvaluatedKey"]
