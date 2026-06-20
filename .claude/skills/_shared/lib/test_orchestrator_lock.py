"""
test_orchestrator_lock.py — Unit tests for orchestrator_lock.py.

Tests the advisory per-repo orchestrator lock introduced by PLAN-AF1
(Single-orchestrator guard: pre-push divergence check + advisory repo lock,
2026-06-20).

Coverage:
  1. Acquire when absent:     lock file does not exist → acquired=True, file written.
  2. Acquire when held fresh: lock exists, age < TTL   → acquired=False, no write.
  3. Acquire when stale:      lock exists, age >= TTL  → acquired=True, file overwritten.
  4. Release idempotency:     release() on absent file → no exception;
                               release() on present file → file deleted.
  5. read_lock — absent:      returns None.
  6. read_lock — malformed:   file present but not valid JSON → returns None.
  7. read_lock — valid:       returns parsed dict.

All tests use tmp_path for filesystem operations.
All staleness logic uses injected now= argument — no sleeping.
All tests are synchronous.

Run: python -m pytest .claude/skills/_shared/lib/test_orchestrator_lock.py
"""

import datetime
import json
import pathlib
import sys

# Make the parent dir importable regardless of cwd
_HERE = pathlib.Path(__file__).resolve().parent
_PARENT = _HERE.parent  # .claude/skills/_shared/
sys.path.insert(0, str(_PARENT))

