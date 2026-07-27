"""
plan_sizing.py - PLAN-size lint for audit-haiku-safe.

Exposes a single public function:

    check_plan_sizing(plan_text, ack_codes) -> dict | None

Returns a PSZ001 finding dict when the PLAN has more than 12 top-level Steps
and PSZ001 is not in the provided acknowledgement codes list. Returns None
when no finding is warranted.

Step-counting algorithm (D4, PLAN-AC7):
  Count lines matching regex r'^\\d+\\.\\s+' (one or more digits, period,
  whitespace, content) appearing between the '## Steps' heading and the next
  '## ' heading (or end of file). Top-level only - sub-items with leading
  whitespace before the digit and letter-prefixed items (e.g. 'a.') are not
  counted.

Design notes:
  - The check is always warn-severity (Not blocker). PSZ001 is a heuristic
    ceiling; a genuinely large atomic PLAN may pass with a recorded
    acknowledgement.
  - This module is the lib-level implementation of the D4 algorithm described
    in audit-haiku-safe/workflows/audit-haiku-safe-steps.md Step 4d.
  - The auditor itself is LLM-driven (reads the workflow doc); this module
    is the testable algorithmic reference. The lib test (test_plan_sizing.py)
    is illustrative and provides algorithmic confidence, not LLM enforcement.

Encoding: reads plan_text as a string (caller opens with errors='replace').
"""

from __future__ import annotations

import re
from typing import Optional


# Ceiling per D1 (PLAN-AC7).
STEP_COUNT_CEILING: int = 12

# Regex for a top-level Step line (D4 algorithm).
_STEP_LINE_RE: re.Pattern[str] = re.compile(r'^\d+\.\s+')

# Regex marking the start of the Steps section.
_STEPS_HEADING_RE: re.Pattern[str] = re.compile(r'^## Steps\s*$', re.MULTILINE)

# Regex marking the start of any subsequent level-2 heading.
_NEXT_H2_RE: re.Pattern[str] = re.compile(r'^## ', re.MULTILINE)


def _extract_steps_block(plan_text: str) -> str:
    """
    Return the text between the '## Steps' heading and the next '## ' heading
    (exclusive), or to end-of-file if no subsequent heading exists.

    Returns an empty string if no '## Steps' heading is found.
    """
    match = _STEPS_HEADING_RE.search(plan_text)
    if match is None:
        return ''

    # Start scanning after the heading line (past its newline).
    after_heading = plan_text[match.end():]

    # Find the next level-2 heading within the remaining text.
    next_h2 = _NEXT_H2_RE.search(after_heading)
    if next_h2 is None:
        return after_heading
    return after_heading[: next_h2.start()]


def count_steps(plan_text: str) -> int:
    """
    Count top-level Steps in a PLAN's '## Steps' section using the D4 algorithm.

    Returns the integer count of lines matching r'^\\d+\\.\\s+' in the Steps block.
    """
    block = _extract_steps_block(plan_text)
    return sum(1 for line in block.splitlines() if _STEP_LINE_RE.match(line))


def check_plan_sizing(plan_text: str, ack_codes: list[str]) -> Optional[dict]:
    """
    Check whether a PLAN exceeds the step-count ceiling (D1 = 12).

    Parameters
    ----------
    plan_text : str
        Full text of the PLAN markdown file.
    ack_codes : list[str]
        Contents of the PLAN's 'audit_acknowledgements' frontmatter field.
        Pass an empty list if the field is absent or empty.

    Returns
    -------
    dict | None
        A PSZ001 finding dict if the PLAN has > 12 top-level Steps and PSZ001
        is not in ack_codes. None otherwise.
    """
    n = count_steps(plan_text)

    if n <= STEP_COUNT_CEILING:
        return None

    if 'PSZ001' in ack_codes:
        return None

    return {
        'code': 'PSZ001',
        'level': 'warning',
        'category': 'plan-sizing',
        'location': '## Steps',
        'message': (
            f'oversized-plan: PLAN has {n} top-level Steps (ceiling is {STEP_COUNT_CEILING}, '
            f'per D1 - PLAN-AC7). Decompose into a plan-of-plans or sequential PLANs, or add '
            f'PSZ001 to audit_acknowledgements with a rationale in the Context section.'
        ),
        'suggested_fix': (
            'Split into a plan-of-plans (parent PLAN with triggers_plans: [...]) or sequential '
            'PLANs. If decomposition is genuinely impractical, add PSZ001 to '
            'audit_acknowledgements and document the rationale in Context.'
        ),
    }
