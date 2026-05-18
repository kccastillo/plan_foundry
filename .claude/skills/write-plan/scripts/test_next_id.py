#!/usr/bin/env python3
"""
test_next_id.py — pytest suite for next_id.py

10 tests:
  1. Empty repo (no LOG, no PLAN files) returns AA0.
  2. Single AA-form PLAN in Workbench + LOG row for AA0 returns AA1.
  3. Mixed historical numeric + AA-form in LOG returns AA4.
  4. Lowest-unused returned, not max-plus-one (AA0, AA1, AA3 used -> returns AA2).
  5. FS/LOG disagreement: orphan AA1 on disk emits stderr warning and is counted.
  6. Malformed LOG row: warning emitted; parsing continues; returns correct next-AA.
  7. ADVICE/RESEARCH still numeric (ADVICE-003 on disk -> 004).
  8. Historic numeric IDs in LOG do not perturb AA allocation (AA0 is still fresh).
  9. Boundary case AZ9 -> BA0.
  10. Exhaustion: all 6,760 AA-form IDs used -> exits 1 with exhaustion message.

Usage: python -m pytest plugins/plan-foundry-core/skills/write-plan/scripts/test_next_id.py
Exit 0 on success.
"""

import importlib.util
import io
import pathlib
import sys
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: load next_id module relative to this script
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("next_id", SCRIPT_DIR / "next_id.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

find_repo_root = _mod.find_repo_root
parse_log_ids = _mod.parse_log_ids
glob_filesystem_ids = _mod.glob_filesystem_ids
compute_used_ids = _mod.compute_used_ids
next_aa_id = _mod.next_aa_id
aa_id_to_index = _mod.aa_id_to_index
index_to_aa_id = _mod.index_to_aa_id
next_numeric_id = _mod.next_numeric_id
_AA_TOTAL = _mod._AA_TOTAL
_LOG_HEADER = _mod._LOG_HEADER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log(status_rows: list[str]) -> str:
    """Build a minimal LOG file with a Status Table."""
    rows = "\n".join(status_rows)
    return (
        "---\ntitle: Test LOG\ntype: bus-log\nstatus: open\n---\n\n"
        "## Status Table\n\n"
        f"{_LOG_HEADER}\n"
        "|---|---|---|---|---|---|\n"
        f"{rows}\n"
        "\n"
        "## Recurring Task Tracker\n\n"
    )


def _plan_row(plan_id: str, title: str = "Test Plan", status: str = "done") -> str:
    return f"| PLAN-{plan_id}_{title.lower().replace(' ', '-')}.md | {title} | sonnet | medium | {status} | — |"


def _setup_repo(tmp: str) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """Create Workbench/ and Retired/ directories under tmp. Return (repo_root, workbench, retired)."""
    repo = pathlib.Path(tmp)
    wb = repo / "Workbench"
    rt = repo / "Retired"
    wb.mkdir()
    rt.mkdir()
    return repo, wb, rt


# ---------------------------------------------------------------------------
# Test 1 — Empty repo: no LOG, no PLAN files -> returns AA0
# ---------------------------------------------------------------------------

def test_1_empty_repo():
    """Empty repo (no LOG, no PLAN files) returns AA0."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)
        used = compute_used_ids(wb, repo)
        assert used == set(), f"Expected empty used set, got {used}"
        result = next_aa_id(used)
        assert result == "AA0", f"Expected AA0, got {result!r}"


# ---------------------------------------------------------------------------
# Test 2 — Single AA-form PLAN: Workbench + LOG both have AA0 -> returns AA1
# ---------------------------------------------------------------------------

def test_2_single_aa_plan(capsys):
    """Workbench has PLAN-AA0_x.md; LOG row references AA0 -> returns AA1."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        # Create file on disk
        (wb / "PLAN-AA0_test.md").write_text("---\ntype: plan\n---\n")

        # Create LOG with AA0 row
        log_content = _make_log([_plan_row("AA0", "Test Plan", "done")])
        (wb / "202605010000_LOG_202605.md").write_text(log_content)

        used = compute_used_ids(wb, repo)
        assert "AA0" in used, f"Expected AA0 in used, got {used}"
        result = next_aa_id(used)
        assert result == "AA1", f"Expected AA1, got {result!r}"


# ---------------------------------------------------------------------------
# Test 3 — Mixed historical + AA-form: LOG has PLAN-001..037 + AA0..AA3 -> AA4
# ---------------------------------------------------------------------------

def test_3_mixed_historical_and_aa():
    """LOG references PLAN-001..037 numerically AND PLAN-AA0..AA3 -> returns AA4."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        numeric_rows = [_plan_row(str(i).zfill(3), f"Plan {i}", "done") for i in range(1, 38)]
        aa_rows = [_plan_row(f"AA{i}", f"AA Plan {i}", "done") for i in range(4)]
        log_content = _make_log(numeric_rows + aa_rows)
        (wb / "202605010000_LOG_202605.md").write_text(log_content)

        used = compute_used_ids(wb, repo)
        # Numerics present but should not block AA allocation
        for i in range(1, 38):
            assert str(i).zfill(3) in used
        # AA0-AA3 present
        for i in range(4):
            assert f"AA{i}" in used
        result = next_aa_id(used)
        assert result == "AA4", f"Expected AA4, got {result!r}"


# ---------------------------------------------------------------------------
# Test 4 — Lowest-unused, not max-plus-one: AA0, AA1, AA3 used -> returns AA2
# ---------------------------------------------------------------------------

def test_4_lowest_unused_not_max_plus_one():
    """LOG references AA0, AA1, AA3 (gap at AA2) -> returns AA2."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        rows = [
            _plan_row("AA0", "Plan AA0", "done"),
            _plan_row("AA1", "Plan AA1", "done"),
            _plan_row("AA3", "Plan AA3", "done"),
        ]
        log_content = _make_log(rows)
        (wb / "202605010000_LOG_202605.md").write_text(log_content)

        used = compute_used_ids(wb, repo)
        assert "AA0" in used
        assert "AA1" in used
        assert "AA2" not in used, "AA2 should not be in used set (gap)"
        assert "AA3" in used
        result = next_aa_id(used)
        assert result == "AA2", f"Expected AA2 (lowest gap), got {result!r}"


