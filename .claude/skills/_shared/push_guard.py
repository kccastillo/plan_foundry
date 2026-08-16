"""
push_guard.py - Pre-push divergence guard for plan-pipeline orchestrators.

Originating PLAN: PLAN-AF1 (Single-orchestrator guard: pre-push divergence check +
advisory repo lock, 2026-06-20). Return-dict contract repaired by PLAN-AM0
(2026-08-16): an unmeasured "ahead"/"behind" count now reports None rather than
a silent 0, so a caller can tell "measured zero" apart from "never measured".
PLAN-AM0 also added the `__main__` CLI entrypoint below, which the new
`.claude/hooks/pre-push` git hook calls.

Public function: check_push_safe(repo_root, remote="origin", branch=None) -> dict

Design (D1 - PLAN-AF1):
  Before any `git push`, the orchestrator calls check_push_safe(). If the local
  branch is BEHIND origin (remote has commits that local lacks), the function
  returns safe=False and the orchestrator MUST refuse to push. The pre-push gate
  catches the irreversible damage - a published fork - at the exact moment it
  would become irreversible.

Fail-open rationale (D1 - PLAN-AF1):
  If git fetch fails for any reason (offline, auth failure, missing remote, timeout),
  or if the remote tracking ref does not yet exist, this function returns safe=True
  (skipped). Rationale: `git push` is itself non-destructive - git rejects a
  non-fast-forward push by default without --force. The native push protection
  remains the backstop. The guard's value is catching the behind-state cleanly and
  early, not replacing git's own safety.
"""

import subprocess
import sys


def check_push_safe(repo_root, remote="origin", branch=None):
    """Check whether it is safe to push the current (or named) branch to the remote.

    Runs `git fetch` then checks ahead/behind counts via `git rev-list`. Returns a
    dict with keys:
      "safe"   : bool      - True if it is safe to push (not behind remote)
      "ahead"  : int|None  - commits local has remote lacks; None when not measured
      "behind" : int|None  - commits remote has local lacks; None when not measured
      "reason" : str       - human-readable explanation

    Fail-open: if any subprocess call fails (non-zero exit, timeout, missing git,
    missing remote tracking ref), returns safe=True with "ahead" and "behind" both
    None (PLAN-AM0) - the unmeasured count is reported as unmeasured, not silently
    as a measured zero.

    Parameters
    ----------
    repo_root : str or Path
        Absolute path to the repository root. Passed as `cwd` to subprocess calls.
    remote : str
        The git remote to check against. Default: "origin".
    branch : str or None
        The branch name to check. If None, resolved via `git rev-parse --abbrev-ref HEAD`.
    """
    repo_root = str(repo_root)

    # Step 1: git fetch <remote>
    try:
        fetch_result = subprocess.run(
            ["git", "fetch", remote],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if fetch_result.returncode != 0:
            reason = (
                f"divergence check skipped: git fetch {remote!r} exited "
                f"{fetch_result.returncode}: {fetch_result.stderr.strip()[:200]}"
            )
            # safeverdict: fetch_failure
            return {"safe": True, "ahead": None, "behind": None, "reason": reason}
    except subprocess.TimeoutExpired:
        # safeverdict: fetch_timeout
        return {
            "safe": True,
            "ahead": None,
            "behind": None,
            "reason": f"divergence check skipped: git fetch timed out after 30s",
        }
    except (FileNotFoundError, OSError) as exc:
        # safeverdict: git_unavailable
        return {
            "safe": True,
            "ahead": None,
            "behind": None,
            "reason": f"divergence check skipped: git not available - {exc}",
        }

    # Step 2: resolve branch if not supplied
    if branch is None:
        try:
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if branch_result.returncode != 0:
                reason = (
                    "divergence check skipped: could not resolve current branch - "
                    + branch_result.stderr.strip()[:200]
                )
                # safeverdict: branch_unresolved
                return {"safe": True, "ahead": None, "behind": None, "reason": reason}
            branch = branch_result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            # safeverdict: branch_resolution_error
            return {
                "safe": True,
                "ahead": None,
                "behind": None,
                "reason": f"divergence check skipped: could not resolve branch - {exc}",
            }

    # Step 3: compute ahead/behind counts
    # Format: <remote>/<branch>...HEAD
    # git rev-list --left-right --count: left = commits remote has local lacks (behind),
    # right = commits local has remote lacks (ahead)
    tracking_ref = f"{remote}/{branch}"
    try:
        revlist_result = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", f"{tracking_ref}...HEAD"],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if revlist_result.returncode != 0:
            # Most likely: remote tracking ref does not exist yet (first push)
            reason = (
                f"divergence check skipped: remote tracking ref {tracking_ref!r} not found "
                f"- {revlist_result.stderr.strip()[:200]}"
            )
            # safeverdict: tracking_ref_missing
            return {"safe": True, "ahead": None, "behind": None, "reason": reason}
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        # safeverdict: rev_list_failure
        return {
            "safe": True,
            "ahead": None,
            "behind": None,
            "reason": f"divergence check skipped: rev-list failed - {exc}",
        }

    # Parse stdout: two whitespace-separated integers
    parts = revlist_result.stdout.strip().split()
    if len(parts) != 2:
        # safeverdict: unexpected_revlist_output
        return {
            "safe": True,
            "ahead": None,
            "behind": None,
            "reason": (
                f"divergence check skipped: unexpected rev-list output "
                f"{revlist_result.stdout.strip()!r}"
            ),
        }
    try:
        behind = int(parts[0])
        ahead = int(parts[1])
    except ValueError:
        # safeverdict: unparseable_revlist_integers
        return {
            "safe": True,
            "ahead": None,
            "behind": None,
            "reason": (
                f"divergence check skipped: could not parse rev-list output "
                f"{revlist_result.stdout.strip()!r}"
            ),
        }

    # Step 4/5: evaluate safety
    if behind > 0:
        return {
            "safe": False,
            "ahead": ahead,
            "behind": behind,
            "reason": (
                f"local branch is {behind} commit(s) behind {remote}/{branch} "
                f"and {ahead} commit(s) ahead - push would be rejected or clobber remote history"
            ),
        }

    # safeverdict: in_sync_or_ahead
    return {
        "safe": True,
        "ahead": ahead,
        "behind": 0,
        "reason": "local branch is up-to-date or ahead of remote",
    }


if __name__ == "__main__":
    repo_root_arg = sys.argv[1]
    remote_arg = sys.argv[2] if len(sys.argv) > 2 else "origin"
    result = check_push_safe(repo_root_arg, remote=remote_arg)
    print(result["reason"])
    sys.exit(1 if result["safe"] is False else 0)
