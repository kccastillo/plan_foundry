"""
test_project_context_inputs.py — Tests for project_context_inputs.py.

Covers (per PLAN-AG5 Step 4):
  - test_check_detects_dangling_and_missing
  - test_offmonth_input_not_flagged_missing          (blocker S002)
  - test_check_clean_when_table_matches
  - test_write_preserves_authored_advises_and_notes  (blocker S202)
  - test_write_seeds_advises_from_frontmatter_only_for_new_rows
  - test_absent_section_treated_as_zero_rows

All tests operate on tmp_path fixtures ONLY — none read or write the real
repo Workbench/.

Run:
    python3 -m pytest .claude/skills/update-workbench-index/lib/test_project_context_inputs.py -q
"""

import sys
from pathlib import Path

# Sibling import: this test lives in lib/; projector lives in scripts/.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import project_context_inputs
from project_context_inputs import compute_rows, diff, render_write


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# All fixture LOGs use month 202607 so the month-filter logic is exercised.
LOG_NAME = "202607010000_LOG_202607.md"
IN_MONTH_DATE = "2026-07-01"
OFF_MONTH_DATE = "2026-05-22"


def _write_advice(
    workbench: Path,
    name: str,
    created: str,
    advises_plan: str = "",
) -> Path:
    """Write a minimal ADVICE-*.md fixture file."""
    p = workbench / name
    p.write_text(
        (
            "---\n"
            "type: advice\n"
            f"created: {created}\n"
            f'advises_plan: "{advises_plan}"\n'
            "integration_status: pending\n"
            "---\n\n"
            "Content.\n"
        ),
        encoding="utf-8",
    )
    return p


def _write_research(
    workbench: Path,
    name: str,
    created: str,
    feeds_plan: str = "",
) -> Path:
    """Write a minimal RESEARCH-*.md fixture file."""
    p = workbench / name
    p.write_text(
        (
            "---\n"
            "type: research\n"
            f"created: {created}\n"
            f'feeds_plan: "{feeds_plan}"\n'
            "integration_status: pending\n"
            "---\n\n"
            "Content.\n"
        ),
        encoding="utf-8",
    )
    return p


def _write_log(
    workbench: Path,
    table_rows: list[tuple[str, str, str]] | None,
    extra_prose: str = "",
) -> Path:
    """
    Write a fixture LOG file.

    table_rows — list of (input, advises, notes) tuples for the Context Inputs
                 table, or None to produce a LOG with NO Context Inputs section.
    extra_prose — optional prose to insert between the section heading and the
                  table (with a trailing newline).
    """
    log = workbench / LOG_NAME

    if table_rows is None:
        # No Context Inputs section at all.
        content = (
            '---\ntitle: "Test LOG"\ntype: log\nmonth: 2026-07\n---\n\n'
            "## Other Section\n\nSome other content.\n"
        )
    else:
        rows_md = "\n".join(
            f"| {inp} | {adv} | {notes} |"
            for inp, adv, notes in table_rows
        )
        content = (
            '---\ntitle: "Test LOG"\ntype: log\nmonth: 2026-07\n---\n\n'
            "## Context Inputs This Month\n\n"
            f"{extra_prose}"
            "| Input | Advises | Notes |\n"
            "|---|---|---|\n"
            f"{rows_md}\n"
            "\n"
            "## Lessons Learned\n\nMore content.\n"
        )

    log.write_text(content, encoding="utf-8")
    return log


def _cli_exit(argv: list[str]) -> int:
    """Run project_context_inputs.main(argv) and capture the SystemExit code."""
    try:
        project_context_inputs.main(argv)
        return 0  # main() exited without sys.exit
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_check_detects_dangling_and_missing(tmp_path):
    """
    diff() returns dangling (in table but not on disk) and missing (on-disk
    in-month input not in table).  --check exits non-zero on drift.
    """
    wb = tmp_path / "Workbench"
    wb.mkdir()

    # Two in-month files on disk.
    _write_advice(wb, "ADVICE-001_alpha.md", IN_MONTH_DATE, "PLAN-XX0_a.md")
    _write_research(wb, "RESEARCH-001_beta.md", IN_MONTH_DATE, "PLAN-XX1_b.md")

    # Table: has ADVICE-001 (on disk) and a dangling row (never on disk).
    # Missing: RESEARCH-001 (on disk but not in table).
    log = _write_log(wb, [
        ("ADVICE-001_alpha.md", "PLAN-XX0_a.md", "Note A"),
        ("DANGLING-NEVER-EXISTED.md", "PLAN-XX9", "Old note"),
    ])

    report = diff(log, wb)

    assert report["dangling"] == ["DANGLING-NEVER-EXISTED.md"], (
        f"Expected dangling=['DANGLING-NEVER-EXISTED.md'], got {report['dangling']}"
    )
    assert report["missing"] == ["RESEARCH-001_beta.md"], (
        f"Expected missing=['RESEARCH-001_beta.md'], got {report['missing']}"
    )

    # CLI exits non-zero when there is drift.
    code = _cli_exit([str(wb), "--log-path", str(log), "--check"])
    assert code != 0, f"Expected non-zero exit on drift, got {code}"


