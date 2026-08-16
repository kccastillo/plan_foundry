#!/usr/bin/env python3
"""
check-harness-contract.py - assert the harness-surface register is complete and
that no bundle file has drifted from it.

This bundle consumes harness capabilities rather than rebuilding them, and
harness surfaces move. The per-skill description cap and the skill-listing
budget have both changed, and superseded figures for each still circulate. The
register at `.claude/skills/_shared/harness-contract.md` records what is assumed
of every surface depended on. This checks the register itself.

Two jobs, and neither needs a network call:

  1. Every registered entry carries all five required fields, and its status is
     one of the three permitted values. A missing status counts as a missing
     field, because an unmarked assumption reads as verified when it is not.

  2. No bundle file outside the register restates a value the register guards.
     An entry may carry a `Value guard` regex for a figure that must be read
     from the register rather than copied. A copy is how the register goes
     stale without anything failing.

Detecting that a documented surface has MOVED is a human job, or `audit-skills`
with a network call. This detects that the bundle has drifted from its own
recorded assumptions, which is the half a check can do.

Modelled on check-live-references.py: same shape, aimed at harness surfaces
instead of internal paths.

Exit 0 if the register is sound, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTER = REPO_ROOT / ".claude" / "skills" / "_shared" / "harness-contract.md"

ENTRIES_HEADING = "Registered surfaces"

REQUIRED_FIELDS = ("Surface", "Version observed", "Assumption", "Re-derivation", "Status")
OPTIONAL_FIELDS = ("Value guard",)
VALID_STATUS = ("observed", "documented", "unverified")

# Scope for the value-guard scan. The register is excluded (it is where the
# value is supposed to live) and so are historical and transient trees.
GUARD_SCAN_ROOTS = (".claude", "scripts")
GUARD_SUFFIXES = (".md", ".py", ".sh", ".json")
GUARD_EXCLUDED_PARTS = {
    "Retired", ".git", "__pycache__", "node_modules", ".plan-foundry-tmp",
}

# `| **Field** | value |` - the row shape every entry uses.
ROW = re.compile(r"^\|\s*\*\*([^*|]+?)\*\*\s*\|\s*(.*?)\s*\|\s*$")

failures: list[str] = []


def fail(where: str, message: str) -> None:
    failures.append(f"{where}: {message}")


def rel(p: Path) -> str:
    return p.relative_to(REPO_ROOT).as_posix()


def parse_entries(text: str) -> dict:
    """Return {entry_title: {field: value}} for every `###` section under the
    `## Registered surfaces` heading.

    Sections are delimited structurally rather than by looking for a Surface
    row. An entry that has lost its Surface row must still be seen, or the
    check silently stops covering it - which is the failure mode it exists to
    prevent.
    """
    entries: dict = {}
    in_entries = False
    title = None
    for line in text.splitlines():
        if line.startswith("## "):
            in_entries = line[3:].strip() == ENTRIES_HEADING
            title = None
            continue
        if not in_entries:
            continue
        if line.startswith("### "):
            title = line[4:].strip()
            entries[title] = {}
            continue
        if title is None:
            continue
        m = ROW.match(line)
        if m:
            field, value = m.group(1).strip(), m.group(2).strip()
            if field in REQUIRED_FIELDS or field in OPTIONAL_FIELDS:
                entries[title][field] = value
    return entries


def check_register_shape(entries: dict) -> None:
    if not entries:
        fail(
            rel(REGISTER),
            f"no entries found under '## {ENTRIES_HEADING}' - refusing to pass. "
            "An unparseable register would silently check nothing.",
        )
        return

    for title, fields in sorted(entries.items()):
        where = f"{rel(REGISTER)} [{title}]"
        for required in REQUIRED_FIELDS:
            value = fields.get(required, "")
            if not value:
                fail(where, f"missing or empty required field '{required}'")
        status = fields.get("Status", "").strip().lower()
        if status and status not in VALID_STATUS:
            fail(
                where,
                f"Status is {status!r}, must be one of {', '.join(VALID_STATUS)}",
            )


def guard_scan_files() -> list:
    out = []
    for root_name in GUARD_SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix not in GUARD_SUFFIXES:
                continue
            if p.resolve() == REGISTER.resolve():
                continue
            if p.resolve() == Path(__file__).resolve():
                continue
            if set(p.relative_to(REPO_ROOT).parts) & GUARD_EXCLUDED_PARTS:
                continue
            out.append(p)
    return out


def check_value_guards(entries: dict) -> None:
    guards = []
    for title, fields in sorted(entries.items()):
        raw = fields.get("Value guard", "").strip()
        if not raw:
            continue
        pattern = raw.strip("`").strip()
        try:
            guards.append((title, re.compile(pattern)))
        except re.error as exc:
            fail(
                f"{rel(REGISTER)} [{title}]",
                f"Value guard is not a valid regular expression - {exc}",
            )
    if not guards:
        return

    for path in guard_scan_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for title, rx in guards:
                m = rx.search(line)
                if m:
                    fail(
                        f"{rel(path)}:{lineno}",
                        f"restates a value guarded by the register entry "
                        f"'{title}' ({m.group(0)!r}). Read it from "
                        f"harness-contract.md instead of copying it.",
                    )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("# harness contract - the register is complete and nothing has drifted from it")
    print()

    if not REGISTER.is_file():
        print(f"ERROR: {rel(REGISTER)} does not exist.", file=sys.stderr)
        return 1

    text = REGISTER.read_text(encoding="utf-8", errors="replace")
    entries = parse_entries(text)

    for label, fn in (
        ("every entry carries all required fields", lambda: check_register_shape(entries)),
        ("no bundle file restates a guarded value", lambda: check_value_guards(entries)),
    ):
        before = len(failures)
        fn()
        status = "ok" if len(failures) == before else "FAIL"
        print(f"  [{status}] {label}")

    print()
    for title, fields in sorted(entries.items()):
        print(f"  {fields.get('Status', '?'):<12} {title}")

    if failures:
        print()
        print("ERROR: harness contract problem(s):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print()
    print("Harness contract sound.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
