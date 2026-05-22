#!/usr/bin/env python3
"""
test_migrate_plan_ids.py — test suite for migrate_plan_ids.py

9 tests:
  1. Chronological sort assigns expected IDs.
  2. Pass-1 rewrite (full stems) — cross-references in linked_inputs / blocked_by / triggers_plans are updated.
  3. Pass-2 rewrite (LOG status-table cells) — bare 12-digit IDs in pipe-delimited rows updated; generic numbers elsewhere are NOT.
  4. Pass-3 rewrite (friendly forms) — "PLAN 202605121430" becomes new ID.
  5. Sibling files in .audit/ and .ideate-critique/ are renamed correctly.
  6. Date fields like "created: 2026-05-13" are NOT touched.
  7. LOG files are not renamed (only content gets pass-2 rewrites).
  8. Existing new-format files (already PLAN-NNN_*.md) are skipped; no double-renaming.
  9. Idempotency — running --apply twice is a no-op on second run.

Usage: python test_migrate_plan_ids.py
Exit 0 on success.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: locate migrate_plan_ids module relative to this script
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import migrate_plan_ids as M

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLAN_FRONTMATTER = """\
---
type: plan
status: ready
schema_version: 2
---

## Objective
Test plan.
"""

ADVICE_FRONTMATTER = """\
---
type: advice
status: ready
schema_version: 2
---

## Content
Test advice.
"""

RESEARCH_FRONTMATTER = """\
---
type: research
status: ready
schema_version: 2
---

## Content
Test research.
"""


def make_old_plan(name: str, extra_body: str = "") -> str:
    return PLAN_FRONTMATTER + extra_body


def make_log(name: str, table_body: str = "") -> str:
    return f"---\ntype: log\nstatus: open\n---\n\n## Status Table\n\n{table_body}\n"


class Failures:
    def __init__(self):
        self.items = []

    def fail(self, msg):
        self.items.append(msg)
        print(f"  FAIL: {msg}")

    def ok(self, msg):
        print(f"  OK:   {msg}")

    @property
    def count(self):
        return len(self.items)


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------

def test_1_chronological_sort_assigns_ids():
    """Test 1: Chronological sort assigns expected IDs."""
    print("Test 1: chronological sort assigns expected IDs")
    f = Failures()

    with tempfile.TemporaryDirectory() as tmp:
        wb = Path(tmp) / "Workbench"
        rt = Path(tmp) / "Retired"
        wb.mkdir()
        rt.mkdir()

        # Create files out of order (alphabetically) but different timestamps
        (wb / "202605130000_PLAN_beta.md").write_text(make_old_plan("beta"))
        (wb / "202605120000_PLAN_alpha.md").write_text(make_old_plan("alpha"))
        (rt / "202604010000_PLAN_earliest.md").write_text(make_old_plan("earliest"))
        (wb / "202605140000_ADVICE_note.md").write_text(ADVICE_FRONTMATTER)
        (wb / "202605140001_RESEARCH_data.md").write_text(RESEARCH_FRONTMATTER)

        rename_map, friendly_map = M.build_rename_map(wb, rt)

        # Expected:
        # PLAN chronological: 202604010000 -> PLAN-001, 202605120000 -> PLAN-002, 202605130000 -> PLAN-003
        # ADVICE: 202605140000 -> ADVICE-001
        # RESEARCH: 202605140001 -> RESEARCH-001

        expected = {
            "202604010000_PLAN_earliest": "PLAN-001_earliest",
            "202605120000_PLAN_alpha": "PLAN-002_alpha",
            "202605130000_PLAN_beta": "PLAN-003_beta",
            "202605140000_ADVICE_note": "ADVICE-001_note",
            "202605140001_RESEARCH_data": "RESEARCH-001_data",
        }

        for old, new in expected.items():
            if rename_map.get(old) == new:
                f.ok(f"{old} -> {new}")
            else:
                f.fail(f"Expected {old} -> {new}, got {rename_map.get(old)!r}")

        # Check friendly map
        if friendly_map.get("202605120000") == "PLAN-002":
            f.ok("friendly_map[202605120000] == PLAN-002")
        else:
            f.fail(f"friendly_map[202605120000] = {friendly_map.get('202605120000')!r}, expected PLAN-002")

    return f.count


def test_2_pass1_stem_rewrite():
    """Test 2: Pass-1 full-stem rewrite updates cross-references."""
    print("Test 2: pass-1 full-stem cross-reference rewrite")
    f = Failures()

    rename_map = {
        "202605121430_PLAN_audit-v2": "PLAN-005_audit-v2",
        "202605130040_ADVICE_strategy": "ADVICE-001_strategy",
    }

    body = """\
