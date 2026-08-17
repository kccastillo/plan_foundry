"""
test_push_guard.py - Unit tests for check_push_safe() and .claude/hooks/pre-push.

Tests the pre-push divergence guard introduced by PLAN-AF1
(Single-orchestrator guard: pre-push divergence check + advisory repo lock,
2026-06-20), and its return-dict contract repair plus the new `pre-push` git
hook added by PLAN-AM0 (Bind push guards to pushing, 2026-08-16).

Pure-function coverage (drives check_push_safe() directly via a mocked
subprocess.run):
  1. Safe - in sync:         ahead=0, behind=0     -> safe=True
  2. Safe - ahead only:      ahead=3, behind=0     -> safe=True
  3. Unsafe - behind:        ahead=0, behind=2     -> safe=False, reason names counts + remote/branch
  4. Unsafe - diverged:      ahead=1, behind=1     -> safe=False
  5. Skipped - fetch fail:   git fetch non-zero    -> safe=True, ahead/behind None
  6. Skipped - missing ref:  rev-list fails        -> safe=True, ahead/behind None
  7-16. One test_safeverdict_<name> per `# safeverdict:` marker in push_guard.py
        (PLAN-AM0 D3, marker parity), asserting each site's ahead/behind contract.

Hook-level coverage (PLAN-AM0 Step 5, real subprocess `git push` through the
real .claude/hooks/pre-push script - no mocking):
  - test_hook_refuses_when_behind
  - test_hook_allows_when_ahead
  - test_hook_degrades_without_guard_module

Run: python -m pytest .claude/skills/_shared/lib/test_push_guard.py
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
from unittest.mock import MagicMock, patch

# Make the parent dir importable regardless of cwd
_HERE = pathlib.Path(__file__).resolve().parent
_PARENT = _HERE.parent  # .claude/skills/_shared/
sys.path.insert(0, str(_PARENT))

from push_guard import check_push_safe  # noqa: E402

# _PARENT -> skills -> .claude -> repo_root, matching the resolution
# test_foundryreq_deletion_guard.py already uses in this same directory.
_REPO_ROOT = _PARENT.parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"


def _make_completed_process(returncode=0, stdout="", stderr=""):
    """Return a minimal CompletedProcess-alike MagicMock."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _fetch_ok():
    """Return a subprocess.run mock result for a successful git fetch."""
    return _make_completed_process(returncode=0, stdout="", stderr="")


def _rev_parse_ok(branch="main"):
    """Return a subprocess.run mock result for git rev-parse --abbrev-ref HEAD."""
    return _make_completed_process(returncode=0, stdout=branch + "\n", stderr="")


def _rev_list_ok(behind, ahead):
    """Return a subprocess.run mock result for git rev-list --left-right --count."""
    return _make_completed_process(returncode=0, stdout=f"{behind}\t{ahead}\n", stderr="")


def _rev_list_fail():
    """Return a subprocess.run mock result simulating a missing remote tracking ref."""
    return _make_completed_process(
        returncode=128,
        stdout="",
        stderr="fatal: no upstream configured for branch 'main'",
    )


def _fetch_fail():
    """Return a subprocess.run mock result simulating a failed git fetch."""
    return _make_completed_process(
        returncode=128,
        stdout="",
        stderr="fatal: unable to connect to remote",
    )


# ---------------------------------------------------------------------------
# Test 1: safe - in sync (ahead=0, behind=0)
# ---------------------------------------------------------------------------

def test_safe_in_sync(tmp_path):
    """1: behind=0, ahead=0 -> safe=True."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_ok(0, 0)]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True, f"expected safe=True, got {result}"
    assert result["behind"] == 0
    assert result["ahead"] == 0
    # Genuinely measured counts are int, not None - the distinction D4 exists for.
    assert isinstance(result["behind"], int)
    assert isinstance(result["ahead"], int)


# ---------------------------------------------------------------------------
# Test 2: safe - ahead only (ahead=3, behind=0)
# ---------------------------------------------------------------------------

def test_safe_ahead_only(tmp_path):
    """2: behind=0, ahead=3 -> safe=True."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_ok(0, 3)]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True, f"expected safe=True, got {result}"
    assert result["behind"] == 0
    assert result["ahead"] == 3
    assert isinstance(result["behind"], int)
    assert isinstance(result["ahead"], int)


# ---------------------------------------------------------------------------
# Test 3: unsafe - behind (ahead=0, behind=2)
# ---------------------------------------------------------------------------

