"""Tests for claude_md_block.block_change_report (PLAN-AK5)."""

from __future__ import annotations

import pathlib
import sys

_SHARED = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SHARED))

import claude_md_block  # noqa: E402


def _write_current_block(target_root: pathlib.Path, body: str) -> None:
    (target_root / "CLAUDE.md").write_text(
        f"# CLAUDE.md\n\n{claude_md_block.SENTINEL_START}\n"
        "<!-- WARNING: content between these markers is managed by the plan_foundry "
        "init-plan-foundry skill. Re-running the skill replaces everything between "
        "the markers with the current operating-rules.md from the bundle. Do not "
        "hand-edit between markers - edits will be lost on re-run. -->\n\n"
        f"{body}\n"
        f"{claude_md_block.SENTINEL_END}\n",
        encoding="utf-8",
    )


def test_purely_additive_change_returns_additive_with_empty_removed(
    tmp_path: pathlib.Path,
):
    _write_current_block(tmp_path, "Rule one.\nRule two.")
    report = claude_md_block.block_change_report(tmp_path, "Rule one.\nRule two.\nRule three.")
    assert report["status"] == "additive"
    assert report["removed_lines"] == []
    assert "Rule three." in report["added_lines"]


def test_replacing_a_line_returns_non_additive_with_old_and_new(tmp_path: pathlib.Path):
    _write_current_block(tmp_path, "Rule one.\nRule two.")
    report = claude_md_block.block_change_report(tmp_path, "Rule one.\nRule two changed.")
    assert report["status"] == "non-additive"
    assert "Rule two." in report["removed_lines"]
    assert "Rule two changed." in report["added_lines"]


def test_reordering_existing_lines_is_still_additive(tmp_path: pathlib.Path):
    _write_current_block(tmp_path, "Rule one.\nRule two.")
    report = claude_md_block.block_change_report(tmp_path, "Rule two.\nRule one.")
    assert report["status"] == "additive"
    assert report["removed_lines"] == []


def test_absent_claude_md_is_unavailable(tmp_path: pathlib.Path):
    report = claude_md_block.block_change_report(tmp_path, "Rule one.")
    assert report["status"] == "unavailable"
    assert report["removed_lines"] == []
    assert report["added_lines"] == []


def test_claude_md_with_no_markers_is_unavailable(tmp_path: pathlib.Path):
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE.md\n\nNo markers here.\n", encoding="utf-8")
    report = claude_md_block.block_change_report(tmp_path, "Rule one.")
    assert report["status"] == "unavailable"


def test_claude_md_with_duplicate_markers_is_unavailable(tmp_path: pathlib.Path):
    start = claude_md_block.SENTINEL_START
    end = claude_md_block.SENTINEL_END
    (tmp_path / "CLAUDE.md").write_text(
        f"{start}\nfirst\n{end}\n\n{start}\nsecond\n{end}\n", encoding="utf-8"
    )
    report = claude_md_block.block_change_report(tmp_path, "Rule one.")
    assert report["status"] == "unavailable"


def test_call_leaves_claude_md_byte_for_byte_unchanged(tmp_path: pathlib.Path):
    _write_current_block(tmp_path, "Rule one.\nRule two.")
    before = (tmp_path / "CLAUDE.md").read_bytes()
    claude_md_block.block_change_report(tmp_path, "Rule one.\nRule two changed.")
    after = (tmp_path / "CLAUDE.md").read_bytes()
    assert before == after
