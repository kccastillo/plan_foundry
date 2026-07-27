#!/usr/bin/env python3
"""
check_current.py - Currency check for plan_foundry (AC6 model).

Reads the target's `.claude/.plan-foundry-bundle-version` pin and compares
it to the bundle's current `HEAD` on the public remote via `git ls-remote`.

Single tier - there is no local bundle clone anymore. The local bundle was
removed by PLAN-AC6 (2026-05-19) when the bundle moved to on-demand network
clone.

Always exits 0; status is conveyed via JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

EXPECTED_REPO = "kccastillo/plan_foundry"
BUNDLE_URL = f"https://github.com/{EXPECTED_REPO}"
VERSION_FILENAME = ".plan-foundry-bundle-version"


def _run(args, cwd=None):
    try:
        p = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError as exc:
        return 1, "", f"git not found: {exc}"
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


def _short(sha: str) -> str:
    return sha[:8] if sha else ""


def _read_version_file(target_claude: pathlib.Path) -> dict | None:
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


def fetch_remote_head(url: str = BUNDLE_URL) -> tuple[str, str]:
    """Return (remote_sha, error). On success error == ''."""
    rc, out, err = _run(["git", "ls-remote", url, "HEAD"])
    if rc != 0:
        return "", err or "git ls-remote failed"
    # First field of the first line is the sha.
    first_line = out.splitlines()[0] if out else ""
    sha = first_line.split()[0] if first_line else ""
    if not sha:
        return "", "ls-remote returned no sha"
    return sha, ""


def check(target_root: pathlib.Path) -> dict:
    result = {
        "status": "unknown",
        "project_sha": "",
        "remote_sha": "",
        "ref": "HEAD",
        "message": "",
    }
    target_claude = target_root / ".claude"
    if not target_claude.exists():
        result["status"] = "not_initialised"
        result["message"] = (
            f"{target_claude} does not exist - run /init-plan-foundry first."
        )
        return result
    if target_claude.is_symlink():
        result["status"] = "legacy_symlink"
        result["message"] = (
            f"{target_claude} is a symlink (legacy AC3 install) - "
            "run /init-plan-foundry to migrate."
        )
        return result
    pin = _read_version_file(target_claude)
    if pin is None:
        result["status"] = "not_initialised"
        result["message"] = (
            f"{target_claude}/{VERSION_FILENAME} is absent - run /init-plan-foundry first."
        )
        return result

    project_sha = pin.get("sha", "")
    result["project_sha"] = _short(project_sha)

    remote_sha, err = fetch_remote_head()
    if err:
        result["status"] = "remote_unreachable"
        result["message"] = (
            f"could not query remote {BUNDLE_URL}: {err}. "
            f"You are pinned at {_short(project_sha) or '(unknown)'}; "
            "run /plan-foundry-sync when network is available to refresh."
        )
        return result
    result["remote_sha"] = _short(remote_sha)

    if not project_sha:
        result["status"] = "unknown"
        result["message"] = "project version pin has empty sha - run /plan-foundry-sync."
        return result

    if project_sha == remote_sha or project_sha[:8] == remote_sha[:8]:
        result["status"] = "current"
        result["message"] = (
            f"project is up to date (pinned at {_short(project_sha)}, "
            f"remote HEAD {_short(remote_sha)})."
        )
        return result

    result["status"] = "behind_or_diverged"
    result["message"] = (
        f"project pin {_short(project_sha)} differs from remote HEAD "
        f"{_short(remote_sha)} - run /plan-foundry-sync to update."
    )
    return result


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-root",
        default=None,
        help="Project root (default: current working directory).",
    )
    args = parser.parse_args(argv)
    target_root = (
        pathlib.Path(args.target_root).expanduser().resolve()
        if args.target_root
        else pathlib.Path.cwd().resolve()
    )
    result = check(target_root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
