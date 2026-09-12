#!/usr/bin/env python3
"""Build a secret-free code zip from the pinned ARM64 dependency directory."""

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
folder = ROOT / ".local/serverless-deploy"
package = folder / "agent-package"
assert (package / "strands").is_dir(), "Install pinned ARM64 requirements first"
shutil.copytree(
    ROOT / "src/rehearsal",
    package / "src/rehearsal",
    dirs_exist_ok=True,
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
)
(package / "main.py").write_text("""import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from rehearsal.serverless.functions import handler
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("rehearsal.serverless.runtime:app", host="0.0.0.0", port=8080)
""")
output = folder / "code.zip"
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
    for file in sorted(package.rglob("*")):
        if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
            z.write(file, file.relative_to(package))
report = {
    "file": str(output),
    "bytes": output.stat().st_size,
    "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
}
(folder / "package.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
