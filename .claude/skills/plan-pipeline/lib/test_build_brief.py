"""
test_build_brief.py — Unit tests for build_brief.py.

Tests both first-iteration and re-audit code paths using in-memory fixtures.
Run: python test_build_brief.py
Exit 0 on success, non-zero on failure.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Ensure the lib directory is on the path so we can import build_brief
sys.path.insert(0, str(Path(__file__).parent))

from build_brief import build_audit_brief, OrchestratorException


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_PLAN_FRONTMATTER = """\
---
schema_version: 2
title: "Smoke Test PLAN v2"
type: plan
status: ready
assigned_to: sonnet
priority: medium
created: 2026-05-12
created_by: opus
created_month: 202605
log_month: 202605
due: ""
repeatable: false
repeat_cadence: ""
linked_decisions: []
linked_inputs: []
blocked_by: ""
rollover_count: 0
triggers_plans: []
closes_thread: ""
advances_thread: ""
parent_plan_of_plans: ""
pipeline_phase: drafted
tags: []
files_touched: []
audit_acknowledgements: []
audit_disputes: []
audit_overrides: []
audit_extracted: null
pipeline_overrides: []
halt_log: []
audit_state:
  sufficiency_iterations: 0
  plan_safety_iterations: 0
  last_stage: none
  last_outcome: none
  last_audit_commit: ""
  preferred_model_override: ""
verification_state:
  state_pass: 0
  state_fail: 0
  acceptance_pass: 0
  acceptance_fail: 0
  human_pending: []
  human_verdict: pending
  human_diagnostics: ""
  human_acknowledged_failures: []
  failure_logs: {}
  human_passed: false
---

## Objective
A trivial test PLAN for smoke-testing build_brief.py. No real work intended.

## Context
Created by test_build_brief.py as a fixture. Not committed to the repository.

## Design Decisions Classification
n/a — ad-hoc PLAN, not produced via ideate.

## Steps

1. Do nothing (step one placeholder).
2. Do nothing (step two placeholder).

## Verification
- [ ] Placeholder verify.
      `verify: test -f /tmp/smoke_placeholder`
- [ ] Placeholder acceptance.
      `acceptance: echo "ok"`

## Executor Notes
*Populated after execution.*

**Executed:**
**Outcome:**
**What was done:**
**Blockers (if any):**
**Files modified:**
"""

FAKE_PRIOR_AUDIT = {
    "schema_version": 2,
    "auditor": "sufficiency",
    "plan_id": "202605121800_PLAN_smoke-test-v2",
    "iteration": 1,
    "findings": [
        {
            "code": "S001",
            "level": "error",
            "category": "assumptions",
            "location": "Step 1",
            "message": "Step 1 assumes /tmp/smoke_placeholder exists but no step creates it.",
            "suggested_fix": "Add a step that creates /tmp/smoke_placeholder before Step 1.",
            "fingerprint": "a1b2c3d4",
        },
        {
            "code": "S201",
            "level": "warning",
            "category": "test-fidelity",
            "location": "Verification",
            "message": "The acceptance check is trivial (echo ok) and does not test any deliverable.",
            "suggested_fix": "Replace with a check that exercises the actual deliverable.",
            "fingerprint": "e5f6a7b8",
        },
    ],
    "summary": {
        "error_count": 1,
        "warning_count": 1,
        "note_count": 0,
    },
}


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def assert_in(needle: str, haystack: str, label: str):
    if needle not in haystack:
        print(f"FAIL [{label}]: expected to find:\n  {needle!r}\nin output:\n  {haystack[:500]!r}")
        sys.exit(1)


def assert_not_in(needle: str, haystack: str, label: str):
    if needle in haystack:
        print(f"FAIL [{label}]: expected NOT to find:\n  {needle!r}\nin output")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_first_iteration_brief():
    """First-iteration brief contains Mode: first iteration and the PLAN title."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_path = Path(tmpdir) / "202605121800_PLAN_smoke-test-v2.md"
        plan_path.write_text(MINIMAL_PLAN_FRONTMATTER, encoding="utf-8")

        brief = build_audit_brief(plan_path, "sufficiency", 1)

    assert_in("**Mode:** first iteration", brief, "first-iter mode label")
    assert_in("Smoke Test PLAN v2", brief, "first-iter plan title")
    assert_in("A trivial test PLAN", brief, "first-iter plan objective")
    assert_in("Sufficiency Auditor", brief, "first-iter auditor label")
    assert_in("**Iteration:** 1 of 5", brief, "first-iter iteration number")
    print("PASS: test_first_iteration_brief")


