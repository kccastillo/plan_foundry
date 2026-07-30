"""
test_build_brief.py - Unit tests for build_brief.py.

Tests both first-iteration and re-audit code paths using in-memory fixtures.
Also tests the PLAN-AE0 precondition fingerprint check (cases a-f).
Run: python test_build_brief.py
Exit 0 on success, non-zero on failure.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure the lib directory is on the path so we can import build_brief
sys.path.insert(0, str(Path(__file__).parent))

from audit_loop import _compute_fingerprint
from build_brief import build_audit_brief, OrchestratorException, _check_audit_loop_precondition, _finding_fingerprint


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
n/a - ad-hoc PLAN, not produced via ideate.

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
        audit_file = audit_dir / "202605121800_PLAN_smoke-test-v2-sufficiency-1.json"
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
        audit_file = audit_dir / "202605121800_PLAN_smoke-test-v2-sufficiency-1.json"
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

    # a1b2c3d4 (S001) acknowledged - the table should NOT have this fp as a table row
    # (it WILL appear in the Acknowledged Findings section listing, which is expected)
    # Check that the table row form doesn't appear: table rows have '| `<fp>` |' format
    assert_not_in("| `a1b2c3d4` |", brief, "acknowledged fp excluded from table row")
    # e5f6a7b8 (S201, not acknowledged) - should still appear as a table row
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
            print("FAIL: test_raises_on_missing_prior_audit - expected OrchestratorException")
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
        audit_file = audit_dir / "202605121800_PLAN_smoke-test-v2-sufficiency-1.json"
        audit_file.write_text(json.dumps(FAKE_PRIOR_AUDIT, indent=2), encoding="utf-8")

        audit_state = {
            "last_audit_commit": "",  # empty - should raise
        }

        try:
            build_audit_brief(plan_path, "sufficiency", 2, audit_state=audit_state)
            print("FAIL: test_raises_on_empty_commit_sha - expected OrchestratorException")
            sys.exit(1)
        except OrchestratorException as e:
            if "last_audit_commit" not in str(e):
                print(f"FAIL: test_raises_on_empty_commit_sha - wrong error message: {e}")
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


def test_plan_safety_brief_admits_auxiliary_families_sufficiency_does_not():
    """PLAN-AG2: the plan-safety brief must admit the SFV/PPV/PSZ/FAL auxiliary
    code families (emitted by audit-haiku-safe Steps 4a-4d and admitted by the
    widened auditor-schema-v2 findings[].code pattern), while the sufficiency
    brief must NOT - those families are plan-safety-only."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_path = Path(tmpdir) / "202605121800_PLAN_smoke-test-v2.md"
        plan_path.write_text(MINIMAL_PLAN_FRONTMATTER, encoding="utf-8")

        plan_safety_brief = build_audit_brief(plan_path, "plan_safety", 1)
        sufficiency_brief = build_audit_brief(plan_path, "sufficiency", 1)

    assert_in("SFV", plan_safety_brief, "plan-safety brief admits auxiliary family token SFV")
    assert_not_in("SFV", sufficiency_brief, "sufficiency brief does not admit auxiliary family token SFV")
    print("PASS: test_plan_safety_brief_admits_auxiliary_families_sufficiency_does_not")


