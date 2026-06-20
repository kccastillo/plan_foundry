"""
test_build_index.py — Regression tests for build_index.py.

Covers:
  - _audit_file_plan_id: all current/legacy/non-audit filename shapes
  - compute_alerts orphaned_audit_files: ADVICE-003 regression assertion
    (stage-suffixed + short-id audit files must NOT be flagged for present PLANs)
  - recurring_blockers: same-stage fingerprint recurrence triggers alert;
    cross-stage same fingerprint does NOT.

Self-contained: builds a tempfile Workbench with synthetic PLAN and .audit/
files; does NOT read the real repo Workbench/ or .audit/.

Run: python3 test_build_index.py
Exit 0 on success, non-zero on failure.
"""

import json
import sys
import tempfile
from pathlib import Path

# Resolve the sibling scripts/ directory so we can import build_index.
# This test lives in lib/; build_index lives in scripts/.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import build_index
from build_index import _audit_file_plan_id, _canonical_plan_id, compute_alerts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fail(label: str, detail: str) -> None:
    print(f"FAIL [{label}]: {detail}")
    sys.exit(1)


def assert_eq(label: str, expected, actual) -> None:
    if expected != actual:
        fail(label, f"expected {expected!r}, got {actual!r}")


def assert_none(label: str, actual) -> None:
    if actual is not None:
        fail(label, f"expected None, got {actual!r}")


# ---------------------------------------------------------------------------
# Minimal PLAN frontmatter template
# ---------------------------------------------------------------------------

PLAN_FRONTMATTER = """\
---
schema_version: 2
title: "Test PLAN"
type: plan
status: in-progress
assigned_to: sonnet
priority: medium
created: 2026-06-15
created_by: opus
created_month: 202606
log_month: 202606
due: ''
repeatable: false
repeat_cadence: ''
linked_decisions: []
linked_inputs: []
blocked_by: ''
rollover_count: 0
triggers_plans: []
closes_thread: ''
advances_thread: ''
parent_plan_of_plans: ''
pipeline_phase: executing
tags: []
files_touched: []
audit_acknowledgements: []
audit_disputes: []
audit_overrides: []
audit_state:
  last_stage: plan_safety
  last_outcome: success
  sufficiency_iterations: 1
  plan_safety_iterations: 1
  last_audit_commit: abc12345
---

## Objective
Test PLAN for build_index regression tests.

## Steps
1. Nothing.

## Verification
- [ ] Placeholder.
"""


# ---------------------------------------------------------------------------
# Test: _audit_file_plan_id
# ---------------------------------------------------------------------------

def test_audit_file_plan_id():
    """Covers all filename shapes documented in the PLAN spec."""
    cases = [
        # (filename, expected_result)
        # Short-id + sufficiency stage
        ("PLAN-AA4-sufficiency-1.json",              "PLAN-AA4"),
        # Short-id + plan_safety stage
        ("PLAN-AA4-plan_safety-1.json",              "PLAN-AA4"),
        # Short-id, no stage segment
        ("PLAN-AA4-1.json",                          "PLAN-AA4"),
        # Full-stem + legacy hyphenated stage
        ("PLAN-AA4_slug-plan-safety-2.json",         "PLAN-AA4"),
        # AA-form PLAN with legacy full-stem filename — short-id is still extracted
        # (AB9 matches [A-Z]{2}\d, so _audit_file_plan_id returns the short-id)
        ("PLAN-AB9_slug-1.json",                     "PLAN-AB9"),
        # AA-form PLAN with legacy full-stem + sufficiency stage suffix
        ("PLAN-AB9_slug-sufficiency-1.json",         "PLAN-AB9"),
        # Non-audit: audit-findings
        ("audit-findings-aecbc8c.json",              None),
        # Non-audit: recovery-inventory
        ("recovery-inventory-7e4cb36.json",          None),
        # Non-json extension (not a JSON file)
        ("release-dryrun-evidence.md",               None),
        # Edge: no trailing -<iter>.json pattern
        ("PLAN-AA4.json",                            None),
    ]

    for filename, expected in cases:
        result = _audit_file_plan_id(filename)
        assert_eq(f"_audit_file_plan_id({filename!r})", expected, result)

    print("PASS: test_audit_file_plan_id")


# ---------------------------------------------------------------------------
# Test: _canonical_plan_id
# ---------------------------------------------------------------------------