# ---------------------------------------------------------------------------
# Test 5 — FS/LOG disagreement: FS has AA1 extra, LOG only has AA0
# ---------------------------------------------------------------------------

def test_5_fs_log_disagreement(capsys):
    """
    Workbench has PLAN-AA0_x.md and PLAN-AA1_y.md; LOG Status Table mentions only AA0.
    Returns AA2 AND emits stderr containing 'PLAN-AA1'.
    Confirms M2 warn-and-union: orphan AA1 is surfaced to stderr but counted as used.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        (wb / "PLAN-AA0_x.md").write_text("---\ntype: plan\n---\n")
        (wb / "PLAN-AA1_y.md").write_text("---\ntype: plan\n---\n")

        log_content = _make_log([_plan_row("AA0", "Plan AA0", "done")])
        (wb / "202605010000_LOG_202605.md").write_text(log_content)

        used = compute_used_ids(wb, repo)
        captured = capsys.readouterr()

        assert "AA0" in used
        assert "AA1" in used, "AA1 (orphan) must be in union"
        assert "PLAN-AA1" in captured.err, (
            f"Expected stderr to mention PLAN-AA1; got: {captured.err!r}"
        )
        result = next_aa_id(used)
        assert result == "AA2", f"Expected AA2, got {result!r}"


# ---------------------------------------------------------------------------
# Test 6 — Malformed LOG row: warning emitted; parsing continues
# ---------------------------------------------------------------------------

def test_6_malformed_log_row(capsys):
    """LOG has a Status Table row with truncated content; warning emitted; continues parsing."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        # A good row, a malformed row, then another good row
        malformed_row = "| truncated"
        good_rows = [
            _plan_row("AA0", "Good Plan 0", "done"),
            malformed_row,
            _plan_row("AA2", "Good Plan 2", "done"),
        ]
        log_content = _make_log(good_rows)
        (wb / "202605010000_LOG_202605.md").write_text(log_content)

        used = compute_used_ids(wb, repo)
        captured = capsys.readouterr()

        # Both good rows should be parsed
        assert "AA0" in used, f"AA0 should be in used; got {used}"
        assert "AA2" in used, f"AA2 should be in used; got {used}"
        # Should have a warning about the malformed row
        assert "warning" in captured.err.lower() or "malformed" in captured.err.lower(), (
            f"Expected malformed-row warning in stderr; got: {captured.err!r}"
        )
        # Lowest unused is AA1
        result = next_aa_id(used)
        assert result == "AA1", f"Expected AA1, got {result!r}"


