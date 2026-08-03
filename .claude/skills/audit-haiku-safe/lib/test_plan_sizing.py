"""
test_plan_sizing.py - pytest tests for the plan-sizing lint module (PSZ001).

Three test cases specified in PLAN-AC7 Step 5:
  (i)  11-Step PLAN -> no PSZ001 finding.
  (ii) 13-Step PLAN with no acknowledgement -> PSZ001 advisory fires.
  (iii) 13-Step PLAN with PSZ001 in audit_acknowledgements -> no finding.

Executor note: the auditor itself is LLM-driven (reads workflow doc); this
module provides algorithmic confidence for the D4 step-counting implementation
in plan_sizing.py. The test is illustrative rather than enforcing for the
LLM-driven check.

Follows the fixture pattern from test_substrate_fidelity.py: inline fixture
PLAN strings, no live repo files read.

Run with:
    python -m pytest .claude/skills/audit-haiku-safe/lib/test_plan_sizing.py
"""

import textwrap

import pytest

from plan_sizing import check_plan_sizing, count_steps, STEP_COUNT_CEILING


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan_text(num_steps: int, extra_section: bool = False) -> str:
    """
    Build a minimal PLAN markdown string with exactly num_steps top-level Steps.

    Each step line is a canonical top-level Step: '1. Do thing one', etc.
    If extra_section=True, add a trailing '## Notes' heading after Steps to
    verify the D4 algorithm stops at the next heading.
    """
    steps_lines = [f'{i + 1}. Do step number {i + 1}.' for i in range(num_steps)]
    steps_block = '\n'.join(steps_lines)

    # Avoid textwrap.dedent + f-string interaction (dedent sees mixed-indent when
    # a multi-line value is substituted into an indented template - it can't find
    # a common leading whitespace and strips nothing, leaving '## Steps' indented
    # and unmatchable by the anchored regex). Build the plan as a column-0 string
    # directly instead.
    plan = (
        '---\n'
        'schema_version: 2\n'
        'title: "Test PLAN"\n'
        'type: plan\n'
        'status: ready\n'
        'audit_acknowledgements: []\n'
        '---\n'
        '\n'
        '## Objective\n'
        '\n'
        'Test objective.\n'
        '\n'
        '## Steps\n'
        '\n'
        f'{steps_block}\n'
        '\n'
        '## Verification\n'
        '\n'
        '- [ ] placeholder\n'
        '      verify: true\n'
    )

    if extra_section:
        plan += '\n## Notes\n\nSome notes here.\n'

    return plan


# ---------------------------------------------------------------------------
# Test (i) - 11-Step PLAN: no PSZ001 finding
# ---------------------------------------------------------------------------

def test_eleven_steps_no_finding():
    """
    11-Step PLAN (below the ceiling of 12) -> check_plan_sizing returns None.
    """
    plan_text = _make_plan_text(num_steps=11)
    result = check_plan_sizing(plan_text, ack_codes=[])
    assert result is None, (
        f'Expected no PSZ001 finding for 11-Step PLAN (ceiling={STEP_COUNT_CEILING}), '
        f'got: {result}'
    )


# ---------------------------------------------------------------------------
# Test (ii) - 13-Step PLAN, no acknowledgement: PSZ001 fires
# ---------------------------------------------------------------------------

def test_thirteen_steps_no_ack_fires_psz001():
    """
    13-Step PLAN with no audit_acknowledgements -> PSZ001 advisory is returned.
    """
    plan_text = _make_plan_text(num_steps=13)
    result = check_plan_sizing(plan_text, ack_codes=[])

    assert result is not None, (
        'Expected PSZ001 finding for 13-Step PLAN with no acknowledgements, got None.'
    )
    assert result['code'] == 'PSZ001', f"Expected code PSZ001, got: {result['code']}"
    assert result['level'] == 'warning', (
        f"PSZ001 must be warn-severity (Not blocker), got level: {result['level']}"
    )
    assert result['category'] == 'plan-sizing', (
        f"Expected category plan-sizing, got: {result['category']}"
    )
    assert '13' in result['message'], (
        f"Finding message should mention the actual step count (13), got: {result['message']}"
    )


# ---------------------------------------------------------------------------
# Test (iii) - 13-Step PLAN with PSZ001 in audit_acknowledgements: no finding
# ---------------------------------------------------------------------------

def test_thirteen_steps_with_psz001_ack_suppresses_finding():
    """
    13-Step PLAN with PSZ001 in audit_acknowledgements -> finding suppressed (None returned).
    """
    plan_text = _make_plan_text(num_steps=13)
    result = check_plan_sizing(plan_text, ack_codes=['PSZ001'])

    assert result is None, (
        f'Expected no finding when PSZ001 is in audit_acknowledgements, got: {result}'
    )