def test_reaudit_brief_lists_prior_findings_diagnostics_shape():
    """
    Bug 1 regression (PLAN-AG6 / RESEARCH-006): build_brief must read prior findings
    from the production envelope shape (diagnostics.findings), not top-level findings.

    Uses the exact shape that audit_loop.py writes to disk: the raw auditor
    <pipeline-result> JSON, with findings under diagnostics.findings and NO pre-baked
    fingerprint keys. Verifies that after the fix the brief shows the correct count
    (not '0 total'), renders both finding codes, and computes fingerprints in lockstep
    with audit_loop._compute_fingerprint.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_path = Path(tmpdir) / "202605121800_PLAN_smoke-test-v2.md"
        plan_path.write_text(MINIMAL_PLAN_FRONTMATTER, encoding="utf-8")

        # Production envelope shape - findings under diagnostics.findings,
        # NO pre-baked fingerprint keys (matching what audit_loop writes).
        production_shape_audit = {
            "outcome": "revision_needed",
            "payload": {"review_text": "Two findings raised."},
            "diagnostics": {
                "findings": [
                    {
                        "code": "S403",
                        "level": "error",
                        "category": "safety",
                        "location": "Step 3",
                        "message": "Step 3 runs a destructive operation without approval gate.",
                    },
                    {
                        "code": "S204",
                        "level": "warning",
                        "category": "concreteness",
                        "location": "Verification",
                        "message": "Acceptance check does not specify the expected output.",
                    },
                ]
            },
        }

        audit_dir = Path(tmpdir) / ".audit"
        audit_dir.mkdir()
        audit_file = audit_dir / "202605121800_PLAN_smoke-test-v2-sufficiency-1.json"
        audit_file.write_text(json.dumps(production_shape_audit, indent=2), encoding="utf-8")

        fake_diff = (
            "--- a/Workbench/202605121800_PLAN_smoke-test-v2.md\n"
            "+++ b/Workbench/202605121800_PLAN_smoke-test-v2.md\n"
            "@@ -1,2 +1,3 @@\n"
            "-Do nothing (step one placeholder).\n"
            "+Do nothing revised (step one placeholder).\n"
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

    # Bug 1 fix: header must show 2 findings, NOT 0
    assert_in("Prior Findings (2 total", brief, "diagnostics-shape: 2 findings total (not 0)")
    # Must NOT emit the empty-findings fallback text
    assert_not_in("_No findings in prior iteration._", brief, "diagnostics-shape: no empty-findings fallback")
    # Both finding codes must appear in the rendered table
    assert_in("S403", brief, "diagnostics-shape: S403 finding code in table")
    assert_in("S204", brief, "diagnostics-shape: S204 finding code in table")

    # Fingerprint lockstep assertion: _finding_fingerprint must agree with audit_loop._compute_fingerprint
    sample_s403 = production_shape_audit["diagnostics"]["findings"][0]
    expected_fp = _compute_fingerprint(sample_s403)
    actual_fp = _finding_fingerprint(sample_s403)
    if expected_fp != actual_fp:
        print(
            f"FAIL [diagnostics-shape: fingerprint lockstep]: "
            f"_finding_fingerprint({sample_s403!r}) = {actual_fp!r} "
            f"but _compute_fingerprint = {expected_fp!r}"
        )
        sys.exit(1)
    # The computed fingerprint must appear in the brief (Fingerprint column rendered)
    assert_in(expected_fp, brief, "diagnostics-shape: computed fingerprint in brief")

    print("PASS: test_reaudit_brief_lists_prior_findings_diagnostics_shape")


# ---------------------------------------------------------------------------
# Precondition check tests (PLAN-AE0, cases a-f)
# These require a real git repo - use pytest tmp_path fixture.
# ---------------------------------------------------------------------------

# Frontmatter template for precondition tests - note plan-ID-friendly filename
PRECONDITION_PLAN_FM = """\
---
schema_version: 2
title: "Precondition Test PLAN"
type: plan
status: ready
assigned_to: sonnet
priority: medium
created: 2026-05-26
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
  sufficiency_iterations: {suf_iter}
  plan_safety_iterations: {ps_iter}
  last_stage: {last_stage}
  last_outcome: {last_outcome}
  last_audit_commit: "{last_commit}"
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
  failure_logs: {{}}
  human_passed: false
---

## Objective
Precondition test fixture.

## Steps
1. Nothing.

