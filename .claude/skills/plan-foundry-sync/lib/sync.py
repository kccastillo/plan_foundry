#!/usr/bin/env python3
"""
sync.py — Implementation of plan-foundry-sync. Copies bundle-managed paths
from the bundle into the current project and refreshes the version pin.

See ../SKILL.md and ../workflows/sync.md for behaviour.
Always exits 0; status conveyed via JSON on stdout.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import sys


def _resolve_bundle_path(arg: str | None) -> pathlib.Path:
    if arg:
        return pathlib.Path(arg).expanduser().resolve()
    env = os.environ.get("PLAN_FOUNDRY_BUNDLE_PATH")
    if env:
        return pathlib.Path(env).expanduser().resolve()
    return (pathlib.Path.home() / ".claude" / "plan_foundry").resolve()


def _import_bundle_copy(bundle_path: pathlib.Path):
    shared = bundle_path / ".claude" / "skills" / "_shared"
    sys.path.insert(0, str(shared))
    import bundle_copy  # noqa: E402

    return bundle_copy


def sync(bundle_path: pathlib.Path, target_root: pathlib.Path) -> dict:
    result: dict = {
        "outcome": "exception",
        "payload": {},
        "summary": "",
        "diagnostics": [],
    }

    if not bundle_path.exists():
        result["summary"] = (
            f"plan_foundry bundle not found at {bundle_path} — clone "
            f"https://github.com/kccastillo/plan_foundry into ~/.claude/plan_foundry first."
        )
        return result
    bundle_claude = bundle_path / ".claude"
    if not (bundle_claude / "skills" / "init-plan-foundry" / "operating-rules.md").exists():
        result["summary"] = (
            f"bundle at {bundle_path} appears malformed: "
            "missing skills/init-plan-foundry/operating-rules.md"
        )
        return result

    target_claude = target_root / ".claude"
    if not target_claude.exists():
        result["summary"] = (
            "this project has no .claude/ directory — run /init-plan-foundry first."
        )
        return result
    if target_claude.is_symlink():
        result["summary"] = (
            "<target>/.claude is a symlink (legacy AC3 install) — "
            "run /init-plan-foundry to migrate this project off the symlink layout."
        )
        return result

    bundle_copy = _import_bundle_copy(bundle_path)

    previous = bundle_copy.read_version_file(target_claude)
    if previous is None:
        result["summary"] = (
            "<target>/.claude/.plan-foundry-bundle-version is absent — "
            "run /init-plan-foundry first to record an initial pin."
        )
        return result
    previous_sha = previous.get("sha", "")

    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    new = bundle_copy.write_version_file(bundle_path, target_claude)

    payload = {
        "previous_sha": previous_sha,
        "new_sha": new["sha"],
        "tag": new["tag"],
        "synced": new["synced"],
        "files_copied": report.files_copied,
        "files_unchanged_count": len(report.files_unchanged),
        "project_additions": report.project_additions,
        "stale_in_target": report.stale_in_target,
    }
    short_prev = previous_sha[:8] if previous_sha else "(none)"
    short_new = new["sha"][:8] if new["sha"] else "(none)"
    result["outcome"] = "success"
    result["payload"] = payload
    result["summary"] = (
        f"synced {short_prev} → {short_new}: "
        f"{len(report.files_copied)} copied, "
        f"{len(report.files_unchanged)} unchanged, "
        f"{len(report.project_additions)} project additions preserved, "
        f"{len(report.stale_in_target)} stale"
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
        default=None,
        help="Path to the plan_foundry bundle clone "
        "(default: $PLAN_FOUNDRY_BUNDLE_PATH or ~/.claude/plan_foundry/).",
    )
    parser.add_argument(
        "--target-root",
        default=None,
        help="Target project root (default: current working directory).",
    )
    args = parser.parse_args(argv)
    bundle_path = _resolve_bundle_path(args.bundle_path)
    target_root = (
        pathlib.Path(args.target_root).expanduser().resolve()
        if args.target_root
        else pathlib.Path.cwd().resolve()
    )
    result = sync(bundle_path, target_root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