def test_unsafe_behind(tmp_path):
    """3: behind=2, ahead=0 -> safe=False; reason names behind/ahead + remote/branch."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_ok(2, 0)]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path), remote="origin")
    assert result["safe"] is False, f"expected safe=False, got {result}"
    assert result["behind"] == 2
    assert result["ahead"] == 0
    # reason must name the counts and the remote/branch
    assert "2" in result["reason"], f"reason missing behind count: {result['reason']!r}"
    assert "origin" in result["reason"], f"reason missing remote: {result['reason']!r}"
    assert "main" in result["reason"], f"reason missing branch: {result['reason']!r}"


# ---------------------------------------------------------------------------
# Test 4: unsafe - diverged (ahead=1, behind=1)
# ---------------------------------------------------------------------------

def test_unsafe_diverged(tmp_path):
    """4: behind=1, ahead=1 -> safe=False."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_ok(1, 1)]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is False, f"expected safe=False, got {result}"
    assert result["behind"] == 1
    assert result["ahead"] == 1


# ---------------------------------------------------------------------------
# Test 5: skipped - fetch failure
# ---------------------------------------------------------------------------

def test_skipped_fetch_failure(tmp_path):
    """5: git fetch exits non-zero -> safe=True, reason contains 'skipped', ahead/behind None."""
    with patch("push_guard.subprocess.run", return_value=_fetch_fail()):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True, f"expected safe=True, got {result}"
    assert "skipped" in result["reason"], f"reason missing 'skipped': {result['reason']!r}"
    assert result["ahead"] is None
    assert result["behind"] is None


# ---------------------------------------------------------------------------
# Test 6: skipped - missing remote tracking ref
# ---------------------------------------------------------------------------

def test_skipped_missing_tracking_ref(tmp_path):
    """6: rev-list fails (no tracking ref) -> safe=True, reason contains 'skipped', ahead/behind None."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_fail()]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True, f"expected safe=True, got {result}"
    assert "skipped" in result["reason"], f"reason missing 'skipped': {result['reason']!r}"
    assert result["ahead"] is None
    assert result["behind"] is None


# ---------------------------------------------------------------------------
# Tests 7-16: one test_safeverdict_<name> per `# safeverdict:` marker in
# push_guard.py (PLAN-AM0 D3, marker parity). Each drives check_push_safe()
# down exactly the return site its marker names.
# ---------------------------------------------------------------------------

def test_safeverdict_fetch_failure(tmp_path):
    """Marker fetch_failure: git fetch exits non-zero -> safe=True, ahead/behind None."""
    with patch("push_guard.subprocess.run", return_value=_fetch_fail()):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True
    assert result["ahead"] is None
    assert result["behind"] is None


def test_safeverdict_fetch_timeout(tmp_path):
    """Marker fetch_timeout: git fetch raises TimeoutExpired -> safe=True, ahead/behind None."""
    side_effects = [subprocess.TimeoutExpired(cmd=["git", "fetch", "origin"], timeout=30)]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True
    assert result["ahead"] is None
    assert result["behind"] is None


def test_safeverdict_git_unavailable(tmp_path):
    """Marker git_unavailable: git fetch raises OSError -> safe=True, ahead/behind None."""
    side_effects = [OSError("git executable not found")]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True
    assert result["ahead"] is None
    assert result["behind"] is None


def test_safeverdict_branch_unresolved(tmp_path):
    """Marker branch_unresolved: rev-parse exits non-zero -> safe=True, ahead/behind None."""
    branch_fail = _make_completed_process(
        returncode=128, stdout="", stderr="fatal: not a git repository"
    )
    side_effects = [_fetch_ok(), branch_fail]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True
    assert result["ahead"] is None
    assert result["behind"] is None


def test_safeverdict_branch_resolution_error(tmp_path):
    """Marker branch_resolution_error: rev-parse raises OSError -> safe=True, ahead/behind None."""
    side_effects = [_fetch_ok(), OSError("rev-parse failed")]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True
    assert result["ahead"] is None
    assert result["behind"] is None


def test_safeverdict_tracking_ref_missing(tmp_path):
    """Marker tracking_ref_missing: rev-list exits non-zero -> safe=True, ahead/behind None."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_fail()]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True
    assert result["ahead"] is None
    assert result["behind"] is None


