#!/usr/bin/env python3
"""
sync.py — Implementation of plan-foundry-sync (AC6 model).

Clones the public plan_foundry repo on demand into <target>/.plan-foundry-tmp/,
copies bundle-managed paths into <target>/.claude/, refreshes the version pin,
deletes the tmp clone. No reliance on any path outside the target.

Always exits 0; status conveyed via JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


def _import_local_helpers():
    """Locate _shared/ alongside this script (within the installed bundle).

    Layout: .claude/skills/plan-foundry-sync/lib/sync.py — _shared is two dirs up.
    """
    shared = pathlib.Path(__file__).resolve().parent.parent.parent / "_shared"
    sys.path.insert(0, str(shared))
    import bundle_copy  # noqa: E402
    import bundle_fetch  # noqa: E402

    return bundle_copy, bundle_fetch


def sync(target_root: pathlib.Path, ref: str = "main") -> dict:
    result: dict = {
        "outcome": "exception",
        "payload": {},
        "summary": "",
        "diagnostics": [],
    }

    target_claude = target_root / ".claude"
    if not target_claude.exists():
        result["summary"] = (
            f"{target_claude} does not exist — run /init-plan-foundry first."
        )
        return result
    if target_claude.is_symlink():
        result["summary"] = (
            f"{target_claude} is a symlink (legacy AC3 install) — "
            "run /init-plan-foundry to migrate this project."
        )
        return result

    bundle_copy, bundle_fetch = _import_local_helpers()

    previous = bundle_copy.read_version_file(target_claude)
    if previous is None:
        result["summary"] = (
            f"{target_claude}/.plan-foundry-bundle-version is absent — "
            "run /init-plan-foundry first to record an initial pin."
        )
        return result
    previous_sha = previous.get("sha", "")

    try:
        bundle_path = bundle_fetch.clone_bundle(target_root, ref=ref)
    except bundle_fetch.BundleFetchError as exc:
        result["summary"] = f"could not fetch bundle: {exc}"
        result["diagnostics"].append({"step": "clone", "error": str(exc)})
        return result

    try:
        report = bundle_copy.copy_bundle_managed(bundle_path / ".claude", target_claude)
        new = bundle_copy.write_version_file(bundle_path, target_claude)
    finally:
        bundle_fetch.cleanup_tmp(target_root)

    payload = {
        "ref": ref,
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
        f"synced {short_prev} → {short_new} (ref={ref}): "
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
        "--target-root",
        default=None,
        help="Target project root (default: current working directory).",
    )
    parser.add_argument(
        "--ref",
        default="main",
        help="Git ref to fetch — branch name, tag, or sha (default: main).",
    )
    args = parser.parse_args(argv)
    target_root = (
        pathlib.Path(args.target_root).expanduser().resolve()
        if args.target_root
        else pathlib.Path.cwd().resolve()
    )
    result = sync(target_root, ref=args.ref)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
