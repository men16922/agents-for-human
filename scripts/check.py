#!/usr/bin/env python3
"""Offline checks for the public documentation and its local links."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/DEVELOPMENT.md",
    "docs/TESTING.md",
    "docs/VERIFICATION.md",
    "infra/serverless/README.md",
    "THIRD_PARTY_NOTICES.md",
)


def main(root: Path = ROOT) -> int:
    errors = []
    for name in DOCUMENTS:
        path = root / name
        if not path.is_file():
            errors.append(f"missing document: {name}")
            continue
        text = path.read_text()
        if not text.startswith("# ") or len(text.strip()) < 30:
            errors.append(f"empty or untitled document: {name}")
        for reference in re.findall(r"\]\(([^)]+)\)", text):
            url = urlsplit(reference)
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if not target.is_relative_to(root.resolve()) or not target.exists():
                errors.append(f"{name}: missing or out-of-repo link: {reference}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {len(DOCUMENTS)} public documents and local links.")
    print("Scope: offline documentation integrity; no cloud or model calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