# ---------------------------------------------------------------------------
# Test 7 — ADVICE/RESEARCH still numeric
# ---------------------------------------------------------------------------

def test_7_advice_research_still_numeric():
    """ADVICE-003_x.md on disk -> next_numeric_id('ADVICE', ...) returns '004'."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        (wb / "ADVICE-003_strategy.md").write_text("---\ntype: advice\n---\n")

        result = next_numeric_id("ADVICE", repo)
        assert result == "004", f"Expected '004', got {result!r}"

        # RESEARCH too
        (wb / "RESEARCH-001_data.md").write_text("---\ntype: research\n---\n")
        (wb / "RESEARCH-007_more.md").write_text("---\ntype: research\n---\n")
        result_r = next_numeric_id("RESEARCH", repo)
        assert result_r == "008", f"Expected '008', got {result_r!r}"


# ---------------------------------------------------------------------------
# Test 8 — Historical numeric IDs in LOG do not perturb AA allocation
# ---------------------------------------------------------------------------

def test_8_numeric_ids_dont_block_aa():
    """
    LOG references PLAN-029 numerically; the AA allocator must NOT see this as
    blocking PLAN-AA0. Numeric and AA-form IDs are disjoint slot-spaces.
    used = {"029"} -> next AA is still AA0.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        log_content = _make_log([_plan_row("029", "Old Plan", "done")])
        (wb / "202605010000_LOG_202605.md").write_text(log_content)

        used = compute_used_ids(wb, repo)
        assert "029" in used, "Numeric 029 should be in used set"
        assert "AA0" not in used, "AA0 should NOT be in used set (disjoint namespace)"

        result = next_aa_id(used)
        assert result == "AA0", f"Expected AA0 (unperturbed by numeric IDs), got {result!r}"


# ---------------------------------------------------------------------------
# Test 9 — Boundary case AZ9 -> BA0
# ---------------------------------------------------------------------------

def test_9_boundary_az9_to_ba0():
    """Synthetic LOG references all AA0..AZ9 (260 IDs) -> returns BA0."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        # All 260 IDs in the AA-block (letter1=A, letter2=A..Z, digit=0..9)
        all_a_block: set[str] = set()
        for l2 in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            for d in range(10):
                all_a_block.add(f"A{l2}{d}")

        # Verify boundary helpers
        assert aa_id_to_index("AZ9") == 259
        assert aa_id_to_index("BA0") == 260
        assert index_to_aa_id(259) == "AZ9"
        assert index_to_aa_id(260) == "BA0"

        result = next_aa_id(all_a_block)
        assert result == "BA0", f"Expected BA0, got {result!r}"


# ---------------------------------------------------------------------------
# Test 10 — Exhaustion: all 6,760 AA IDs used -> RuntimeError -> exits 1
# ---------------------------------------------------------------------------

def test_10_exhaustion():
    """All AA0..ZZ9 used -> next_aa_id raises RuntimeError with exhaustion message."""
    all_ids = {index_to_aa_id(i) for i in range(_AA_TOTAL)}
    assert len(all_ids) == _AA_TOTAL, f"Expected {_AA_TOTAL} IDs, got {len(all_ids)}"

    with pytest.raises(RuntimeError, match="exhausted"):
        next_aa_id(all_ids)
