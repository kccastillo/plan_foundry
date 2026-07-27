#!/usr/bin/env python3
"""
sync.py - Implementation of plan-foundry-sync (AC6 model).

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

    Layout: .claude/skills/plan-foundry-sync/lib/sync.py - _shared is two dirs up.
    """
    shared = pathlib.Path(__file__).resolve().parent.parent.parent / "_shared"
    sys.path.insert(0, str(shared))
    import bundle_copy  # noqa: E402
    import bundle_fetch  # noqa: E402
    import claude_md_block  # noqa: E402

    return bundle_copy, bundle_fetch, claude_md_block


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
            f"{target_claude} does not exist - run /init-plan-foundry first."
        )
        return result
    if target_claude.is_symlink():
        result["summary"] = (
            f"{target_claude} is a symlink (legacy AC3 install) - "
            "run /init-plan-foundry to migrate this project."
        )
        return result

    bundle_copy, bundle_fetch, claude_md_block = _import_local_helpers()

    previous = bundle_copy.read_version_file(target_claude)
    if previous is None:
        result["summary"] = (
            f"{target_claude}/.plan-foundry-bundle-version is absent - "
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

    # Initialise settings_report and cmd variables before the try block so they
    # are always defined even if an exception occurs partway through.
    settings_report: dict = {}
    ga_status, ga_added = "SKIPPED", []
    hp_status, hp_note = "SKIPPED", "not attempted"
    cmd_status, cmd_note = "SKIPPED", "not reached"

    try:
        report = bundle_copy.copy_bundle_managed(bundle_path / ".claude", target_claude)
        new = bundle_copy.write_version_file(bundle_path, target_claude)

        # Merge bundle settings fragment into target settings.json.
        # Load merge_settings from the freshly-cloned bundle's _shared/ (NOT
        # _import_local_helpers which resolves from the target's installed copy
        # and would fail ImportError on any pre-AH2 consumer that lacks the helper).
        bundle_shared = bundle_path / ".claude" / "skills" / "_shared"
        if str(bundle_shared) not in sys.path:
            sys.path.insert(0, str(bundle_shared))
        import merge_settings  # noqa: E402

        fragment_path = bundle_shared / "bundle-settings.json"
        target_settings = target_root / ".claude" / "settings.json"
        settings_report = merge_settings.merge_bundle_settings(target_settings, fragment_path)

        # Pin LF endings for hooks and shell scripts in the consumer repo.
        # Sync is the path by which the commit-msg hook actually arrives, so a
        # consumer who installed before the pin existed converges here rather
        # than only on a fresh install. Imported from the bundle for the same
        # reason as merge_settings: a pre-AH2 consumer has no local copy.
        try:
            import gitattributes_pin  # noqa: E402

            ga_status, ga_added = gitattributes_pin.ensure_gitattributes_pin(target_root)
        except ImportError:
            # Bundle predates the helper - skip gracefully, do not crash a sync.
            ga_status, ga_added = "SKIPPED", []

        # Wire core.hooksPath (D10). Ordered strictly after the pin above: a
        # hook wired before its line endings are guaranteed is a hook that
        # fails silently on Windows. Narrows D10's accepted weakness, since a
        # contributor who clones and syncs converges without re-running init.
        try:
            import hooks_path  # noqa: E402

            hp_status, hp_note = hooks_path.ensure_hooks_path(target_root)
        except ImportError:
            hp_status, hp_note = "SKIPPED", "bundle predates hooks_path helper"

        # Refresh the CLAUDE.md operating-rules block from the bundle.
        # Must be done inside the try block (before cleanup_tmp) while the bundle still exists.
        operating_rules_path = (
            bundle_path / ".claude" / "skills" / "init-plan-foundry" / "operating-rules.md"
        )
        try:
            operating_rules = operating_rules_path.read_text(encoding="utf-8")
            cmd_status, cmd_note = claude_md_block.apply_operating_rules_block(
                target_root, operating_rules
            )
        except OSError:
            # operating-rules.md absent in an old bundle - skip gracefully, do not crash.
            cmd_status, cmd_note = "SKIPPED", "operating-rules.md absent in bundle"
    finally:
        bundle_fetch.cleanup_tmp(target_root)

    settings_status = "PASS" if settings_report.get("changed") else "SKIPPED"
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
        "claude_md": {"status": cmd_status, "note": cmd_note},
        "settings_merge": {
            "status": settings_status,
            "entries_added": settings_report.get("entries_added", []),
            "entries_already_present": settings_report.get("entries_already_present", []),
        },
        "gitattributes": {"status": ga_status, "pins_added": ga_added},
        "hooks_path": {"status": hp_status, "note": hp_note},
    }
    short_prev = previous_sha[:8] if previous_sha else "(none)"
    short_new = new["sha"][:8] if new["sha"] else "(none)"
    result["diagnostics"].append(f"CLAUDE.md: {cmd_note}")
    result["diagnostics"].append(
        f"settings merge: {settings_status} "
        f"(added={settings_report.get('entries_added', [])}, "
        f"already_present={settings_report.get('entries_already_present', [])})"
    )
    result["diagnostics"].append(f"gitattributes: {ga_status} (pins_added={ga_added})")
    result["diagnostics"].append(f"hooks path: {hp_status} ({hp_note})")
    result["payload"] = payload
    result["summary"] = (
        f"synced {short_prev} -> {short_new} (ref={ref}): "
        f"{len(report.files_copied)} copied, "
        f"{len(report.files_unchanged)} unchanged, "
        f"{len(report.project_additions)} project additions preserved, "
        f"{len(report.stale_in_target)} stale"
        f", CLAUDE.md {cmd_status} ({cmd_note})"
        f", settings {settings_status}"
    )
    if cmd_status == "FAIL":
        result["outcome"] = "exception"
    else:
        result["outcome"] = "success"
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
        help="Git ref to fetch - branch name, tag, or sha (default: main).",
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
