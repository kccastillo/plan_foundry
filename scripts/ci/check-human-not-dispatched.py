#!/usr/bin/env python3
"""Guard the `assigned_to: human` no-dispatch branch against removal.

A PLAN whose steps only a human-driven parent session can perform declares
`assigned_to: human`. The orchestrator's dispatch path resolves that value
through the prose surfaces named in `REQUIRED` below. None of them carried a
`human` branch until
2026-08-05, so the value fell through to "unrecognised" and an executor was
dispatched against steps it is structurally unable to perform: invoking
`plan-pipeline`, `ideate` or `write-input`, all barred by the executor
capability boundary in `_shared/executor-capability-boundary.md`. That is the
PLAN-009 regression shape, and PLAN-AK3's plan-safety audit caught it live.

The branch is prose because the whole dispatch path is prose - the orchestrator
is the reader. This guard is what makes the branch load-bearing rather than
advisory: delete any surface's `human` row and CI goes red.

Three surfaces state the mapping, not two. The first pass of this guard covered
the tier table and section 4C and missed `plan-pipeline/SKILL.md`, which the
orchestrator loads at every invocation and which enumerated three executor
destinations with a `default` that swallowed anything unrecognised. PLAN-AK3's
plan-safety re-audit caught the omission: a surface outside `REQUIRED` can
contradict the two inside it while CI stays green. Any new statement of the
mapping belongs in `REQUIRED` on the same day it is written.

Modelled on check-mobile-web-claim.py: a missing required pattern fails CI.

Exit 0 if every surface named in `REQUIRED` carries the branch, 1 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Each entry: (relative path, human-readable surface name, required pattern).
# The patterns match the semantic content - a `human` value next to a refusal
# to dispatch - rather than exact wording, so the prose can be rewritten
# without a false failure while a deletion still fails.
REQUIRED = (
    (
        ".claude/skills/plan-pipeline/references/phase-state-machine.md",
        "executor-tier table",
        re.compile(r"(?i)`human`[^\n]{0,80}\bdo not dispatch\b"),
    ),
    (
        ".claude/skills/plan-pipeline/workflows/dispatch.md",
        "section 4C dispatch mapping",
        re.compile(r"(?i)`human`[^\n]{0,40}->[^\n]{0,40}\bdo not dispatch\b"),
    ),
    (
        ".claude/skills/plan-pipeline/SKILL.md",
        "essential-principles tier-selection line",
        re.compile(r"(?i)`human`[^\n]{0,60}\bdo not dispatch\b"),
    ),
    (
        ".claude/agents/plan-executor.md",
        "executor agent's own tier statement",
        re.compile(r"(?i)`assigned_to: human`[^\n]{0,40}\bnot dispatched\b"),
    ),
)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    failures: list[str] = []
    for rel, surface, pattern in REQUIRED:
        path = REPO_ROOT / rel
        if not path.is_file():
            failures.append(f"{rel}: missing (expected the {surface})")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not pattern.search(text):
            failures.append(f"{rel}: the {surface} carries no `human` no-dispatch branch")

    if failures:
        print("check-human-not-dispatched: the no-dispatch branch has been lost")
        for f in failures:
            print(f"  {f}")
        print()
        print(
            "A PLAN with `assigned_to: human` must halt at `checked` rather than "
            "reaching an executor. Without an explicit branch the value resolves as "
            "unrecognised and routes to `plan-executor`, which cannot invoke "
            "plan-pipeline, ideate or write-input. Restore the branch in every "
            "surface named above - see PLAN-AK3's plan-safety audit, 2026-08-05."
        )
        return 1

    print("check-human-not-dispatched: every dispatch surface refuses `assigned_to: human`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
