"""Integration tests for plan-foundry-sync (AC6 model).

clone_bundle is monkeypatched to a pre-built fixture bundle so tests
do not hit the network. The fixture is a real on-disk git repo that
sync's bundle_copy + write_version_file can read.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

_SYNC_LIB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_SYNC_LIB))

import sync as sync_mod  # noqa: E402


def _init_git_bundle(root: pathlib.Path) -> pathlib.Path:
    """Build a fixture bundle (real git repo) suitable for sync's helpers."""
    bundle_root = root / "fixture-bundle"
    claude = bundle_root / ".claude"
    (claude / "skills" / "init-plan-foundry").mkdir(parents=True)
    (claude / "skills" / "init-plan-foundry" / "operating-rules.md").write_text(
        "operating rules\n"
    )
    (claude / "skills" / "_shared").mkdir(parents=True)
    bundle_copy_src = (
        pathlib.Path(__file__).resolve().parents[2] / "_shared" / "bundle_copy.py"
    )
    (claude / "skills" / "_shared" / "bundle_copy.py").write_text(
        bundle_copy_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (claude / "agents").mkdir(parents=True)
    (claude / "agents" / "an-agent.md").write_text("agent body\n")
    (claude / "commands").mkdir(parents=True)
    (claude / "commands" / "cmd.md").write_text("cmd body\n")
    (claude / "hooks").mkdir(parents=True)
    (claude / "hooks" / "hook.json").write_text("{}\n")

    subprocess.run(["git", "init", "--quiet"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=bundle_root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=bundle_root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "init"], cwd=bundle_root, check=True
    )
    return bundle_root


def _init_target_via_copy(bundle_root: pathlib.Path, target_root: pathlib.Path):
    """Simulate having previously run /init-plan-foundry."""
    sys.path.insert(0, str(bundle_root / ".claude" / "skills" / "_shared"))
    import bundle_copy

    target_claude = target_root / ".claude"
    bundle_copy.copy_bundle_managed(bundle_root / ".claude", target_claude)
    bundle_copy.write_version_file(bundle_root, target_claude)


@pytest.fixture
def patched_clone(monkeypatch, tmp_path):
    """Replace clone_bundle with a function that 'clones' from a fixture path."""
    bundle_root = _init_git_bundle(tmp_path)

    def fake_clone(target_root, ref="main"):
        import shutil

        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(bundle_root, tmp)
        return tmp

    sync_mod._import_local_helpers()  # ensure bundle_fetch is sys.path-visible
    import bundle_fetch

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone)
    return bundle_root


def test_sync_success_when_bundle_advances(patched_clone, tmp_path: pathlib.Path):
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    new_file = bundle_root / ".claude" / "skills" / "new-skill" / "SKILL.md"
    new_file.parent.mkdir(parents=True)
    new_file.write_text("new skill body\n")
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "add new-skill"],
        cwd=bundle_root,
        check=True,
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert "skills/new-skill/SKILL.md" in result["payload"]["files_copied"]
    assert (target / ".claude" / "skills" / "new-skill" / "SKILL.md").exists()
    assert result["payload"]["previous_sha"] != result["payload"]["new_sha"]
    assert not (target / ".plan-foundry-tmp").exists(), "tmp clone must be cleaned up"


def test_sync_refuses_when_claude_is_symlink(patched_clone, tmp_path: pathlib.Path):
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    target_claude = target / ".claude"
    try:
        target_claude.symlink_to(bundle_root / ".claude", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform/permission level")
    result = sync_mod.sync(target)
    assert result["outcome"] == "exception"
    assert "symlink" in result["summary"].lower()


def test_sync_refuses_when_version_file_absent(patched_clone, tmp_path: pathlib.Path):
    target = tmp_path / "target"
    (target / ".claude" / "skills").mkdir(parents=True)
    result = sync_mod.sync(target)
    assert result["outcome"] == "exception"
    assert "bundle-version" in result["summary"] or "version" in result["summary"]


def test_sync_refuses_when_claude_absent(patched_clone, tmp_path: pathlib.Path):
    target = tmp_path / "target"
    target.mkdir()
    result = sync_mod.sync(target)
    assert result["outcome"] == "exception"
    assert ".claude" in result["summary"]


def test_sync_preserves_project_additions(patched_clone, tmp_path: pathlib.Path):
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    project_skill = target / ".claude" / "skills" / "myproj" / "SKILL.md"
    project_skill.parent.mkdir(parents=True)
    project_skill.write_text("project skill\n")

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert "skills/myproj/SKILL.md" in result["payload"]["project_additions"]
    assert project_skill.exists()
    assert not (target / ".plan-foundry-tmp").exists()


def test_sync_reports_clone_failure(monkeypatch, tmp_path: pathlib.Path):
    """If clone_bundle raises, sync surfaces the error and returns exception."""
    target = tmp_path / "target"
    target.mkdir()
    # Pre-populate target so we get past the version-file check.
    bundle_root = _init_git_bundle(tmp_path)
    _init_target_via_copy(bundle_root, target)

    sync_mod._import_local_helpers()
    import bundle_fetch

    def fake_clone(target_root, ref="main"):
        raise bundle_fetch.BundleFetchError("network unreachable")

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone)
    result = sync_mod.sync(target)
    assert result["outcome"] == "exception"
    assert "network unreachable" in result["summary"]
