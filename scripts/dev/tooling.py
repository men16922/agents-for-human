#!/usr/bin/env python3
"""Install pinned runtimes into this repository, without changing shell profiles."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    pins = json.loads((ROOT / "dev/toolchain.json").read_text())
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv is required. See docs/DEVELOPMENT.md; no global installer is run.")
    actual_uv = subprocess.check_output([uv, "--version"], text=True).split()[1]
    if actual_uv != pins["uv"]:
        raise SystemExit(
            f"Expected uv {pins['uv']}, found {actual_uv}. Use the documented version."
        )
    local = ROOT / ".tooling"
    local.mkdir(exist_ok=True)
    env = os.environ | {
        "UV_CACHE_DIR": str(local / "uv-cache"),
        "UV_PYTHON_INSTALL_DIR": str(local / "python"),
        "UV_PYTHON_PREFERENCE": "only-managed",
    }
    subprocess.run([uv, "python", "install", pins["python"], "--no-bin"], env=env, check=True)
    system = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64"}.get(platform.machine())
    key = f"{system}-{arch}"
    if key not in pins["node_artifacts"]:
        raise SystemExit(f"Unsupported platform {key}; use documented macOS/Linux environments.")
    target = local / "node"
    binary = target / "bin/node"
    if not binary.exists():
        artifact = pins["node_artifacts"][key]
        url = f"https://nodejs.org/download/release/v{pins['node']}/{artifact['archive']}"
        with tempfile.TemporaryDirectory(prefix="node-", dir=local) as scratch:
            archive = Path(scratch) / artifact["archive"]
            with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as out:
                shutil.copyfileobj(response, out)
            if hashlib.sha256(archive.read_bytes()).hexdigest() != artifact["sha256"]:
                raise SystemExit("Node archive SHA-256 mismatch; refusing extraction.")
            with tarfile.open(archive) as bundle:
                if not hasattr(tarfile, "data_filter"):
                    raise SystemExit("Bootstrap requires Python with tarfile data_filter (3.12+).")
                bundle.extractall(scratch, filter="data")
            extracted = Path(scratch) / artifact["archive"].removesuffix(".tar.gz")
            extracted.rename(target)
    version = subprocess.check_output([str(binary), "--version"], text=True).strip()
    if version != f"v{pins['node']}":
        raise SystemExit(f"Unexpected local Node: {version}; preserve and inspect .tooling/node.")
    print(
        f"Ready: Python {pins['python']}; Node {version}; uv {actual_uv}; repository-local runtimes"
    )


if __name__ == "__main__":
    main()
