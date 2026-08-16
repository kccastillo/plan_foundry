#!/usr/bin/env python3
"""
check-no-marginalia.py - assert reference documents carry no commentary about themselves.

A skill, helper or reference file carries what the reader must do. It does not
carry provenance notes, adaptation commentary, open questions addressed to the
operator, or parked conflicts left for someone to resolve later. That material
belongs in a PLAN, a commit message or a Workbench input, all of which are built
to hold it.

Written 2026-07-29 after the human deleted an "Adapted for plan_foundry" section
and a "Provenance" section from _shared/writing-style.md and asked for a guard so
it would not come back. The rule alone had already failed once - CLAUDE.md said
to read that file before longform output and nobody did - so the rule is stated
in writing-style.md AND checked here.

The test a human would apply: does removing this sentence change what a reader
does? If not, it does not belong in the file. That test needs judgement, so this
script does not attempt it. It looks for the specific shapes the class takes,
which are narrow and high-signal.

Escape hatch: a line containing the literal comment marker below is exempt. This
mirrors the `determinism-ok` convention in check-invariants.py. Use it for a
genuine one-off, not to silence the rule wholesale.

Exit 0 if clean, 1 otherwise. Prints file, line and the offending text.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_ROOTS = [
    REPO_ROOT / ".claude" / "skills",
    REPO_ROOT / "references",
]

EXCLUDED_PARTS = {"Retired", ".git", "__pycache__", "node_modules", ".plan-foundry-tmp"}

EXEMPT_MARKER = "marginalia-ok"

# Section headings that are commentary about the document rather than content of it.
HEADING_PATTERNS = [
    (re.compile(r"^#{1,4}\s+Provenance\b", re.I), "provenance section"),
    (re.compile(r"^#{1,4}\s+Attribution\b", re.I), "attribution section"),
    (re.compile(r"^#{1,4}\s+Adapted for\b", re.I), "adaptation-commentary section"),
    (re.compile(r"^#{1,4}\s+Open question", re.I), "open question addressed to the reader"),
    (re.compile(r"^#{1,4}\s+Divergences?\b", re.I), "divergence-from-source section"),
]

# Phrases that only appear when a document is talking about itself.
PHRASE_PATTERNS = [
    (re.compile(r"\bdecision for the human\b", re.I), "defers a decision to the operator"),
    (re.compile(r"\bhuman may want to revisit\b", re.I), "parks a decision for later"),
    (re.compile(r"\brecorded here rather than dropped\b", re.I), "explains its own retention"),
    # "the source document" was tried here and removed the same day: convert-pdf uses
    # "source document" as domain vocabulary for the user's input file, so it fired twice
    # on config-schema.md with nothing wrong. A guard that cries wolf gets switched off.
    (re.compile(r"source document(?:'s)? (?:says|said|stated|defers|second|first|plain)", re.I), "compares itself to an original"),
    (re.compile(r"\bso it does not dangle\b", re.I), "explains its own construction"),
    (re.compile(r"\bthe two cannot both hold\b", re.I), "records an unresolved conflict"),
    (re.compile(r"\bnot one to take by transcription\b", re.I), "defers a decision to the operator"),
]


def live_markdown() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.md")):
            rel_parts = set(p.relative_to(REPO_ROOT).parts)
            if rel_parts & EXCLUDED_PARTS:
                continue
            out.append(p)
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    failures: list[str] = []
    scanned = 0

    for path in live_markdown():
        scanned += 1
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        in_frontmatter = False
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), 1):
            # Frontmatter is metadata, not prose. Skip it.
            if lineno == 1 and line.strip() == "---":
                in_frontmatter = True
                continue
            if in_frontmatter:
                if line.strip() == "---":
                    in_frontmatter = False
                continue
            # A fenced block holds a template, an example or quoted material. The
            # document is not talking about itself inside one. references/risk-criteria-
            # survey-prompt.md carries a report template whose "## Divergences" heading
            # is a required output section of the survey, not commentary on the prompt.
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if EXEMPT_MARKER in line:
                continue
            for pattern, why in HEADING_PATTERNS + PHRASE_PATTERNS:
                if pattern.search(line):
                    failures.append(f"{rel}:{lineno}: {why} - {line.strip()[:90]}")
                    break

    if failures:
        print("ERROR: reference documents must not carry commentary about themselves.", file=sys.stderr)
        print("Move it to a PLAN, a commit message or a Workbench input.", file=sys.stderr)
        print(f"Exempt a genuine one-off with an inline `{EXEMPT_MARKER}` marker.", file=sys.stderr)
        print("", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    print("no marginalia: markdown under .claude/skills and references is clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
