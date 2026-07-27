#!/usr/bin/env python3
"""
test_next_id.py - pytest suite for next_id.py

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
glob_filesystem_ids = _mod.glob_filesystem_ids
glob_filesystem_ids_by_source = _mod.glob_filesystem_ids_by_source
compute_used_ids = _mod.compute_used_ids
next_aa_id = _mod.next_aa_id
aa_id_to_index = _mod.aa_id_to_index
index_to_aa_id = _mod.index_to_aa_id
next_numeric_id = _mod.next_numeric_id
_AA_TOTAL = _mod._AA_TOTAL

# The Status Table header that next_id.py used to anchor on before PLAN-AD2
# W0.2 removed the LOG scan. Kept here (not imported) so the tests can still
# build realistic LOG files and assert that their contents are now ignored.
_LOG_HEADER = "| Plan File | Title | Assigned | Priority | Status | Due |"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLAN_STUB = "---\ntype: plan\n---\n"


def _make_log(status_rows: list[str]) -> str:
    """
    Build a minimal LOG file with a Status Table.

    Post-PLAN-AD2 W0.2 the allocator never reads these. They are still
    written in several tests precisely to assert that they are ignored.
    """
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
    return f"| PLAN-{plan_id}_{title.lower().replace(' ', '-')}.md | {title} | sonnet | medium | {status} | - |"


def _setup_repo(tmp: str) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """Create Workbench/ and Retired/ directories under tmp. Return (repo_root, workbench, retired)."""
    repo = pathlib.Path(tmp)
    wb = repo / "Workbench"
    rt = repo / "Retired"
    wb.mkdir()
    rt.mkdir()
    return repo, wb, rt


# ---------------------------------------------------------------------------
# Test 1 - Empty repo: no LOG, no PLAN files -> returns AA0
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
# Test 2 - Single AA-form PLAN: Workbench + LOG both have AA0 -> returns AA1
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
# Test 3 - Mixed historical + AA-form: LOG has PLAN-001..037 + AA0..AA3 -> AA4
# ---------------------------------------------------------------------------

def test_3_mixed_historical_and_aa():
    """
    Historical numeric PLAN files (001..037) plus AA0..AA3 on disk -> returns AA4.
    Post-W0.2 the IDs must be on the filesystem; LOG rows no longer contribute.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        for i in range(1, 38):
            (rt / f"PLAN-{str(i).zfill(3)}_plan-{i}.md").write_text(_PLAN_STUB)
        for i in range(4):
            (wb / f"PLAN-AA{i}_aa-plan-{i}.md").write_text(_PLAN_STUB)

        used = compute_used_ids(repo)
        for i in range(1, 38):
            assert str(i).zfill(3) in used
        for i in range(4):
            assert f"AA{i}" in used
        result = next_aa_id(used)
        assert result == "AA4", f"Expected AA4, got {result!r}"

# ---------------------------------------------------------------------------
# Test 4 - Lowest-unused, not max-plus-one: AA0, AA1, AA3 used -> returns AA2
# ---------------------------------------------------------------------------

def test_4_lowest_unused_not_max_plus_one():
    """AA0, AA1, AA3 on disk (gap at AA2) -> returns AA2, not AA4."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        for plan_id in ("AA0", "AA1", "AA3"):
            (wb / f"PLAN-{plan_id}_plan.md").write_text(_PLAN_STUB)

        used = compute_used_ids(repo)
        assert "AA0" in used
        assert "AA1" in used
        assert "AA2" not in used, "AA2 should not be in used set (gap)"
        assert "AA3" in used
        result = next_aa_id(used)
        assert result == "AA2", f"Expected AA2 (lowest gap), got {result!r}"

# ---------------------------------------------------------------------------
# Test 5 - FS/LOG disagreement: FS has AA1 extra, LOG only has AA0
# ---------------------------------------------------------------------------

def test_5_log_contents_are_ignored(capsys):
    """
    PLAN-AD2 W0.2 contract: the LOG Status Table is not read at all.

    A LOG naming AA5 with no corresponding file must NOT mark AA5 used, and a
    PLAN file with no LOG row must be counted silently. This is the inverse of
    the pre-W0.2 warn-and-union behaviour, and it is the test that fails if the
    scan is ever reinstated.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        (wb / "PLAN-AA0_x.md").write_text(_PLAN_STUB)
        (wb / "PLAN-AA1_y.md").write_text(_PLAN_STUB)

        # LOG claims AA0 and AA5; only AA0 and AA1 exist on disk.
        (wb / "202605010000_LOG_202605.md").write_text(
            _make_log([_plan_row("AA0", "Plan AA0"), _plan_row("AA5", "Ghost Plan")])
        )

        used = compute_used_ids(repo)
        captured = capsys.readouterr()

        assert "AA0" in used and "AA1" in used
        assert "AA5" not in used, (
            f"LOG-only ID AA5 must NOT be counted post-W0.2; got {used}"
        )
        assert captured.err == "", (
            f"compute_used_ids must be silent by default; got: {captured.err!r}"
        )
        assert next_aa_id(used) == "AA2"