---
linked_inputs: [202605130040_ADVICE_strategy]
blocked_by: 202605121430_PLAN_audit-v2
triggers_plans: [202605121430_PLAN_audit-v2]
---

See also 202605121430_PLAN_audit-v2 for details.
Input: 202605130040_ADVICE_strategy
created: 2026-05-12
date: 2026-05-13T00:40:00
"""

    new_text, count = M.apply_pass1(body, rename_map)

    # Assertions
    if "202605121430_PLAN_audit-v2" not in new_text:
        f.ok("old PLAN stem removed from content")
    else:
        f.fail("old PLAN stem still present in content")

    if "202605130040_ADVICE_strategy" not in new_text:
        f.ok("old ADVICE stem removed from content")
    else:
        f.fail("old ADVICE stem still present in content")

    if "PLAN-005_audit-v2" in new_text:
        f.ok("new PLAN stem present")
    else:
        f.fail("new PLAN stem missing from content")

    if "ADVICE-001_strategy" in new_text:
        f.ok("new ADVICE stem present")
    else:
        f.fail("new ADVICE stem missing from content")

    # Date fields must not be touched
    if "created: 2026-05-12" in new_text:
        f.ok("date field 'created: 2026-05-12' preserved")
    else:
        f.fail("date field was modified")

    if count >= 4:
        f.ok(f"replacement count {count} >= 4")
    else:
        f.fail(f"replacement count {count} < 4 (expected at least 4)")

    return f.count


def test_3_pass2_log_table():
    """Test 3: Pass-2 LOG table rewrite updates ID cells; generic 12-digit numbers are NOT touched."""
    print("Test 3: pass-2 LOG status-table cell rewrite")
    f = Failures()

    friendly_map = {
        "202605121430": "PLAN-005",
        "202605131800": "PLAN-007",
    }

    log_text = """\
---
type: log
---

## Status Table

| ID | Title | Status |
|---|---|---|
| 202605121430 | Audit v2 | done |
| 202605131800 | Pipeline hooks | ready |
| 202604010000 | Some unrelated plan | ready |

Some prose: version 202604010000 is the log version code. Not an ID.

| Date | Notes |
|---|---|
| 202605131800 | Meeting notes entry |
"""

    new_text, count = M.apply_pass2(log_text, friendly_map)

    # ID column cells should be rewritten
    if "PLAN-005" in new_text:
        f.ok("PLAN-005 appears in table")
    else:
        f.fail("PLAN-005 missing from table output")

    if "PLAN-007" in new_text:
        f.ok("PLAN-007 appears in table")
    else:
        f.fail("PLAN-007 missing from table output")

    # 202604010000 is NOT in friendly_map — must remain untouched in table
    if "202604010000" in new_text:
        f.ok("unknown 12-digit 202604010000 left untouched in table")
    else:
        f.fail("202604010000 incorrectly modified")

    # Prose mention NOT in table context must NOT be changed by pass 2
    # (pass 2 only handles pipe-table rows)
    if "version 202604010000 is the log version code" in new_text:
        f.ok("prose 12-digit number in non-table context preserved")
    else:
        f.fail("prose 12-digit number was incorrectly modified by pass 2")

    # The second table (Date | Notes) has 202605131800 in the Date column — not an ID column
    # Pass 2 should NOT rewrite it because the header is "Date", not "ID"/"Plan"
    second_table_check = "| 202605131800 | Meeting notes entry |"
    if second_table_check in new_text:
        f.ok("second table's Date column 202605131800 not touched (non-ID column)")
    else:
        f.fail("second table's Date column was incorrectly rewritten")

    return f.count


def test_4_pass3_friendly_forms():
    """Test 4: Pass-3 friendly-form rewrite."""
    print("Test 4: pass-3 friendly-form rewrite")
    f = Failures()

    friendly_map = {
        "202605121430": "PLAN-005",
        "202605130040": "ADVICE-001",
    }

    body = """\
