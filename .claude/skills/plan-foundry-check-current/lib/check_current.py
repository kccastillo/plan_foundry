#!/usr/bin/env python3
"""
check_current.py — Report whether the local plan_foundry bundle is at origin/main.

See ../SKILL.md and ../workflows/check.md for behaviour.
Always exits 0; status is conveyed via JSON on stdout.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


EXPECTED_REPO = "kccastillo/plan_foundry"


def _run(args, cwd):
    """Run a git command; return (rc, stdout-stripped, stderr-stripped)."""
    try:
        p = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


def _remote_matches(url: str) -> bool:
    """True iff the URL points at kccastillo/plan_foundry (HTTPS or SSH form)."""
    if not url:
        return False
    candidates = (
        f"https://github.com/{EXPECTED_REPO}",
        f"https://github.com/{EXPECTED_REPO}.git",
        f"git@github.com:{EXPECTED_REPO}",
        f"git@github.com:{EXPECTED_REPO}.git",
        f"ssh://git@github.com/{EXPECTED_REPO}",
        f"ssh://git@github.com/{EXPECTED_REPO}.git",
    )
    return url in candidates


def _short(sha: str) -> str:
    return sha[:8] if sha else ""


def check(bundle_path: Path) -> dict:
    result = {
        "status": "no_bundle",
        "local_sha": "",
        "remote_sha": "",
        "behind_by": 0,
        "ahead_by": 0,
        "message": "",
    }

    if not bundle_path.exists() or not (bundle_path / ".git").exists():
        result["message"] = (
            f"plan_foundry bundle not found at {bundle_path} — "
            f"clone https://github.com/{EXPECTED_REPO} into ~/.claude/plan_foundry first."
        )
        return result

    rc, url, _ = _run(["git", "remote", "get-url", "origin"], cwd=bundle_path)
    if rc != 0 or not _remote_matches(url):
        result["status"] = "wrong_remote"
        result["message"] = (
            f"Bundle at {bundle_path} has remote '{url}'; expected {EXPECTED_REPO}."
        )
        return result

    # Best-effort fetch; ignore network failures (status will be inferred from
    # whatever origin/main is locally).
    _run(["git", "fetch", "origin", "main"], cwd=bundle_path)

    rc_l, local, _ = _run(["git", "rev-parse", "HEAD"], cwd=bundle_path)
    rc_r, remote, _ = _run(["git", "rev-parse", "origin/main"], cwd=bundle_path)
    if rc_l != 0 or rc_r != 0:
        result["status"] = "wrong_remote"
        result["message"] = (
            f"Could not resolve HEAD / origin/main in {bundle_path} — bundle malformed."
        )
        return result

    result["local_sha"] = _short(local)
    result["remote_sha"] = _short(remote)

    rc_b, behind, _ = _run(
        ["git", "rev-list", "--count", "HEAD..origin/main"], cwd=bundle_path
    )
    rc_a, ahead, _ = _run(
        ["git", "rev-list", "--count", "origin/main..HEAD"], cwd=bundle_path
    )
    result["behind_by"] = int(behind) if rc_b == 0 and behind.isdigit() else 0
    result["ahead_by"] = int(ahead) if rc_a == 0 and ahead.isdigit() else 0

    b = result["behind_by"]
    a = result["ahead_by"]
    if b == 0 and a == 0:
        result["status"] = "current"
        result["message"] = "plan_foundry is up to date."
    elif b > 0 and a == 0:
        result["status"] = "behind"
        result["message"] = (
            f"plan_foundry is behind by {b} commit(s) — run: cd {bundle_path} && git pull"
        )
    elif b == 0 and a > 0:
        result["status"] = "ahead"
        result["message"] = f"plan_foundry has {a} local commit(s) not on origin/main."
    else:
        result["status"] = "diverged"
        result["message"] = (
            f"plan_foundry has diverged from origin/main (behind {b}, ahead {a}) — "
            f"consider re-cloning."
        )
    return result


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle-path",
        default=os.environ.get(
            "PLAN_FOUNDRY_BUNDLE_PATH",
            str(Path.home() / ".claude" / "plan_foundry"),
        ),
        help="Path to the plan_foundry bundle clone (default: ~/.claude/plan_foundry/).",
    )
    args = parser.parse_args(argv)
    result = check(Path(args.bundle_path).expanduser())
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
