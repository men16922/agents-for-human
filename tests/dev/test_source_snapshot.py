import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("snapshot", ROOT / "scripts/dev/source_snapshot.py")
assert spec and spec.loader
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text(".env\n.local/\nnode_modules/\n")
    (root / ".env").write_text("PRIVATE=never-copy-this\n")
    (root / "source.py").write_text("print('source')\n")
    (root / "source.py").chmod(0o755)
    (root / ".env.example").write_text("PRIVATE=\n")
    return root, tmp_path / "snapshot"


def test_uncommitted_source_copy_has_exact_hashes_and_excludes_ignored_secrets(repo):
    root, target = repo
    report = snapshot.snapshot(root, target)
    assert report["file_count"] == 3
    assert set(report["files"]) == {".gitignore", ".env.example", "source.py"}
    assert not (target / "source/.env").exists()
    for name, row in report["files"].items():
        assert hashlib.sha256((target / "source" / name).read_bytes()).hexdigest() == row["sha256"]
    assert (target / "source/source.py").stat().st_mode & 0o111
    assert json.loads((target / "source-manifest.json").read_text()) == report
    with pytest.raises(FileExistsError):
        snapshot.snapshot(root, target)


def test_forced_git_tracking_does_not_override_secret_exclusion(repo):
    root, target = repo
    subprocess.run(["git", "add", "-f", ".env"], cwd=root, check=True)
    with pytest.raises(ValueError, match="Unsafe"):
        snapshot.snapshot(root, target)
    assert not target.exists()


def test_symlink_cannot_copy_private_sibling(repo):
    root, target = repo
    private = root.parent / "private.txt"
    private.write_text("not-source")
    (root / "public.txt").symlink_to(private)
    with pytest.raises(ValueError, match="Unsafe"):
        snapshot.snapshot(root, target)
    assert not target.exists()


def test_credential_pattern_is_rejected_without_printing_the_value(repo):
    root, target = repo
    secret = "AKIA" + "Q" * 16
    (root / "accidental.txt").write_text(secret)
    with pytest.raises(ValueError, match="Credential pattern") as error:
        snapshot.snapshot(root, target)
    assert secret not in str(error.value) and not target.exists()


def test_parent_destination_cannot_contain_the_live_tree(repo):
    root, _ = repo
    with pytest.raises(ValueError, match="destination"):
        snapshot.snapshot(root, root.parent)
    assert (root / "source.py").is_file()