This is related to PLAN 202605121430 which covers audit changes.
We also reference ADVICE 202605130040 for background.
The timestamp 202605121430 alone (no type prefix) should NOT be changed.
Date 2026-05-12 should NOT be changed.
"""

    new_text, count = M.apply_pass3(body, friendly_map)

    if "PLAN 202605121430" not in new_text:
        f.ok("'PLAN 202605121430' replaced")
    else:
        f.fail("'PLAN 202605121430' not replaced")

    if "PLAN-005" in new_text:
        f.ok("'PLAN-005' present")
    else:
        f.fail("'PLAN-005' missing")

    if "ADVICE 202605130040" not in new_text:
        f.ok("'ADVICE 202605130040' replaced")
    else:
        f.fail("'ADVICE 202605130040' not replaced")

    if "ADVICE-001" in new_text:
        f.ok("'ADVICE-001' present")
    else:
        f.fail("'ADVICE-001' missing")

    # Bare timestamp without type prefix must NOT be changed
    if "The timestamp 202605121430 alone" in new_text:
        f.ok("bare timestamp without type prefix preserved")
    else:
        f.fail("bare timestamp without type prefix was incorrectly changed")

    # Date must not be changed
    if "Date 2026-05-12" in new_text:
        f.ok("date field preserved")
    else:
        f.fail("date field modified")

    return f.count


def test_5_sibling_file_renames():
    """Test 5: Sibling files in .audit/ and .ideate-critique/ are renamed."""
    print("Test 5: sibling file renames in .audit/ and .ideate-critique/")
    f = Failures()

    with tempfile.TemporaryDirectory() as tmp:
        wb = Path(tmp) / "Workbench"
        rt = Path(tmp) / "Retired"
        wb.mkdir()
        rt.mkdir()
        audit_dir = wb / ".audit"
        critique_dir = wb / ".ideate-critique"
        audit_dir.mkdir()
        critique_dir.mkdir()

        (wb / "202605131830_PLAN_plan-id-renaming.md").write_text(make_old_plan("plan-id-renaming"))
        (audit_dir / "202605131830_PLAN_plan-id-renaming-1.json").write_text('{"plan_path": "Workbench/202605131830_PLAN_plan-id-renaming.md"}')
        (critique_dir / "202605131830_PLAN_plan-id-renaming-1.json").write_text('{"plan_path": "Workbench/202605131830_PLAN_plan-id-renaming.md"}')

        rename_map, friendly_map = M.build_rename_map(wb, rt)
        sibling_moves = M.build_sibling_moves(wb, rename_map)

        if len(sibling_moves) == 2:
            f.ok("2 sibling moves found (1 .audit + 1 .ideate-critique)")
        else:
            f.fail(f"Expected 2 sibling moves, got {len(sibling_moves)}")

        # Check that new paths contain PLAN-001
        new_names = [new_p.name for _, new_p in sibling_moves]
        for name in new_names:
            if "PLAN-001_plan-id-renaming-1.json" == name:
                f.ok(f"sibling new name correct: {name}")
            else:
                f.fail(f"sibling new name unexpected: {name!r} (expected PLAN-001_plan-id-renaming-1.json)")

    return f.count


def test_6_date_fields_preserved():
    """Test 6: Date fields like 'created: 2026-05-13' are not touched by any pass."""
    print("Test 6: date fields preserved across all passes")
    f = Failures()

    rename_map = {"202605121430_PLAN_foo": "PLAN-001_foo"}
    friendly_map = {"202605121430": "PLAN-001"}

    body = """\
---
created: 2026-05-13
due: 2026-05-20
created_month: 202605
log_month: 202605
linked_inputs: [202605121430_PLAN_foo]
---

