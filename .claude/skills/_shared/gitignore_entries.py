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
import subprocess

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


def filter_tracked(target_root: pathlib.Path, entries) -> tuple:
    """Split `entries` into (safe, skipped) by whether git already tracks
    content under each path.

    A consumer whose `.claude/skills/` is scratch space wants that path
    ignored. A repo that ships `.claude/` content has tracked files there,
    and adding the path to .gitignore untracks its product as a silent side
    effect of install - invisible until someone reads `git status`. So an
    entry with tracked content beneath it is dropped and reported
    (PLAN-AJ6 D4, raised from paper_trail_dev).

    Fail-open: if git is unavailable or the target is not a repo, nothing is
    tracked as far as we can tell, so every entry is treated as safe. That
    matches the pre-guard behaviour rather than blocking an install.
    """
    target_root = pathlib.Path(target_root)
    safe, skipped = [], []
    for entry in entries:
        try:
            proc = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", entry.rstrip("/")],
                cwd=str(target_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            tracked = proc.returncode == 0 and proc.stdout.strip() != ""
        except (OSError, subprocess.SubprocessError):
            tracked = False
        (skipped if tracked else safe).append(entry)
    return safe, skipped


def ensure_gitignore_entries(
    target_root: pathlib.Path, entries=REQUIRED_GITIGNORE_ENTRIES
) -> tuple:
    """Append any of `entries` missing from target_root/.gitignore.

    Non-clobbering, append-only, idempotent - mirrors the original
    init-plan-foundry _step_gitignore behaviour. Read/write with
    encoding="utf-8".

    Entries with tracked content beneath them are dropped first via
    filter_tracked and never written.

    Returns (status, added, skipped_tracked) where status is "PASS" if any
    entries were added, else "SKIPPED". `added` is the list of entries newly
    written (empty when SKIPPED). `skipped_tracked` is the list dropped
    because git already tracks content under them - a caller must surface it,
    because a dropped entry means the target owns that path.
    """
    target_root = pathlib.Path(target_root)
    entries, skipped_tracked = filter_tracked(target_root, entries)
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
        return "PASS", added, skipped_tracked
    return "SKIPPED", [], skipped_tracked
