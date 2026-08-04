#!/usr/bin/env python3
"""
gitattributes_pin.py - ensure a consumer repo pins LF endings for bundle hooks.

Single source of truth for the line-ending pin, shared by `init-plan-foundry`
(fresh install) and `plan-foundry-sync` (converge an existing install). Both
call `ensure_gitattributes_pin()`; neither restates the pin lines.

Why this exists
---------------
Git executes hooks via their shebang. On a Windows checkout with
`core.autocrlf=true` (the Git for Windows default) a hook committed with LF is
written to the working tree with CRLF, and the kernel reads the shebang as
`/usr/bin/env sh\\r`:

    .git/hooks/commit-msg: /usr/bin/env: 'sh\\r': No such file or directory

The failure mode is the dangerous kind - the file looks correct in the repo, in
a diff, and in review; nothing surfaces the CR. The bundle's `commit-msg` hook
additionally exits 0 on every failure path by design so it can never stall a
pipeline, which means a broken hook and a working hook are outwardly identical.

A pin in the *bundle* repo does not travel with copied files: sync writes files
into the consumer's working tree, and the consumer's own `.gitattributes`
governs their checkout. So the pin has to be written into the consumer's repo,
which is what this module does.

Non-clobbering by the same discipline as the settings merge (PLAN-AH2): existing
consumer entries are never rewritten or reordered, and an existing pin for the
same pattern is left exactly as the consumer wrote it, whatever value it names.

Per FOUNDRYREQ-plan_foundry_dev-20260727-1350 and PLAN-AD2 D10.
"""

import pathlib

# The patterns this bundle requires, as (pattern, full_line) pairs. Matching is
# on the pattern alone, so a consumer who has already pinned `*.sh` to anything
# is left untouched - we do not adjudicate their choice, only ensure coverage.
REQUIRED_GITATTRIBUTES_PINS = [
    ("*.sh", "*.sh             text eol=lf"),
    (".claude/hooks/**", ".claude/hooks/** text eol=lf"),
]

_HEADER = [
    "",
    "# plan_foundry: git hooks and shell scripts must keep LF endings.",
    "# A CRLF-terminated shebang makes the kernel look for an interpreter named",
    "# `sh\\r`, so the hook fails silently on Windows checkouts. See",
    "# .claude/skills/_shared/gitattributes_pin.py for the full rationale.",
]


def _pattern_of(line: str) -> str:
    """Return the pattern field of a .gitattributes line, or '' for non-rules."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return ""
    return stripped.split()[0]


def ensure_gitattributes_pin(target_root: pathlib.Path) -> tuple[str, list[str]]:
    """
    Ensure `<target_root>/.gitattributes` covers every required pin.

    Creates the file when absent. Appends only the missing patterns, preserving
    everything already present byte-for-byte. Idempotent - a second call on an
    already-converged repo returns ("SKIPPED", []).

    Returns (status, added_lines) where status is "PASS" when the file was
    written and "SKIPPED" when it was already compliant.
    """
    ga = target_root / ".gitattributes"
    existing = ga.read_text(encoding="utf-8", errors="replace") if ga.exists() else ""
    lines = existing.splitlines()
    covered = {_pattern_of(ln) for ln in lines}

    missing = [line for pattern, line in REQUIRED_GITATTRIBUTES_PINS if pattern not in covered]
    if not missing:
        return "SKIPPED", []

    if lines:
        lines.extend(_HEADER)
    else:
        # Fresh file - drop the leading blank from the header.
        lines.extend(_HEADER[1:])
    lines.extend(missing)
    ga.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return "PASS", missing


def check_gitattributes_pin(target_root: pathlib.Path) -> list[str]:
    """Return the list of required patterns not covered by target_root. Read-only."""
    ga = target_root / ".gitattributes"
    if not ga.exists():
        return [pattern for pattern, _ in REQUIRED_GITATTRIBUTES_PINS]
    covered = {
        _pattern_of(ln)
        for ln in ga.read_text(encoding="utf-8", errors="replace").splitlines()
    }
    return [pattern for pattern, _ in REQUIRED_GITATTRIBUTES_PINS if pattern not in covered]
