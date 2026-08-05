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
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Library import - the shared Step-line pattern lives in the plan-pipeline
# skill (PLAN-AJ1). Resolved with the same walk as
# .claude/skills/ideate/lib/render_critique.py:44 - parents[N] to reach the
# target lib directory, insert on sys.path when absent, import inside a try
# that raises a typed ImportError naming the expected location. Referring to
# the preceding Step in the PLAN rather than to a number is deliberate - an
# ordinal cross-reference in a PLAN about ordinal drift is the defect it
# exists to fix.
# ---------------------------------------------------------------------------

_STEP_RENUMBER_LIB = Path(__file__).resolve().parents[2] / "plan-pipeline" / "lib"

if str(_STEP_RENUMBER_LIB) not in sys.path:
    sys.path.insert(0, str(_STEP_RENUMBER_LIB))

try:
    from step_renumber import STEP_LINE_RE as _STEP_LINE_RE
except ImportError as e:
    raise ImportError(
        f"Cannot import STEP_LINE_RE from {_STEP_RENUMBER_LIB}. "
        "Expected it alongside the plan-pipeline skill under "
        ".claude/skills/plan-pipeline/lib/step_renumber.py. "
        f"Original error: {e}"
    ) from e


# Ceiling per D1 (PLAN-AC7).
STEP_COUNT_CEILING: int = 12

# Regex marking the start of the Steps section.
_STEPS_HEADING_RE: re.Pattern[str] = re.compile(r'^## Steps\s*$', re.MULTILINE)

# Regex marking the start of any subsequent level-2 heading.
_NEXT_H2_RE: re.Pattern[str] = re.compile(r'^## ', re.MULTILINE)

# A line carrying substantive content inside the Steps block. Used only to tell
# "this PLAN has few Steps" apart from "this Steps section is not in the form the
# counter reads". Template placeholder lines and markdown scaffolding do not count.
_SUBSTANTIVE_LINE_RE: re.Pattern[str] = re.compile(r'^\s*(?:[-*+]\s+|#{1,6}\s+|\d+\)\s+|\w)')

# Bracketed template guidance, e.g. the plan-template's "[Numbered steps to execute ...]".
_TEMPLATE_GUIDANCE_RE: re.Pattern[str] = re.compile(r'^\s*[\[<]')


def _steps_block_has_content(block: str) -> bool:
    """
    Return True when the Steps block carries lines that look like authored content
    rather than an empty or placeholder-only section.
    """
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _TEMPLATE_GUIDANCE_RE.match(line):
            continue
        if _SUBSTANTIVE_LINE_RE.match(line):
            return True
    return False


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

    # A count of zero has two very different causes, and absorbing both as "small
    # PLAN" is a silent false pass: the ceiling check reports nothing wrong on a
    # PLAN it could not read at all. Distinguish them before comparing to the
    # ceiling. Note this cannot be fixed by making the counter cleverer - any
    # format-based counter can match zero against a form it does not recognise,
    # so the check has to notice that it found nothing and say so.
    if n == 0:
        block = _extract_steps_block(plan_text)
        if not _STEPS_HEADING_RE.search(plan_text):
            reason = "no '## Steps' heading was found"
        elif _steps_block_has_content(block):
            reason = (
                "the '## Steps' section carries content but no line matches the "
                r"counting algorithm r'^\d+\.\s+' (D4). Steps written as headings, "
                'bullets, or any other form are invisible to the ceiling check'
            )
        else:
            # Genuinely empty Steps section - a different defect, caught elsewhere.
            reason = ''

        if reason and 'PSZ002' not in ack_codes:
            return {
                'code': 'PSZ002',
                'level': 'warning',
                'category': 'plan-sizing',
                'location': '## Steps',
                'message': (
                    f'uncountable-steps: the step-count ceiling check could not run because '
                    f'{reason}. The PLAN has not been found compliant with the '
                    f'{STEP_COUNT_CEILING}-Step ceiling - it has not been measured against it.'
                ),
                'suggested_fix': (
                    r"Write top-level Steps as lines matching r'^\d+\.\s+' (e.g. '1. Read ...') "
                    'inside the ## Steps section, per the D4 counting algorithm in '
                    '_shared/plan-safe.md. If this PLAN genuinely has no Steps, add PSZ002 to '
                    'audit_acknowledgements with a rationale.'
                ),
            }

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
