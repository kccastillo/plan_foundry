"""
Tests for scripts/recover-deleted-retirees.py.

Uses tempfile.TemporaryDirectory to construct synthetic git repos and exercise
each function against known states.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile

import pytest

# Load the script as a module (script filename has hyphens, not valid Python identifier).
SCRIPT_PATH = pathlib.Path(__file__).parent / "recover-deleted-retirees.py"
spec = importlib.util.spec_from_file_location("recover_deleted_retirees", SCRIPT_PATH)
recover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recover)


def _git(repo_root: pathlib.Path, *args: str) -> str:
    """Helper to run git in a repo with predictable config."""
    env_args = [
        "-c", "user.name=Test",
        "-c", "user.email=test@example.com",
        "-c", "commit.gpgsign=false",
    ]
    result = subprocess.run(
        ["git", "-C", str(repo_root), *env_args, *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _init_repo() -> pathlib.Path:
    """Create a tmp dir, init git there, and return its path."""
    tmp = tempfile.mkdtemp()
    root = pathlib.Path(tmp)
    _git(root, "init", "--initial-branch=main")
    (root / "Workbench").mkdir()
    (root / "Retired").mkdir()
    return root


def test_1_find_deletion_commit():
    """find_deletion_commit returns the SHA of the rm commit."""
    root = _init_repo()
    (root / "Workbench" / "PLAN-099_test.md").write_text("---\nfoo: bar\n---\nbody", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "add")
    _git(root, "rm", "Workbench/PLAN-099_test.md")
    _git(root, "commit", "-m", "delete")
    rm_sha = _git(root, "rev-parse", "HEAD").strip()

    sha = recover.find_deletion_commit(root, "Workbench/PLAN-099_test.md")
    assert sha == rm_sha


def test_2_extract_body_pre_deletion():
    """extract_body_pre_deletion returns the original content."""
    root = _init_repo()
    body_text = "---\ntitle: Test\n---\nbody content"
    (root / "Workbench" / "PLAN-098_x.md").write_text(body_text, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "add")
    _git(root, "rm", "Workbench/PLAN-098_x.md")
    _git(root, "commit", "-m", "delete")
    sha = _git(root, "rev-parse", "HEAD").strip()

    body = recover.extract_body_pre_deletion(root, sha, "Workbench/PLAN-098_x.md")
    # git show may add a trailing newline or normalise line endings on some platforms;
    # be tolerant on the trailing byte, strict on the body content.
    assert body_text.encode("utf-8") in body or body.decode("utf-8").rstrip() == body_text.rstrip()


def test_3_recover_one_end_to_end():
    """recover_one writes the file to Retired/."""
    root = _init_repo()
    (root / "Workbench" / "PLAN-097_y.md").write_text("payload", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "add")
    _git(root, "rm", "Workbench/PLAN-097_y.md")
    _git(root, "commit", "-m", "delete")

    result = recover.recover_one(root, "PLAN-097_y.md")
    assert result["status"] == "success"
    assert (root / "Retired" / "PLAN-097_y.md").exists()
    assert (root / "Retired" / "PLAN-097_y.md").read_text(encoding="utf-8").startswith("payload")


def test_4_file_never_existed():
    """recover_one returns unrecoverable when no deletion record and no slug match exist."""
    root = _init_repo()
    (root / "Workbench" / "other.md").write_text("x", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "init")

    result = recover.recover_one(root, "PLAN-096_never.md")
    assert result["status"] == "unrecoverable"
    assert not (root / "Retired" / "PLAN-096_never.md").exists()


def test_5_already_present_is_idempotent():
    """recover_one returns already_present without overwriting."""
    root = _init_repo()
    (root / "Workbench" / "PLAN-095_z.md").write_text("v1", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "add")
    _git(root, "rm", "Workbench/PLAN-095_z.md")
    _git(root, "commit", "-m", "delete")

    # Pre-populate Retired/ with different content; recover_one should NOT overwrite.
    (root / "Retired" / "PLAN-095_z.md").write_text("DIFFERENT", encoding="utf-8")

    result = recover.recover_one(root, "PLAN-095_z.md")
    assert result["status"] == "already_present"
    assert (root / "Retired" / "PLAN-095_z.md").read_text(encoding="utf-8") == "DIFFERENT"
