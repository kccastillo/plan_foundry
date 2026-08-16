"""
test_resume_preflight.py - Unit tests for check_resume_drift().

Tests the resumption drift preflight introduced by PLAN-AG4
(Deterministic branch/PR drift preflight on resumption, 2026-07-13).

Coverage:
  1.  Clean state: no drift on fetch-ok + all-clean axes.
  2.  Behind remote -> drift: behind=2 triggers drift.
  3.  Diverged -> drift: ahead=1 and behind=1 triggers drift + diverged=True.
  4.  Merged PR (authoritative) -> drift: MERGED PR state in gh output triggers drift.
  5.  Dynamic default branch: symbolic-ref returns master -> default_branch == "master".
  5b. Dynamic default fallback: symbolic-ref fails -> default_branch == "main" + notes entry.
  6.  Fetch failure -> fail-open: git-axes checked=False, drift=False (no baseline).
  7.  gh unavailable -> best-effort skip: pr_state.available=False, function still returns.
  8.  PLAN drift via tmp_path: real PLAN file with baseline mismatch fires drift.
  9.  Real-git-repo tests (subprocess not mocked; skipped if git not on PATH):
      9a. True non-ff merge -> merged_into_default=True, drift=True.
      9b. Behind-empty branch (disclosed FALSE POSITIVE) -> merged_into_default=True.
      9c. Ahead/diverged branch -> merged_into_default=False.
      9d. Squash-merge (disclosed FALSE NEGATIVE) -> merged_into_default=False.

Run: python -m pytest .claude/skills/_shared/lib/test_resume_preflight.py
"""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, patch

# Make the parent dir importable regardless of cwd
_HERE = pathlib.Path(__file__).resolve().parent
_PARENT = _HERE.parent  # .claude/skills/_shared/
sys.path.insert(0, str(_PARENT))

from resume_preflight import check_resume_drift  # noqa: E402


# ---------------------------------------------------------------------------
# Mock helpers - mirror test_push_guard.py conventions exactly
# ---------------------------------------------------------------------------