def test_reaudit_brief_contains_prior_findings():
    """Re-audit brief contains Mode: re-audit, the prior findings table header, and a diff block."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_path = Path(tmpdir) / "202605121800_PLAN_smoke-test-v2.md"
        plan_path.write_text(MINIMAL_PLAN_FRONTMATTER, encoding="utf-8")

        # Write the fake audit JSON
        audit_dir = Path(tmpdir) / ".audit"
        audit_dir.mkdir()
        audit_file = audit_dir / "202605121800_PLAN_smoke-test-v2-1.json"
        audit_file.write_text(json.dumps(FAKE_PRIOR_AUDIT, indent=2), encoding="utf-8")

        # Mock git diff so we don't need an actual git repo
        fake_diff = (
            "--- a/Workbench/202605121800_PLAN_smoke-test-v2.md\n"
            "+++ b/Workbench/202605121800_PLAN_smoke-test-v2.md\n"
            "@@ -1,2 +1,3 @@\n"
            "-Do nothing (step one placeholder).\n"
            "+Do nothing revised (step one placeholder).\n"
            "+Added a new line.\n"
        )

        audit_state = {
            "sufficiency_iterations": 1,
            "plan_safety_iterations": 0,
            "last_stage": "sufficiency",
            "last_outcome": "revision_needed",
            "last_audit_commit": "abc1234f",
            "preferred_model_override": "",
        }

        with patch("build_brief._get_git_diff", return_value=fake_diff):
            brief = build_audit_brief(plan_path, "sufficiency", 2, audit_state=audit_state)

    assert_in("**Mode:** re-audit", brief, "reaudit mode label")
    assert_in("Prior Findings", brief, "reaudit prior findings section")
    assert_in("Fingerprint", brief, "reaudit table header")
    assert_in("a1b2c3d4", brief, "reaudit fingerprint in table")
    assert_in("```diff", brief, "reaudit diff block")
    assert_in("Do nothing revised", brief, "reaudit diff content")
    assert_in("**Iteration:** 2 of 5", brief, "reaudit iteration number")
    print("PASS: test_reaudit_brief_contains_prior_findings")


def test_reaudit_excludes_acknowledged_findings():
    """Acknowledged fingerprints are excluded from the prior findings table."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_path = Path(tmpdir) / "202605121800_PLAN_smoke-test-v2.md"
        plan_path.write_text(MINIMAL_PLAN_FRONTMATTER, encoding="utf-8")

        audit_dir = Path(tmpdir) / ".audit"
        audit_dir.mkdir()
        audit_file = audit_dir / "202605121800_PLAN_smoke-test-v2-1.json"
        audit_file.write_text(json.dumps(FAKE_PRIOR_AUDIT, indent=2), encoding="utf-8")

        fake_diff = "--- a/plan.md\n+++ b/plan.md\n@@ -1 +1 @@\n-old\n+new\n"

        audit_state = {
            "sufficiency_iterations": 1,
            "plan_safety_iterations": 0,
            "last_stage": "sufficiency",
            "last_outcome": "revision_needed",
            "last_audit_commit": "abc1234f",
            "preferred_model_override": "",
            # Acknowledge the first finding (S001)
            "_acknowledged_fingerprints": ["a1b2c3d4"],
        }

        with patch("build_brief._get_git_diff", return_value=fake_diff):
            brief = build_audit_brief(plan_path, "sufficiency", 2, audit_state=audit_state)

    # a1b2c3d4 (S001) acknowledged — the table should NOT have this fp as a table row
    # (it WILL appear in the Acknowledged Findings section listing, which is expected)
    # Check that the table row form doesn't appear: table rows have '| `<fp>` |' format
    assert_not_in("| `a1b2c3d4` |", brief, "acknowledged fp excluded from table row")
    # e5f6a7b8 (S201, not acknowledged) — should still appear as a table row
    assert_in("e5f6a7b8", brief, "non-acknowledged fp still in table")
    # Acknowledged section should appear
    assert_in("Acknowledged Findings", brief, "acknowledged section header")
    # The acknowledged fp should appear in the Acknowledged Findings list (not excluded from there)
    assert_in("a1b2c3d4", brief, "acknowledged fp listed in acknowledgements section")
    print("PASS: test_reaudit_excludes_acknowledged_findings")