def test_canonical_plan_id():
    """Short-id extraction from stems."""
    cases = [
        ("PLAN-AA4_dungeon-architect-skill",   "PLAN-AA4"),
        ("PLAN-ZZ9_some-other-plan",           "PLAN-ZZ9"),
        # PLAN-AB9 is also AA-form (AB + 9), so it canonicalises to short-id
        ("PLAN-AB9_log-vs-index-rationalisation", "PLAN-AB9"),
        # Legacy numeric-form PLAN — no _ after PLAN-NNN form, returned unchanged
        ("PLAN-123_some-plan",                 "PLAN-123_some-plan"),
        # Legacy timestamp-prefix stem — returned unchanged
        ("202605121800_PLAN_smoke-test",       "202605121800_PLAN_smoke-test"),
    ]
    for stem, expected in cases:
        result = _canonical_plan_id(stem)
        assert_eq(f"_canonical_plan_id({stem!r})", expected, result)

    print("PASS: test_canonical_plan_id")


# ---------------------------------------------------------------------------
# Test: compute_alerts — orphaned_audit_files (ADVICE-003 regression)
# ---------------------------------------------------------------------------

def _make_plan_file(workbench: Path, plan_stem: str) -> Path:
    """Write a minimal PLAN file and return its path."""
    plan_path = workbench / f"{plan_stem}.md"
    plan_path.write_text(PLAN_FRONTMATTER, encoding="utf-8")
    return plan_path


def _make_audit_file(audit_dir: Path, name: str, stage: str = "sufficiency",
                     iteration: int = 1, findings: list | None = None) -> Path:
    """Write a minimal audit JSON and return its path."""
    data = {
        "outcome": "success",
        "findings": findings or [],
    }
    path = audit_dir / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_orphaned_audit_no_false_positives():
    """
    ADVICE-003 regression: stage-suffixed + short-id audit files must NOT be
    flagged as orphaned when their PLAN exists in Workbench/.

    Fixture: PLAN-AA4_dungeon-architect-skill.md present in Workbench/.
    Audit files in .audit/:
      - PLAN-AA4-sufficiency-1.json
      - PLAN-AA4-plan_safety-1.json
      - PLAN-AA4-1.json  (no stage segment)
    Expected: compute_alerts()["orphaned_audit_files"] is empty.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workbench = Path(tmpdir) / "Workbench"
        workbench.mkdir()
        audit_dir = workbench / ".audit"
        audit_dir.mkdir()

        _make_plan_file(workbench, "PLAN-AA4_dungeon-architect-skill")

        _make_audit_file(audit_dir, "PLAN-AA4-sufficiency-1.json")
        _make_audit_file(audit_dir, "PLAN-AA4-plan_safety-1.json", stage="plan_safety")
        _make_audit_file(audit_dir, "PLAN-AA4-1.json")

        plans = []
        for md in sorted(workbench.iterdir()):
            if md.suffix == ".md" and build_index.PLAN_PATTERN.match(md.name):
                p = build_index.load_plan(md)
                if p:
                    plans.append(p)

        alerts = compute_alerts(plans, workbench)
        orphans = alerts.get("orphaned_audit_files", [])

        if orphans:
            fail(
                "test_orphaned_audit_no_false_positives",
                f"Expected no orphans but got {len(orphans)}: "
                + ", ".join(o["plan_id"] for o in orphans),
            )

    print("PASS: test_orphaned_audit_no_false_positives")


def test_orphaned_audit_flags_missing_plan():
    """
    When the PLAN file is absent, the audit files ARE correctly flagged as orphaned.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workbench = Path(tmpdir) / "Workbench"
        workbench.mkdir()
        audit_dir = workbench / ".audit"
        audit_dir.mkdir()

        # No PLAN file — only audit files
        _make_audit_file(audit_dir, "PLAN-AA4-sufficiency-1.json")
        _make_audit_file(audit_dir, "PLAN-AA4-plan_safety-1.json", stage="plan_safety")
        _make_audit_file(audit_dir, "PLAN-AA4-1.json")

        plans = []  # empty — PLAN not present
        alerts = compute_alerts(plans, workbench)
        orphans = alerts.get("orphaned_audit_files", [])

        if not orphans:
            fail(
                "test_orphaned_audit_flags_missing_plan",
                "Expected orphan alerts but got none",
            )
        # All three files should be flagged
        if len(orphans) != 3:
            fail(
                "test_orphaned_audit_flags_missing_plan",
                f"Expected 3 orphan alerts, got {len(orphans)}",
            )

    print("PASS: test_orphaned_audit_flags_missing_plan")


