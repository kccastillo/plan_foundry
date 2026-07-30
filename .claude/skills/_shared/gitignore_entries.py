"""
gitignore_entries.py - canonical .gitignore entry list for plan_foundry
bundle-managed paths.

Single source of truth (PLAN-AH7 Step 11). Before this module existed,
init-plan-foundry/lib/run_install.py and plan-foundry-uninstall/lib/uninstall.py
each defined their own copy - REQUIRED_GITIGNORE_ENTRIES and
GITIGNORE_BUNDLE_ENTRIES respectively - and the two had already drifted:
uninstall's list additionally carried "Retired/", which init's list
intentionally omits (Retired/ is tracked per PLAN-AD0 D2-A). That divergence
is real and is preserved here rather than silently unified - this module
does NOT carry "Retired/"; uninstall.py appends it locally at its own call
site so the divergence stays visible where it is used, not encoded into the
shared list. Resolving whether uninstall should stop reversing that entry is
a separate question, out of scope for this PLAN.

REQUIRED_GITIGNORE_ENTRIES includes the two paths PLAN-AH7 adds
(.claude/.plan-foundry-bundle-files, .claude/.plan-foundry-quarantine/) so
that plan-foundry-sync's convergence step (sync.py) reaches every
already-installed consumer, not just fresh installs via init-plan-foundry -
init-only would leave the entire existing consumer population (the
population this substrate exists for) with both paths untracked and
committable.
"""

from __future__ import annotations

import pathlib

REQUIRED_GITIGNORE_ENTRIES = (
    "Workbench/.heartbeat/",
    ".plan-foundry-tmp/",
    ".claude/skills/",
    ".claude/agents/",
    ".claude/commands/",
    ".claude/hooks/",
    ".claude/.plan-foundry-bundle-version",
    ".claude/.plan-foundry-bundle-files",
    ".claude/.plan-foundry-quarantine/",
)


def ensure_gitignore_entries(
    target_root: pathlib.Path, entries=REQUIRED_GITIGNORE_ENTRIES
) -> tuple:
    """Append any of `entries` missing from target_root/.gitignore.

    Non-clobbering, append-only, idempotent - mirrors the original
    init-plan-foundry _step_gitignore behaviour. Read/write with
    encoding="utf-8".

    Returns (status, added) where status is "PASS" if any entries were
    added, else "SKIPPED". `added` is the list of entries that were newly
    written (empty when SKIPPED).
    """
    target_root = pathlib.Path(target_root)
    gi = target_root / ".gitignore"
    existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
    lines = existing.splitlines()
    line_set = {ln.strip() for ln in lines}
    added: list = []
    for entry in entries:
        if entry not in line_set:
            lines.append(entry)
            added.append(entry)
    if added:
        gi.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return "PASS", added
    return "SKIPPED", []
