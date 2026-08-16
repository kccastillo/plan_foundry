#!/usr/bin/env python3
"""
uninstall.py - Implementation of plan-foundry-uninstall.

Local-only. Removes the four bundle-managed dirs, the version pin,
the bundle .gitignore entries, and the CLAUDE.md sentinel block.
Leaves Workbench/, Retired/, and project-local .claude/
files untouched.

Always exits 0; status is conveyed via JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import stat
import sys

_LIB_DIR = pathlib.Path(__file__).resolve().parent
_SHARED = _LIB_DIR.parent.parent / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

BUNDLE_IDENTITY = "plan_foundry"


def _installed_bundle_identity(shared: pathlib.Path):
    """Return the `bundle` field of the installed _shared/bundle-contract.json.

    Inline, importing nothing from _shared/, for the reason given at length
    in plan-foundry-sync/lib/sync.py's installed_bundle_identity: this is
    the function that decides whether _shared/ can be trusted, so it cannot
    be loaded from _shared/. None means absent or malformed or fieldless -
    the pre-identity state that every consumer installed before this field
    existed is in, which is trusted.
    """
    path = pathlib.Path(shared) / "bundle-contract.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("bundle")
    return value if isinstance(value, str) and value else None


_FOREIGN_SHARED = _installed_bundle_identity(_SHARED)
if _FOREIGN_SHARED == BUNDLE_IDENTITY:
    _FOREIGN_SHARED = None

# A sibling bundle's _shared/ at this path carries its own
# REQUIRED_GITIGNORE_ENTRIES, and uninstall reverses whatever it reads. Left
# unchecked that strips the other bundle's .gitignore entries while leaving
# plan_foundry's behind - the exact inversion of what uninstall is for. When
# the installed _shared/ is not ours the entries are left alone and the step
# reports SKIPPED with the reason; every other uninstall step is unaffected,
# because they read no _shared/ helper.
if _FOREIGN_SHARED is None:
    from gitignore_entries import REQUIRED_GITIGNORE_ENTRIES  # noqa: E402
else:
    REQUIRED_GITIGNORE_ENTRIES = ()

BUNDLE_MANAGED_DIRS = ("skills", "agents", "commands", "hooks")
# GITIGNORE_BUNDLE_ENTRIES = the canonical list plus "Retired/", appended
# locally rather than folded into the shared module (PLAN-AH7 Step 11) - see
# _shared/gitignore_entries.py's module docstring for why the divergence is
# preserved rather than unified.
GITIGNORE_BUNDLE_ENTRIES = ("Retired/",) + REQUIRED_GITIGNORE_ENTRIES
SENTINEL_START = "<!-- plan-foundry:init-plan-foundry:start -->"
SENTINEL_END = "<!-- plan-foundry:init-plan-foundry:end -->"


def _force_rmtree(path: pathlib.Path) -> bool:
    """Remove path, clearing the read-only bit on failure before retrying.

    Returns True once the path is confirmed gone, False if anything under it
    survives - a locked file, a permission the chmod retry could not clear,
    or any other OSError neither attempt could work around.
    """

    def on_error(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
        except OSError:
            return
        try:
            func(p)
        except OSError:
            return

    shutil.rmtree(path, onerror=on_error)
    return not path.exists()


def _remove_bundle_dirs(target_claude: pathlib.Path) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    failed: list[str] = []
    for sub in BUNDLE_MANAGED_DIRS:
        path = target_claude / sub
        if path.exists():
            if _force_rmtree(path):
                removed.append(f".claude/{sub}/")
            else:
                failed.append(f".claude/{sub}/")
    return removed, failed


def _remove_files(target_root: pathlib.Path) -> tuple[list[str], list[str]]:
    """Remove the version pin, install receipt, telemetry log, the
    quarantine tree, and any leftover .plan-foundry-tmp/ (PLAN-AH7 Step 13:
    uninstall previously knew neither the receipt nor the quarantine tree
    and would leave both behind). Also removes the incomplete-sync marker
    (PLAN-AK6) - a target being uninstalled mid-repair should not leave that
    marker behind for whatever installs next to trip over."""
    removed: list[str] = []
    failed: list[str] = []
    target_claude = target_root / ".claude"
    for relpath in (
        ".plan-foundry-bundle-version",
        ".plan-foundry-bundle-files",
        ".plan-foundry-sync-incomplete",
    ):
        p = target_claude / relpath
        if p.exists():
            try:
                p.unlink()
            except OSError:
                failed.append(f".claude/{relpath}")
            else:
                removed.append(f".claude/{relpath}")
    quarantine_dir = target_claude / ".plan-foundry-quarantine"
    if quarantine_dir.exists():
        if _force_rmtree(quarantine_dir):
            removed.append(".claude/.plan-foundry-quarantine/")
        else:
            failed.append(".claude/.plan-foundry-quarantine/")
    receipts_dir = target_claude / ".bundle-receipts"
    if receipts_dir.exists():
        if _force_rmtree(receipts_dir):
            removed.append(".claude/.bundle-receipts/")
        else:
            failed.append(".claude/.bundle-receipts/")
    tmp = target_root / ".plan-foundry-tmp"
    if tmp.exists():
        if _force_rmtree(tmp):
            removed.append(".plan-foundry-tmp/")
        else:
            failed.append(".plan-foundry-tmp/")
    return removed, failed


def _reverse_gitignore(target_root: pathlib.Path) -> list[str]:
    gi = target_root / ".gitignore"
    if not gi.exists():
        return []
    if _FOREIGN_SHARED is not None:
        # The entry list would have come from another bundle's helper. Doing
        # nothing is the only safe move; say so rather than reporting an
        # empty removal as success.
        return [
            f".gitignore: SKIPPED - installed .claude/skills/_shared/ belongs "
            f"to '{_FOREIGN_SHARED}', not '{BUNDLE_IDENTITY}'; entries left "
            f"in place for you to remove by hand"
        ]
    lines = gi.read_text(encoding="utf-8").splitlines()
    removed_entries: list[str] = []
    kept: list[str] = []
    bundle_set = set(GITIGNORE_BUNDLE_ENTRIES)
    for line in lines:
        if line.strip() in bundle_set:
            removed_entries.append(line.strip())
        else:
            kept.append(line)
    # Trim trailing blank lines if we removed content
    while kept and kept[-1].strip() == "":
        kept.pop()
    if not kept:
        gi.unlink()
    else:
        gi.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return [f".gitignore: {e}" for e in removed_entries]


def _remove_sentinel_block(target_root: pathlib.Path) -> list[str]:
    claude_md = target_root / "CLAUDE.md"
    if not claude_md.exists():
        return []
    text = claude_md.read_text(encoding="utf-8")
    start_idx = text.find(SENTINEL_START)
    end_idx = text.find(SENTINEL_END)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        return []
    # Extend end_idx to the end of the line containing SENTINEL_END
    line_end = text.find("\n", end_idx)
    if line_end == -1:
        line_end = len(text)
    else:
        line_end += 1  # include the newline
    # Extend start_idx backwards to the start of its line
    line_start = text.rfind("\n", 0, start_idx)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1  # don't include the previous line's newline
    # Trim one preceding blank line if present (cosmetic)
    if line_start >= 2 and text[line_start - 2 : line_start] == "\n\n":
        line_start -= 1
    new_text = text[:line_start] + text[line_end:]
    claude_md.write_text(new_text, encoding="utf-8")
    return ["CLAUDE.md sentinel block"]


def _list_kept(target_root: pathlib.Path) -> list[str]:
    kept: list[str] = []
    for d in ("Workbench", "Retired"):
        if (target_root / d).exists():
            kept.append(f"{d}/")
    target_claude = target_root / ".claude"
    if target_claude.exists():
        for entry in sorted(target_claude.iterdir()):
            # The bundle-managed dirs were just removed in Step 1.
            # Anything left is operator data.
            kept.append(f".claude/{entry.name}")
    return kept


def uninstall(target_root: pathlib.Path) -> dict:
    target_root = pathlib.Path(target_root)
    target_claude = target_root / ".claude"
    removed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    if not target_claude.exists():
        skipped.append(".claude/ (already absent)")
    else:
        dirs_removed, dirs_failed = _remove_bundle_dirs(target_claude)
        removed.extend(dirs_removed)
        failed.extend(dirs_failed)
        files_removed, files_failed = _remove_files(target_root)
        removed.extend(files_removed)
        failed.extend(files_failed)

    removed.extend(_reverse_gitignore(target_root))
    removed.extend(_remove_sentinel_block(target_root))

    # If .claude/ is now empty, remove it.
    if target_claude.exists() and not any(target_claude.iterdir()):
        target_claude.rmdir()
        removed.append(".claude/ (empty after cleanup)")

    kept = _list_kept(target_root)
    outcome = "exception" if failed else "success"
    summary = (
        f"uninstalled plan_foundry; removed {len(removed)} path(s); "
        f"kept {len(kept)} operator-data path(s)"
    )
    if failed:
        summary += f"; FAILED to remove {len(failed)} path(s)"
    payload = {"removed": removed, "skipped": skipped, "kept": kept}
    if failed:
        payload["failed"] = failed
    return {
        "outcome": outcome,
        "payload": payload,
        "summary": summary,
    }


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
    result = uninstall(target_root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
