"""
orchestrator_lock.py — Advisory per-repo orchestrator lock for plan-pipeline.

Originating PLAN: PLAN-AF1 (Single-orchestrator guard: pre-push divergence check +
advisory repo lock, 2026-06-20).

Design decisions (PLAN-AF1):

D2 — "Repo-Lock": A gitignored local lockfile `Workbench/.orchestrator.lock` acts as
a short-lived mutex around a single synchronous dispatch walk. Acquired at the top of
a state-mutating invocation, released when the walk returns control, with a staleness
TTL so a crashed session self-clears.

D3 — "Per-Repo-Granularity": The lock is keyed on the working tree (one active
orchestrator per repo), NOT per-PLAN. Rationale: the shared-working-tree problem means
even orchestrators working different PLANs collide on git operations and intermingle
uncommitted work; and the architecture already assumes a single orchestrator
("Single conversational re-entry point", SKILL.md essential_principles) — this module
merely enforces that existing assumption mechanically.

D4 — "TTL-Tradeoff": The lock TTL is generous enough to cover a legitimately long
synchronous walk (foreground audit dispatches can take minutes) but short enough that a
crashed session self-clears in reasonable time. Default TTL: 3600 seconds (60 minutes),
defined as the module constant LOCK_TTL_SECONDS so it is tunable.

KEY DESIGN INSIGHT: the lock does NOT require any persistent session-identity concept.
Because the orchestrator is synchronous — each dispatch walk acquires on entry and
releases on return — the lock only needs to answer "is another walk in progress right
now?". A fresh timestamp plus a held marker answers that; TTL covers the crash case.

The lock intentionally does NOT span the asynchronous background-execution window.
When dispatch branch 4C dispatches the executor with run_in_background: true and
returns control, release() fires — so no lock is held while the executor runs. The
executor cannot commit or push, so the irreversible fork vector cannot originate
during that window. The D1 divergence guard (push_guard.py) is the backstop for the
irreversible part.

TTL tuning note: increase LOCK_TTL_SECONDS if legitimate synchronous walks routinely
exceed 60 minutes. Decrease only after confirming that crash-recovery latency at the
new value is acceptable for your workflow cadence.
"""

import datetime
import json
import pathlib
import secrets

LOCK_TTL_SECONDS = 3600

_LOCK_FILENAME = ".orchestrator.lock"


def _lock_path(repo_root):
    """Return the pathlib.Path for the lock file inside repo_root/Workbench/."""
    return pathlib.Path(repo_root) / "Workbench" / _LOCK_FILENAME


def acquire(repo_root, phase="", plan="", now=None):
    """Acquire the advisory orchestrator lock for the given repository.

    Parameters
    ----------
    repo_root : str or Path
        Absolute path to the repository root.
    phase : str
        The current orchestrator phase label (e.g. "executing", "drafted"). Stored in
        the lock for diagnostic display only.
    plan : str
        The PLAN ID being processed (e.g. "PLAN-AF1"). Stored in the lock for
        diagnostic display only.
    now : datetime.datetime or None
        Injection point for the "current time". When None (default), uses
        datetime.datetime.now(datetime.timezone.utc). Provide an explicit timezone-aware
        datetime to simulate staleness in unit tests without sleeping.

    Returns
    -------
    dict
        {"acquired": True,  "holder": <new lock dict>}   — lock written, walk may proceed.
        {"acquired": False, "holder": <existing lock dict>} — lock held by another walk,
            caller MUST refuse to proceed.
    """
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)

    lock_file = _lock_path(repo_root)

    # Attempt to read an existing lock
    existing = _read_raw(lock_file)

    if existing is not None and "acquired_at" in existing:
        try:
            acquired_at = datetime.datetime.fromisoformat(existing["acquired_at"])
            # Ensure both are timezone-aware for comparison
            if acquired_at.tzinfo is None:
                acquired_at = acquired_at.replace(tzinfo=datetime.timezone.utc)
            age_seconds = (now - acquired_at).total_seconds()
            if age_seconds < LOCK_TTL_SECONDS:
                # Lock is held and fresh — refuse
                return {"acquired": False, "holder": existing}
        except (ValueError, TypeError):
            # Malformed acquired_at — treat as stale, fall through to write
            pass

    # Absent, malformed JSON, missing acquired_at, or stale → write a fresh lock
    new_lock = {
        "acquired_at": now.isoformat(),
        "phase": phase,
        "plan": plan,
        "marker": secrets.token_hex(4),
    }
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(json.dumps(new_lock, indent=2), encoding="utf-8")
    return {"acquired": True, "holder": new_lock}


def release(repo_root):
    """Release the advisory orchestrator lock.

    Idempotent: no error if the lock file is already absent.

    Parameters
    ----------
    repo_root : str or Path
        Absolute path to the repository root.
    """
    _lock_path(repo_root).unlink(missing_ok=True)


def read_lock(repo_root):
    """Return the current lock dict, or None if absent or malformed.

    Parameters
    ----------
    repo_root : str or Path
        Absolute path to the repository root.

    Returns
    -------
    dict or None
        Parsed lock contents, or None if the file does not exist or is not valid JSON.
    """
    return _read_raw(_lock_path(repo_root))


def _read_raw(lock_file):
    """Internal helper: read and parse the lock file. Returns dict or None."""
    lock_file = pathlib.Path(lock_file)
    try:
        text = lock_file.read_text(encoding="utf-8", errors="replace")
        return json.loads(text)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        return None