# ---------------------------------------------------------------------------
# Test 6 - Malformed LOG row: warning emitted; parsing continues
# ---------------------------------------------------------------------------

def test_6_malformed_log_never_read(capsys):
    """
    A structurally broken LOG cannot affect allocation, because no LOG is read.
    Pre-W0.2 this file produced a malformed-row warning; it must now be inert.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        (wb / "PLAN-AA0_good.md").write_text(_PLAN_STUB)
        (wb / "202605010000_LOG_202605.md").write_text(
            "---\ntitle: Broken LOG\n---\n\n## Status Table\n\n| truncated\n"
        )

        used = compute_used_ids(repo)
        captured = capsys.readouterr()

        assert used == {"AA0"}, f"Only the on-disk PLAN should count; got {used}"
        assert captured.err == "", (
            f"A malformed LOG must produce no output; got: {captured.err!r}"
        )
        assert next_aa_id(used) == "AA1"

# ---------------------------------------------------------------------------
# Test 7 - ADVICE/RESEARCH still numeric
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
# Test 8 - Historical numeric IDs in LOG do not perturb AA allocation
# ---------------------------------------------------------------------------

def test_8_numeric_ids_dont_block_aa():
    """
    A historical numeric PLAN file (PLAN-029) must not block PLAN-AA0.
    Numeric and AA-form IDs are disjoint slot-spaces - the invariant that makes
    dropping the LOG scan safe, since everything it contributed was numeric.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        (rt / "PLAN-029_old-plan.md").write_text(_PLAN_STUB)

        used = compute_used_ids(repo)
        assert "029" in used, "Numeric 029 should be in used set"
        assert "AA0" not in used, "AA0 should NOT be in used set (disjoint namespace)"

        result = next_aa_id(used)
        assert result == "AA0", f"Expected AA0 (unperturbed by numeric IDs), got {result!r}"

# ---------------------------------------------------------------------------
# Test 9 - Boundary case AZ9 -> BA0
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
# Test 10 - Exhaustion: all 6,760 AA IDs used -> RuntimeError -> exits 1
# ---------------------------------------------------------------------------

def test_10_exhaustion():
    """All AA0..ZZ9 used -> next_aa_id raises RuntimeError with exhaustion message."""
    all_ids = {index_to_aa_id(i) for i in range(_AA_TOTAL)}
    assert len(all_ids) == _AA_TOTAL, f"Expected {_AA_TOTAL} IDs, got {len(all_ids)}"

    with pytest.raises(RuntimeError, match="exhausted"):
        next_aa_id(all_ids)


# ---------------------------------------------------------------------------
# Test 11 - Nested Retired/<month>/: nested PLAN file + rolled-over LOG counted
# ---------------------------------------------------------------------------

def test_11_nested_retired_dir(capsys):
    """
    Retired/ nests rolled-over artefacts in per-month subdirectories. A PLAN
    file at Retired/<month>/PLAN-AA3_x.md must be discovered - a non-recursive
    scan silently under-counts and the allocator then re-issues a used ID.

    Post-W0.2 the recursive filesystem scan is the ONLY protection against
    this, so this test carries more weight than it did when a LOG scan
    backstopped it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        (wb / "PLAN-AA0_current.md").write_text(_PLAN_STUB)

        month_dir = rt / "202604"
        month_dir.mkdir()
        for plan_id in ("AA1", "AA2", "AA3"):
            (month_dir / f"PLAN-{plan_id}_april.md").write_text(_PLAN_STUB)

        # A rolled-over LOG alongside them must remain inert.
        (month_dir / "202604010000_LOG_202604.md").write_text(
            _make_log([_plan_row("AA9", "Ghost Plan")])
        )

        used = compute_used_ids(repo)
        captured = capsys.readouterr()

        assert "AA0" in used, "current-month PLAN file missed"
        assert {"AA1", "AA2", "AA3"} <= used, f"nested retired PLAN files missed; got {used}"
        assert "AA9" not in used, "nested rolled-over LOG must not contribute IDs"
        assert captured.err == "", f"expected silence; got: {captured.err!r}"
        assert next_aa_id(used) == "AA4"

# ---------------------------------------------------------------------------
# Test 12 - Nested Retired/<month>/ ADVICE files counted by numeric allocator
# ---------------------------------------------------------------------------

def test_12_nested_retired_numeric():
    """
    next_numeric_id must scan Retired/ recursively too - a nested retired
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
# Test 13 - Post-AB9 D2: Retired/ scan is authoritative; no LOG required
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
# Test 14 - LOG-scan as non-authoritative defence-in-depth fallback
# ---------------------------------------------------------------------------

