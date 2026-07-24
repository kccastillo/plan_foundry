"""
test_audit_loop.py — Tests for audit_loop.apply_audit_outcome.

Uses pytest + tmp_path fixture with a real git repo (git init + minimal config)
because audit_loop.py makes subprocess git calls.

Run: python -m pytest .claude/skills/plan-pipeline/lib/test_audit_loop.py -v
"""

import json
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import module under test
# ---------------------------------------------------------------------------
import sys

sys.path.insert(0, str(Path(__file__).parent))
from audit_loop import apply_audit_outcome, _compute_fingerprint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_PLAN = """\
---
schema_version: 2
title: "Audit Loop Test PLAN"
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
Test PLAN for audit_loop unit tests.

## Steps
1. Nothing.

## Verification
- [ ] No-op.
"""

SUFFICIENCY_SUCCESS_RETURN = json.dumps({
    "outcome": "success",
    "payload": {
        "outcome_subtype": "done",
        "review_text": "PLAN passes all seven sufficiency lenses.",
        "triaged_human_items": [],
    },
    "diagnostics": {
        "findings": [
            {
                "code": "S201",
                "level": "warning",
                "category": "test-fidelity",
                "location": "Verification",
                "message": "Verification is trivial.",
                "suggested_fix": "Add real verification.",
            }
        ],
        "summary": {"error_count": 0, "warning_count": 1, "note_count": 0},
    },
})

SUFFICIENCY_REVISION_RETURN = json.dumps({
    "outcome": "revision_needed",
    "payload": {
        "outcome_subtype": "needs-revision",
        "review_text": "Two errors require revision.",
        "triaged_human_items": [],
    },
    "diagnostics": {
        "findings": [
            {
                "code": "S001",
                "level": "error",
                "category": "assumptions",
                "location": "Step 1",
                "message": "Step 1 is not actionable.",
                "suggested_fix": "Rewrite Step 1.",
            },
            {
                "code": "S201",
                "level": "warning",
                "category": "test-fidelity",
                "location": "Verification",
                "message": "Verification is trivial.",
                "suggested_fix": "Add real verification.",
            },
        ],
        "summary": {"error_count": 1, "warning_count": 1, "note_count": 0},
    },
})


def _make_git_repo(tmp_path: Path) -> tuple[Path, Path]:
    """
    Create a minimal git repo with a PLAN-AE1_test file.
    Returns (repo_root, plan_path).
    Repo layout: tmp_path/ is the repo root; Workbench/ contains the PLAN.
    """
    repo_root = tmp_path
    workbench = repo_root / "Workbench"
    workbench.mkdir()

    plan_path = workbench / "PLAN-AE1_audit-loop-test.md"
    plan_path.write_text(MINIMAL_PLAN, encoding="utf-8")

    # Initialise git repo
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo_root), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(repo_root), check=True, capture_output=True,
    )
    # Initial commit so HEAD exists
    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=str(repo_root), check=True, capture_output=True,
    )

    return repo_root, plan_path


# ---------------------------------------------------------------------------
# Test: happy-path success cycle
# ---------------------------------------------------------------------------

def test_happy_path_success(tmp_path):
    """
    apply_audit_outcome returns correct shape, writes audit JSON, mutates
    frontmatter correctly, and produces exactly two commits.
    """
    repo_root, plan_path = _make_git_repo(tmp_path)

    result = apply_audit_outcome(
        plan_path=str(plan_path),
        stage="sufficiency",
        audit_return_json=SUFFICIENCY_SUCCESS_RETURN,
        iteration=1,
    )

    # --- Return shape ---
    assert result["outcome"] == "success"
    assert result["plan_id"] == "PLAN-AE1"
    assert result["stripped_count"] == 0
    assert result["recurring_fingerprints"] == []
    assert len(result["last_audit_commit"]) == 8
    assert result["review_text"] == "PLAN passes all seven sufficiency lenses."

    # --- Audit JSON snapshot written ---
    audit_path = Path(result["audit_json_path"])
    assert audit_path.exists()
    assert audit_path.name == "PLAN-AE1-sufficiency-1.json"
    written = json.loads(audit_path.read_text(encoding="utf-8"))
    assert written["outcome"] == "success"

    # --- Frontmatter mutated ---
    import yaml
    text = plan_path.read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---", 2)[1])
    assert fm["audit_state"]["last_stage"] == "sufficiency"
    assert fm["audit_state"]["last_outcome"] == "success"
    assert fm["audit_state"]["sufficiency_iterations"] == 1
    assert fm["audit_state"]["last_audit_commit"] == result["last_audit_commit"]

    # --- Two commits landed ---
    git_log = subprocess.run(
        ["git", "log", "--oneline", "-5"],
        cwd=str(repo_root), check=True, capture_output=True, text=True,
    )
    commits = git_log.stdout.strip().splitlines()
    assert len(commits) == 3  # initial + two from helper
    assert "record last_audit_commit for PLAN-AE1" in commits[0]
    assert "audit_state update - sufficiency:success" in commits[1]