def test_safeverdict_rev_list_failure(tmp_path):
    """Marker rev_list_failure: rev-list raises OSError -> safe=True, ahead/behind None."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), OSError("rev-list failed")]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True
    assert result["ahead"] is None
    assert result["behind"] is None


def test_safeverdict_unexpected_revlist_output(tmp_path):
    """Marker unexpected_revlist_output: rev-list stdout is not two tokens -> safe=True, ahead/behind None."""
    bad_output = _make_completed_process(returncode=0, stdout="not-two-ints\n", stderr="")
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), bad_output]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True
    assert result["ahead"] is None
    assert result["behind"] is None


def test_safeverdict_unparseable_revlist_integers(tmp_path):
    """Marker unparseable_revlist_integers: rev-list returns two non-integer tokens -> safe=True, ahead/behind None."""
    bad_output = _make_completed_process(returncode=0, stdout="abc\txyz\n", stderr="")
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), bad_output]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True
    assert result["ahead"] is None
    assert result["behind"] is None


def test_safeverdict_in_sync_or_ahead(tmp_path):
    """Marker in_sync_or_ahead: behind=0 -> safe=True, ahead/behind are real measured ints."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_ok(0, 2)]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True
    assert result["ahead"] == 2
    assert result["behind"] == 0
    assert isinstance(result["ahead"], int)
    assert isinstance(result["behind"], int)


# ---------------------------------------------------------------------------
# Hook-level tests: exercise .claude/hooks/pre-push as a real subprocess
# through a real `git push`, no mocking. Fixture shape mirrors
# test_foundryreq_deletion_guard.py's hook-level tests in this same
# directory: a self-managed tempfile.TemporaryDirectory(), git init -q, and
# git config for user.name/user.email/commit.gpgsign in every throwaway repo.
# ---------------------------------------------------------------------------

def _configure_identity(root: pathlib.Path) -> None:
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(root), capture_output=True, check=True)


def _init_repo(root: pathlib.Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(root), capture_output=True, check=True)
    _configure_identity(root)


def _setup_tracking_repo(root: pathlib.Path):
    """Build a bare 'origin', a local working repo wired to it via
    core.hooksPath, and a second clone used only to place commits onto
    origin. Establishes a first commit + push in the local repo so a remote
    tracking ref exists before any assertion runs - without it,
    check_push_safe() takes its missing-tracking-ref skip on every call and
    a test asserting the hook allows/refuses a push would pass while
    exercising the skip path instead of the path it is named for.

    Returns (bare, local, clone2, branch).
    """
    bare = root / "origin.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", "-q"], cwd=str(bare), capture_output=True, check=True)

    local = root / "local"
    local.mkdir()
    _init_repo(local)
    subprocess.run(
        ["git", "config", "core.hooksPath", _HOOKS_DIR.as_posix()],
        cwd=str(local), capture_output=True, check=True,
    )
    subprocess.run(["git", "remote", "add", "origin", bare.as_posix()], cwd=str(local), capture_output=True, check=True)

    (local / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(local), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=str(local), capture_output=True, check=True)

    branch_result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(local), capture_output=True, encoding="utf-8", errors="replace", check=True,
    )
    branch = branch_result.stdout.strip()

    # The hook is active for this push and permits it through
    # check_push_safe()'s missing-tracking-ref skip; origin/<branch> exists
    # afterwards.
    push_result = subprocess.run(
        ["git", "push", "origin", branch],
        cwd=str(local), capture_output=True, encoding="utf-8", errors="replace",
    )
    assert push_result.returncode == 0, (push_result.stdout, push_result.stderr)

    clone2 = root / "clone2"
    subprocess.run(["git", "clone", "-q", bare.as_posix(), str(clone2)], capture_output=True, check=True)
    _configure_identity(clone2)

    return bare, local, clone2, branch


