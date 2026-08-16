"""Unit tests for claude_md_block.py (shared sentinel-block helper).

Covers build_block, apply_operating_rules_block - all branches including
wrapping fidelity, create, append, skip, replace, and malformed-marker FAIL cases.

All fixtures use synthetic, distinctive operating-rules text (D4) so tests
remain independent of the live operating-rules.md content.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

# Make the _shared directory importable regardless of cwd.
_SHARED = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_SHARED))

import claude_md_block  # noqa: E402

SENTINEL_START = claude_md_block.SENTINEL_START
SENTINEL_END = claude_md_block.SENTINEL_END

# Distinctive synthetic operating-rules text (D4).
RULES_V1 = "# Synthetic operating rules v1\n\nRule A: do the thing.\nRule B: do it again.\n"
RULES_V2 = "# Synthetic operating rules v2\n\nRule A: do the thing differently.\nRule C: new rule.\n"


# ---------------------------------------------------------------------------
# build_block tests
# ---------------------------------------------------------------------------


def test_build_block_contains_sentinel_start():
    block = claude_md_block.build_block(RULES_V1)
    assert SENTINEL_START in block


def test_build_block_contains_sentinel_end():
    block = claude_md_block.build_block(RULES_V1)
    assert SENTINEL_END in block


def test_build_block_contains_warning_comment():
    block = claude_md_block.build_block(RULES_V1)
    assert "WARNING: content between these markers is managed by the plan_foundry" in block


def test_build_block_contains_operating_rules_text():
    block = claude_md_block.build_block(RULES_V1)
    assert "Synthetic operating rules v1" in block
    assert "Rule A: do the thing." in block


def test_build_block_order_start_before_warning_before_rules_before_end():
    block = claude_md_block.build_block(RULES_V1)
    i_start = block.index(SENTINEL_START)
    i_warning = block.index("<!-- WARNING")
    i_rules = block.index("Synthetic operating rules v1")
    i_end = block.index(SENTINEL_END)
    assert i_start < i_warning < i_rules < i_end, (
        "Expected order: SENTINEL_START < WARNING < rules < SENTINEL_END"
    )


def test_build_block_ends_with_newline():
    block = claude_md_block.build_block(RULES_V1)
    assert block.endswith("\n")


# ---------------------------------------------------------------------------
# apply_operating_rules_block - absent file (create)
# ---------------------------------------------------------------------------


def test_apply_absent_file_returns_pass_created(tmp_path):
    status, note = claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    assert status == "PASS"
    assert note == "created"


def test_apply_absent_file_creates_claude_md(tmp_path):
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    assert (tmp_path / "CLAUDE.md").exists()


def test_apply_absent_file_stub_contains_header(tmp_path):
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# CLAUDE.md" in text


def test_apply_absent_file_stub_contains_sentinel_start(tmp_path):
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert SENTINEL_START in text


def test_apply_absent_file_stub_contains_operating_rules(tmp_path):
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Synthetic operating rules v1" in text


# ---------------------------------------------------------------------------
# apply_operating_rules_block - file exists without markers (append)
# ---------------------------------------------------------------------------


def test_apply_no_markers_returns_pass_appended(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "# My project\n\nHand-authored content.\n", encoding="utf-8"
    )
    status, note = claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    assert status == "PASS"
    assert note == "appended-block"


def test_apply_no_markers_preserves_original_host_content(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "# My project\n\nHand-authored content.\n", encoding="utf-8"
    )
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# My project" in text
    assert "Hand-authored content." in text


def test_apply_no_markers_block_present_after_append(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "# My project\n\nHand-authored content.\n", encoding="utf-8"
    )
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert SENTINEL_START in text
    assert "Synthetic operating rules v1" in text


# ---------------------------------------------------------------------------
# apply_operating_rules_block - existing current block (skip)
# ---------------------------------------------------------------------------


def test_apply_current_block_returns_skipped(tmp_path):
    block = claude_md_block.build_block(RULES_V1)
    (tmp_path / "CLAUDE.md").write_text(
        f"# My project\n\nSome notes.\n\n{block}", encoding="utf-8"
    )
    status, note = claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    assert status == "SKIPPED"
    assert note == "already current"


def test_apply_current_block_file_unchanged(tmp_path):
    block = claude_md_block.build_block(RULES_V1)
    original = f"# My project\n\nSome notes.\n\n{block}"
    (tmp_path / "CLAUDE.md").write_text(original, encoding="utf-8")
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert text == original


# ---------------------------------------------------------------------------
# apply_operating_rules_block - stale block (replace)
# ---------------------------------------------------------------------------


def test_apply_stale_block_returns_pass_replaced(tmp_path):
    stale_block = claude_md_block.build_block(RULES_V1)
    (tmp_path / "CLAUDE.md").write_text(
        f"# My project\n\nNotes above.\n\n{stale_block}\nNotes below.\n",
        encoding="utf-8",
    )
    status, note = claude_md_block.apply_operating_rules_block(tmp_path, RULES_V2)
    assert status == "PASS"
    assert note == "replaced-block"


def test_apply_stale_block_host_content_preserved(tmp_path):
    stale_block = claude_md_block.build_block(RULES_V1)
    (tmp_path / "CLAUDE.md").write_text(
        f"# My project\n\nNotes above.\n\n{stale_block}\nNotes below.\n",
        encoding="utf-8",
    )
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V2)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# My project" in text
    assert "Notes above." in text
    assert "Notes below." in text


def test_apply_stale_block_new_rules_present(tmp_path):
    stale_block = claude_md_block.build_block(RULES_V1)
    (tmp_path / "CLAUDE.md").write_text(
        f"# My project\n\nNotes above.\n\n{stale_block}\nNotes below.\n",
        encoding="utf-8",
    )
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V2)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Synthetic operating rules v2" in text
    assert "Rule C: new rule." in text


def test_apply_stale_block_old_rules_gone(tmp_path):
    stale_block = claude_md_block.build_block(RULES_V1)
    (tmp_path / "CLAUDE.md").write_text(
        f"# My project\n\nNotes above.\n\n{stale_block}\nNotes below.\n",
        encoding="utf-8",
    )
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V2)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Synthetic operating rules v1" not in text
    assert "Rule A: do the thing.\n" not in text


# ---------------------------------------------------------------------------
# apply_operating_rules_block - malformed: end before start (FAIL, non-destructive)
# ---------------------------------------------------------------------------


def test_apply_end_before_start_returns_fail(tmp_path):
    bad_content = (
        "# My project\n\n"
        f"{SENTINEL_END}\nsome text\n{SENTINEL_START}\n"
    )
    (tmp_path / "CLAUDE.md").write_text(bad_content, encoding="utf-8")
    status, note = claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    assert status == "FAIL"
    assert "end before start" in note


def test_apply_end_before_start_file_unchanged(tmp_path):
    bad_content = (
        "# My project\n\n"
        f"{SENTINEL_END}\nsome text\n{SENTINEL_START}\n"
    )
    (tmp_path / "CLAUDE.md").write_text(bad_content, encoding="utf-8")
    original_bytes = (tmp_path / "CLAUDE.md").read_bytes()
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    assert (tmp_path / "CLAUDE.md").read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# apply_operating_rules_block - malformed: duplicate start markers (FAIL, non-destructive)
# ---------------------------------------------------------------------------


def test_apply_duplicate_start_returns_fail(tmp_path):
    bad_content = (
        "# My project\n\n"
        f"{SENTINEL_START}\nsome text\n{SENTINEL_START}\nmore text\n{SENTINEL_END}\n"
    )
    (tmp_path / "CLAUDE.md").write_text(bad_content, encoding="utf-8")
    status, note = claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    assert status == "FAIL"
    assert "start_count=2" in note


def test_apply_duplicate_start_file_unchanged(tmp_path):
    bad_content = (
        "# My project\n\n"
        f"{SENTINEL_START}\nsome text\n{SENTINEL_START}\nmore text\n{SENTINEL_END}\n"
    )
    (tmp_path / "CLAUDE.md").write_text(bad_content, encoding="utf-8")
    original_bytes = (tmp_path / "CLAUDE.md").read_bytes()
    claude_md_block.apply_operating_rules_block(tmp_path, RULES_V1)
    assert (tmp_path / "CLAUDE.md").read_bytes() == original_bytes
