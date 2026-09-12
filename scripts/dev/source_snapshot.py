#!/usr/bin/env python3
"""Copy Git-visible source into a private, hash-checked reproduction directory.

This neither commits nor publishes the tree. Ignored local state is never included.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = {
    ".git",
    ".local",
    ".tooling",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "playwright-report",
    "test-results",
}
SECRET = re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


def visible(root: Path) -> list[str]:
    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    )
    return sorted(set(raw.decode().rstrip("\0").split("\0")))


def snapshot(root: Path, directory: Path) -> dict:
    root = root.resolve()
    directory = directory.resolve()
    if directory == root or root.is_relative_to(directory):
        raise ValueError("Snapshot destination must not contain the source repository")
    names = visible(root)
    records = {}
    # Validate every path before making the destination or copying any content.
    for name in names:
        rel = Path(name)
        source = root / rel
        if (
            not name
            or rel.is_absolute()
            or ".." in rel.parts
            or any(p in FORBIDDEN for p in rel.parts)
            or any(p.startswith(".env") and p != ".env.example" for p in rel.parts)
            or any((root / parent).is_symlink() for parent in (rel, *rel.parents))
            or not source.is_file()
            or not source.resolve().is_relative_to(root)
        ):
            raise ValueError(f"Unsafe or missing source path: {name}")
        raw = source.read_bytes()
        if SECRET.search(raw):
            raise ValueError(f"Credential pattern found; content not printed: {name}")
        records[name] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "executable": bool(source.stat().st_mode & stat.S_IXUSR),
        }
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    target = directory / "source"
    target.mkdir(mode=0o700)
    for name, record in records.items():
        raw = (root / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError(f"Source changed during copy: {name}")
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o755 if record["executable"] else 0o644)
    if visible(root) != names or any(
        hashlib.sha256((root / name).read_bytes()).hexdigest() != record["sha256"]
        for name, record in records.items()
    ):
        raise ValueError("Source changed during snapshot; copy is not approved for reproduction")
    manifest = {
        "schema": "rehearsal-source-snapshot-v1",
        "scope": "local-unpublished-source-copy-not-a-git-release",
        "files": records,
        "file_count": len(records),
        "total_bytes": sum(r["bytes"] for r in records.values()),
        "ignored_runtime_credentials_databases_included": False,
        "source_unchanged_during_copy": True,
    }
    (directory / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    manifest = snapshot(ROOT, args.directory)
    print(f"Copied {manifest['file_count']} files / {manifest['total_bytes']} bytes.")
    print(f"Private reproduction inputs: {args.directory}; no commit or publication.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
