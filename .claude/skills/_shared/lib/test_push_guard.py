"""
test_push_guard.py — Unit tests for check_push_safe().

Tests the pre-push divergence guard introduced by PLAN-AF1
(Single-orchestrator guard: pre-push divergence check + advisory repo lock,
2026-06-20).

Coverage:
  1. Safe — in sync:         ahead=0, behind=0  → safe=True
  2. Safe — ahead only:      ahead=3, behind=0  → safe=True
  3. Unsafe — behind:        ahead=0, behind=2  → safe=False, reason names counts + remote/branch
  4. Unsafe — diverged:      ahead=1, behind=1  → safe=False
  5. Skipped — fetch fail:   git fetch non-zero → safe=True, reason contains "skipped"
  6. Skipped — missing ref:  rev-list fails     → safe=True, reason contains "skipped"

Run: python -m pytest .claude/skills/_shared/lib/test_push_guard.py
"""

import pathlib
import sys
import types
from unittest.mock import MagicMock, patch

# Make the parent dir importable regardless of cwd
_HERE = pathlib.Path(__file__).resolve().parent
_PARENT = _HERE.parent  # .claude/skills/_shared/
sys.path.insert(0, str(_PARENT))

from push_guard import check_push_safe  # noqa: E402


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
# Test 1: safe — in sync (ahead=0, behind=0)
# ---------------------------------------------------------------------------

def test_safe_in_sync(tmp_path):
    """1: behind=0, ahead=0 → safe=True."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_ok(0, 0)]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True, f"expected safe=True, got {result}"
    assert result["behind"] == 0
    assert result["ahead"] == 0


# ---------------------------------------------------------------------------
# Test 2: safe — ahead only (ahead=3, behind=0)
# ---------------------------------------------------------------------------

def test_safe_ahead_only(tmp_path):
    """2: behind=0, ahead=3 → safe=True."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_ok(0, 3)]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True, f"expected safe=True, got {result}"
    assert result["behind"] == 0
    assert result["ahead"] == 3


# ---------------------------------------------------------------------------
# Test 3: unsafe — behind (ahead=0, behind=2)
# ---------------------------------------------------------------------------

def test_unsafe_behind(tmp_path):
    """3: behind=2, ahead=0 → safe=False; reason names behind/ahead + remote/branch."""
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
# Test 4: unsafe — diverged (ahead=1, behind=1)
# ---------------------------------------------------------------------------

def test_unsafe_diverged(tmp_path):
    """4: behind=1, ahead=1 → safe=False."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_ok(1, 1)]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is False, f"expected safe=False, got {result}"
    assert result["behind"] == 1
    assert result["ahead"] == 1


# ---------------------------------------------------------------------------
# Test 5: skipped — fetch failure
# ---------------------------------------------------------------------------

def test_skipped_fetch_failure(tmp_path):
    """5: git fetch exits non-zero → safe=True, reason contains 'skipped'."""
    with patch("push_guard.subprocess.run", return_value=_fetch_fail()):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True, f"expected safe=True, got {result}"
    assert "skipped" in result["reason"], f"reason missing 'skipped': {result['reason']!r}"


# ---------------------------------------------------------------------------
# Test 6: skipped — missing remote tracking ref
# ---------------------------------------------------------------------------

def test_skipped_missing_tracking_ref(tmp_path):
    """6: rev-list fails (no tracking ref) → safe=True, reason contains 'skipped'."""
    side_effects = [_fetch_ok(), _rev_parse_ok("main"), _rev_list_fail()]
    with patch("push_guard.subprocess.run", side_effect=side_effects):
        result = check_push_safe(str(tmp_path))
    assert result["safe"] is True, f"expected safe=True, got {result}"
    assert "skipped" in result["reason"], f"reason missing 'skipped': {result['reason']!r}"


if __name__ == "__main__":
    import tempfile

    tests = [
        test_safe_in_sync,
        test_safe_ahead_only,
        test_unsafe_behind,
        test_unsafe_diverged,
        test_skipped_fetch_failure,
        test_skipped_missing_tracking_ref,
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