def _make_completed_process(returncode=0, stdout="", stderr=""):
    """Return a minimal CompletedProcess-alike MagicMock."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _fetch_ok():
    """Successful git fetch."""
    return _make_completed_process(returncode=0, stdout="", stderr="")


def _fetch_fail():
    """Failed git fetch."""
    return _make_completed_process(
        returncode=128, stdout="", stderr="fatal: unable to connect to remote"
    )


def _rev_parse_ok(branch="main"):
    """git rev-parse --abbrev-ref HEAD -> branch name."""
    return _make_completed_process(returncode=0, stdout=branch + "\n", stderr="")


def _symbolic_ref_ok(remote="origin", branch="main"):
    """git symbolic-ref refs/remotes/<remote>/HEAD -> resolved ref."""
    return _make_completed_process(
        returncode=0, stdout=f"refs/remotes/{remote}/{branch}\n", stderr=""
    )


def _symbolic_ref_fail():
    """git symbolic-ref fails (remote HEAD not set)."""
    return _make_completed_process(
        returncode=128, stdout="", stderr="fatal: ref refs/remotes/origin/HEAD is not a symbolic ref"
    )


def _rev_list_ok(behind, ahead):
    """git rev-list --left-right --count -> '<behind>\\t<ahead>'."""
    return _make_completed_process(returncode=0, stdout=f"{behind}\t{ahead}\n", stderr="")


def _rev_list_fail():
    """git rev-list fails (no tracking ref)."""
    return _make_completed_process(
        returncode=128, stdout="", stderr="fatal: no upstream configured for branch 'main'"
    )


def _rev_list_content_ok(commits_str):
    """git rev-list returning a list of commit hashes (newline-separated)."""
    return _make_completed_process(returncode=0, stdout=commits_str, stderr="")


def _rev_list_empty():
    """git rev-list returning empty output (ancestor check passes)."""
    return _make_completed_process(returncode=0, stdout="", stderr="")


def _rev_parse_sha(sha="abc1234"):
    """git rev-parse <ref> -> a commit SHA."""
    return _make_completed_process(returncode=0, stdout=sha + "\n", stderr="")


def _gh_pr_list_ok(prs):
    """gh pr list --json -> JSON list of PR objects."""
    return _make_completed_process(returncode=0, stdout=json.dumps(prs), stderr="")


def _gh_pr_list_fail():
    """gh pr list fails."""
    return _make_completed_process(
        returncode=1, stdout="", stderr="error: no GitHub authentication"
    )


def _build_clean_side_effects(branch="main", default="main", remote="origin"):
    """Return the side_effect list for a perfectly clean state.

    Order of subprocess.run calls in check_resume_drift:
      1. git fetch
      2. git rev-parse --abbrev-ref HEAD
      3. git symbolic-ref refs/remotes/<remote>/HEAD
      4. git rev-list --left-right --count <remote>/<branch>...HEAD  (remote_compare)
      5. gh pr list (pr_state - raises FileNotFoundError for gh-missing; use fail here)
      6. git rev-list --left-right --count <remote>/<default>...HEAD (default_compare)
    """
    return [
        _fetch_ok(),
        _rev_parse_ok(branch),
        _symbolic_ref_ok(remote, default),
        _rev_list_ok(0, 0),      # remote_compare: clean
        _gh_pr_list_ok([]),      # pr_state: no PRs
        _rev_list_ok(0, 0),      # default_compare: clean
    ]


# ---------------------------------------------------------------------------
# Test 1: Clean state - no drift
# ---------------------------------------------------------------------------

def test_clean_state(tmp_path):
    """1: All clean -> drift=False, clean=True."""
    side_effects = _build_clean_side_effects()
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(str(tmp_path))
    assert result["drift"] is False, f"expected drift=False, got {result}"
    assert result["clean"] is True
    assert result["remote_compare"]["checked"] is True
    assert result["remote_compare"]["behind"] == 0
    assert result["default_compare"]["checked"] is True
    assert result["default_compare"]["merged_into_default"] is False
    assert result["summary"] == ""
    assert result["plan_drift"] == []


# ---------------------------------------------------------------------------
# Test 2: Behind remote -> drift
# ---------------------------------------------------------------------------

def test_behind_remote_drift(tmp_path):
    """2: behind=2 -> drift=True; summary names the behind count."""
    side_effects = [
        _fetch_ok(),
        _rev_parse_ok("main"),
        _symbolic_ref_ok("origin", "main"),
        _rev_list_ok(2, 0),      # remote_compare: behind=2
        _gh_pr_list_ok([]),
        _rev_list_ok(0, 0),      # default_compare: clean
    ]
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(str(tmp_path))
    assert result["drift"] is True, f"expected drift=True, got {result}"
    assert result["remote_compare"]["behind"] == 2
    assert "2" in result["summary"], f"summary missing behind count: {result['summary']!r}"
    assert result["summary"] != ""


# ---------------------------------------------------------------------------
# Test 3: Diverged -> drift
# ---------------------------------------------------------------------------

def test_diverged_drift(tmp_path):
    """3: behind=1, ahead=1 -> drift=True; remote_compare.diverged=True."""
    side_effects = [
        _fetch_ok(),
        _rev_parse_ok("main"),
        _symbolic_ref_ok("origin", "main"),
        _rev_list_ok(1, 1),      # remote_compare: diverged
        _gh_pr_list_ok([]),
        _rev_list_ok(0, 0),
    ]
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(str(tmp_path))
    assert result["drift"] is True, f"expected drift=True, got {result}"
    assert result["remote_compare"]["diverged"] is True
    assert result["summary"] != ""


# ---------------------------------------------------------------------------
# Test 4: Merged PR (authoritative) -> drift, summary names PR number
# ---------------------------------------------------------------------------

def test_merged_pr_authoritative(tmp_path):
    """4: gh reports MERGED PR -> merged_into_default=True; summary names PR number + restart."""
    merged_pr = [{"number": 42, "state": "MERGED", "isDraft": False, "title": "feat: foo"}]
    side_effects = [
        _fetch_ok(),
        _rev_parse_ok("feature-branch"),
        _symbolic_ref_ok("origin", "main"),
        _rev_list_ok(0, 3),      # remote_compare: ahead only
        _gh_pr_list_ok(merged_pr),
        _rev_list_ok(3, 0),      # default_compare: behind default (merged)
    ]
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(str(tmp_path))
    assert result["default_compare"]["merged_into_default"] is True
    assert result["drift"] is True
    assert "42" in result["summary"], f"summary missing PR number: {result['summary']!r}"
    assert "restart" in result["summary"].lower(), f"summary missing restart hint: {result['summary']!r}"


# ---------------------------------------------------------------------------
# Test 5: Dynamic default branch - symbolic-ref returns master
# ---------------------------------------------------------------------------

def test_dynamic_default_branch_master(tmp_path):
    """5: symbolic-ref returns refs/remotes/origin/master -> default_branch == 'master'."""
    side_effects = [
        _fetch_ok(),
        _rev_parse_ok("feature"),
        _symbolic_ref_ok("origin", "master"),
        _rev_list_ok(0, 0),   # remote_compare vs origin/feature
        _gh_pr_list_ok([]),
        _rev_list_ok(0, 0),   # default_compare vs origin/master
    ]
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(str(tmp_path))
    assert result["default_branch"] == "master", (
        f"expected default_branch='master', got {result['default_branch']!r}"
    )
    # default_compare should have used origin/master (check via the reason field)
    assert "master" in result["default_compare"]["reason"]


# ---------------------------------------------------------------------------
# Test 5b: Dynamic default branch - symbolic-ref fails -> falls back to 'main'
# ---------------------------------------------------------------------------

def test_dynamic_default_branch_fallback(tmp_path):
    """5b: symbolic-ref fails -> default_branch == 'main' and notes mentions fallback."""
    side_effects = [
        _fetch_ok(),
        _rev_parse_ok("feature"),
        _symbolic_ref_fail(),   # symbolic-ref fails
        _rev_list_ok(0, 0),
        _gh_pr_list_ok([]),
        _rev_list_ok(0, 0),
    ]
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(str(tmp_path))
    assert result["default_branch"] == "main", (
        f"expected fallback default_branch='main', got {result['default_branch']!r}"
    )
    assert any("fell back" in n for n in result["notes"]), (
        f"notes missing fallback entry: {result['notes']}"
    )


# ---------------------------------------------------------------------------
# Test 6: Fetch failure -> fail-open
# ---------------------------------------------------------------------------

def test_fetch_failure_fail_open(tmp_path):
    """6: git fetch non-zero -> git axes checked=False, drift=False (no baseline), notes has 'skipped'."""
    with patch("resume_preflight.subprocess.run", return_value=_fetch_fail()):
        result = check_resume_drift(str(tmp_path))
    assert result["drift"] is False, f"expected drift=False on fetch failure, got {result}"
    assert result["remote_compare"]["checked"] is False
    assert result["default_compare"]["checked"] is False
    assert any("skipped" in n for n in result["notes"]), (
        f"notes missing 'skipped': {result['notes']}"
    )


# ---------------------------------------------------------------------------
# Test 7: gh unavailable -> best-effort skip
# ---------------------------------------------------------------------------

def test_gh_unavailable(tmp_path):
    """7: gh raises FileNotFoundError -> pr_state.available=False, function still returns."""

    def _side_effect(args, **kwargs):
        if args[0] == "gh":
            raise FileNotFoundError("gh not found")
        return _make_completed_process(returncode=0, stdout="", stderr="")

    # We need a tailored sequence: fetch, rev-parse, symbolic-ref, rev-list x 2, gh (raises), rev-list
    call_count = [0]
    subprocess_calls = [
        _fetch_ok(),
        _rev_parse_ok("main"),
        _symbolic_ref_ok("origin", "main"),
        _rev_list_ok(0, 0),
        # gh call will raise FileNotFoundError
        _rev_list_ok(0, 0),
    ]

    def smart_side_effect(args, **kwargs):
        if args[0] == "gh":
            raise FileNotFoundError("gh not found")
        idx = call_count[0]
        call_count[0] += 1
        return subprocess_calls[idx]

    with patch("resume_preflight.subprocess.run", side_effect=smart_side_effect):
        result = check_resume_drift(str(tmp_path))

    assert result["pr_state"]["available"] is False
    # Function must still return without raising
    assert "drift" in result
    assert any("skipped" in n for n in result["notes"]), (
        f"notes missing 'skipped' for gh: {result['notes']}"
    )


# ---------------------------------------------------------------------------
# Test 8: PLAN drift via tmp_path - baseline mismatch
# ---------------------------------------------------------------------------

PLAN_FRONTMATTER_TEMPLATE = """\
---
schema_version: 2
title: Test PLAN
type: plan
status: checked
pipeline_phase: {pipeline_phase}
last_executor_outcome: {last_executor_outcome}
---