# ---------------------------------------------------------------------------
# Test: fingerprint computation (3 cases)
# ---------------------------------------------------------------------------

def test_fingerprint_same_finding_is_deterministic():
    finding = {"code": "S001", "level": "error", "category": "assumptions", "location": "Step 1"}
    fp1 = _compute_fingerprint(finding)
    fp2 = _compute_fingerprint(finding)
    assert fp1 == fp2
    assert len(fp1) == 8


def test_fingerprint_different_code_differs():
    f1 = {"code": "S001", "level": "error", "category": "assumptions", "location": "Step 1"}
    f2 = {"code": "S002", "level": "error", "category": "assumptions", "location": "Step 1"}
    assert _compute_fingerprint(f1) != _compute_fingerprint(f2)


def test_fingerprint_missing_fields_tolerated():
    finding = {}
    fp = _compute_fingerprint(finding)
    assert len(fp) == 8  # sha256 of "|||" — should not raise


# ---------------------------------------------------------------------------
# Test: acknowledgement stripping (2 cases)
# ---------------------------------------------------------------------------

def test_acknowledgement_stripping_partial(tmp_path):
    """
    One of two findings is acknowledged — only that one is stripped.
    stripped_count == 1.
    """
    repo_root, plan_path = _make_git_repo(tmp_path)

    # Compute the fingerprint for S001 (error finding in SUFFICIENCY_REVISION_RETURN)
    s001_finding = {
        "code": "S001",
        "level": "error",
        "category": "assumptions",
        "location": "Step 1",
    }
    s001_fp = _compute_fingerprint(s001_finding)

    # Patch the PLAN frontmatter to include this acknowledgement
    import yaml
    text = plan_path.read_text(encoding="utf-8")
    _, fm_text, body = text.split("---", 2)
    fm = yaml.safe_load(fm_text)
    fm["audit_acknowledgements"] = [
        {"fingerprint": s001_fp, "rationale": "accepted risk", "ack_date": "2026-05-26", "ack_iteration": 0}
    ]
    fm_out = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    plan_path.write_text(f"---\n{fm_out}---{body}", encoding="utf-8")

    # Commit the updated PLAN so the repo is clean for git add
    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "update PLAN with acknowledgement"],
        cwd=str(repo_root), check=True, capture_output=True,
    )

    result = apply_audit_outcome(
        plan_path=str(plan_path),
        stage="sufficiency",
        audit_return_json=SUFFICIENCY_REVISION_RETURN,
        iteration=1,
    )

    assert result["stripped_count"] == 1  # S001 stripped; S201 kept


def test_acknowledgement_stripping_all(tmp_path):
    """
    Both findings are acknowledged → stripped_count == 2, recurring_fingerprints == [].
    """
    repo_root, plan_path = _make_git_repo(tmp_path)

    findings = [
        {"code": "S001", "level": "error", "category": "assumptions", "location": "Step 1"},
        {"code": "S201", "level": "warning", "category": "test-fidelity", "location": "Verification"},
    ]
    fps = [_compute_fingerprint(f) for f in findings]

    import yaml
    text = plan_path.read_text(encoding="utf-8")
    _, fm_text, body = text.split("---", 2)
    fm = yaml.safe_load(fm_text)
    fm["audit_acknowledgements"] = [
        {"fingerprint": fp, "rationale": "ok", "ack_date": "2026-05-26", "ack_iteration": 0}
        for fp in fps
    ]
    fm_out = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    plan_path.write_text(f"---\n{fm_out}---{body}", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "update PLAN with all acknowledgements"],
        cwd=str(repo_root), check=True, capture_output=True,
    )

    result = apply_audit_outcome(
        plan_path=str(plan_path),
        stage="sufficiency",
        audit_return_json=SUFFICIENCY_REVISION_RETURN,
        iteration=1,
    )

    assert result["stripped_count"] == 2
    assert result["recurring_fingerprints"] == []