def test_offmonth_input_not_flagged_missing(tmp_path):
    """
    An off-month on-disk input (different YYYYMM in frontmatter `created`)
    must NOT appear under `missing`.  The --check CLI exits 0 when the table
    matches the in-month set, even though an off-month file is present on disk.
    (blocker S002)
    """
    wb = tmp_path / "Workbench"
    wb.mkdir()

    # In-month files.
    _write_advice(wb, "ADVICE-001_alpha.md", IN_MONTH_DATE, "PLAN-XX0_a.md")
    _write_research(wb, "RESEARCH-001_beta.md", IN_MONTH_DATE, "PLAN-XX1_b.md")

    # Off-month file (May 2026) — present on disk but NOT a July input.
    _write_advice(wb, "ADVICE-090_offmonth.md", OFF_MONTH_DATE, "PLAN-XX2_c.md")

    # Table exactly matches the in-month set.
    log = _write_log(wb, [
        ("ADVICE-001_alpha.md", "PLAN-XX0_a.md", "Note A"),
        ("RESEARCH-001_beta.md", "PLAN-XX1_b.md", "Note B"),
    ])

    report = diff(log, wb)

    assert "ADVICE-090_offmonth.md" not in report["missing"], (
        "Off-month file must not appear under missing"
    )
    assert report["dangling"] == [], f"Expected no dangling, got {report['dangling']}"
    assert report["missing"] == [], f"Expected no missing, got {report['missing']}"

    # CLI exits 0 — no drift.
    code = _cli_exit([str(wb), "--log-path", str(log), "--check"])
    assert code == 0, f"Expected exit 0 on clean table, got {code}"


def test_check_clean_when_table_matches(tmp_path):
    """
    diff() returns empty dangling and missing when the table rows exactly
    match the in-month on-disk input set.  --check exits 0.
    """
    wb = tmp_path / "Workbench"
    wb.mkdir()

    _write_advice(wb, "ADVICE-002_gamma.md", IN_MONTH_DATE, "PLAN-YY0_g.md")
    _write_research(wb, "RESEARCH-002_delta.md", IN_MONTH_DATE, "PLAN-YY1_d.md")

    log = _write_log(wb, [
        ("ADVICE-002_gamma.md", "PLAN-YY0", "Note G"),
        ("RESEARCH-002_delta.md", "PLAN-YY1", "Note D"),
    ])

    report = diff(log, wb)

    assert report["dangling"] == [], f"Expected no dangling, got {report['dangling']}"
    assert report["missing"] == [], f"Expected no missing, got {report['missing']}"

    code = _cli_exit([str(wb), "--log-path", str(log), "--check"])
    assert code == 0, f"Expected exit 0 on clean table, got {code}"


