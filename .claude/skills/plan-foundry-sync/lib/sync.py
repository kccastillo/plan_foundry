#!/usr/bin/env python3
"""
sync.py - Implementation of plan-foundry-sync (AC6 model).

Clones the public plan_foundry repo on demand into <target>/.plan-foundry-tmp/,
copies bundle-managed paths into <target>/.claude/, refreshes the version pin,
deletes the tmp clone. No reliance on any path outside the target.

Always exits 0; status conveyed via JSON on stdout.

PLAN-AH9, guarantee 4: shim-then-delete lifecycle. A deprecated surface
keeps its path and gains a shim body (preflight.shim_body,
scripts/generate-deprecation-shim.py) for at least one minor release; only
at the next major does the path disappear from the bundle, at which point
classify_stale (PLAN-AH7) sees it as gone_upstream and this module
quarantines it. The shim is what makes the eventual quarantine safe -
by the time a surface is quarantined, every consumer has had a release in
which invoking it told them what replaced it. This module cross-references
each quarantined path against the deprecation ledger (preflight.
read_deprecations) and, for a match among file-path-addressed entries
(kind: skill | reference | hook), reports replaced_by and note rather than
a bare path. kind: helper entries are symbol-addressed (file.py::symbol)
and are never offered to this match - they have no file-level path to
compare against.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Optional


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


def sync(
    target_root: pathlib.Path, ref: str = "main", allow_in_flight: bool = False
) -> dict:
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

    # PLAN-AH7 Step 1 (load-bearing ordering invariant): the receipt MUST be
    # read here, before the clone, alongside the existing pin read above -
    # never after the copy. See bundle_copy.py's module docstring for why.
    receipt = bundle_copy.read_receipt(target_claude)

    try:
        bundle_path = bundle_fetch.clone_bundle(target_root, ref=ref)
    except bundle_fetch.BundleFetchError as exc:
        result["summary"] = f"could not fetch bundle: {exc}"
        result["diagnostics"].append({"step": "clone", "error": str(exc)})
        return result

    # PLAN-AH8 guarantee 2: the in-flight pre-flight, wired after the clone
    # and before copy_bundle_managed. Imported from the freshly-cloned
    # bundle's _shared/ (NOT the target's installed copy, which may predate
    # this helper) under an ImportError guard - same pattern as
    # gitignore_entries, gitattributes_pin, and hooks_path below.
    # Deliberately NOT claude_md_block, which arrives via
    # _import_local_helpers() above and is guarded on OSError over a file
    # read rather than ImportError - it is one of the three pre-imported,
    # cache-poisoned names, so citing it here would teach the opposite of
    # this module's own lesson.
    bundle_shared = bundle_path / ".claude" / "skills" / "_shared"
    if str(bundle_shared) not in sys.path:
        sys.path.insert(0, str(bundle_shared))
    preflight_verdict = "unavailable"
    in_flight_plans: list = []
    # PLAN-AH9 Step 5: bind the sentinel BEFORE the try, so the name always
    # exists in scope regardless of which branch runs. Two distinct
    # consumer cases hit this block: a --ref predating AH8 has no preflight
    # module in the clone at all (import preflight raises ImportError, and
    # because preflight was never bound, any later reference - including a
    # getattr(preflight, ...) guard - would raise NameError, not
    # AttributeError, if the sentinel were not pre-bound); a --ref between
    # AH8 and AH9 has preflight present but no read_deprecations attribute
    # (resolved via getattr below, not a widened except clause - see
    # preflight.py's own module docstring for why AttributeError must not
    # be caught here).
    preflight = None
    ledger_unavailable_reason: Optional[str] = None
    try:
        import preflight  # noqa: E402
    except ImportError:
        # Bundle predates the preflight helper - skip gracefully, do not
        # crash a sync.
        ledger_unavailable_reason = "preflight module absent (ref predates AH8)"

    if preflight is not None:
        preflight_verdict = preflight.compare_against_clone(target_claude, bundle_path)
        if preflight_verdict == "major_step":
            in_flight_plans = preflight.scan_in_flight_plans(target_root)

    # PLAN-AH9 Step 5 (second case): preflight present, read_deprecations
    # absent - a --ref between AH8 and AH9. getattr guards the attribute,
    # never a widened except AttributeError clause.
    read_deprecations_fn = (
        getattr(preflight, "read_deprecations", None) if preflight is not None else None
    )
    if read_deprecations_fn is None and ledger_unavailable_reason is None:
        ledger_unavailable_reason = (
            "preflight present, read_deprecations absent (ref between AH8 and AH9)"
        )

    if preflight_verdict == "major_step" and in_flight_plans and not allow_in_flight:
        # A deliberate refusal to proceed is not a crash - this is a third
        # outcome value, "blocked", distinct from "exception". Consumer-
        # visible contract change, declared in workflows/sync.md's
        # Reporting block and plan-foundry-sync/SKILL.md.
        bundle_fetch.cleanup_tmp(target_root)
        result["outcome"] = "blocked"
        result["payload"] = {
            "in_flight_plans": in_flight_plans,
            "blocked_reason": (
                "sync crosses a major version step (pin vs. the cloned "
                "bundle) while PLAN(s) are in flight"
            ),
        }
        result["diagnostics"].append(
            f"preflight: version_step=major_step in_flight={in_flight_plans}"
        )
        result["summary"] = (
            f"sync blocked: major version step with {len(in_flight_plans)} "
            "PLAN(s) in flight - re-run with --allow-in-flight to override"
        )
        return result

    result["diagnostics"].append(
        f"preflight: version_step={preflight_verdict} in_flight={in_flight_plans} "
        f"allow_in_flight={allow_in_flight}"
    )

    # Initialise settings_report and cmd variables before the try block so they
    # are always defined even if an exception occurs partway through.
    settings_report: dict = {}
    ga_status, ga_added = "SKIPPED", []
    hp_status, hp_note = "SKIPPED", "not attempted"
    cmd_status, cmd_note = "SKIPPED", "not reached"
    gi_status, gi_added, gi_skipped_tracked = "SKIPPED", [], []
    quarantine_report: dict = {
        "receipt_absent": receipt is None,
        "gone_upstream_quarantined": [],
        "consumer_owned_preserved": [],
        "swept": [],
    }
    dangling_hook_registrations: list = []

    try:
        contract = bundle_copy.read_bundle_contract(bundle_path)
        report = bundle_copy.copy_bundle_managed(
            bundle_path / ".claude",
            target_claude,
            deprecations=contract.get("deprecations", []),
        )
        new = bundle_copy.write_version_file(bundle_path, target_claude)

        # PLAN-AH7 Steps 6-10: classify -> quarantine -> sweep, strictly after
        # the copy and strictly before the receipt write at the end of this
        # try block (see the ordering invariant recorded above and in
        # bundle_copy.py's module docstring).
        bundle_files = set(report.files_copied) | set(report.files_unchanged)
        target_files = (
            bundle_files | set(report.project_additions) | set(report.stale_in_target)
        )
        classification = bundle_copy.classify_stale(bundle_files, target_files, receipt)

        if receipt is None:
            quarantine_report["reason"] = (
                "no install receipt - nothing quarantined; a receipt is "
                "written by this sync and the next sync can act"
            )

        # PLAN-AH9 Step 5: the deprecation ledger, filtered to file-path-
        # addressed entries (kind: skill | reference | hook) before
        # matching. A kind: helper entry's path is a file.py::symbol
        # string that can never equal a quarantined file path, and per the
        # address-space split it must not even be offered to this matcher.
        ledger = []
        if read_deprecations_fn is not None:
            try:
                ledger = read_deprecations_fn(bundle_path) or []
            except Exception:
                ledger = []
        file_kind_ledger = {
            e["path"]: e
            for e in ledger
            if isinstance(e, dict) and e.get("kind") in ("skill", "reference", "hook")
        }
        quarantine_report["ledger_unavailable"] = ledger_unavailable_reason

        receipt_files = receipt.get("files", {}) if receipt else {}
        quarantine_details = []
        for rel in classification.gone_upstream:
            src = target_claude / rel
            try:
                on_disk_hash = bundle_copy._file_sha256(src)
            except OSError:
                on_disk_hash = None
            recorded_hash = receipt_files.get(rel)
            detail = {
                "path": rel,
                "sha256": on_disk_hash,
                "modified_since_install": bool(
                    on_disk_hash is not None
                    and recorded_hash is not None
                    and on_disk_hash != recorded_hash
                ),
            }
            ledger_entry = file_kind_ledger.get(rel)
            if ledger_entry is not None:
                # Guarantee 4's acceptance coverage: a quarantined path
                # carrying a ledger entry reports replaced_by and note,
                # not a bare path.
                detail["replaced_by"] = ledger_entry.get("replaced_by", "")
                detail["note"] = ledger_entry.get("note", "")
            quarantine_details.append(detail)
        # quarantine() is called with gone_upstream ONLY - never touches
        # consumer_owned. Calls no delete primitive (shutil.move only).
        bundle_copy.quarantine(target_claude, classification.gone_upstream)
        quarantine_report["gone_upstream_quarantined"] = quarantine_details
        quarantine_report["consumer_owned_preserved"] = classification.consumer_owned
        quarantine_report["unknown"] = classification.unknown

        # PLAN-AH9 Step 6: dangling hook registrations. .claude/settings.json
        # registers hooks by path and the settings merge below only adds
        # entries, so quarantining a dropped hook leaves a registration
        # pointing at a moved file, which errors on every tool call. Loud
        # rather than silent - a diagnostic, not a halt.
        dangling_hook_registrations = []
        target_settings_path = target_root / ".claude" / "settings.json"
        if target_settings_path.exists():
            try:
                settings_text = target_settings_path.read_text(encoding="utf-8")
            except OSError:
                settings_text = ""
            for rel in classification.gone_upstream:
                if rel.startswith("hooks/") and rel in settings_text:
                    dangling_hook_registrations.append(rel)

        # sweep_quarantine is the only function permitted to delete, and only
        # whole aged (>=30 day) quarantine directories.
        quarantine_report["swept"] = bundle_copy.sweep_quarantine(target_claude)

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

        # PLAN-AH7 Step 12: gitignore convergence for the two new paths this
        # PLAN adds (.plan-foundry-bundle-files, .plan-foundry-quarantine/).
        # Imported from the freshly-cloned bundle's _shared/ (now on sys.path
        # via bundle_shared above) under an ImportError guard, same pattern
        # as gitattributes_pin below - init-only is not sufficient, every
        # already-installed consumer needs this too.
        try:
            import gitignore_entries  # noqa: E402

            gi_status, gi_added, gi_skipped_tracked = (
                gitignore_entries.ensure_gitignore_entries(target_root)
            )
        except ImportError:
            gi_status, gi_added, gi_skipped_tracked = "SKIPPED", [], []

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

        # PLAN-AH7 Step 5 (load-bearing ordering invariant): write the new
        # receipt LAST - after classify/quarantine/sweep above, never
        # immediately after the copy. Records everything now installed
        # (copied + already-unchanged), so the next sync's read_receipt call
        # can distinguish "we installed this" from "the consumer added this".
        bundle_copy.write_receipt(
            target_claude,
            report.files_copied + report.files_unchanged,
            new["sha"],
        )
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
        "gitignore_convergence": {
            "status": gi_status,
            "entries_added": gi_added,
            "entries_skipped_tracked": gi_skipped_tracked,
        },
        "shim_skipped": report.shim_skipped,
        "quarantine": quarantine_report,
        "dangling_hook_registrations": dangling_hook_registrations,
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
    result["diagnostics"].append(
        f"gitignore convergence: {gi_status} (entries_added={gi_added}, "
        f"entries_skipped_tracked={gi_skipped_tracked})"
    )
    result["diagnostics"].append(
        f"quarantine: receipt_absent={quarantine_report['receipt_absent']} "
        f"gone_upstream={len(quarantine_report['gone_upstream_quarantined'])} "
        f"consumer_owned_preserved={len(quarantine_report['consumer_owned_preserved'])} "
        f"swept={len(quarantine_report['swept'])} "
        f"ledger_unavailable={quarantine_report.get('ledger_unavailable')}"
    )
    if dangling_hook_registrations:
        result["diagnostics"].append(
            f"dangling hook registrations: {dangling_hook_registrations}"
        )
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
    parser.add_argument(
        "--allow-in-flight",
        action="store_true",
        default=False,
        help=(
            "Override the pre-flight halt on a major version step with "
            "in-flight PLANs (PLAN-AH8, outcome: blocked)."
        ),
    )
    args = parser.parse_args(argv)
    target_root = (
        pathlib.Path(args.target_root).expanduser().resolve()
        if args.target_root
        else pathlib.Path.cwd().resolve()
    )
    result = sync(target_root, ref=args.ref, allow_in_flight=args.allow_in_flight)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