from orchestrator_lock import (  # noqa: E402
    LOCK_TTL_SECONDS,
    acquire,
    read_lock,
    release,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC = datetime.timezone.utc


def _workbench(tmp_path):
    """Ensure Workbench/ exists under tmp_path and return tmp_path (repo_root)."""
    (tmp_path / "Workbench").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _lock_file(tmp_path):
    """Return the expected lock file Path."""
    return tmp_path / "Workbench" / ".orchestrator.lock"


def _write_lock(tmp_path, data):
    """Write a raw lock JSON dict to disk."""
    _workbench(tmp_path)
    _lock_file(tmp_path).write_text(json.dumps(data), encoding="utf-8")


# A known base time for injection
_BASE_NOW = datetime.datetime(2026, 6, 20, 12, 0, 0, tzinfo=_UTC)


# ---------------------------------------------------------------------------
# Test 1: acquire when absent
# ---------------------------------------------------------------------------

def test_acquire_when_absent(tmp_path):
    """1: lock file does not exist → acquired=True, holder has required fields, file written."""
    _workbench(tmp_path)
    result = acquire(tmp_path, phase="executing", plan="PLAN-AF1", now=_BASE_NOW)
    assert result["acquired"] is True, f"expected acquired=True, got {result}"
    holder = result["holder"]
    assert "acquired_at" in holder, f"holder missing acquired_at: {holder}"
    assert "marker" in holder, f"holder missing marker: {holder}"
    assert holder["phase"] == "executing"
    assert holder["plan"] == "PLAN-AF1"
    # File must exist on disk
    assert _lock_file(tmp_path).exists(), "lock file was not written"
    on_disk = json.loads(_lock_file(tmp_path).read_text(encoding="utf-8"))
    assert on_disk["acquired_at"] == holder["acquired_at"]


# ---------------------------------------------------------------------------
# Test 2: acquire when held (fresh)
# ---------------------------------------------------------------------------

def test_acquire_when_held_fresh(tmp_path):
    """2: existing lock age < TTL (30 s) → acquired=False, no file write."""
    acquired_at = _BASE_NOW - datetime.timedelta(seconds=30)
    existing = {
        "acquired_at": acquired_at.isoformat(),
        "phase": "drafted",
        "plan": "PLAN-ZZ9",
        "marker": "aabbccdd",
    }
    _write_lock(tmp_path, existing)
    mtime_before = _lock_file(tmp_path).stat().st_mtime

    # Inject now = _BASE_NOW (30 s after acquired_at, well within TTL)
    result = acquire(tmp_path, now=_BASE_NOW)
    assert result["acquired"] is False, f"expected acquired=False, got {result}"
    assert result["holder"]["marker"] == "aabbccdd", "holder should be the existing lock"
    # File must NOT have been overwritten
    mtime_after = _lock_file(tmp_path).stat().st_mtime
    assert mtime_before == mtime_after, "lock file was unexpectedly overwritten"


# ---------------------------------------------------------------------------
# Test 3: acquire when stale
# ---------------------------------------------------------------------------

def test_acquire_when_stale(tmp_path):
    """3: existing lock age > TTL (3700 s) → acquired=True, file overwritten."""
    acquired_at = _BASE_NOW - datetime.timedelta(seconds=3700)
    existing = {
        "acquired_at": acquired_at.isoformat(),
        "phase": "drafted",
        "plan": "PLAN-OLD",
        "marker": "oldmarker",
    }
    _write_lock(tmp_path, existing)

    # Inject now = _BASE_NOW (3700 s after acquired_at, past TTL=3600)
    result = acquire(tmp_path, phase="checking", plan="PLAN-NEW", now=_BASE_NOW)
    assert result["acquired"] is True, f"expected acquired=True (stale lock), got {result}"
    holder = result["holder"]
    assert holder["marker"] != "oldmarker", "marker should be fresh after stale overwrite"
    assert holder["plan"] == "PLAN-NEW"
    # On-disk content should reflect new lock
    on_disk = json.loads(_lock_file(tmp_path).read_text(encoding="utf-8"))
    assert on_disk["plan"] == "PLAN-NEW"


# ---------------------------------------------------------------------------
# Test 4: release idempotency
# ---------------------------------------------------------------------------

def test_release_idempotent_absent(tmp_path):
    """4a: release() on absent file → no exception."""
    _workbench(tmp_path)
    # Should not raise
    release(tmp_path)


def test_release_deletes_file(tmp_path):
    """4b: release() on present lock file → file is deleted."""
    _write_lock(tmp_path, {"acquired_at": _BASE_NOW.isoformat(), "marker": "x"})
    assert _lock_file(tmp_path).exists(), "precondition: lock file must exist"
    release(tmp_path)
    assert not _lock_file(tmp_path).exists(), "lock file should be deleted after release()"


# ---------------------------------------------------------------------------
# Test 5: read_lock — absent
# ---------------------------------------------------------------------------

def test_read_lock_absent(tmp_path):
    """5: read_lock() when no file exists → returns None."""
    _workbench(tmp_path)
    assert read_lock(tmp_path) is None


# ---------------------------------------------------------------------------
# Test 6: read_lock — malformed JSON
# ---------------------------------------------------------------------------

def test_read_lock_malformed_json(tmp_path):
    """6: lock file present but not valid JSON → returns None."""
    _workbench(tmp_path)
    _lock_file(tmp_path).write_text("this is not json{{{", encoding="utf-8")
    assert read_lock(tmp_path) is None


# ---------------------------------------------------------------------------
# Test 7: read_lock — valid
# ---------------------------------------------------------------------------

def test_read_lock_valid(tmp_path):
    """7: lock file contains valid JSON → returns parsed dict."""
    data = {
        "acquired_at": _BASE_NOW.isoformat(),
        "phase": "executing",
        "plan": "PLAN-AF1",
        "marker": "cafebabe",
    }
    _write_lock(tmp_path, data)
    result = read_lock(tmp_path)
    assert result is not None, "expected a dict, got None"
    assert result["marker"] == "cafebabe"
    assert result["plan"] == "PLAN-AF1"


if __name__ == "__main__":
    import tempfile

    tests = [
        test_acquire_when_absent,
        test_acquire_when_held_fresh,
        test_acquire_when_stale,
        test_release_idempotent_absent,
        test_release_deletes_file,
        test_read_lock_absent,
        test_read_lock_malformed_json,
        test_read_lock_valid,
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
