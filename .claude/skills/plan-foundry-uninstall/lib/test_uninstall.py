"""Tests for plan-foundry-uninstall."""

from __future__ import annotations

import pathlib
import sys

import pytest

_LIB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_LIB))

import uninstall as uninstall_mod  # noqa: E402


def _fully_install(target: pathlib.Path):
    """Build a target dir that looks like a fully-installed plan_foundry project."""
    target.mkdir(parents=True, exist_ok=True)
    claude = target / ".claude"
    for sub in ("skills", "agents", "commands", "hooks"):
        (claude / sub).mkdir(parents=True)
        (claude / sub / "PLACEHOLDER.md").write_text("body\n", encoding="utf-8")
    (claude / ".plan-foundry-bundle-version").write_text(
        "sha=abc123\ntag=v0.5.0\nsynced=2026-05-19T00:00:00Z\n", encoding="utf-8"
    )
    (claude / "settings.local.json").write_text("{}\n", encoding="utf-8")
    (claude / "plan-foundry.config").write_text("ok\n", encoding="utf-8")

    (target / "Workbench").mkdir()
    (target / "Workbench" / "PLAN-AA1.md").write_text("operator plan\n", encoding="utf-8")
    (target / "Retired").mkdir()
    (target / "Retired" / "old.md").write_text("retired\n", encoding="utf-8")

    (target / ".gitignore").write_text(
        "node_modules/\n"
        "Retired/\n"
        "Workbench/.heartbeat/\n"
        ".plan-foundry-tmp/\n"
        ".claude/skills/\n"
        ".claude/agents/\n"
        ".claude/commands/\n"
        ".claude/hooks/\n"
        ".claude/.plan-foundry-bundle-version\n"
        "*.log\n",
        encoding="utf-8",
    )

    (target / "CLAUDE.md").write_text(
        "# CLAUDE.md\n\n"
        "Project intro.\n\n"
        "<!-- plan-foundry:init-plan-foundry:start -->\n"
        "Operating rule 1\n"
        "Operating rule 2\n"
        "<!-- plan-foundry:init-plan-foundry:end -->\n",
        encoding="utf-8",
    )


def test_uninstall_removes_bundle_artefacts(tmp_path):
    _fully_install(tmp_path)
    result = uninstall_mod.uninstall(tmp_path)
    assert result["outcome"] == "success"
    for sub in ("skills", "agents", "commands", "hooks"):
        assert not (tmp_path / ".claude" / sub).exists(), f".claude/{sub}/ not removed"
    assert not (tmp_path / ".claude" / ".plan-foundry-bundle-version").exists()


def test_uninstall_preserves_operator_data(tmp_path):
    _fully_install(tmp_path)
    uninstall_mod.uninstall(tmp_path)
    assert (tmp_path / "Workbench" / "PLAN-AA1.md").exists()
    assert (tmp_path / "Retired" / "old.md").exists()
    assert (tmp_path / ".claude" / "settings.local.json").exists()
    assert (tmp_path / ".claude" / "plan-foundry.config").exists()


def test_uninstall_reverses_gitignore_preserves_unrelated(tmp_path):
    _fully_install(tmp_path)
    uninstall_mod.uninstall(tmp_path)
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in text
    assert "*.log" in text
    assert ".claude/skills/" not in text
    assert "Retired/" not in text
    assert "Workbench/.heartbeat/" not in text


def test_uninstall_removes_sentinel_block_preserves_rest(tmp_path):
    _fully_install(tmp_path)
    uninstall_mod.uninstall(tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Project intro." in text
    assert "plan-foundry:init-plan-foundry:start" not in text
    assert "plan-foundry:init-plan-foundry:end" not in text
    assert "Operating rule 1" not in text


def test_uninstall_idempotent(tmp_path):
    _fully_install(tmp_path)
    uninstall_mod.uninstall(tmp_path)
    # Second run should succeed with nothing-to-do.
    result = uninstall_mod.uninstall(tmp_path)
    assert result["outcome"] == "success"


def test_uninstall_on_partial_install(tmp_path):
    """Only some of the bundle dirs present - uninstall handles gracefully."""
    claude = tmp_path / ".claude"
    (claude / "skills").mkdir(parents=True)
    (claude / "skills" / "x.md").write_text("x\n")
    # No agents/, no commands/, no hooks/, no version pin.
    result = uninstall_mod.uninstall(tmp_path)
    assert result["outcome"] == "success"
    assert not (claude / "skills").exists()


def test_uninstall_reports_kept_paths(tmp_path):
    _fully_install(tmp_path)
    result = uninstall_mod.uninstall(tmp_path)
    kept = result["payload"]["kept"]
    assert any("Workbench" in k for k in kept)
    assert any("Retired" in k for k in kept)
    assert any("settings.local.json" in k for k in kept)


def test_uninstall_handles_missing_claude_md(tmp_path):
    _fully_install(tmp_path)
    (tmp_path / "CLAUDE.md").unlink()
    result = uninstall_mod.uninstall(tmp_path)
    assert result["outcome"] == "success"


def test_uninstall_handles_malformed_sentinels(tmp_path):
    _fully_install(tmp_path)
    # Corrupt CLAUDE.md sentinels - end marker before start.
    (tmp_path / "CLAUDE.md").write_text(
        "<!-- plan-foundry:init-plan-foundry:end -->\n"
        "stuff\n"
        "<!-- plan-foundry:init-plan-foundry:start -->\n",
        encoding="utf-8",
    )
    result = uninstall_mod.uninstall(tmp_path)
    assert result["outcome"] == "success"
    # Malformed: file untouched.
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "stuff" in text


def test_uninstall_cleans_stale_tmp_clone(tmp_path):
    _fully_install(tmp_path)
    tmp_clone = tmp_path / ".plan-foundry-tmp"
    tmp_clone.mkdir()
    (tmp_clone / "junk.md").write_text("junk\n")
    uninstall_mod.uninstall(tmp_path)
    assert not tmp_clone.exists()


def test_uninstall_removes_receipt_and_quarantine(tmp_path):
    """A-6: uninstall leaves no receipt and no quarantine directory
    (PLAN-AH7 Step 13)."""
    _fully_install(tmp_path)
    claude = tmp_path / ".claude"
    (claude / ".plan-foundry-bundle-files").write_text(
        "sha=abc123\nwritten=2026-07-28T00:00:00Z\nskills/foo/SKILL.md\tdeadbeef\n",
        encoding="utf-8",
    )
    quarantine_dir = claude / ".plan-foundry-quarantine" / "20260101T000000Z"
    quarantine_dir.mkdir(parents=True)
    (quarantine_dir / "leftover.md").write_text("stale\n", encoding="utf-8")

    result = uninstall_mod.uninstall(tmp_path)

    assert result["outcome"] == "success"
    assert not (claude / ".plan-foundry-bundle-files").exists()
    assert not (claude / ".plan-foundry-quarantine").exists()
