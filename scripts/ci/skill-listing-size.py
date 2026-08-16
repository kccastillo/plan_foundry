#!/usr/bin/env python3
"""
skill-listing-size.py - re-derive the skill listing's context cost on demand.

Every skill's name and description sit in context on every turn, in every
project that has the skill installed, whether or not the skill is ever used.
That total is the thing to watch, and it is exactly the thing that must never
be written down: a number on disk is right on the day it is typed and silently
wrong afterwards. So this prints it instead.

Delisted skills (`disable-model-invocation: true`) are excluded from the total.
Their descriptions leave the listing, which is the whole point of delisting one.
They are still reported, under a separate heading, because a delisted skill is
still a skill somebody has to be able to find.

The per-skill cap is READ from `.claude/skills/_shared/harness-contract.md`
rather than hard-coded here. The register guards the value so a copy fails, and
this script is the reason the guard is worth having.

USAGE:
    python3 scripts/ci/skill-listing-size.py               # report
    python3 scripts/ci/skill-listing-size.py --check-caps  # fail if any skill is over
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
REGISTER = REPO_ROOT / ".claude" / "skills" / "_shared" / "harness-contract.md"

# The listing carries `description` plus `when_to_use`, and truncates the pair.
LISTED_FIELDS = ("description", "when_to_use")

_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")


def read_cap() -> int:
    """Pull the combined description cap out of the harness contract.

    Fails loudly rather than falling back to a default. A silent default is how
    a checker ends up asserting a number nobody registered.
    """
    if not REGISTER.is_file():
        raise SystemExit(
            "ERROR: skill-listing-size: harness-contract.md not found. "
            "The cap is registered there and is not defaulted here."
        )
    text = REGISTER.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"truncated at ([\d,]+) characters", text)
    if not m:
        raise SystemExit(
            "ERROR: skill-listing-size: could not read the combined description "
            "cap from harness-contract.md. Refusing to run - an unparseable cap "
            "would silently check nothing."
        )
    return int(m.group(1).replace(",", ""))


def parse_frontmatter(text: str) -> dict:
    """Tolerant top-level frontmatter reader.

    Deliberately not pyyaml. This runs as a CI gate and must not acquire a
    dependency to read two keys. Continuation lines are folded into the
    preceding value, which is how a wrapped description survives.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict = {}
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = _KEY.match(line)
        if m and not line.startswith((" ", "\t")):
            key = m.group(1)
            out[key] = m.group(2).strip()
        elif key is not None and line.strip():
            out[key] = (out[key] + " " + line.strip()).strip()
    for key, value in out.items():
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            out[key] = value[1:-1]
    return out


def collect() -> list:
    """One record per skill: (name, listed_chars, delisted)."""
    if not SKILLS_DIR.is_dir():
        raise SystemExit("ERROR: skill-listing-size: .claude/skills/ not found.")
    out = []
    for child in sorted(SKILLS_DIR.iterdir()):
        skill_md = child / "SKILL.md"
        if not child.is_dir() or child.name == "_shared" or not skill_md.is_file():
            continue
        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
        name = fm.get("name", child.name)
        listed = sum(len(fm.get(f, "")) for f in LISTED_FIELDS)
        delisted = fm.get("disable-model-invocation", "").strip().lower() == "true"
        # The listing carries the name too, always, even when delisted.
        out.append((name, len(name) + listed, listed, delisted))
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    check_caps = "--check-caps" in sys.argv
    cap = read_cap()
    records = collect()

    live = [r for r in records if not r[3]]
    delisted = [r for r in records if r[3]]

    print("# skill listing size (re-derived, never recorded)")
    print(f"# per-skill cap read from harness-contract.md: {cap}")
    print()

    print("listed (in context on every turn):")
    for name, total, listed, _ in sorted(live, key=lambda r: -r[1]):
        print(f"  {total:>6}  {name}  (description+when_to_use {listed})")
    print(f"  {'-' * 6}")
    print(f"  {sum(r[1] for r in live):>6}  TOTAL listed")
    print()

    if delisted:
        print("delisted (name only in the listing):")
        for name, total, listed, _ in sorted(delisted, key=lambda r: -r[2]):
            print(f"  {len(name):>6}  {name}  (description withheld, {listed} chars)")
        print(f"  recovered by delisting: {sum(r[2] for r in delisted)}")
        print()

    over = [(name, listed) for name, _, listed, _ in records if listed > cap]
    if over:
        print("ERROR: skill(s) over the registered per-skill cap:", file=sys.stderr)
        for name, listed in over:
            print(f"  - {name}: {listed} > {cap}", file=sys.stderr)
        if check_caps:
            return 1

    if check_caps:
        print("All skill descriptions are within the registered cap.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
