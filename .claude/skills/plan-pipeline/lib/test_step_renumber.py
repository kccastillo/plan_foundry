"""
test_step_renumber.py - Tests for step_renumber.py (PLAN-AJ1).

Run: python -m pytest .claude/skills/plan-pipeline/lib/test_step_renumber.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from step_renumber import (
    RefusedRenumber,
    extract_steps_block,
    may_renumber,
    renumber_report,
    renumber_steps,
)


def _make_block(ordinals: list[int]) -> str:
    body = "\n".join(f"{n}. do thing {i}" for i, n in enumerate(ordinals))
    return f"## Steps\n\n{body}\n\n## Verification\n"


def test_clean_sequence_unchanged() -> None:
    text = _make_block([1, 2, 3])
    new_text, remap = renumber_steps(text)
    assert new_text == text
    assert remap == []


def test_insertion_at_position_five_in_twelve_step_block() -> None:
    # 12 steps, with a duplicate inserted after step 5: 1..5, 5, 6..12 (13 lines).
    ordinals = [1, 2, 3, 4, 5, 5, 6, 7, 8, 9, 10, 11, 12]
    text = _make_block(ordinals)
    new_text, remap = renumber_steps(text)
    assert new_text != text
    assert len(remap) == 8
    assert {"old": 5, "new": 6} in remap


def test_indented_continuation_lines_unchanged() -> None:
    text = (
        "## Steps\n\n"
        "1. First step.\n"
        "   Continuation line for step 1.\n"
        "2. Second step.\n"
        "   Another continuation line.\n"
        "3. Third step.\n"
        "\n## Verification\n"
    )
    new_text, remap = renumber_steps(text)
    assert "   Continuation line for step 1." in new_text
    assert "   Another continuation line." in new_text
    assert remap == []


def test_prose_outside_steps_block_untouched() -> None:
    text = (
        "## Context\n\n"
        "See item 1. something for background.\n\n"
        "## Steps\n\n"
        "1. do thing\n"
        "2. do other thing\n\n"
        "## Verification\n"
    )
    new_text, remap = renumber_steps(text)
    assert "1. something" in new_text
    assert remap == []


def test_steps_block_runs_to_end_of_text() -> None:
    text = "## Steps\n\n1. a\n2. b\n3. c\n"
    block, start, end = extract_steps_block(text)
    assert end == len(text)
    assert "3. c" in block


def test_no_steps_heading_raises() -> None:
    text = "## Objective\n\nNo steps section here.\n"
    with pytest.raises(ValueError):
        renumber_steps(text)


def test_restarting_run_refused() -> None:
    ordinals = [1, 2, 3, 1, 2]
    text = _make_block(ordinals)
    with pytest.raises(RefusedRenumber):
        renumber_steps(text)


def test_insertion_signature_renumbers_not_refuses() -> None:
    ordinals = [1, 2, 3, 4, 5, 5, 6, 7]
    text = _make_block(ordinals)
    new_text, remap = renumber_steps(text)
    assert new_text != text
    assert remap != []


def test_renumber_report_empty() -> None:
    assert renumber_report([]) == "no ordinal changes"


def test_renumber_report_nonempty() -> None:
    report = renumber_report([{"old": 5, "new": 6}, {"old": 6, "new": 7}])
    assert report == "Step 5 -> Step 6\nStep 6 -> Step 7"


# ---------------------------------------------------------------------------
# may_renumber over the five ordinal sequences from D6's corpus paragraph
# (given literally in the PLAN so this test does not have to go to disk).
# ---------------------------------------------------------------------------

def test_may_renumber_ai8_renumbered() -> None:
    assert may_renumber([7, 8, 9, 10]) is True


def test_may_renumber_aa8_renumbered() -> None:
    assert may_renumber([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16]) is True


def test_may_renumber_ab8_renumbered() -> None:
    assert may_renumber([7]) is True


def test_may_renumber_005_refused() -> None:
    assert may_renumber([1, 2, 3, 4, 5, 1, 2, 3, 4, 1, 2, 3, 1, 2, 3]) is False


def test_may_renumber_af1_refused() -> None:
    assert (
        may_renumber([1, 2, 3, 4, 5, 1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6, 7]) is False
    )
