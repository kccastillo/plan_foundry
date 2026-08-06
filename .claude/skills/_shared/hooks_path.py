#!/usr/bin/env python3
"""
hooks_path.py - point a consumer repo's git hooks at the bundle's hooks dir.

Single source of truth for the `core.hooksPath` wiring, shared by
`init-plan-foundry` (fresh install) and `plan-foundry-sync` (converge an
existing install).

Why core.hooksPath and not a copy into .git/hooks
-------------------------------------------------
PLAN-AD2 D10 (Hooks Path Not Hook Copy). `plan-foundry-sync` already overwrites
`.claude/hooks/*` on every sync, so pointing git at that directory means a
bundle update upgrades live hook behaviour with no companion change to the
install or sync skills. An install-time copy into `.git/hooks/` goes stale
unless sync re-copies every time, and needs a per-contributor install run.

D10's accepted weakness is that `core.hooksPath` is repo-local, untracked git
config, so every fresh clone needs the one-time write. Applying this from sync
as well as from init narrows that window: a contributor who clones and syncs
converges without anyone remembering to re-run the installer.

Non-clobbering
--------------
A consumer who has already set `core.hooksPath` to something of their own keeps
it. We report the conflict rather than overwriting - silently redirecting a
repo's hooks would be a considerably worse failure than not wiring ours.

Ordering constraint
-------------------
This must not run before the line-ending pin is in place. A CRLF-mangled hook
fails on every Windows consumer while exiting 0 on all failure paths, so a
broken hook and a working one are outwardly identical. Wiring first would ship
exactly that. See _shared/gitattributes_pin.py and
FOUNDRYREQ-plan_foundry_dev-20260727-1350.
"""

import pathlib
import subprocess

HOOKS_PATH_VALUE = ".claude/hooks"


def _git(target_root: pathlib.Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(target_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout.strip()


def ensure_hooks_path(target_root: pathlib.Path) -> tuple[str, str]:
    """
    Set `core.hooksPath` to `.claude/hooks` for the repo at target_root.

    Returns (status, note):
      PASS    - the value was written.
      SKIPPED - already correct, or target is not a git repo (nothing to wire).
      FAIL    - a conflicting consumer-set value is present; left untouched.

    Idempotent. Never overwrites a value the consumer chose.
    """
    rc, _ = _git(target_root, "rev-parse", "--git-dir")
    if rc != 0:
        return "SKIPPED", "not a git repository - no hooks to wire"

    rc, current = _git(target_root, "config", "--local", "core.hooksPath")
    if rc == 0 and current:
        if current == HOOKS_PATH_VALUE:
            return "SKIPPED", f"core.hooksPath already {HOOKS_PATH_VALUE}"
        return (
            "FAIL",
            f"core.hooksPath is already set to {current!r} - left untouched. "
            f"plan_foundry's commit-msg hook will not run until this points at "
            f"{HOOKS_PATH_VALUE!r} or its behaviour is merged into the existing path.",
        )

    rc, _ = _git(target_root, "config", "--local", "core.hooksPath", HOOKS_PATH_VALUE)
    if rc != 0:
        return "FAIL", "git config write failed"
    return "PASS", f"core.hooksPath set to {HOOKS_PATH_VALUE}"


def check_hooks_path(target_root: pathlib.Path) -> str:
    """Return the repo's current core.hooksPath, or '' if unset. Read-only."""
    rc, current = _git(target_root, "config", "--local", "core.hooksPath")
    return current if rc == 0 else ""
