#!/usr/bin/env python3
"""
test_next_id.py — pytest suite for next_id.py

12 tests:
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
  11. Nested Retired/<month>/ PLAN file + rolled-over LOG both counted -> AA4.
  12. Nested Retired/<month>/ ADVICE files counted by the numeric allocator.

Usage: python -m pytest .claude/skills/write-plan/scripts/test_next_id.py
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
glob_filesystem_ids_by_source = _mod.glob_filesystem_ids_by_source
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
        used = compute_used_ids(repo)
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

        used = compute_used_ids(repo)
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

        used = compute_used_ids(repo)
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

        used = compute_used_ids(repo)
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

        used = compute_used_ids(repo)
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

        used = compute_used_ids(repo)
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

        used = compute_used_ids(repo)
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


# ---------------------------------------------------------------------------
# Test 11 — Nested Retired/<month>/: nested PLAN file + rolled-over LOG counted
# ---------------------------------------------------------------------------

def test_11_nested_retired_dir(capsys):
    """
    Retired/ nests rolled-over artefacts in per-month subdirectories. A PLAN
    file at Retired/<month>/PLAN-AA3_x.md and a rolled-over LOG at
    Retired/<month>/..._LOG_....md must both be discovered — a non-recursive
    scan silently under-counts and the allocator then returns a used ID.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        # Current-month LOG in Workbench/ references AA0 only.
        (wb / "202605010000_LOG_202605.md").write_text(
            _make_log([_plan_row("AA0", "Current Plan", "done")])
        )

        # Rolled-over LOG nested under Retired/<month>/ references AA1 and AA2.
        month_dir = rt / "202604"
        month_dir.mkdir()
        (month_dir / "202604010000_LOG_202604.md").write_text(
            _make_log([
                _plan_row("AA1", "April Plan 1", "retired"),
                _plan_row("AA2", "April Plan 2", "retired"),
            ])
        )

        # Retired PLAN file nested under Retired/<month>/ (AA3), no LOG row.
        (month_dir / "PLAN-AA3_april-orphan.md").write_text("---\ntype: plan\n---\n")

        used = compute_used_ids(repo)
        captured = capsys.readouterr()

        assert "AA0" in used, "current-month LOG id missed"
        assert "AA1" in used and "AA2" in used, (
            f"nested rolled-over LOG ids missed; got {used}"
        )
        assert "AA3" in used, "nested retired PLAN file missed"
        assert "PLAN-AA3" in captured.err, (
            f"orphan warning for nested PLAN-AA3 missing; got: {captured.err!r}"
        )
        result = next_aa_id(used)
        assert result == "AA4", f"Expected AA4, got {result!r}"


# ---------------------------------------------------------------------------
# Test 12 — Nested Retired/<month>/ ADVICE files counted by numeric allocator
# ---------------------------------------------------------------------------

def test_12_nested_retired_numeric():
    """
    next_numeric_id must scan Retired/ recursively too — a nested retired
    ADVICE file otherwise leaves max(NNN) too low and yields an already-used ID.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        # ADVICE-001..003 nested under Retired/<month>/.
        month_dir = rt / "202604"
        month_dir.mkdir()
        for n in (1, 2, 3):
            (month_dir / f"ADVICE-{n:03d}_archived.md").write_text(
                "---\ntype: advice\n---\n"
            )
        # ADVICE-004 current, flat in Workbench/.
        (wb / "ADVICE-004_current.md").write_text("---\ntype: advice\n---\n")

        result = next_numeric_id("ADVICE", repo)
        assert result == "005", f"Expected '005' (nested + flat, max+1), got {result!r}"


# ---------------------------------------------------------------------------
# Test 13 — Post-AB9 D2: Retired/ scan is authoritative; no LOG required
# ---------------------------------------------------------------------------

def test_13_retired_first_scan_no_log():
    """
    Post-PLAN-AB9 D2 (2026-05-23): Workbench/ + Retired/ are authoritative
    for "used IDs". A clone with PLAN files on disk but no monthly LOG at
    all must still correctly account for those IDs and allocate the next.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        # Three PLANs on disk, no LOG file anywhere.
        (wb / "PLAN-AA0_active.md").write_text("---\ntype: plan\n---\n")
        month_dir = rt / "202604"
        month_dir.mkdir()
        (month_dir / "PLAN-AA1_april.md").write_text("---\ntype: plan\n---\n")
        (month_dir / "PLAN-AA2_april.md").write_text("---\ntype: plan\n---\n")

        used = compute_used_ids(repo)
        assert "AA0" in used and "AA1" in used and "AA2" in used, (
            f"FS-primary scan missed IDs: got {used}"
        )
        result = next_aa_id(used)
        assert result == "AA3", f"Expected AA3, got {result!r}"


# ---------------------------------------------------------------------------
# Test 14 — LOG-scan as non-authoritative defence-in-depth fallback
# ---------------------------------------------------------------------------