def test_hook_refuses_when_behind():
    """The hook refuses a push whose HEAD branch is behind origin, exercised
    through a real subprocess `git push` against the actual
    .claude/hooks/pre-push script."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        bare, local, clone2, branch = _setup_tracking_repo(root)

        # Put a commit onto origin from the second clone, so origin holds a
        # commit the local repository lacks.
        (clone2 / "from-clone2.txt").write_text("remote-only\n", encoding="utf-8")
        subprocess.run(["git", "add", "from-clone2.txt"], cwd=str(clone2), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "remote commit"], cwd=str(clone2), capture_output=True, check=True)
        clone_push = subprocess.run(
            ["git", "push", "origin", branch], cwd=str(clone2), capture_output=True, encoding="utf-8", errors="replace",
        )
        assert clone_push.returncode == 0, (clone_push.stdout, clone_push.stderr)

        # Commit once more locally, then try to push - local is now behind origin.
        (local / "from-local.txt").write_text("local-only\n", encoding="utf-8")
        subprocess.run(["git", "add", "from-local.txt"], cwd=str(local), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "local commit"], cwd=str(local), capture_output=True, check=True)

        result = subprocess.run(
            ["git", "push", "origin", branch], cwd=str(local), capture_output=True, encoding="utf-8", errors="replace",
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "behind" in combined, f"guard refusal text not found in: {combined!r}"


def test_hook_allows_when_ahead():
    """The hook allows a push whose HEAD branch is only ahead of origin (no
    remote-only commits), exercised through a real subprocess `git push`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        bare, local, clone2, branch = _setup_tracking_repo(root)

        (local / "ahead-only.txt").write_text("ahead\n", encoding="utf-8")
        subprocess.run(["git", "add", "ahead-only.txt"], cwd=str(local), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "ahead-only commit"], cwd=str(local), capture_output=True, check=True)

        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(local), capture_output=True, encoding="utf-8", errors="replace", check=True,
        ).stdout.strip()

        result = subprocess.run(
            ["git", "push", "origin", branch], cwd=str(local), capture_output=True, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0, (result.stdout, result.stderr)

        # The bare repository's ref must have actually moved - a push that
        # succeeded because the hook never ran cannot satisfy this test.
        bare_head = subprocess.run(
            ["git", "rev-parse", branch], cwd=str(bare), capture_output=True, encoding="utf-8", errors="replace", check=True,
        ).stdout.strip()
        assert bare_head == head_sha


def test_hook_degrades_without_guard_module():
    """A local repository whose core.hooksPath points at an isolated copy of
    pre-push alone (no ../skills/_shared/push_guard.py reachable) must
    degrade to inactive and let a force-push through, even from a state the
    guard would otherwise refuse. --force is required: from a behind state
    git itself rejects a plain push as non-fast-forward, so a plain push
    exits non-zero whether the hook degraded or refused, and the assertion
    could not tell the two apart."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        bare, local, clone2, branch = _setup_tracking_repo(root)

        (clone2 / "from-clone2.txt").write_text("remote-only\n", encoding="utf-8")
        subprocess.run(["git", "add", "from-clone2.txt"], cwd=str(clone2), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "remote commit"], cwd=str(clone2), capture_output=True, check=True)
        clone_push = subprocess.run(
            ["git", "push", "origin", branch], cwd=str(clone2), capture_output=True, encoding="utf-8", errors="replace",
        )
        assert clone_push.returncode == 0, (clone_push.stdout, clone_push.stderr)

        (local / "from-local.txt").write_text("local-only\n", encoding="utf-8")
        subprocess.run(["git", "add", "from-local.txt"], cwd=str(local), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "local commit"], cwd=str(local), capture_output=True, check=True)

        isolated_hooks = root / "isolated-hooks"
        isolated_hooks.mkdir()
        shutil.copy2(_HOOKS_DIR / "pre-push", isolated_hooks / "pre-push")
        subprocess.run(
            ["git", "config", "core.hooksPath", isolated_hooks.resolve().as_posix()],
            cwd=str(local), capture_output=True, check=True,
        )

        result = subprocess.run(
            ["git", "push", "--force", "origin", branch], cwd=str(local), capture_output=True, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        combined = result.stdout + result.stderr
        assert "behind" not in combined, f"guard refusal text unexpectedly present: {combined!r}"


if __name__ == "__main__":
    # The three hook-level tests above (test_hook_refuses_when_behind,
    # test_hook_allows_when_ahead, test_hook_degrades_without_guard_module)
    # are excluded from the list below: they manage their own tempfile
    # fixtures and take no tmp_path argument, so calling them as t(tmp_p)
    # below would raise TypeError. They are reached through pytest only.
    tests = [
        test_safe_in_sync,
        test_safe_ahead_only,
        test_unsafe_behind,
        test_unsafe_diverged,
        test_skipped_fetch_failure,
        test_skipped_missing_tracking_ref,
        test_safeverdict_fetch_failure,
        test_safeverdict_fetch_timeout,
        test_safeverdict_git_unavailable,
        test_safeverdict_branch_unresolved,
        test_safeverdict_branch_resolution_error,
        test_safeverdict_tracking_ref_missing,
        test_safeverdict_rev_list_failure,
        test_safeverdict_unexpected_revlist_output,
        test_safeverdict_unparseable_revlist_integers,
        test_safeverdict_in_sync_or_ahead,
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
    sys.exit(0 if failures == 0 else 1)
