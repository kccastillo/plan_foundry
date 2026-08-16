#!/usr/bin/env python3
"""Guard against the mobile/web skill-loading claim reversing again.

The repo held two contradictory claims about whether Claude Code mobile and
web sessions read project-local `.claude/{skills,agents,commands}/`. The
human settled it on 2026-07-29: they do NOT. Two sites still carried the old
"DO read/load" claim - `.claude/skills/init-plan-foundry/operating-rules.md`
and `ARCHITECTURE.md` - and were corrected. This is the guard against the
false claim being restated on the durable/shipped surface.

Modelled on check_value_guards in check-harness-contract.py: a regex hit
anywhere under the scanned roots fails CI. It is a standalone script rather
than a harness-contract.md register entry because that register's required
fields (Version observed, Assumption, Re-derivation) describe a harness
capability, not a documentation claim, and its scan roots exclude the repo
root, where ARCHITECTURE.md lives.

Scope is the durable/shipped surface: `.claude/`, `scripts/`, and the root
reference docs. `Workbench/` is excluded - it is ephemeral working material
(per project convention) and several retired-but-not-yet-swept notes there
quote the old claim verbatim while discussing the contradiction itself; they
are not restating it as fact. `Retired/` is excluded outright - frozen
history is not a live claim.

Exit 0 if the surface is clean, 1 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# mobile ... web ... "do" not immediately followed by "not" ... read/load.
# Catches "mobile and web apps DO read ..." and "Mobile and web ... DO load
# ..." in either case; does not catch "do NOT read/load" or phrasings that
# never place an unnegated "do" between the two nouns and the verb.
PATTERN = re.compile(
    r"(?i)mobile[^\n]{0,30}web[^\n]{0,40}\bdo\b(?!\s*not\b)[^\n]{0,10}\b(read|load)\b"
)

ROOT_DOCS = ("CLAUDE.md", "ARCHITECTURE.md", "README.md", "BOOTSTRAP.md")
SCAN_DIRS = (".claude", "scripts")
SCAN_SUFFIXES = (".md", ".py", ".sh", ".json")
EXCLUDED_PARTS = {"Retired", ".git", "__pycache__", "node_modules", ".plan-foundry-tmp"}


def scan_files() -> list[Path]:
    out = []
    for name in ROOT_DOCS:
        p = REPO_ROOT / name
        if p.is_file():
            out.append(p)
    for base in SCAN_DIRS:
        root = REPO_ROOT / base
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix not in SCAN_SUFFIXES:
                continue
            if p.resolve() == Path(__file__).resolve():
                continue
            if set(p.relative_to(REPO_ROOT).parts) & EXCLUDED_PARTS:
                continue
            out.append(p)
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    violations: list[str] = []
    for path in scan_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                violations.append(f"{rel}:{lineno}: {line.strip()}")

    if violations:
        print("check-mobile-web-claim: the superseded claim has returned")
        for v in violations:
            print(f"  {v}")
        print()
        print(
            "Claude Code mobile and web sessions do NOT read project-local "
            "`.claude/{skills,agents,commands}/`. This was settled 2026-07-29 - "
            "see Retired/HANDOFF-NEXT-SESSION-202607291630.md."
        )
        return 1

    print("check-mobile-web-claim: no restatement of the superseded claim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