def test_14_verbose_reports_filesystem_only():
    """
    verbose=True (wired to --explain) emits a single summary note naming the
    filesystem as the sole source, and no per-ID warning lines. Guards the
    48-line stderr regression W0.2 removed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        for plan_id in ("AA0", "AA1"):
            (wb / f"PLAN-{plan_id}_x.md").write_text(_PLAN_STUB)

        buf = io.StringIO()
        real_stderr, sys.stderr = sys.stderr, buf
        try:
            used = compute_used_ids(repo, verbose=True)
        finally:
            sys.stderr = real_stderr

        err = buf.getvalue()
        assert used == {"AA0", "AA1"}
        assert len(err.strip().splitlines()) == 1, (
            f"verbose output must be one summary line, not per-ID; got: {err!r}"
        )
        assert "filesystem" in err
        assert "warning:" not in err, "expected a note, not a warning"

# ---------------------------------------------------------------------------
# Test 15 - glob_filesystem_ids_by_source partitions correctly
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
# Test 16 - --explain flag emits per-ID source labels to stderr
# ---------------------------------------------------------------------------

def test_16_explain_flag_stderr_format():
    """
    Invoking the script with `--explain` emits one stderr line per used ID in
    the format `<ID>\\t<source>`, lex-sorted, with a trailing blank line, while
    stdout still prints the next ID unchanged.

    Post-PLAN-AD2 W0.2 `<source>` is `Workbench` or `Retired` only - the
    `LOG-only` label is gone with the scan that produced it, and an ID named
    solely by a LOG is not reported at all because it is not used.

    Runs the script as a subprocess against a synthetic repo to exercise the
    argparse wiring and stdout/stderr separation.
    """
    import subprocess

    with tempfile.TemporaryDirectory() as tmp:
        repo, wb, rt = _setup_repo(tmp)

        # One Workbench PLAN, one nested Retired PLAN, and a LOG that also
        # names a third ID (AA2) with no file anywhere.
        (wb / "PLAN-AA0_active.md").write_text(_PLAN_STUB)
        month_dir = rt / "202604"
        month_dir.mkdir()
        (month_dir / "PLAN-AA1_retired.md").write_text(_PLAN_STUB)
        (wb / "202605010000_LOG_202605.md").write_text(
            _make_log([
                _plan_row("AA0", "Active", "in-progress"),
                _plan_row("AA1", "Retired", "done"),
                _plan_row("AA2", "Lost", "done"),
            ])
        )

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
        # AA2 exists only in the LOG, so it is not used and AA2 is allocated.
        stdout_line = result.stdout.strip()
        assert stdout_line == "AA2", (
            f"Expected stdout 'AA2' (LOG-only AA2 is not used post-W0.2); "
            f"got {stdout_line!r}"
        )

        explain_lines = [
            line for line in result.stderr.splitlines()
            if "\t" in line and any(
                line.endswith(s) for s in ("\tWorkbench", "\tRetired")
            )
        ]
        assert len(explain_lines) == 2, (
            f"Expected 2 explain lines; got {len(explain_lines)}: {explain_lines!r}\n"
            f"full stderr: {result.stderr!r}"
        )
        assert "LOG-only" not in result.stderr, (
            f"The LOG-only label was removed with the scan; got: {result.stderr!r}"
        )
        ids_in_order = [line.split("\t", 1)[0] for line in explain_lines]
        assert ids_in_order == sorted(ids_in_order), (
            f"Explain lines not lex-sorted: {ids_in_order!r}"
        )
        labelled = dict(line.split("\t", 1) for line in explain_lines)
        assert labelled.get("AA0") == "Workbench", labelled
        assert labelled.get("AA1") == "Retired", labelled

# ---------------------------------------------------------------------------
# Test 17 - --explain absent: stderr has no <ID>\t<source> lines
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
        # No LOG -> AA0 is FS-orphan -> stderr warning, but no explain lines.

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