def test_14_log_only_fallback_emits_warning(capsys):
    """
    LOG references PLAN-AA5 but neither Workbench/ nor Retired/ has the file
    (simulating a pre-D2-A archive state where Retired/ was gitignored and
    the PLAN body never made it into the clone). The allocator MUST still
    treat AA5 as used (defence-in-depth) AND emit a stderr warning naming
    AA5 as a LOG-only ID.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        # No PLAN files on disk. LOG references AA5.
        log_content = _make_log([_plan_row("AA5", "Lost Plan", "done")])
        (wb / "202605010000_LOG_202605.md").write_text(log_content)

        used = compute_used_ids(repo)
        captured = capsys.readouterr()

        assert "AA5" in used, (
            "LOG-only ID must still be counted as used (defence-in-depth)"
        )
        assert "PLAN-AA5" in captured.err or "AA5" in captured.err, (
            f"Expected LOG-only warning naming AA5; got: {captured.err!r}"
        )
        assert "LOG-only" in captured.err or "fallback" in captured.err.lower(), (
            f"Expected fallback/LOG-only label in warning; got: {captured.err!r}"
        )
        # AA0 is the lowest unused (AA5 is the only "used" entry).
        result = next_aa_id(used)
        assert result == "AA0", f"Expected AA0 (lowest unused), got {result!r}"


# ---------------------------------------------------------------------------
# Test 15 — glob_filesystem_ids_by_source partitions correctly
# ---------------------------------------------------------------------------

def test_15_by_source_partition():
    """
    glob_filesystem_ids_by_source returns disjoint sets keyed by directory.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        (wb / "PLAN-AA0_active.md").write_text("---\ntype: plan\n---\n")
        (wb / "PLAN-AA1_active.md").write_text("---\ntype: plan\n---\n")
        month_dir = rt / "202604"
        month_dir.mkdir()
        (month_dir / "PLAN-AB0_retired.md").write_text("---\ntype: plan\n---\n")
        (month_dir / "PLAN-AB1_retired.md").write_text("---\ntype: plan\n---\n")

        wb_ids, rt_ids = glob_filesystem_ids_by_source(repo)
        assert wb_ids == {"AA0", "AA1"}, f"Workbench mismatch: {wb_ids}"
        assert rt_ids == {"AB0", "AB1"}, f"Retired mismatch: {rt_ids}"


# ---------------------------------------------------------------------------
# Test 16 — --explain flag emits per-ID source labels to stderr
# ---------------------------------------------------------------------------

def test_16_explain_flag_stderr_format():
    """
    Invoking the script with `--explain` emits one stderr line per used ID
    in the format `<ID>\\t<source>`, lex-sorted, with a trailing blank line,
    while stdout still prints the next-ID unchanged.

    Runs the script as a subprocess against a synthetic repo to exercise
    the argparse wiring and stdout/stderr separation.
    """
    import subprocess
    import os

    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        # One Workbench PLAN, one Retired PLAN, one LOG-only ID.
        (wb / "PLAN-AA0_active.md").write_text("---\ntype: plan\n---\n")
        month_dir = rt / "202604"
        month_dir.mkdir()
        (month_dir / "PLAN-AA1_retired.md").write_text("---\ntype: plan\n---\n")
        log_content = _make_log([
            _plan_row("AA0", "Active", "in-progress"),
            _plan_row("AA1", "Retired", "done"),
            _plan_row("AA2", "Lost", "done"),
        ])
        (wb / "202605010000_LOG_202605.md").write_text(log_content)

        # Copy next_id.py into the synthetic repo so find_repo_root (which
        # walks up from __file__'s parent) lands on the tmp repo's Workbench/.
        import shutil
        script = repo / "next_id.py"
        shutil.copy(SCRIPT_DIR / "next_id.py", script)
        result = subprocess.run(
            [sys.executable, str(script), "PLAN", "--explain"],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )

        assert result.returncode == 0, (
            f"Non-zero exit: rc={result.returncode}, stderr={result.stderr!r}"
        )
        # stdout should be just the next ID (AA3, since AA0-AA2 all used).
        stdout_line = result.stdout.strip()
        assert stdout_line == "AA3", (
            f"Expected stdout 'AA3', got {stdout_line!r}"
        )

        # stderr should contain three explain lines (plus any warnings).
        # Filter for the `<ID>\t<source>` lines.
        explain_lines = [
            line for line in result.stderr.splitlines()
            if "\t" in line and any(
                line.endswith(s) for s in ("\tWorkbench", "\tRetired", "\tLOG-only")
            )
        ]
        assert len(explain_lines) == 3, (
            f"Expected 3 explain lines; got {len(explain_lines)}: {explain_lines!r}\n"
            f"full stderr: {result.stderr!r}"
        )
        # Lex-sorted by ID
        ids_in_order = [line.split("\t", 1)[0] for line in explain_lines]
        assert ids_in_order == sorted(ids_in_order), (
            f"Explain lines not lex-sorted: {ids_in_order!r}"
        )
        # Source assignments
        labelled = dict(line.split("\t", 1) for line in explain_lines)
        assert labelled.get("AA0") == "Workbench", labelled
        assert labelled.get("AA1") == "Retired", labelled
        assert labelled.get("AA2") == "LOG-only", labelled


# ---------------------------------------------------------------------------
# Test 17 — --explain absent: stderr has no <ID>\t<source> lines
# ---------------------------------------------------------------------------

def test_17_no_explain_no_per_id_lines():
    """
    Without `--explain`, stderr contains warnings (if any) but no
    `<ID>\\t<source>` per-ID lines. Stdout unchanged.
    """
    import subprocess

    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)
        (wb / "PLAN-AA0_active.md").write_text("---\ntype: plan\n---\n")
        # No LOG → AA0 is FS-orphan → stderr warning, but no explain lines.

        import shutil
        script = repo / "next_id.py"
        shutil.copy(SCRIPT_DIR / "next_id.py", script)
        result = subprocess.run(
            [sys.executable, str(script), "PLAN"],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )

        assert result.returncode == 0, (
            f"Non-zero exit: rc={result.returncode}, stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "AA1", (
            f"Expected stdout 'AA1', got {result.stdout!r}"
        )
        # No tab-delimited per-ID lines.
        explain_lines = [
            line for line in result.stderr.splitlines()
            if "\t" in line and any(
                line.endswith(s) for s in ("\tWorkbench", "\tRetired", "\tLOG-only")
            )
        ]
        assert explain_lines == [], (
            f"Did not expect explain lines without --explain; got: {explain_lines!r}"
        )