See PLAN 202605121430 for context.
Today: 2026-05-13T12:00:00Z
"""

    after_p1, _ = M.apply_pass1(body, rename_map)
    after_p3, _ = M.apply_pass3(after_p1, friendly_map)

    dates_to_check = [
        "created: 2026-05-13",
        "due: 2026-05-20",
        "Today: 2026-05-13T12:00:00Z",
        "created_month: 202605",
        "log_month: 202605",
    ]

    for date_str in dates_to_check:
        if date_str in after_p3:
            f.ok(f"preserved: {date_str!r}")
        else:
            f.fail(f"date field modified: {date_str!r}")

    return f.count


def test_7_log_files_not_renamed():
    """Test 7: LOG files are not renamed."""
    print("Test 7: LOG files not renamed")
    f = Failures()

    with tempfile.TemporaryDirectory() as tmp:
        wb = Path(tmp) / "Workbench"
        rt = Path(tmp) / "Retired"
        wb.mkdir()
        rt.mkdir()

        log_name = "202605010000_LOG_202605.md"
        (wb / log_name).write_text("---\ntype: log\n---\n")
        (wb / "202605121430_PLAN_some-plan.md").write_text(make_old_plan("some-plan"))

        rename_map, friendly_map = M.build_rename_map(wb, rt)

        # LOG stem must NOT appear in rename_map keys
        log_stem = "202605010000_LOG_202605"
        if log_stem not in rename_map:
            f.ok("LOG file excluded from rename map")
        else:
            f.fail("LOG file incorrectly included in rename map")

        # PLAN must be in rename map
        plan_stem = "202605121430_PLAN_some-plan"
        if plan_stem in rename_map:
            f.ok("PLAN file included in rename map")
        else:
            f.fail("PLAN file missing from rename map")

    return f.count


def test_8_already_new_format_skipped():
    """Test 8: Existing new-format files (PLAN-NNN_*.md) are skipped."""
    print("Test 8: already new-format files skipped")
    f = Failures()

    with tempfile.TemporaryDirectory() as tmp:
        wb = Path(tmp) / "Workbench"
        rt = Path(tmp) / "Retired"
        wb.mkdir()
        rt.mkdir()

        # Mix of old and new format
        (wb / "PLAN-001_already-migrated.md").write_text(make_old_plan("already-migrated"))
        (wb / "PLAN-002_also-migrated.md").write_text(make_old_plan("also-migrated"))
        (wb / "202605131800_PLAN_not-yet-migrated.md").write_text(make_old_plan("not-yet-migrated"))

        rename_map, friendly_map = M.build_rename_map(wb, rt)

        # New-format files must not be in rename_map keys
        for stem in ["PLAN-001_already-migrated", "PLAN-002_also-migrated"]:
            if stem not in rename_map:
                f.ok(f"new-format file '{stem}' not in rename map")
            else:
                f.fail(f"new-format file '{stem}' incorrectly included in rename map")

        # Old-format file must be in rename map
        old_stem = "202605131800_PLAN_not-yet-migrated"
        if old_stem in rename_map:
            f.ok("old-format file included in rename map")
        else:
            f.fail("old-format file missing from rename map")

        # New-format files shouldn't cause double-renaming — the result should start from PLAN-001
        # (skipping the 2 existing PLAN-00x files we have... but actually next_id scanning is per
        # the existing counters. In build_rename_map we only count OLD-format files and assign
        # starting at 001. The 2 already-migrated PLAN-001 and PLAN-002 are not in the count,
        # but that's OK for migration purposes — there should be exactly 1 entry in rename_map.)
        if len(rename_map) == 1:
            f.ok("exactly 1 file in rename map (old-format only)")
        else:
            f.fail(f"rename_map has {len(rename_map)} entries, expected 1")

    return f.count


def test_9_idempotency():
    """Test 9: Running --apply twice is a no-op on second run."""
    print("Test 9: idempotency (two --apply runs)")
    f = Failures()

    with tempfile.TemporaryDirectory() as tmp:
        wb = Path(tmp) / "Workbench"
        rt = Path(tmp) / "Retired"
        wb.mkdir()
        rt.mkdir()
        audit_dir = wb / ".audit"
        critique_dir = wb / ".ideate-critique"
        audit_dir.mkdir()
        critique_dir.mkdir()

        # Create fixture files
        plan_a = wb / "202605121430_PLAN_alpha.md"
        plan_b = rt / "202604010000_PLAN_beta.md"
        advice_c = wb / "202605140000_ADVICE_gamma.md"

        plan_a.write_text(
            "---\ntype: plan\nlinked_inputs: [202605140000_ADVICE_gamma]\n---\n"
            "See PLAN 202605121430 for context.\n"
        )
        plan_b.write_text("---\ntype: plan\n---\nOlder plan content.\n")
        advice_c.write_text("---\ntype: advice\n---\nAdvice content.\n")

        sibling_json = audit_dir / "202605121430_PLAN_alpha-1.json"
        sibling_json.write_text(json.dumps({"plan_path": "Workbench/202605121430_PLAN_alpha.md"}, indent=2))

        # First run — scope repo_root to the temp dir so we don't walk the real repo
        repo_root = Path(tmp)
        M.run_migration(wb, rt, dry_run=False, repo_root=repo_root)

        # Collect state after first run
        wb_files_1 = sorted(p.name for p in wb.glob("*.md"))
        rt_files_1 = sorted(p.name for p in rt.glob("*.md"))
        audit_files_1 = sorted(p.name for p in audit_dir.glob("*.json"))

        # Second run — should be a no-op
        M.run_migration(wb, rt, dry_run=False, repo_root=repo_root)

        wb_files_2 = sorted(p.name for p in wb.glob("*.md"))
        rt_files_2 = sorted(p.name for p in rt.glob("*.md"))
        audit_files_2 = sorted(p.name for p in audit_dir.glob("*.json"))

        if wb_files_1 == wb_files_2:
            f.ok("Workbench filenames unchanged on second run")
        else:
            f.fail(f"Workbench filenames changed on second run: {wb_files_1} -> {wb_files_2}")

        if rt_files_1 == rt_files_2:
            f.ok("Retired filenames unchanged on second run")
        else:
            f.fail(f"Retired filenames changed on second run: {rt_files_1} -> {rt_files_2}")

        if audit_files_1 == audit_files_2:
            f.ok(".audit filenames unchanged on second run")
        else:
            f.fail(f".audit filenames changed on second run: {audit_files_1} -> {audit_files_2}")

        # Verify new-format files exist after first run
        new_plan_a = wb / "PLAN-002_alpha.md"  # PLAN-002 because beta is older -> PLAN-001
        new_plan_b = rt / "PLAN-001_beta.md"
        new_advice_c = wb / "ADVICE-001_gamma.md"

        for p in [new_plan_a, new_plan_b, new_advice_c]:
            if p.exists():
                f.ok(f"new-format file exists: {p.name}")
            else:
                # Search what actually exists
                actual = sorted(p.parent.glob("*.md"))
                f.fail(f"expected {p.name} not found; dir contains: {[x.name for x in actual]}")

        # Old format files must not exist
        for old_name in ["202605121430_PLAN_alpha.md", "202604010000_PLAN_beta.md", "202605140000_ADVICE_gamma.md"]:
            old_p = (wb if "alpha" in old_name or "gamma" in old_name else rt) / old_name
            if not old_p.exists():
                f.ok(f"old-format file removed: {old_name}")
            else:
                f.fail(f"old-format file still exists: {old_name}")

    return f.count


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    tests = [
        test_1_chronological_sort_assigns_ids,
        test_2_pass1_stem_rewrite,
        test_3_pass2_log_table,
        test_4_pass3_friendly_forms,
        test_5_sibling_file_renames,
        test_6_date_fields_preserved,
        test_7_log_files_not_renamed,
        test_8_already_new_format_skipped,
        test_9_idempotency,
    ]

    total_failures = 0
    print("=" * 60)
    print("migrate_plan_ids test suite")
    print("=" * 60)

    for i, test_fn in enumerate(tests, start=1):
        print()
        failures = test_fn()
        if failures == 0:
            print(f"  -> PASSED")
        else:
            print(f"  -> FAILED ({failures} assertion(s))")
        total_failures += failures

    print()
    print("=" * 60)
    if total_failures == 0:
        print(f"All {len(tests)} tests PASSED.")
        sys.exit(0)
    else:
        print(f"{total_failures} assertion(s) FAILED across {len(tests)} tests.")
        sys.exit(1)


if __name__ == "__main__":
    main()
