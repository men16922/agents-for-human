"""Persist provider-call admission/usage before another paid call can proceed."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from rehearsal.agents.metering import UsageLedger

from .control import Control


class DurableLedger(UsageLedger):
    control: Control
    s3: Any
    bucket: str
    cloud_run_id: str

    def bind(self, control: Control, s3: Any, bucket: str, run_id: str) -> None:
        self.control, self.s3, self.bucket, self.cloud_run_id = control, s3, bucket, run_id
        self.persist()

    def persist(self) -> None:
        import sqlite3

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "usage.sqlite3"
            with self.connect() as source:
                with sqlite3.connect(target) as backup:
                    source.backup(backup)
            self.s3.put_object(
                Bucket=self.bucket,
                Key=f"runs/{self.cloud_run_id}/usage.sqlite3",
                Body=target.read_bytes(),
                ContentType="application/octet-stream",
            )
        self.control.publish(self.cloud_run_id, "progress", {"usage": self.report()})

    def reserve(
        self,
        projected_input: int | None,
        *,
        role: str = "executor",
        execution_id: str | None = None,
    ) -> tuple[int | None, str | None]:
        result = super().reserve(projected_input, role=role, execution_id=execution_id)
        self.persist()
        return result

    def finish(self, call_id: int, usage: dict[str, Any] | None, error: str | None = None) -> None:
        super().finish(call_id, usage, error)
        self.persist()
