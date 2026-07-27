"""
test_build_index.py - Regression tests for build_index.py.

Covers:
  - _audit_file_plan_id: all current/legacy/non-audit filename shapes
  - compute_alerts orphaned_audit_files: ADVICE-003 regression assertion
    (stage-suffixed + short-id audit files must NOT be flagged for present PLANs)
  - recurring_blockers: same-stage fingerprint recurrence triggers alert;
    cross-stage same fingerprint does NOT.
  - orphaned_input: empty or dangling feeds_plan/advises_plan fires alert;
    input feeding a retired PLAN does not.
  - dangling_linked_input: PLAN with linked_inputs referencing an absent file
    fires alert.
  - reference_review_due: reference-mode input with past review_by fires alert;
    future or absent review_by does not.
  - malformed input file does not abort the build.
  - plan_of_plans_linkage_mismatch: child-does-not-back-reference,
    parent-does-not-trigger, triggered-child-missing, and correctly-linked
    negative case; exercises both bare-id and parent_plan_of_plans forms.

Self-contained: builds a temp Workbench with synthetic PLAN and input files;
does NOT read the real repo Workbench/ or .audit/.

Run: python -m pytest .claude/skills/update-workbench-index/lib/test_build_index.py -q
  or: python3 test_build_index.py
Exit 0 on success, non-zero on failure.
"""

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

