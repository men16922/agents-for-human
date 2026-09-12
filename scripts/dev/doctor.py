#!/usr/bin/env python3
"""Read-only, offline readiness checks; a missing tool is a failure, never a skip."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    pins = json.loads((ROOT / "dev/toolchain.json").read_text())
    required = [
        ".venv/bin/python",
        ".tooling/node/bin/node",
        "node_modules/.package-lock.json",
        "uv.lock",
        "package-lock.json",
    ]
    missing = [item for item in required if not (ROOT / item).is_file()]
    if missing:
        print("FAIL: missing " + ", ".join(missing) + "; run make setup.", file=sys.stderr)
        return 1
    checks = [
        (
            "Python version",
            [
                str(ROOT / ".venv/bin/python"),
                "-c",
                f"import platform; assert platform.python_version() == {pins['python']!r}",
            ],
        ),
        (
            "Node version",
            [
                str(ROOT / ".tooling/node/bin/node"),
                "-e",
                f"if(process.versions.node !== {json.dumps(pins['node'])}) process.exit(1)",
            ],
        ),
        (
            "Python imports",
            [
                str(ROOT / ".venv/bin/python"),
                "-c",
                "from rehearsal.api import app; from strands import Agent; "
                "from strands.multiagent import GraphBuilder; "
                "from strands.models import BedrockModel; "
                "import sqlite3; assert sqlite3.sqlite_version_info >= (3, 35)",
            ],
        ),
        (
            "Python dependency compatibility",
            ["uv", "pip", "check", "--python", str(ROOT / ".venv/bin/python")],
        ),
        ("npm dependency compatibility", ["npm", "ls", "--depth=0", "--json"]),
    ]
    for label, command in checks:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        if result.returncode:
            print(
                f"FAIL: {label}. Run make setup and inspect dependency versions.", file=sys.stderr
            )
            # Import errors can be diagnosed without printing environment values.
            print(result.stderr[-2000:], file=sys.stderr)
            return 1
        print("PASS: " + label, flush=True)
    print("Scope: local tools/imports only; no model initialization, AWS or commerce request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
