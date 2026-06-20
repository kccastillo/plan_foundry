"""Tests for bundle_copy module (PLAN-AC5)."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SHARED))

import bundle_copy  # noqa: E402


def _make_bundle(root: pathlib.Path) -> pathlib.Path:
    """Build a minimal bundle .claude tree under root/.claude. Returns the .claude dir."""
    claude = root / ".claude"
    (claude / "skills" / "foo").mkdir(parents=True)
    (claude / "skills" / "foo" / "SKILL.md").write_text("foo skill body\n")
    (claude / "skills" / "foo" / "notes.md").write_text("foo notes\n")
    (claude / "skills" / "bar").mkdir(parents=True)
    (claude / "skills" / "bar" / "SKILL.md").write_text("bar skill body\n")
    (claude / "agents").mkdir(parents=True)
    (claude / "agents" / "an-agent.md").write_text("agent body\n")
    (claude / "commands").mkdir(parents=True)
    (claude / "commands" / "cmd.md").write_text("cmd body\n")
    (claude / "hooks").mkdir(parents=True)
    (claude / "hooks" / "hook.json").write_text("{}\n")
    return claude


def test_copy_into_empty_target(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert sorted(report.files_copied) == [
        "agents/an-agent.md",
        "commands/cmd.md",
        "hooks/hook.json",
        "skills/bar/SKILL.md",
        "skills/foo/SKILL.md",
        "skills/foo/notes.md",
    ]
    assert report.files_unchanged == []
    assert report.project_additions == []
    assert report.stale_in_target == []
    assert (target_claude / "skills" / "foo" / "SKILL.md").read_text() == "foo skill body\n"


def test_idempotent_second_run(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert report.files_copied == []
    assert len(report.files_unchanged) == 6


def test_project_addition_under_new_subskill_preserved(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    project_skill = target_claude / "skills" / "myproj" / "SKILL.md"
    project_skill.parent.mkdir(parents=True)
    project_skill.write_text("project-specific skill\n")
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert "skills/myproj/SKILL.md" in report.project_additions
    assert project_skill.exists()
    assert project_skill.read_text() == "project-specific skill\n"


def test_stale_in_target_reported_when_bundle_drops_file(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    (bundle_claude / "skills" / "foo" / "notes.md").unlink()
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert "skills/foo/notes.md" in report.stale_in_target
    assert (target_claude / "skills" / "foo" / "notes.md").exists()


def test_hand_edited_bundle_file_overwritten(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    target_file = target_claude / "skills" / "foo" / "SKILL.md"
    target_file.write_text("hand-edited content\n")
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert "skills/foo/SKILL.md" in report.files_copied
    assert target_file.read_text() == "foo skill body\n"


def test_missing_bundle_subdir_is_silently_skipped(tmp_path: pathlib.Path):
    bundle_claude = tmp_path / "bundle" / ".claude"
    (bundle_claude / "skills" / "only").mkdir(parents=True)
    (bundle_claude / "skills" / "only" / "S.md").write_text("only\n")
    target_claude = tmp_path / "target" / ".claude"
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert report.files_copied == ["skills/only/S.md"]


def _init_git_bundle(root: pathlib.Path) -> pathlib.Path:
    bundle_root = root / "bundle"
    bundle_root.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=bundle_root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=bundle_root, check=True)
    (bundle_root / "marker.txt").write_text("v1\n")
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "init"], cwd=bundle_root, check=True
    )
    return bundle_root


def test_write_and_read_version_file(tmp_path: pathlib.Path):
    bundle_root = _init_git_bundle(tmp_path)
    target_claude = tmp_path / "target" / ".claude"
    data = bundle_copy.write_version_file(bundle_root, target_claude)
    assert len(data["sha"]) == 40
    assert "synced" in data and data["synced"].endswith("Z")
    read = bundle_copy.read_version_file(target_claude)
    assert read is not None
    assert read["sha"] == data["sha"]
    assert read["synced"] == data["synced"]


def test_read_version_file_absent_returns_none(tmp_path: pathlib.Path):
    assert bundle_copy.read_version_file(tmp_path / "nothing") is None


def test_write_version_file_handles_non_git_bundle(tmp_path: pathlib.Path):
    bundle_root = tmp_path / "not-git"
    bundle_root.mkdir()
    target_claude = tmp_path / "target" / ".claude"
    data = bundle_copy.write_version_file(bundle_root, target_claude)
    assert data["sha"] == ""
    assert data["tag"] == ""