# ---------------------------------------------------------------------------
# Additional: ceiling boundary (exactly 12 Steps -> no finding)
# ---------------------------------------------------------------------------

def test_twelve_steps_at_ceiling_no_finding():
    """
    PLAN with exactly 12 Steps (the ceiling) -> no finding (ceiling is non-inclusive).
    """
    plan_text = _make_plan_text(num_steps=12)
    result = check_plan_sizing(plan_text, ack_codes=[])
    assert result is None, (
        f'Expected no PSZ001 for exactly-at-ceiling (12 Steps), got: {result}'
    )


# ---------------------------------------------------------------------------
# Additional: D4 algorithm accuracy - sub-items not counted
# ---------------------------------------------------------------------------

def test_d4_algorithm_excludes_sub_items():
    """
    D4 step-counting regex must not count sub-items (lines with leading
    whitespace or letter-prefixed items like 'a.').
    """
    plan_text = textwrap.dedent("""\
        ---
        schema_version: 2
        title: "Test PLAN"
        type: plan
        status: ready
        audit_acknowledgements: []
        ---

        ## Steps

        1. First step.
           a. Sub-item A.
           b. Sub-item B.
        2. Second step.
           - Sub-bullet.
        3. Third step.

        ## Verification

        - [ ] placeholder
              verify: true
        """)

    n = count_steps(plan_text)
    assert n == 3, (
        f'Expected 3 top-level Steps (sub-items excluded by D4 algorithm), got: {n}'
    )


# ---------------------------------------------------------------------------
# Additional: D4 algorithm accuracy - stops at next ## heading
# ---------------------------------------------------------------------------

def test_d4_algorithm_stops_at_next_heading():
    """
    D4 must not count numbered lines in sections after '## Steps'.
    """
    plan_text = textwrap.dedent("""\
        ---
        schema_version: 2
        title: "Test PLAN"
        type: plan
        status: ready
        audit_acknowledgements: []
        ---

        ## Steps

        1. First step.
        2. Second step.

        ## Verification

        1. This numbered line is in the Verification section, not Steps.
        2. Should not be counted as a Step.
        """)

    n = count_steps(plan_text)
    assert n == 2, (
        f'Expected 2 top-level Steps (D4 stops at next ## heading), got: {n}'
    )


# ---------------------------------------------------------------------------
# PSZ002 - the counter must not report silence as compliance
# ---------------------------------------------------------------------------

def test_heading_style_steps_are_not_a_silent_pass():
    """
    Steps written as '### Step N' headings match no line of the D4 algorithm, so
    count_steps returns 0. Before PSZ002 that sailed through as a small PLAN.
    """
    plan = textwrap.dedent('''\
        # PLAN

        ## Steps

        ### Step 1
        Read the file.

        ### Step 2
        Write the file.

        ## Verification
        - [ ] done
        ''')
    assert count_steps(plan) == 0
    finding = check_plan_sizing(plan, [])
    assert finding is not None
    assert finding['code'] == 'PSZ002'
    assert 'could not run' in finding['message']


def test_missing_steps_heading_is_not_a_silent_pass():
    plan = '# PLAN\n\n## Verification\n- [ ] done\n'
    assert count_steps(plan) == 0
    finding = check_plan_sizing(plan, [])
    assert finding is not None
    assert finding['code'] == 'PSZ002'
    assert "no '## Steps' heading" in finding['message']


def test_empty_steps_section_does_not_fire_psz002():
    """
    An empty Steps section is a different defect and is caught elsewhere. PSZ002
    is specifically about a section that carries content the counter cannot read.
    """
    plan = '# PLAN\n\n## Steps\n\n## Verification\n- [ ] done\n'
    assert check_plan_sizing(plan, []) is None


def test_template_placeholder_only_does_not_fire_psz002():
    """The unfilled plan-template's bracketed guidance must not be read as content."""
    plan = textwrap.dedent('''\
        # PLAN

        ## Steps
        [Numbered steps to execute via the `execute-plan` skill.]

        ## Verification
        - [ ] done
        ''')
    assert check_plan_sizing(plan, []) is None


def test_psz002_is_acknowledgeable():
    plan = '# PLAN\n\n## Steps\n\n### Step 1\nDo a thing.\n\n## Verification\n- [ ] done\n'
    assert check_plan_sizing(plan, ['PSZ002']) is None


def test_canonical_steps_still_counted_and_psz002_silent():
    """A well-formed small PLAN must produce neither finding."""
    plan = _make_plan_text(3)
    assert count_steps(plan) == 3
    assert check_plan_sizing(plan, []) is None