def test_write_preserves_authored_advises_and_notes(tmp_path):
    """
    --write preserves the authored Advises and Notes cells verbatim for
    surviving rows, even when those cells DIVERGE from the file's frontmatter
    advises_plan / feeds_plan values.  Dangling rows are removed.  (blocker S202)
    """
    wb = tmp_path / "Workbench"
    wb.mkdir()

    # ADVICE-003: frontmatter advises_plan is EMPTY, but the authored Advises
    # cell in the table is a rich routing note.
    _write_advice(wb, "ADVICE-003_pref.md", IN_MONTH_DATE, "")  # empty advises_plan

    # RESEARCH-003: frontmatter feeds_plan points to PLAN-AF5 (stale), but the
    # authored Advises cell correctly says PLAN-AG3 (via parent PLAN-AF6).
    _write_research(wb, "RESEARCH-003_qref.md", IN_MONTH_DATE, "PLAN-AF5_stale.md")

    authored_advice_advises = "PLAN-AG4 (via parent PLAN-AF6)"
    authored_advice_notes = "Authored note that must be preserved verbatim."
    authored_research_advises = "PLAN-AG3 (via parent PLAN-AF6)"
    authored_research_notes = "Research note verbatim."

    # Table: one dangling row + two surviving rows with authored cells.
    log = _write_log(wb, [
        ("DANGLING-OBS.md", "Old advises", "Old notes that will be dropped"),
        ("ADVICE-003_pref.md", authored_advice_advises, authored_advice_notes),
        ("RESEARCH-003_qref.md", authored_research_advises, authored_research_notes),
    ])

    code = _cli_exit([str(wb), "--log-path", str(log), "--write"])
    assert code == 0, f"Expected exit 0 from --write, got {code}"

    new_content = log.read_text(encoding="utf-8")

    # Dangling row removed.
    assert "DANGLING-OBS.md" not in new_content, "Dangling row should be removed"

    # ADVICE-003 authored Advises preserved (NOT the empty frontmatter value).
    assert authored_advice_advises in new_content, (
        "Authored Advises cell for ADVICE-003 not preserved"
    )

    # ADVICE-003 authored Notes preserved verbatim.
    assert authored_advice_notes in new_content, (
        "Authored Notes cell for ADVICE-003 not preserved"
    )

    # RESEARCH-003 authored Advises preserved (NOT the stale "PLAN-AF5_stale.md"
    # value from frontmatter feeds_plan).
    assert authored_research_advises in new_content, (
        "Authored Advises cell for RESEARCH-003 not preserved"
    )
    assert authored_research_notes in new_content, (
        "Authored Notes cell for RESEARCH-003 not preserved"
    )

    # The stale frontmatter value must NOT have been written into the table.
    # (It only lives in the file's own frontmatter, not the LOG table.)
    assert "PLAN-AF5_stale.md" not in new_content, (
        "Stale frontmatter feeds_plan must not appear in the reconciled table"
    )


def test_write_seeds_advises_from_frontmatter_only_for_new_rows(tmp_path):
    """
    --write seeds the Advises cell from frontmatter advises_plan / feeds_plan
    ONLY for newly-appended missing rows.  Surviving rows keep their authored
    Advises cells unchanged.
    """
    wb = tmp_path / "Workbench"
    wb.mkdir()

    # Surviving: ADVICE-004 is already in the table with an authored Advises cell.
    # Its frontmatter advises_plan carries a STALE value that must NOT overwrite
    # the authored cell.
    _write_advice(wb, "ADVICE-004_exist.md", IN_MONTH_DATE, "PLAN-ZZ9_stale.md")

    # New (missing): RESEARCH-004 is on disk but not in the table.
    # Its feeds_plan should be used to seed the Advises cell of the appended row.
    _write_research(wb, "RESEARCH-004_new.md", IN_MONTH_DATE, "PLAN-ZZ8_correct.md")

    authored_advises = "PLAN-ZZ7 (authored routing, must be preserved)"

    log = _write_log(wb, [
        ("ADVICE-004_exist.md", authored_advises, "Existing note"),
    ])

    code = _cli_exit([str(wb), "--log-path", str(log), "--write"])
    assert code == 0, f"Expected exit 0 from --write, got {code}"

    new_content = log.read_text(encoding="utf-8")

    # Surviving row keeps authored Advises (NOT the stale frontmatter value).
    assert authored_advises in new_content, (
        "Authored Advises not preserved on surviving row"
    )
    assert "PLAN-ZZ9_stale.md" not in new_content, (
        "Stale frontmatter advises_plan must not appear in the reconciled table"
    )

    # Newly-appended row present, seeded from frontmatter feeds_plan.
    assert "RESEARCH-004_new.md" in new_content, "New row not appended"
    assert "PLAN-ZZ8_correct.md" in new_content, (
        "frontmatter feeds_plan fallback not used for newly-appended row"
    )


def test_absent_section_treated_as_zero_rows(tmp_path):
    """
    If '## Context Inputs This Month' heading is absent, diff() treats the
    existing table as zero rows without crashing:
      dangling: []
      missing:  all in-month on-disk inputs
    """
    wb = tmp_path / "Workbench"
    wb.mkdir()

    _write_advice(wb, "ADVICE-005_alpha.md", IN_MONTH_DATE, "PLAN-AA0_a.md")
    _write_research(wb, "RESEARCH-005_beta.md", IN_MONTH_DATE, "PLAN-AA1_b.md")

    # LOG with NO Context Inputs section.
    log = _write_log(wb, None)

    # Must not crash.
    report = diff(log, wb)

    assert report["dangling"] == [], (
        f"Expected no dangling when heading absent, got {report['dangling']}"
    )
    assert "ADVICE-005_alpha.md" in report["missing"], (
        "In-month ADVICE file should appear as missing when section is absent"
    )
    assert "RESEARCH-005_beta.md" in report["missing"], (
        "In-month RESEARCH file should appear as missing when section is absent"
    )