# ---------------------------------------------------------------------------
# Test: recurrence compare with prior-iter JSON absent → empty list
# ---------------------------------------------------------------------------

def test_recurrence_prior_absent(tmp_path):
    """
    iteration=2, no prior JSON → recurring_fingerprints == [].
    """
    repo_root, plan_path = _make_git_repo(tmp_path)

    result = apply_audit_outcome(
        plan_path=str(plan_path),
        stage="sufficiency",
        audit_return_json=SUFFICIENCY_REVISION_RETURN,
        iteration=2,  # no prior iter-1 file in .audit/
    )

    assert result["recurring_fingerprints"] == []


# ---------------------------------------------------------------------------
# Test: recurrence compare with prior present → correct overlap
# ---------------------------------------------------------------------------

def test_recurrence_with_prior(tmp_path):
    """
    Two iterations with overlapping findings → recurring_fingerprints contains
    the fingerprint of the finding that appears in both.
    """
    repo_root, plan_path = _make_git_repo(tmp_path)

    # First, seed a fake prior audit JSON (iter 1)
    # The prior JSON has S001 (error) only.
    s001_finding = {"code": "S001", "level": "error", "category": "assumptions", "location": "Step 1"}
    prior_data = {
        "outcome": "revision_needed",
        "payload": {"review_text": "prior iter"},
        "diagnostics": {
            "findings": [s001_finding],
            "summary": {"error_count": 1, "warning_count": 0, "note_count": 0},
        },
    }
    audit_dir = plan_path.parent / ".audit"
    audit_dir.mkdir(exist_ok=True)
    prior_path = audit_dir / "PLAN-AE1-sufficiency-1.json"
    prior_path.write_text(json.dumps(prior_data), encoding="utf-8")

    # Commit the prior audit so the repo is clean
    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "seed prior audit"],
        cwd=str(repo_root), check=True, capture_output=True,
    )

    # Now run iter 2 — SUFFICIENCY_REVISION_RETURN has both S001 and S201
    result = apply_audit_outcome(
        plan_path=str(plan_path),
        stage="sufficiency",
        audit_return_json=SUFFICIENCY_REVISION_RETURN,
        iteration=2,
    )

    # S001 appears in both → should be recurring
    s001_fp = _compute_fingerprint(s001_finding)
    assert s001_fp in result["recurring_fingerprints"]
    # S201 is new (not in prior) → NOT in recurring
    s201_finding = {"code": "S201", "level": "warning", "category": "test-fidelity", "location": "Verification"}
    s201_fp = _compute_fingerprint(s201_finding)
    assert s201_fp not in result["recurring_fingerprints"]


# ---------------------------------------------------------------------------
# Test: subprocess failure raises CalledProcessError
# ---------------------------------------------------------------------------

def test_subprocess_failure_raises(tmp_path):
    """
    apply_audit_outcome raises subprocess.CalledProcessError if git operations fail
    (e.g., called outside a git repo).
    """
    # Use a directory that is NOT a git repo
    non_repo = tmp_path / "not_a_repo"
    non_repo.mkdir()
    workbench = non_repo / "Workbench"
    workbench.mkdir()
    plan_path = workbench / "PLAN-AE1_audit-loop-test.md"
    plan_path.write_text(MINIMAL_PLAN, encoding="utf-8")

    with pytest.raises(subprocess.CalledProcessError):
        apply_audit_outcome(
            plan_path=str(plan_path),
            stage="sufficiency",
            audit_return_json=SUFFICIENCY_SUCCESS_RETURN,
            iteration=1,
        )