## Verification
- [ ] No-op.
"""

PLAN_ID_PC = "PLAN-AE1"
PLAN_FILENAME_PC = "PLAN-AE1_precondition-test.md"


def _make_precondition_repo(tmp_path: Path, last_stage: str, last_outcome: str,
                             suf_iter: int = 1, ps_iter: int = 0,
                             last_commit: str = "") -> tuple[Path, Path]:
    """Create a minimal git repo for precondition tests."""
    repo_root = tmp_path
    workbench = repo_root / "Workbench"
    workbench.mkdir(parents=True, exist_ok=True)

    fm = PRECONDITION_PLAN_FM.format(
        last_stage=last_stage,
        last_outcome=last_outcome,
        suf_iter=suf_iter,
        ps_iter=ps_iter,
        last_commit=last_commit,
    )
    plan_path = workbench / PLAN_FILENAME_PC
    plan_path.write_text(fm, encoding="utf-8")

    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(repo_root), check=True, capture_output=True)

    return repo_root, plan_path


def _add_commit(repo_root: Path, message: str, plan_path: Path) -> str:
    """Add a dummy commit with the given message (touches the plan file). Returns short SHA."""
    plan_path.write_text(plan_path.read_text(encoding="utf-8") + f"\n<!-- {message} -->", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=str(repo_root), check=True, capture_output=True)
    r = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=str(repo_root), check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()


# Case (a): sufficiency iter 1 - precondition skipped (last_stage == none)
def test_precondition_skipped_for_sufficiency_iter1(tmp_path):
    """
    Case (a): last_stage == none -> precondition is skipped entirely.
    No git commits exist; the check still passes.
    """
    repo_root, plan_path = _make_precondition_repo(tmp_path, last_stage="none", last_outcome="none")

    audit_state = {"last_stage": "none", "last_outcome": "none", "last_audit_commit": ""}

    # Should NOT raise - precondition skipped
    _check_audit_loop_precondition(
        plan_path=plan_path,
        plan_id=PLAN_ID_PC,
        audit_state=audit_state,
        repo_root=repo_root,
    )
    # If we reach here, the test passes


# Case (b): sufficiency iter 2 - passes when commit-pair is present
def test_precondition_passes_when_pair_present(tmp_path):
    """
    Case (b): last_stage=sufficiency, iter 2. Commit-pair is present -> passes.
    """
    repo_root, plan_path = _make_precondition_repo(
        tmp_path, last_stage="sufficiency", last_outcome="revision_needed", suf_iter=1
    )

    # Add the two expected commits (record comes first - more recent)
    _add_commit(repo_root, f"plan-pipeline: audit_state update - sufficiency:revision_needed", plan_path)
    sha = _add_commit(repo_root, f"plan-pipeline: record last_audit_commit for {PLAN_ID_PC}", plan_path)

    audit_state = {
        "last_stage": "sufficiency",
        "last_outcome": "revision_needed",
        "last_audit_commit": sha,
    }

    # Should NOT raise
    _check_audit_loop_precondition(
        plan_path=plan_path,
        plan_id=PLAN_ID_PC,
        audit_state=audit_state,
        repo_root=repo_root,
    )


# Case (c): sufficiency iter 2 - fails when only update commit, no record commit
def test_precondition_fails_when_record_commit_missing(tmp_path):
    """
    Case (c): audit_state update commit exists but paired record_last_audit_commit is absent.
    Should raise SystemExit(2).
    """
    repo_root, plan_path = _make_precondition_repo(
        tmp_path, last_stage="sufficiency", last_outcome="revision_needed", suf_iter=1
    )

    # Only the update commit - no record commit
    _add_commit(repo_root, f"plan-pipeline: audit_state update - sufficiency:revision_needed", plan_path)

    audit_state = {
        "last_stage": "sufficiency",
        "last_outcome": "revision_needed",
        "last_audit_commit": "",
    }

    with pytest.raises(SystemExit) as exc_info:
        _check_audit_loop_precondition(
            plan_path=plan_path,
            plan_id=PLAN_ID_PC,
            audit_state=audit_state,
            repo_root=repo_root,
        )
    assert exc_info.value.code == 2


# Case (d): plan_safety iter 1 after sufficiency:success - the PLAN-AD9 bug class
def test_precondition_plan_safety_iter1_after_sufficiency_success(tmp_path):
    """
    Case (d): plan_safety iter 1 (first cross-stage transition) with sufficiency:success.
    This is the PLAN-AD9 bug class - the precondition MUST fire here.

    Subcase (d.pass): sufficiency commit-pair exists -> passes.
    Subcase (d.fail): only sufficiency update commit, no record commit -> fails.
    """
    # --- d.pass ---
    repo_root_pass, plan_path_pass = _make_precondition_repo(
        tmp_path / "pass", last_stage="sufficiency", last_outcome="success", suf_iter=1
    )
    # Both commits present
    _add_commit(repo_root_pass, "plan-pipeline: audit_state update - sufficiency:success", plan_path_pass)
    sha = _add_commit(repo_root_pass, f"plan-pipeline: record last_audit_commit for {PLAN_ID_PC}", plan_path_pass)

    audit_state_pass = {
        "last_stage": "sufficiency",
        "last_outcome": "success",
        "last_audit_commit": sha,
    }

    # Should NOT raise
    _check_audit_loop_precondition(
        plan_path=plan_path_pass,
        plan_id=PLAN_ID_PC,
        audit_state=audit_state_pass,
        repo_root=repo_root_pass,
    )

    # --- d.fail ---
    repo_root_fail, plan_path_fail = _make_precondition_repo(
        tmp_path / "fail", last_stage="sufficiency", last_outcome="success", suf_iter=1
    )
    # Only the update commit - no record commit
    _add_commit(repo_root_fail, "plan-pipeline: audit_state update - sufficiency:success", plan_path_fail)

    audit_state_fail = {
        "last_stage": "sufficiency",
        "last_outcome": "success",
        "last_audit_commit": "",
    }

    with pytest.raises(SystemExit) as exc_info:
        _check_audit_loop_precondition(
            plan_path=plan_path_fail,
            plan_id=PLAN_ID_PC,
            audit_state=audit_state_fail,
            repo_root=repo_root_fail,
        )
    assert exc_info.value.code == 2


# Case (e): plan_safety iter 2 - same shape as (b)/(c)
def test_precondition_plan_safety_iter2(tmp_path):
    """
    Case (e): plan_safety iter 2 - passes when pair present, fails when missing.
    """
    # --- pass ---
    repo_root_pass, plan_path_pass = _make_precondition_repo(
        tmp_path / "pass", last_stage="plan_safety", last_outcome="revision_needed",
        suf_iter=1, ps_iter=1
    )
    _add_commit(repo_root_pass, "plan-pipeline: audit_state update - plan_safety:revision_needed", plan_path_pass)
    sha = _add_commit(repo_root_pass, f"plan-pipeline: record last_audit_commit for {PLAN_ID_PC}", plan_path_pass)

    audit_state_pass = {
        "last_stage": "plan_safety",
        "last_outcome": "revision_needed",
        "last_audit_commit": sha,
    }
    _check_audit_loop_precondition(
        plan_path=plan_path_pass,
        plan_id=PLAN_ID_PC,
        audit_state=audit_state_pass,
        repo_root=repo_root_pass,
    )

    # --- fail ---
    repo_root_fail, plan_path_fail = _make_precondition_repo(
        tmp_path / "fail", last_stage="plan_safety", last_outcome="revision_needed",
        suf_iter=1, ps_iter=1
    )
    _add_commit(repo_root_fail, "plan-pipeline: audit_state update - plan_safety:revision_needed", plan_path_fail)

    audit_state_fail = {
        "last_stage": "plan_safety",
        "last_outcome": "revision_needed",
        "last_audit_commit": "",
    }

    with pytest.raises(SystemExit) as exc_info:
        _check_audit_loop_precondition(
            plan_path=plan_path_fail,
            plan_id=PLAN_ID_PC,
            audit_state=audit_state_fail,
            repo_root=repo_root_fail,
        )
    assert exc_info.value.code == 2


# Case (f): precondition skipped when PLAN created before AE0 ship date and --since excludes commits
def test_precondition_grandfather_cutoff(tmp_path):
    """
    Case (f): PLAN was created before AE0 ship date AND the audit_state update commit
    predates the --since cutoff. The git log returns empty -> update_idx is None ->
    SystemExit(2). This is the expected behaviour: grandfather protects only PLANs
    created after (or on) AE0_SHIP_DATE, because we use max(plan_created, AE0_SHIP_DATE).

    A PLAN created on 2026-04-01 (before AE0) with a commit from 2026-04-15 (before
    the since cutoff of max(2026-04-01, 2026-05-26) = 2026-05-26) would be excluded
    from the search window. Since git log has no commits matching the pattern in the
    window, update_idx == None -> the check fails with SystemExit(2).

    NOTE: This test verifies the precondition logic itself. In practice, the
    grandfather only saves you if the commit-pair was written before AE0_SHIP_DATE.
    Since git does not allow backdating commits in our workflow, the real-world effect
    is: any PLAN whose first audit ran before AE0 shipped won't have a commit pair,
    but the git log --since window will also exclude those old commits, so the check
    will fail to find the pair and will raise. That is intentional - the grandfather
    is conservative, and the operator uses audit_loop.apply_audit_outcome() to create
    the missing pair if needed.

    In THIS test we simulate that scenario: we add commits, but then use a plan
    created date far in the past so the since-window excludes everything, and
    the precondition can't find the pair -> raises.
    """
    import yaml

    # Create a PLAN with a very old created date
    repo_root, plan_path = _make_precondition_repo(
        tmp_path, last_stage="sufficiency", last_outcome="success", suf_iter=1
    )

    # Overwrite created date to be far in the past
    text = plan_path.read_text(encoding="utf-8")
    text = text.replace("created: 2026-05-26", "created: 2025-01-01")
    plan_path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "set old created date"], cwd=str(repo_root), check=True, capture_output=True)

    # The since cutoff will be max(2025-01-01, 2026-05-26) = 2026-05-26
    # Add commits ONLY to make them present in history; they will be inside the window
    # but NOT matching the expected pattern for this plan's last_stage/last_outcome
    _add_commit(repo_root, "unrelated: some other commit", plan_path)

    audit_state = {
        "last_stage": "sufficiency",
        "last_outcome": "success",
        "last_audit_commit": "",
    }

    # No audit_state update commit exists for this plan within the since window
    # -> precondition raises SystemExit(2)
    with pytest.raises(SystemExit) as exc_info:
        _check_audit_loop_precondition(
            plan_path=plan_path,
            plan_id=PLAN_ID_PC,
            audit_state=audit_state,
            repo_root=repo_root,
        )
    assert exc_info.value.code == 2


# Case (g): Bug 2 regression - precondition passes under interleaved batch housekeeping
def test_precondition_passes_under_interleaved_batch_housekeeping(tmp_path):
    """
    Bug 2 regression (PLAN-AG6 / AF6 dogfood): reproduces the AG3/AG4/AG5 live case.

    Target PLAN's update+record pair is present but buried >2 commits deep by two
    foreign PLANs' newer housekeeping pairs. The old early-break loop would fire at
    i=0 (update_idx > 2) and raise SystemExit(2) on a healthy pair. The fix uses
    range(max(0, update_idx-2), update_idx) AND scopes git log to the target plan file,
    so foreign commits are excluded entirely.

    Foreign plans use a DIFFERENT outcome (revision_needed) so update_pattern for the
    target (sufficiency:success) still resolves unambiguously even without path-scoping
    - this test isolates the pairing-scan ordering fix only.
    """
    repo_root, plan_path = _make_precondition_repo(
        tmp_path, last_stage="sufficiency", last_outcome="success", suf_iter=1
    )

    # Add target's pair (touching the target PLAN file)
    _add_commit(repo_root, "plan-pipeline: audit_state update - sufficiency:success", plan_path)
    sha = _add_commit(repo_root, f"plan-pipeline: record last_audit_commit for {PLAN_ID_PC}", plan_path)

    # Create two foreign PLAN files and add newer update+record pairs touching only those files
    workbench = plan_path.parent
    foreign1 = workbench / "PLAN-ZZ1_foreign.md"
    foreign2 = workbench / "PLAN-ZZ2_foreign.md"
    foreign1.write_text("stub\n", encoding="utf-8")
    foreign2.write_text("stub\n", encoding="utf-8")

    # Foreign ZZ1 pair (newer than target's pair) - different outcome so update_pattern won't match
    _add_commit(repo_root, "plan-pipeline: audit_state update - sufficiency:revision_needed", foreign1)
    _add_commit(repo_root, "plan-pipeline: record last_audit_commit for PLAN-ZZ1", foreign1)

    # Foreign ZZ2 pair (newest) - different outcome
    _add_commit(repo_root, "plan-pipeline: audit_state update - sufficiency:revision_needed", foreign2)
    _add_commit(repo_root, "plan-pipeline: record last_audit_commit for PLAN-ZZ2", foreign2)

    # Target's update is now buried >=4 positions from HEAD in the unfiltered log.
    # With path-scoping on plan_path, only target's 2 commits are visible -> passes.
    audit_state = {
        "last_stage": "sufficiency",
        "last_outcome": "success",
        "last_audit_commit": sha,
    }

    # Should NOT raise - reaching end of test is the pass
    _check_audit_loop_precondition(
        plan_path=plan_path,
        plan_id=PLAN_ID_PC,
        audit_state=audit_state,
        repo_root=repo_root,
    )


# Case (h): Bug 2 regression - precondition isolates target's pair despite foreign same outcome
def test_precondition_identifies_target_pair_despite_foreign_same_outcome(tmp_path):
    """
    Bug 2 regression (PLAN-AG6): exercises the plan-id ambiguity specifically.

    A foreign PLAN has a NEWER update commit with the SAME stage:outcome as the target
    (sufficiency:success). Without path-scoping, update_pattern matches the foreign
    commit first, and the adjacent record is for the foreign plan id - not the target -
    so pair_found is never set to True and SystemExit(2) is raised on a healthy target pair.
    With path-scoping (git log -- <plan_path>), the foreign commit is excluded and the
    target's own pair is found correctly.
    """
    repo_root, plan_path = _make_precondition_repo(
        tmp_path, last_stage="sufficiency", last_outcome="success", suf_iter=1
    )

    # Add target's pair
    _add_commit(repo_root, "plan-pipeline: audit_state update - sufficiency:success", plan_path)
    sha = _add_commit(repo_root, f"plan-pipeline: record last_audit_commit for {PLAN_ID_PC}", plan_path)

    # Create one foreign PLAN and add a NEWER pair with the SAME stage:outcome
    workbench = plan_path.parent
    foreign1 = workbench / "PLAN-ZZ1_foreign.md"
    foreign1.write_text("stub\n", encoding="utf-8")

    _add_commit(repo_root, "plan-pipeline: audit_state update - sufficiency:success", foreign1)
    _add_commit(repo_root, "plan-pipeline: record last_audit_commit for PLAN-ZZ1", foreign1)

    audit_state = {
        "last_stage": "sufficiency",
        "last_outcome": "success",
        "last_audit_commit": sha,
    }

    # Should NOT raise - path-scoped git log sees only target's commits
    _check_audit_loop_precondition(
        plan_path=plan_path,
        plan_id=PLAN_ID_PC,
        audit_state=audit_state,
        repo_root=repo_root,
    )


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
        test_reaudit_brief_lists_prior_findings_diagnostics_shape,
        test_plan_safety_brief_admits_auxiliary_families_sufficiency_does_not,
    ]

    print(f"Running {len(tests)} tests...\n")
    for test in tests:
        test()

    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    main()


# Surface 3 human override - the third valid provenance artefact.
# Dogfooded on PLAN-AI7 2026-07-31: the override advanced sufficiency to success,
# and this check then refused to build the plan-safety brief because neither
# housekeeping commit exists on that path. The override's own commit template is
# the record of the transition.
def test_precondition_accepts_human_override_without_commit_pair(tmp_path):
    """
    A Surface 3 override writes `plan-pipeline: human-override <phase> <stage> for
    <file>` and no audit_state/record pair, because apply_audit_outcome never runs.
    The precondition must accept it and must not demand a paired SHA-record commit.
    """
    repo_root, plan_path = _make_precondition_repo(
        tmp_path, last_stage="sufficiency", last_outcome="success", suf_iter=5
    )

    _add_commit(
        repo_root,
        f"plan-pipeline: human-override drafted sufficiency for {PLAN_FILENAME_PC}",
        plan_path,
    )

    audit_state = {
        "last_stage": "sufficiency",
        "last_outcome": "success",
        "last_audit_commit": "",
    }

    # Should NOT raise - the override is the provenance artefact.
    _check_audit_loop_precondition(
        plan_path=plan_path,
        plan_id=PLAN_ID_PC,
        audit_state=audit_state,
        repo_root=repo_root,
    )


def test_precondition_still_fails_when_neither_artefact_present(tmp_path):
    """
    The override branch must not weaken the check: with no housekeeping pair AND no
    override commit, frontmatter claiming an outcome git history does not support
    still exits 2.
    """
    repo_root, plan_path = _make_precondition_repo(
        tmp_path, last_stage="sufficiency", last_outcome="success", suf_iter=5
    )

    _add_commit(repo_root, "some unrelated commit", plan_path)

    audit_state = {
        "last_stage": "sufficiency",
        "last_outcome": "success",
        "last_audit_commit": "",
    }

    with pytest.raises(SystemExit) as exc:
        _check_audit_loop_precondition(
            plan_path=plan_path,
            plan_id=PLAN_ID_PC,
            audit_state=audit_state,
            repo_root=repo_root,
        )
    assert exc.value.code == 2


def test_precondition_override_for_one_stage_does_not_satisfy_another(tmp_path):
    """
    An override of the sufficiency stage must not satisfy a plan_safety provenance
    check. The stage name is matched, not merely the word `human-override`.
    """
    repo_root, plan_path = _make_precondition_repo(
        tmp_path, last_stage="plan_safety", last_outcome="success", suf_iter=5, ps_iter=1
    )

    _add_commit(
        repo_root,
        f"plan-pipeline: human-override drafted sufficiency for {PLAN_FILENAME_PC}",
        plan_path,
    )

    audit_state = {
        "last_stage": "plan_safety",
        "last_outcome": "success",
        "last_audit_commit": "",
    }

    with pytest.raises(SystemExit) as exc:
        _check_audit_loop_precondition(
            plan_path=plan_path,
            plan_id=PLAN_ID_PC,
            audit_state=audit_state,
            repo_root=repo_root,
        )
    assert exc.value.code == 2