def test_non_audit_files_excluded():
    """
    Non-audit JSON files (audit-findings-*.json, recovery-*.json) must not
    be flagged as orphaned regardless of whether any PLAN is present.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workbench = Path(tmpdir) / "Workbench"
        workbench.mkdir()
        audit_dir = workbench / ".audit"
        audit_dir.mkdir()

        # Only non-audit files
        (audit_dir / "audit-findings-aecbc8c.json").write_text("{}", encoding="utf-8")
        (audit_dir / "recovery-inventory-7e4cb36.json").write_text("{}", encoding="utf-8")

        plans = []
        alerts = compute_alerts(plans, workbench)
        orphans = alerts.get("orphaned_audit_files", [])

        if orphans:
            fail(
                "test_non_audit_files_excluded",
                f"Non-audit files were incorrectly flagged: "
                + ", ".join(o["plan_id"] for o in orphans),
            )

    print("PASS: test_non_audit_files_excluded")


# ---------------------------------------------------------------------------
# Test: recurring_blockers — stage-aware (D3 Per-Stage-Recurrence)
# ---------------------------------------------------------------------------

def _make_audit_with_findings(audit_dir: Path, name: str,
                               findings: list) -> Path:
    """Write an audit JSON file with given findings list."""
    data = {"outcome": "revision_needed", "findings": findings}
    path = audit_dir / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_recurring_blockers_same_stage_triggers_alert():
    """
    Two consecutive sufficiency iterations sharing an error fingerprint → one alert.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workbench = Path(tmpdir) / "Workbench"
        workbench.mkdir()
        audit_dir = workbench / ".audit"
        audit_dir.mkdir()

        _make_plan_file(workbench, "PLAN-AA4_dungeon-architect-skill")

        shared_finding = {
            "code": "S001",
            "level": "error",
            "category": "assumptions",
            "location": "Step 1",
            "message": "Missing prerequisite.",
            "fingerprint": "aabbccdd",
        }

        # Two sufficiency iterations with the same error fingerprint
        _make_audit_with_findings(
            audit_dir, "PLAN-AA4-sufficiency-1.json", [shared_finding]
        )
        _make_audit_with_findings(
            audit_dir, "PLAN-AA4-sufficiency-2.json", [shared_finding]
        )

        plans = []
        for md in sorted(workbench.iterdir()):
            if md.suffix == ".md" and build_index.PLAN_PATTERN.match(md.name):
                p = build_index.load_plan(md)
                if p:
                    plans.append(p)

        alerts = compute_alerts(plans, workbench)
        recurring = alerts.get("recurring_blockers", [])

        if not recurring:
            fail(
                "test_recurring_blockers_same_stage_triggers_alert",
                "Expected one recurring_blockers alert but got none",
            )
        if len(recurring) != 1:
            fail(
                "test_recurring_blockers_same_stage_triggers_alert",
                f"Expected exactly 1 alert, got {len(recurring)}",
            )

    print("PASS: test_recurring_blockers_same_stage_triggers_alert")


def test_recurring_blockers_cross_stage_no_alert():
    """
    Same error fingerprint appearing in sufficiency iter 1 and plan_safety iter 1
    must NOT trigger a recurring_blockers alert (cross-stage adjacency).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workbench = Path(tmpdir) / "Workbench"
        workbench.mkdir()
        audit_dir = workbench / ".audit"
        audit_dir.mkdir()

        _make_plan_file(workbench, "PLAN-AA4_dungeon-architect-skill")

        shared_finding = {
            "code": "S001",
            "level": "error",
            "category": "assumptions",
            "location": "Step 1",
            "message": "Missing prerequisite.",
            "fingerprint": "aabbccdd",
        }

        # One sufficiency iteration, one plan_safety iteration — same fingerprint
        _make_audit_with_findings(
            audit_dir, "PLAN-AA4-sufficiency-1.json", [shared_finding]
        )
        _make_audit_with_findings(
            audit_dir, "PLAN-AA4-plan_safety-1.json", [shared_finding]
        )

        plans = []
        for md in sorted(workbench.iterdir()):
            if md.suffix == ".md" and build_index.PLAN_PATTERN.match(md.name):
                p = build_index.load_plan(md)
                if p:
                    plans.append(p)

        alerts = compute_alerts(plans, workbench)
        recurring = alerts.get("recurring_blockers", [])

        if recurring:
            fail(
                "test_recurring_blockers_cross_stage_no_alert",
                f"Expected no recurring_blockers for cross-stage pair but got {len(recurring)}: "
                + ", ".join(r["detail"] for r in recurring),
            )

    print("PASS: test_recurring_blockers_cross_stage_no_alert")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    tests = [
        test_audit_file_plan_id,
        test_canonical_plan_id,
        test_orphaned_audit_no_false_positives,
        test_orphaned_audit_flags_missing_plan,
        test_non_audit_files_excluded,
        test_recurring_blockers_same_stage_triggers_alert,
        test_recurring_blockers_cross_stage_no_alert,
    ]

    print(f"Running {len(tests)} tests...\n")
    failures = 0
    for test in tests:
        try:
            test()
        except SystemExit as e:
            failures += 1
            if e.code != 0:
                # sys.exit(1) was called inside fail() — already printed
                pass

    if failures > 0:
        print(f"\n{failures}/{len(tests)} tests FAILED.")
        sys.exit(1)

    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