def test_raises_on_missing_prior_audit():
    """OrchestratorException raised when prior audit file is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_path = Path(tmpdir) / "202605121800_PLAN_smoke-test-v2.md"
        plan_path.write_text(MINIMAL_PLAN_FRONTMATTER, encoding="utf-8")

        audit_state = {
            "last_audit_commit": "abc1234f",
        }

        try:
            build_audit_brief(plan_path, "sufficiency", 2, audit_state=audit_state)
            print("FAIL: test_raises_on_missing_prior_audit — expected OrchestratorException")
            sys.exit(1)
        except OrchestratorException:
            pass  # expected

    print("PASS: test_raises_on_missing_prior_audit")


def test_raises_on_empty_commit_sha():
    """OrchestratorException raised when last_audit_commit is empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_path = Path(tmpdir) / "202605121800_PLAN_smoke-test-v2.md"
        plan_path.write_text(MINIMAL_PLAN_FRONTMATTER, encoding="utf-8")

        audit_dir = Path(tmpdir) / ".audit"
        audit_dir.mkdir()
        audit_file = audit_dir / "202605121800_PLAN_smoke-test-v2-1.json"
        audit_file.write_text(json.dumps(FAKE_PRIOR_AUDIT, indent=2), encoding="utf-8")

        audit_state = {
            "last_audit_commit": "",  # empty — should raise
        }

        try:
            build_audit_brief(plan_path, "sufficiency", 2, audit_state=audit_state)
            print("FAIL: test_raises_on_empty_commit_sha — expected OrchestratorException")
            sys.exit(1)
        except OrchestratorException as e:
            if "last_audit_commit" not in str(e):
                print(f"FAIL: test_raises_on_empty_commit_sha — wrong error message: {e}")
                sys.exit(1)

    print("PASS: test_raises_on_empty_commit_sha")


def test_plan_safety_auditor_label():
    """plan_safety auditor produces correct labels."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_path = Path(tmpdir) / "202605121800_PLAN_smoke-test-v2.md"
        plan_path.write_text(MINIMAL_PLAN_FRONTMATTER, encoding="utf-8")

        brief = build_audit_brief(plan_path, "plan_safety", 1)

    assert_in("Plan-Safety Auditor", brief, "plan_safety auditor label")
    assert_in("H001", brief, "plan_safety H-code namespace reference")
    print("PASS: test_plan_safety_auditor_label")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    tests = [
        test_first_iteration_brief,
        test_reaudit_brief_contains_prior_findings,
        test_reaudit_excludes_acknowledged_findings,
        test_raises_on_missing_prior_audit,
        test_raises_on_empty_commit_sha,
        test_plan_safety_auditor_label,
    ]

    print(f"Running {len(tests)} tests...\n")
    for test in tests:
        test()

    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
