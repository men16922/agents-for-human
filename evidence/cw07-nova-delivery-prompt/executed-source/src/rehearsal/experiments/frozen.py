"""Content-addressed policy + execution-source manifests, created before fixture execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from rehearsal.agents.executor import SYSTEM_PROMPT
from rehearsal.world.storage import ContractError, Json, canonical

from .policy import Policy, policy_prompt

SOURCES = (
    "src/rehearsal/experiments/baseline.py",
    "src/rehearsal/experiments/policy.py",
    "src/rehearsal/agents/executor.py",
    "src/rehearsal/agents/runner.py",
    "src/rehearsal/operating/tools.py",
)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def manifest_id(value: Json) -> str:
    return "frozen-" + digest(canonical({k: v for k, v in value.items() if k != "id"}).encode())


@dataclass(frozen=True)
class FrozenPolicy:
    policy: Policy
    identifier: str
    prompt_sha256: str
    sources: tuple[tuple[str, str], ...]
    root: Path
    learning_evidence: tuple[tuple[str, str], ...] = ()

    def check(self) -> None:
        if digest(policy_prompt(SYSTEM_PROMPT, self.policy).encode()) != self.prompt_sha256:
            raise ContractError("FROZEN_PROMPT_CHANGED")
        if any(digest((self.root / path).read_bytes()) != sha for path, sha in self.sources):
            raise ContractError("FROZEN_EXECUTION_SOURCE_CHANGED")

    @classmethod
    def load(cls, path: Path, root: Path) -> FrozenPolicy:
        value = json.loads(path.read_text())
        required = {
            "id",
            "schema",
            "policy",
            "policy_version",
            "prompt_sha256",
            "source_sha256",
            "learning_evidence",
            "scope",
        }
        if set(value) != required or value["schema"] != "rehearsal-frozen-policy-v1":
            raise ContractError("INVALID_FROZEN_MANIFEST")
        policy = Policy.parse(value["policy"])
        if value["id"] != manifest_id(value) or value["policy_version"] != policy.version:
            raise ContractError("FROZEN_MANIFEST_MISMATCH")
        if set(value["source_sha256"]) != set(SOURCES):
            raise ContractError("FROZEN_SOURCE_SET_MISMATCH")
        result = cls(
            policy,
            value["id"],
            value["prompt_sha256"],
            tuple(sorted(value["source_sha256"].items())),
            root,
            tuple(sorted(value["learning_evidence"].items())),
        )
        result.check()
        return result


def freeze(
    policy: Policy, path: Path, root: Path, learning: dict[str, Path] | None = None
) -> FrozenPolicy:
    value: Json = {
        "schema": "rehearsal-frozen-policy-v1",
        "policy": asdict(policy),
        "policy_version": policy.version,
        "prompt_sha256": digest(policy_prompt(SYSTEM_PROMPT, policy).encode()),
        "source_sha256": {name: digest((root / name).read_bytes()) for name in SOURCES},
        "learning_evidence": {name: digest(p.read_bytes()) for name, p in (learning or {}).items()},
        "scope": "immutable-execution-input-not-proof-of-model-or-held-out-performance",
    }
    value["id"] = manifest_id(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as output:
        output.write(json.dumps(value, indent=2) + "\n")
    return FrozenPolicy.load(path, root)