## Objective
Test PLAN for unit tests.
"""


def _write_plan(path, pipeline_phase="outcome-verifying", last_executor_outcome=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        PLAN_FRONTMATTER_TEMPLATE.format(
            pipeline_phase=pipeline_phase,
            last_executor_outcome=last_executor_outcome,
        ),
        encoding="utf-8",
    )


def test_plan_drift_absent_field_matches_empty_baseline(tmp_path):
    """8b: an absent/blank frontmatter field reads as None, and the handoff baseline
    renders the same condition as "". Those two must not count as drift, or every PLAN
    that has never entered the pipeline fires on every resume."""
    plan_path = tmp_path / "Workbench" / "PLAN-ZZ1_x.md"
    _write_plan(plan_path, pipeline_phase="", last_executor_outcome="")

    expected = {
        "Workbench/PLAN-ZZ1_x.md": {
            "pipeline_phase": "",
            "status": "checked",
            "last_executor_outcome": "",
        },
    }

    side_effects = [
        _fetch_ok(),
        _rev_parse_ok("main"),
        _symbolic_ref_ok("origin", "main"),
        _rev_list_ok(0, 0),
        _gh_pr_list_ok([]),
        _rev_list_ok(0, 0),
    ]
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(
            str(tmp_path),
            expected_plan_states=expected,
            plan_glob="Workbench/PLAN-*.md",
        )

    assert result["plan_drift"] == [], f"expected no drift, got {result['plan_drift']}"
    assert result["drift"] is False
    # A real mismatch on the same PLAN must still fire.
    expected["Workbench/PLAN-ZZ1_x.md"]["pipeline_phase"] = "executing"
    side_effects = [
        _fetch_ok(),
        _rev_parse_ok("main"),
        _symbolic_ref_ok("origin", "main"),
        _rev_list_ok(0, 0),
        _gh_pr_list_ok([]),
        _rev_list_ok(0, 0),
    ]
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(
            str(tmp_path),
            expected_plan_states=expected,
            plan_glob="Workbench/PLAN-*.md",
        )
    assert len(result["plan_drift"]) == 1
    assert result["plan_drift"][0]["field"] == "pipeline_phase"
    assert result["drift"] is True


def test_plan_drift_baseline_mismatch(tmp_path):
    """8: on-disk PLAN differs from baseline -> plan_drift fires, drift=True."""
    plan_path = tmp_path / "Workbench" / "PLAN-ZZ0_x.md"
    _write_plan(plan_path, pipeline_phase="outcome-verifying")

    expected = {
        "Workbench/PLAN-ZZ0_x.md": {"pipeline_phase": "executing"},
    }

    side_effects = [
        _fetch_ok(),
        _rev_parse_ok("main"),
        _symbolic_ref_ok("origin", "main"),
        _rev_list_ok(0, 0),
        _gh_pr_list_ok([]),
        _rev_list_ok(0, 0),
    ]
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(
            str(tmp_path),
            expected_plan_states=expected,
            plan_glob="Workbench/PLAN-*.md",
        )

    assert result["plan_drift"], f"expected non-empty plan_drift, got {result['plan_drift']}"
    assert len(result["plan_drift"]) == 1
    pd = result["plan_drift"][0]
    assert pd["field"] == "pipeline_phase"
    assert pd["expected"] == "executing"
    assert pd["actual"] == "outcome-verifying"
    assert result["drift"] is True
    assert "PLAN-ZZ0_x.md" in result["summary"]


PLAN_BLOCK_OUTCOME_TEMPLATE = """\
---
schema_version: 2
title: Test PLAN
type: plan
status: in-progress
pipeline_phase: outcome-verifying
last_executor_outcome:
  outcome: success
  outcome_subtype: done
  executed: true
  diagnostics_summary: 'All Steps applied.'
