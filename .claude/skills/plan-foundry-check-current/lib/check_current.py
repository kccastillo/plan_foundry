#!/usr/bin/env python3
"""
check_current.py — Two-tier currency report for plan_foundry.

Tier 1: is the local bundle at ~/.claude/plan_foundry/ current with origin/main?
Tier 2: is the current project's recorded bundle version (`.claude/.plan-foundry-bundle-version`)
        equal to the bundle's HEAD?

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
VERSION_FILENAME = ".plan-foundry-bundle-version"


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


def check_bundle(bundle_path: Path) -> dict:
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
        result["message"] = "plan_foundry bundle is up to date with origin/main."
    elif b > 0 and a == 0:
        result["status"] = "behind"
        result["message"] = (
            f"plan_foundry bundle is behind by {b} commit(s) — run: "
            f"cd {bundle_path} && git pull"
        )
    elif b == 0 and a > 0:
        result["status"] = "ahead"
        result["message"] = (
            f"plan_foundry bundle has {a} local commit(s) not on origin/main."
        )
    else:
        result["status"] = "diverged"
        result["message"] = (
            f"plan_foundry bundle has diverged from origin/main "
            f"(behind {b}, ahead {a}) — consider re-cloning."
        )
    return result


def _read_version_file(target_claude: Path) -> dict | None:
    path = target_claude / VERSION_FILENAME
    if not path.exists():
        return None
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def check_project(bundle_path: Path, target_root: Path, bundle_local_sha: str) -> dict:
    """Tier-2 check: is this project's pinned bundle version equal to the bundle's HEAD?"""
    result = {
        "status": "not_initialised",
        "project_sha": "",
        "bundle_sha": bundle_local_sha,
        "message": "",
    }
    target_claude = target_root / ".claude"
    if not target_claude.exists():
        result["message"] = (
            f"{target_root}/.claude does not exist — run /init-plan-foundry first."
        )
        return result
    if target_claude.is_symlink():
        result["status"] = "legacy_symlink"
        result["message"] = (
            f"{target_claude} is a symlink (legacy AC3 install) — "
            "run /init-plan-foundry to migrate."
        )
        return result
    pin = _read_version_file(target_claude)
    if pin is None:
        result["message"] = (
            f"{target_claude}/{VERSION_FILENAME} is absent — run /init-plan-foundry first."
        )
        return result
    project_sha = pin.get("sha", "")
    result["project_sha"] = _short(project_sha)
    if not project_sha:
        result["status"] = "unknown"
        result["message"] = "project version pin has empty sha — re-run /plan-foundry-sync."
        return result
    if not bundle_local_sha:
        result["status"] = "unknown"
        result["message"] = "bundle sha unknown — cannot compare."
        return result
    if project_sha[:8] == bundle_local_sha[:8] or project_sha == bundle_local_sha:
        result["status"] = "current"
        result["message"] = "project is in sync with the local bundle."
        return result
    # Try to compute commit distance.
    rc_b, behind, _ = _run(
        ["git", "rev-list", "--count", f"{project_sha}..HEAD"], cwd=bundle_path
    )
    if rc_b == 0 and behind.isdigit() and int(behind) > 0:
        result["status"] = "behind"
        result["message"] = (
            f"project is behind the local bundle by {behind} commit(s) — "
            "run /plan-foundry-sync."
        )
    else:
        result["status"] = "drift"
        result["message"] = (
            f"project pin {project_sha[:8]} differs from local bundle "
            f"{bundle_local_sha[:8]} — run /plan-foundry-sync."
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
    parser.add_argument(
        "--target-root",
        default=None,
        help="Project root to compare against the bundle "
        "(default: current working directory; pass --no-target-check to skip tier 2).",
    )
    parser.add_argument(
        "--no-target-check",
        action="store_true",
        help="Skip tier-2 (project vs bundle) check. Useful when invoked outside any project.",
    )
    args = parser.parse_args(argv)
    bundle_path = Path(args.bundle_path).expanduser()

    bundle = check_bundle(bundle_path)
    out: dict = {"bundle": bundle}

    if not args.no_target_check:
        target_root = (
            Path(args.target_root).expanduser().resolve()
            if args.target_root
            else Path.cwd().resolve()
        )
        bundle_local_sha = ""
        if bundle["status"] not in ("no_bundle", "wrong_remote"):
            rc, sha, _ = _run(["git", "rev-parse", "HEAD"], cwd=bundle_path)
            bundle_local_sha = sha if rc == 0 else ""
        project = check_project(bundle_path, target_root, bundle_local_sha)
        out["project"] = project

    # Backward-compat: top-level keys (status / message / etc.) mirror the bundle tier
    # so existing consumers don't break.
    for k in ("status", "local_sha", "remote_sha", "behind_by", "ahead_by", "message"):
        if k in bundle:
            out[k] = bundle[k]

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