# Resolve the sibling scripts/ directory so we can import build_index.
# This test lives in lib/; build_index lives in scripts/.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import build_index
from build_index import (
    _audit_file_plan_id,
    _bare_plan_id,
    _canonical_plan_id,
    compute_alerts,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fail(label: str, detail: str) -> None:
    """Raise AssertionError so both pytest and the custom runner see the failure."""
    raise AssertionError(f"[{label}]: {detail}")


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
parent: ''
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


def _make_plan_frontmatter(
    plan_id_short: str = "PLAN-AA4",
    triggers_plans: list | None = None,
    parent_plan_of_plans: str = "",
    parent: str = "",
    linked_inputs: list | None = None,
) -> str:
    """
    Return a minimal PLAN frontmatter with customised fields.
    triggers_plans and linked_inputs are rendered as YAML inline lists.
    """
    triggers_str = (
        "[" + ", ".join(triggers_plans) + "]"
        if triggers_plans else "[]"
    )
    linked_str = (
        "[" + ", ".join(f'"{x}"' for x in linked_inputs) + "]"
        if linked_inputs else "[]"
    )
    return f"""\
---
schema_version: 2
title: "Test PLAN {plan_id_short}"
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
linked_inputs: {linked_str}
blocked_by: ''
rollover_count: 0
triggers_plans: {triggers_str}
closes_thread: ''
advances_thread: ''
parent_plan_of_plans: '{parent_plan_of_plans}'
parent: '{parent}'
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
# Helpers: fixture writers
# ---------------------------------------------------------------------------

def _make_plan_file(workbench: Path, plan_stem: str, content: str | None = None) -> Path:
    """Write a minimal PLAN file and return its path."""
    plan_path = workbench / f"{plan_stem}.md"
    plan_path.write_text(content or PLAN_FRONTMATTER, encoding="utf-8")
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


def _make_input_file(
    workbench: Path,
    filename: str,
    input_type: str = "advice",
    feeds_plan: str = "",
    advises_plan: str = "",
    lifecycle_mode: str = "input",
    review_by: str = "",
) -> Path:
    """Write a minimal RESEARCH or ADVICE input file."""
    feeds_line = f'feeds_plan: "{feeds_plan}"' if input_type == "research" else f'advises_plan: "{advises_plan}"'
    review_line = f'review_by: "{review_by}"' if review_by else 'review_by: ""'
    content = f"""\
---
title: "Test Input"
type: {input_type}
created: 2026-06-15
{feeds_line}
from: "test"
question_asked: "test"
integration_status: pending
lifecycle_mode: {lifecycle_mode}
{review_line}
---

## Findings
Test input content.
"""
    path = workbench / filename
    path.write_text(content, encoding="utf-8")
    return path


def _load_plans(workbench: Path) -> list:
    """Load all PLAN files from a workbench directory."""
    plans = []
    for md in sorted(workbench.iterdir()):
        if md.suffix == ".md" and build_index.PLAN_PATTERN.match(md.name):
            p = build_index.load_plan(md)
            if p:
                plans.append(p)
    return plans


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
        # AA-form PLAN with legacy full-stem filename - short-id is still extracted
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
        # Legacy numeric-form PLAN - no _ after PLAN-NNN form, returned unchanged
        ("PLAN-123_some-plan",                 "PLAN-123_some-plan"),
        # Legacy timestamp-prefix stem - returned unchanged
        ("202605121800_PLAN_smoke-test",       "202605121800_PLAN_smoke-test"),
    ]
    for stem, expected in cases:
        result = _canonical_plan_id(stem)
        assert_eq(f"_canonical_plan_id({stem!r})", expected, result)

    print("PASS: test_canonical_plan_id")


# ---------------------------------------------------------------------------
# Test: compute_alerts - orphaned_audit_files (ADVICE-003 regression)
# ---------------------------------------------------------------------------

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

        plans = _load_plans(workbench)
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

        # No PLAN file - only audit files
        _make_audit_file(audit_dir, "PLAN-AA4-sufficiency-1.json")
        _make_audit_file(audit_dir, "PLAN-AA4-plan_safety-1.json", stage="plan_safety")
        _make_audit_file(audit_dir, "PLAN-AA4-1.json")

        plans = []  # empty - PLAN not present
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
# Test: recurring_blockers - stage-aware (D3 Per-Stage-Recurrence)
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
    Two consecutive sufficiency iterations sharing an error fingerprint -> one alert.
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

        plans = _load_plans(workbench)
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

        # One sufficiency iteration, one plan_safety iteration - same fingerprint
        _make_audit_with_findings(
            audit_dir, "PLAN-AA4-sufficiency-1.json", [shared_finding]
        )
        _make_audit_with_findings(
            audit_dir, "PLAN-AA4-plan_safety-1.json", [shared_finding]
        )

        plans = _load_plans(workbench)
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
# Tests: orphaned_input (Step 3)
# ---------------------------------------------------------------------------

def test_orphaned_input_empty_feeds_plan(tmp_path):
    """(a) An input with empty feeds_plan produces an orphaned_input alert."""
    workbench = tmp_path / "Workbench"
    workbench.mkdir()

    _make_input_file(workbench, "ADVICE-001_empty-feeds.md",
                     input_type="advice", advises_plan="")

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    orphaned = alerts.get("orphaned_input", [])

    assert len(orphaned) == 1, f"Expected 1 orphaned_input alert, got {len(orphaned)}"
    assert "ADVICE-001_empty-feeds.md" in orphaned[0]["plan_id"]
    assert "empty" in orphaned[0]["detail"]


def test_orphaned_input_dangling_feeds_plan(tmp_path):
    """(b) An input whose feeds_plan names an absent PLAN produces orphaned_input."""
    workbench = tmp_path / "Workbench"
    workbench.mkdir()

    _make_input_file(workbench, "RESEARCH-001_dangling.md",
                     input_type="research",
                     feeds_plan="PLAN-ZZ9_nonexistent-plan.md")

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    orphaned = alerts.get("orphaned_input", [])

    assert len(orphaned) == 1, f"Expected 1 orphaned_input alert, got {len(orphaned)}"
    assert "PLAN-ZZ9" in orphaned[0]["detail"] or "nonexistent" in orphaned[0]["detail"]


def test_orphaned_input_retired_plan_no_alert(tmp_path):
    """(c) An input whose feeds_plan names a PLAN in Retired/ does NOT produce orphaned_input."""
    workbench = tmp_path / "Workbench"
    workbench.mkdir()
    retired_dir = tmp_path / "Retired"
    retired_dir.mkdir()

    # Write the consuming PLAN in Retired/
    retired_plan = retired_dir / "PLAN-ZZ9_retired-plan.md"
    retired_plan.write_text(PLAN_FRONTMATTER, encoding="utf-8")

    _make_input_file(workbench, "ADVICE-002_retired-consumer.md",
                     input_type="advice",
                     advises_plan="PLAN-ZZ9_retired-plan.md")

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    orphaned = alerts.get("orphaned_input", [])

    assert len(orphaned) == 0, (
        f"Expected 0 orphaned_input alerts (PLAN is in Retired/), got {len(orphaned)}: "
        + str(orphaned)
    )


def test_dangling_linked_input(tmp_path):
    """(d) A PLAN with a linked_inputs entry that exists in neither Workbench/ nor Retired/ produces dangling_linked_input."""
    workbench = tmp_path / "Workbench"
    workbench.mkdir()

    content = _make_plan_frontmatter(
        plan_id_short="PLAN-AA5",
        linked_inputs=["nonexistent-research-file.md"],
    )
    _make_plan_file(workbench, "PLAN-AA5_test-dangling", content=content)

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    dangling = alerts.get("dangling_linked_input", [])

    assert len(dangling) == 1, f"Expected 1 dangling_linked_input alert, got {len(dangling)}"
    assert "nonexistent-research-file.md" in dangling[0]["detail"]


def test_reference_review_due_past_date(tmp_path):
    """(e1) A lifecycle_mode: reference input with a past review_by produces reference_review_due."""
    workbench = tmp_path / "Workbench"
    workbench.mkdir()

    past_date = (date.today() - timedelta(days=1)).isoformat()
    _make_input_file(workbench, "ADVICE-003_ref-past.md",
                     input_type="advice",
                     lifecycle_mode="reference",
                     review_by=past_date)

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    review_due = alerts.get("reference_review_due", [])

    assert len(review_due) == 1, f"Expected 1 reference_review_due alert, got {len(review_due)}"
    assert past_date in review_due[0]["detail"]


def test_reference_review_due_future_date_no_alert(tmp_path):
    """(e2) A lifecycle_mode: reference input with a future review_by does NOT produce reference_review_due."""
    workbench = tmp_path / "Workbench"
    workbench.mkdir()

    future_date = (date.today() + timedelta(days=30)).isoformat()
    _make_input_file(workbench, "ADVICE-004_ref-future.md",
                     input_type="advice",
                     lifecycle_mode="reference",
                     review_by=future_date)

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    review_due = alerts.get("reference_review_due", [])

    assert len(review_due) == 0, (
        f"Expected 0 reference_review_due alerts (future date), got {len(review_due)}"
    )


def test_reference_review_due_no_review_by_no_alert(tmp_path):
    """(e3) A lifecycle_mode: reference input with no review_by does NOT produce reference_review_due."""
    workbench = tmp_path / "Workbench"
    workbench.mkdir()

    _make_input_file(workbench, "ADVICE-005_ref-no-date.md",
                     input_type="advice",
                     lifecycle_mode="reference",
                     review_by="")

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    review_due = alerts.get("reference_review_due", [])

    assert len(review_due) == 0, (
        f"Expected 0 reference_review_due alerts (no review_by), got {len(review_due)}"
    )


def test_malformed_input_does_not_abort_build(tmp_path):
    """(f) A malformed input file does not abort the build; other alerts still compute."""
    workbench = tmp_path / "Workbench"
    workbench.mkdir()

    # Write a malformed input file: valid UTF-8 but entirely missing frontmatter
    # delimiters - the frontmatter parser returns {} so it is skipped gracefully.
    malformed = workbench / "ADVICE-006_malformed.md"
    malformed.write_text("THIS IS NOT YAML FRONTMATTER\nJust raw text.", encoding="utf-8")

    # Also write a valid PLAN that has a dangling linked_input so we can
    # verify alerts still compute after the malformed file.
    content = _make_plan_frontmatter(
        plan_id_short="PLAN-AA6",
        linked_inputs=["missing-input.md"],
    )
    _make_plan_file(workbench, "PLAN-AA6_has-dangling", content=content)

    plans = _load_plans(workbench)
    # Should not raise - malformed input is skipped
    alerts = compute_alerts(plans, workbench)

    # The dangling_linked_input for PLAN-AA6 should still fire
    dangling = alerts.get("dangling_linked_input", [])
    assert len(dangling) == 1, (
        f"Expected dangling_linked_input alert still present after malformed input; got {len(dangling)}"
    )


# ---------------------------------------------------------------------------
# Tests: plan_of_plans_linkage_mismatch (Step 3b)
# ---------------------------------------------------------------------------

def test_pop_mismatch_child_not_in_parent_triggers(tmp_path):
    """
    (a) Child PLAN whose parent_plan_of_plans names a parent whose triggers_plans
    OMITS that child produces a plan_of_plans_linkage_mismatch alert.
    """
    workbench = tmp_path / "Workbench"
    workbench.mkdir()

    # Parent: triggers_plans is empty (omits the child)
    parent_content = _make_plan_frontmatter(
        plan_id_short="PLAN-AB0",
        triggers_plans=[],  # deliberately omits PLAN-AB1
    )
    _make_plan_file(workbench, "PLAN-AB0_parent", content=parent_content)

    # Child: parent_plan_of_plans = PLAN-AB0 (uses parent_plan_of_plans form)
    child_content = _make_plan_frontmatter(
        plan_id_short="PLAN-AB1",
        parent_plan_of_plans="PLAN-AB0",
    )
    _make_plan_file(workbench, "PLAN-AB1_child", content=child_content)

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    mismatches = alerts.get("plan_of_plans_linkage_mismatch", [])

    assert len(mismatches) >= 1, (
        f"Expected >= 1 plan_of_plans_linkage_mismatch alert, got {len(mismatches)}"
    )
    detail_texts = " ".join(m["detail"] for m in mismatches)
    assert "AB0" in detail_texts and "AB1" in detail_texts, (
        f"Expected both PLAN-AB0 and PLAN-AB1 mentioned in detail; got: {detail_texts}"
    )


def test_pop_mismatch_parent_triggers_child_no_backref(tmp_path):
    """
    (b) A parent PLAN listing a triggers_plans child id that does NOT back-reference
    it produces the alert. Exercises the bare parent: form.
    """
    workbench = tmp_path / "Workbench"
    workbench.mkdir()

    # Parent: triggers PLAN-AB3
    parent_content = _make_plan_frontmatter(
        plan_id_short="PLAN-AB2",
        triggers_plans=["PLAN-AB3"],
    )
    _make_plan_file(workbench, "PLAN-AB2_parent", content=parent_content)

    # Child: has a different parent (or none) - does not back-reference PLAN-AB2
    child_content = _make_plan_frontmatter(
        plan_id_short="PLAN-AB3",
        parent="",          # bare parent field - empty, so no back-reference
        parent_plan_of_plans="",
    )
    _make_plan_file(workbench, "PLAN-AB3_child", content=child_content)

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    mismatches = alerts.get("plan_of_plans_linkage_mismatch", [])

    assert len(mismatches) >= 1, (
        f"Expected >= 1 plan_of_plans_linkage_mismatch alert, got {len(mismatches)}"
    )
    detail_texts = " ".join(m["detail"] for m in mismatches)
    assert "AB2" in detail_texts and "AB3" in detail_texts, (
        f"Expected both PLAN-AB2 and PLAN-AB3 mentioned; got: {detail_texts}"
    )


def test_pop_mismatch_triggered_child_absent(tmp_path):
    """
    (S201 gap fix) A parent's triggers_plans names a bare id absent from both
    Workbench/ and Retired/ produces a plan_of_plans_linkage_mismatch alert
    with the triggered-child-missing direction.
    """
    workbench = tmp_path / "Workbench"
    workbench.mkdir()
    # No Retired/ directory - child is truly absent

    # Parent: triggers a nonexistent child
    parent_content = _make_plan_frontmatter(
        plan_id_short="PLAN-AB4",
        triggers_plans=["PLAN-ZZ9"],  # PLAN-ZZ9 does not exist anywhere
    )
    _make_plan_file(workbench, "PLAN-AB4_parent", content=parent_content)

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    mismatches = alerts.get("plan_of_plans_linkage_mismatch", [])

    assert len(mismatches) >= 1, (
        f"Expected >= 1 plan_of_plans_linkage_mismatch (triggered-child-missing), got {len(mismatches)}"
    )
    detail_texts = " ".join(m["detail"] for m in mismatches)
    assert "absent" in detail_texts or "ZZ9" in detail_texts, (
        f"Expected 'absent' or 'ZZ9' in detail; got: {detail_texts}"
    )


def test_pop_mismatch_correctly_linked_no_alert(tmp_path):
    """
    (c) A correctly cross-linked parent/child pair produces NO plan_of_plans_linkage_mismatch alert.
    Exercises BOTH the bare-id parent form and the parent_plan_of_plans form.
    """
    workbench = tmp_path / "Workbench"
    workbench.mkdir()

    # Parent A (plan_of_plans parent) triggers both children
    parent_content = _make_plan_frontmatter(
        plan_id_short="PLAN-AC0",
        triggers_plans=["PLAN-AC1", "PLAN-AC2"],
    )
    _make_plan_file(workbench, "PLAN-AC0_parent", content=parent_content)

    # Child 1: uses parent_plan_of_plans form
    child1_content = _make_plan_frontmatter(
        plan_id_short="PLAN-AC1",
        parent_plan_of_plans="PLAN-AC0",
    )
    _make_plan_file(workbench, "PLAN-AC1_child1", content=child1_content)

    # Child 2: uses bare parent: form
    child2_content = _make_plan_frontmatter(
        plan_id_short="PLAN-AC2",
        parent="PLAN-AC0",
    )
    _make_plan_file(workbench, "PLAN-AC2_child2", content=child2_content)

    plans = _load_plans(workbench)
    alerts = compute_alerts(plans, workbench)
    mismatches = alerts.get("plan_of_plans_linkage_mismatch", [])

    assert len(mismatches) == 0, (
        f"Expected 0 mismatches for correctly-linked parent/children, got {len(mismatches)}: "
        + str(mismatches)
    )


# ---------------------------------------------------------------------------
# Main (custom runner for backward compatibility)
# ---------------------------------------------------------------------------

def main():
    """Custom runner - works without pytest installed."""
    tests = [
        test_audit_file_plan_id,
        test_canonical_plan_id,
        test_orphaned_audit_no_false_positives,
        test_orphaned_audit_flags_missing_plan,
        test_non_audit_files_excluded,
        test_recurring_blockers_same_stage_triggers_alert,
        test_recurring_blockers_cross_stage_no_alert,
    ]

    print(f"Running {len(tests)} tests (custom runner; use pytest for full suite)...\n")
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"FAIL: {e}")
            failures += 1

    if failures > 0:
        print(f"\n{failures}/{len(tests)} tests FAILED.")
        sys.exit(1)

    print(f"\nAll {len(tests)} tests passed.")
    print("Note: pytest-style tests (test_orphaned_input_*, test_pop_mismatch_*)")
    print("require 'python -m pytest' to run (they use the tmp_path fixture).")


if __name__ == "__main__":
    main()