verification_state:
  state_pass: 14
---

## Objective
Test PLAN for unit tests.
"""


def test_plan_drift_block_mapping_outcome(tmp_path):
    """8c: the executor writes last_executor_outcome as a block mapping, and the handoff
    baseline records its nested `outcome:` scalar. Reading the key line alone yields None
    and fires false drift on every executed PLAN, every resume."""
    plan_path = tmp_path / "Workbench" / "PLAN-ZZ2_x.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(PLAN_BLOCK_OUTCOME_TEMPLATE, encoding="utf-8")

    expected = {
        "Workbench/PLAN-ZZ2_x.md": {
            "pipeline_phase": "outcome-verifying",
            "status": "in-progress",
            "last_executor_outcome": "success",
        },
    }

    side_effects = [
        _fetch_ok(),
        _rev_parse_ok("main"),
        _symbolic_ref_ok("origin", "main"),
        _rev_list_ok(0, 0),
        _gh_pr_list_ok([]),
        _rev_list_ok(0, 0),
    ]
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(
            str(tmp_path),
            expected_plan_states=expected,
            plan_glob="Workbench/PLAN-*.md",
        )

    states = result["plan_states"]["Workbench/PLAN-ZZ2_x.md"]
    assert states["last_executor_outcome"] == "success"
    # outcome_subtype must not satisfy the lookup for outcome.
    assert states["pipeline_phase"] == "outcome-verifying"
    assert result["plan_drift"] == [], f"expected no drift, got {result['plan_drift']}"
    assert result["drift"] is False

    # A genuine mismatch on the nested scalar must still fire.
    expected["Workbench/PLAN-ZZ2_x.md"]["last_executor_outcome"] = "failure"
    side_effects = [
        _fetch_ok(),
        _rev_parse_ok("main"),
        _symbolic_ref_ok("origin", "main"),
        _rev_list_ok(0, 0),
        _gh_pr_list_ok([]),
        _rev_list_ok(0, 0),
    ]
    with patch("resume_preflight.subprocess.run", side_effect=side_effects):
        result = check_resume_drift(
            str(tmp_path),
            expected_plan_states=expected,
            plan_glob="Workbench/PLAN-*.md",
        )
    assert len(result["plan_drift"]) == 1
    assert result["plan_drift"][0]["field"] == "last_executor_outcome"
    assert result["drift"] is True


# ---------------------------------------------------------------------------
# Tests 9a-9d: Real-git-repo tests (not mocked; skipped if git not on PATH)
# ---------------------------------------------------------------------------

def _git(args, cwd, check=True):
    """Run a git command in a directory; raises CalledProcessError on failure if check=True."""
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=check,
    )


def _setup_real_repos(tmp_path):
    """
    Set up a bare 'origin' repo and a work repo with an initial commit on 'main'.

    Returns (origin_path, work_path, default_branch).
    The work repo has:
      - remote 'origin' pointing at the bare repo
      - git fetch completed (refs/remotes/origin/main exists)
      - refs/remotes/origin/HEAD set via 'git remote set-head origin -a'
        so that symbolic-ref resolution works deterministically.
    """
    if shutil.which("git") is None:
        return None, None, None

    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    origin.mkdir()
    work.mkdir()

    # Init bare origin
    _git(["init", "--bare", "--initial-branch=main", str(origin)], cwd=tmp_path, check=False)
    # Some git versions don't support --initial-branch; fall back
    try:
        _git(["init", "--bare", str(origin)], cwd=tmp_path, check=False)
    except Exception:
        pass

    # Init work repo
    _git(["init", str(work)], cwd=tmp_path, check=False)
    _git(["config", "user.email", "test@example.com"], cwd=work)
    _git(["config", "user.name", "Test User"], cwd=work)

    # Make initial commit on work (default branch: main or whatever git named it)
    readme = work / "README.md"
    readme.write_text("initial", encoding="utf-8")
    _git(["add", "README.md"], cwd=work)
    _git(["commit", "-m", "initial commit"], cwd=work)

    # Figure out what the local default branch is named
    default_result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(work),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    default_branch = default_result.stdout.strip() or "main"

    # Add remote and push
    _git(["remote", "add", "origin", str(origin)], cwd=work)
    _git(["push", "-u", "origin", default_branch], cwd=work)

    # Populate refs/remotes/origin/HEAD so symbolic-ref works
    _git(["remote", "set-head", "origin", "-a"], cwd=work, check=False)

    return origin, work, default_branch


def test_real_git_non_ff_merge(tmp_path):
    """9a: True non-ff merge -> merged_into_default=True, drift=True."""
    if shutil.which("git") is None:
        return  # Skip if git not available

    origin, work, default_branch = _setup_real_repos(tmp_path)
    if work is None:
        return

    # Create feature branch with one commit
    _git(["checkout", "-b", "feature-branch"], cwd=work)
    feat_file = work / "feature.txt"
    feat_file.write_text("feature change", encoding="utf-8")
    _git(["add", "feature.txt"], cwd=work)
    _git(["commit", "-m", "feature commit"], cwd=work)

    # Merge feature into default with --no-ff
    _git(["checkout", default_branch], cwd=work)
    _git(["merge", "--no-ff", "feature-branch", "-m", "Merge feature-branch"], cwd=work)

    # Push the default branch (so origin/main has the merge commit)
    _git(["push", "origin", default_branch], cwd=work)

    # Check out the feature branch (it is now an ancestor of origin/main)
    _git(["checkout", "feature-branch"], cwd=work)

    # No gh available in real git test; heuristic path is taken
    result = check_resume_drift(
        str(work),
        remote="origin",
        default_branch=default_branch,
    )

    assert result["default_compare"]["merged_into_default"] is True, (
        f"Expected merged_into_default=True for non-ff merge, got {result['default_compare']}"
    )
    assert result["drift"] is True


def test_real_git_behind_empty_false_positive(tmp_path):
    """9b: Behind-empty branch (disclosed FALSE POSITIVE) -> merged_into_default=True.

    A feature branch with NO commits while default advances: the strictly-behind
    topology is identical to a genuine merge, so the heuristic fires.
    This is the disclosed false positive (J2); assert True + comment.
    """
    if shutil.which("git") is None:
        return

    origin, work, default_branch = _setup_real_repos(tmp_path)
    if work is None:
        return

    # Create feature branch at current HEAD (no feature commits)
    _git(["checkout", "-b", "empty-feature"], cwd=work)

    # Push a new commit to the default branch (advancing origin/main)
    _git(["checkout", default_branch], cwd=work)
    advance_file = work / "advance.txt"
    advance_file.write_text("advance", encoding="utf-8")
    _git(["add", "advance.txt"], cwd=work)
    _git(["commit", "-m", "advance default"], cwd=work)
    _git(["push", "origin", default_branch], cwd=work)

    # Check out the empty feature branch (it is strictly behind default, no unique commits)
    _git(["checkout", "empty-feature"], cwd=work)

    result = check_resume_drift(
        str(work),
        remote="origin",
        default_branch=default_branch,
    )

    # DISCLOSED FALSE POSITIVE: the heuristic fires here even though the branch
    # was never merged. This is topologically identical to a genuine non-ff merge
    # and is NOT guarded in code (blocker S603 resolution: the earlier >= 1 unique
    # commit guard was self-contradictory). Asserted True as a known positive.
    assert result["default_compare"]["merged_into_default"] is True, (
        f"Expected True (disclosed behind-empty false positive), got {result['default_compare']}"
    )


def test_real_git_ahead_diverged_not_merged(tmp_path):
    """9c: Feature branch with unique commits -> merged_into_default=False (correct negative)."""
    if shutil.which("git") is None:
        return

    origin, work, default_branch = _setup_real_repos(tmp_path)
    if work is None:
        return

    # Create feature branch and add a commit
    _git(["checkout", "-b", "ahead-feature"], cwd=work)
    feat_file = work / "unique.txt"
    feat_file.write_text("unique change", encoding="utf-8")
    _git(["add", "unique.txt"], cwd=work)
    _git(["commit", "-m", "unique feature commit"], cwd=work)

    result = check_resume_drift(
        str(work),
        remote="origin",
        default_branch=default_branch,
    )

    assert result["default_compare"]["merged_into_default"] is False, (
        f"Expected merged_into_default=False for unmerged ahead branch, got {result['default_compare']}"
    )


def test_real_git_squash_merge_false_negative(tmp_path):
    """9d: Squash-merge (disclosed FALSE NEGATIVE) -> merged_into_default=False.

    A squash lands a NEW commit on default; the feature tip is NOT an ancestor of it.
    The heuristic does not fire (rev-list <default>..HEAD is non-empty).
    Assert False + comment on the disclosed squash-merge false negative.
    """
    if shutil.which("git") is None:
        return

    origin, work, default_branch = _setup_real_repos(tmp_path)
    if work is None:
        return

    # Create feature branch with a commit
    _git(["checkout", "-b", "squash-feature"], cwd=work)
    feat_file = work / "squash_change.txt"
    feat_file.write_text("squash change", encoding="utf-8")
    _git(["add", "squash_change.txt"], cwd=work)
    _git(["commit", "-m", "squash feature commit"], cwd=work)

    # Squash-merge onto default (the feature tip is NOT an ancestor of the squash commit)
    _git(["checkout", default_branch], cwd=work)
    _git(["merge", "--squash", "squash-feature"], cwd=work)
    _git(["commit", "-m", "Squash merge squash-feature"], cwd=work)
    _git(["push", "origin", default_branch], cwd=work)

    # Check out the feature branch (its tip is NOT an ancestor of the squash commit on default)
    _git(["checkout", "squash-feature"], cwd=work)

    result = check_resume_drift(
        str(work),
        remote="origin",
        default_branch=default_branch,
    )

    # DISCLOSED FALSE NEGATIVE: the squash creates a new commit not ancestored by the
    # feature tip, so rev-list <default>..HEAD is non-empty and the heuristic does not fire.
    # This means a squash-merged branch is NOT auto-warned to restart.
    assert result["default_compare"]["merged_into_default"] is False, (
        f"Expected False (disclosed squash-merge false negative), got {result['default_compare']}"
    )


# ---------------------------------------------------------------------------
# Self-run harness - same pattern as test_push_guard.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_clean_state,
        test_behind_remote_drift,
        test_diverged_drift,
        test_merged_pr_authoritative,
        test_dynamic_default_branch_master,
        test_dynamic_default_branch_fallback,
        test_fetch_failure_fail_open,
        test_gh_unavailable,
        test_plan_drift_baseline_mismatch,
        test_real_git_non_ff_merge,
        test_real_git_behind_empty_false_positive,
        test_real_git_ahead_diverged_not_merged,
        test_real_git_squash_merge_false_negative,
    ]
    failures = 0
    for t in tests:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = pathlib.Path(tmp)
            try:
                t(tmp_p)
                print(f"PASS: {t.__name__}")
            except AssertionError as e:
                print(f"FAIL: {t.__name__}: {e}")
                failures += 1
            except Exception as e:
                print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")
                failures += 1
    sys.exit(0 if failures == 0 else 1)
