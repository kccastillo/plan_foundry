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


def test_uninstall_leaves_writing_style_supplement_behind(tmp_path):
    """FOUNDRYREQ-horse-chestnut-brickhouse-20260805-1715: a project's
    .claude/writing-style-local.md is not one of the four bundle-managed
    dirs, so uninstall must leave it on disk and report it kept."""
    _fully_install(tmp_path)
    supplement = tmp_path / ".claude" / "writing-style-local.md"
    supplement.write_text(
        "## Additional banned words or phrases\n- utilise\n", encoding="utf-8"
    )

    result = uninstall_mod.uninstall(tmp_path)

    assert supplement.exists()
    assert supplement.read_text(encoding="utf-8") == (
        "## Additional banned words or phrases\n- utilise\n"
    )
    assert any("writing-style-local.md" in k for k in result["payload"]["kept"])


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
    (PLAN-AH7 Step 13). Extended for PLAN-AK5: also asserts the namespaced
    .bundle-receipts/ directory is removed - the prior version of this test
    wrote only the legacy receipt path and never touched .bundle-receipts/,
    so it would pass whether or not uninstall's directory-removal code for
    the new path worked at all."""
    _fully_install(tmp_path)
    claude = tmp_path / ".claude"
    (claude / ".plan-foundry-bundle-files").write_text(
        "sha=abc123\nwritten=2026-07-28T00:00:00Z\nskills/foo/SKILL.md\tdeadbeef\n",
        encoding="utf-8",
    )
    quarantine_dir = claude / ".plan-foundry-quarantine" / "20260101T000000Z"
    quarantine_dir.mkdir(parents=True)
    (quarantine_dir / "leftover.md").write_text("stale\n", encoding="utf-8")
    receipts_dir = claude / ".bundle-receipts"
    receipts_dir.mkdir(parents=True)
    (receipts_dir / "plan_foundry.files").write_text(
        "sha=abc123\nwritten=2026-07-28T00:00:00Z\nbundle=plan_foundry\n"
        "skills/foo/SKILL.md\tdeadbeef\n",
        encoding="utf-8",
    )

    result = uninstall_mod.uninstall(tmp_path)

    assert result["outcome"] == "success"
    assert not (claude / ".plan-foundry-bundle-files").exists()
    assert not (claude / ".plan-foundry-quarantine").exists()
    assert not receipts_dir.exists()


# ---------------------------------------------------------------------------
# Bundle identity: uninstall reverses whatever REQUIRED_GITIGNORE_ENTRIES it
# reads, and reads it from .claude/skills/_shared/ - which a sibling bundle
# installed at the same path may own. Raised from paper_trail_dev,
# 2026-08-04.
# ---------------------------------------------------------------------------


def test_identity_helper_reads_field(tmp_path: pathlib.Path):
    shared = tmp_path / "_shared"
    shared.mkdir()
    (shared / "bundle-contract.json").write_text(
        '{"bundle": "paper_trail"}', encoding="utf-8"
    )
    assert uninstall_mod._installed_bundle_identity(shared) == "paper_trail"


def test_identity_helper_none_when_absent(tmp_path: pathlib.Path):
    assert uninstall_mod._installed_bundle_identity(tmp_path / "nope") is None


def test_this_bundle_is_not_foreign_to_itself():
    """Running against its own installed tree, uninstall must take the
    ordinary path - otherwise the guard has disabled the normal case."""
    assert uninstall_mod._FOREIGN_SHARED is None


def test_uninstall_reports_exception_when_a_delete_fails(tmp_path, monkeypatch):
    """A delete that genuinely fails on disk must not be reported as removed
    (FOUNDRYREQ-horse-chestnut-brickhouse-20260805-1501). Forces
    _force_rmtree to report failure for .claude/skills/ without touching the
    filesystem, so the test does not depend on OS-specific lock behaviour."""
    _fully_install(tmp_path)

    real_force_rmtree = uninstall_mod._force_rmtree

    def fake_force_rmtree(path):
        if path.name == "skills":
            return False
        return real_force_rmtree(path)

    monkeypatch.setattr(uninstall_mod, "_force_rmtree", fake_force_rmtree)

    result = uninstall_mod.uninstall(tmp_path)

    assert result["outcome"] == "exception"
    assert ".claude/skills/" in result["payload"]["failed"]
    assert ".claude/skills/" not in result["payload"]["removed"]


def test_gitignore_reversal_skipped_when_shared_is_another_bundles(
    monkeypatch, tmp_path: pathlib.Path
):
    """Reversing another bundle's entry list strips its .gitignore lines and
    leaves plan_foundry's behind - the inversion of what uninstall is for."""
    monkeypatch.setattr(uninstall_mod, "_FOREIGN_SHARED", "paper_trail")
    target = tmp_path / "proj"
    target.mkdir()
    gi = target / ".gitignore"
    original = "Retired/\n.claude/.plan-foundry-tmp/\nnode_modules/\n"
    gi.write_text(original, encoding="utf-8")

    removed = uninstall_mod._reverse_gitignore(target)

    assert gi.read_text(encoding="utf-8") == original, "entries must be left alone"
    assert len(removed) == 1
    assert "SKIPPED" in removed[0] and "paper_trail" in removed[0]
