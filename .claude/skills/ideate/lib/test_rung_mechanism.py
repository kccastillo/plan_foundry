"""
test_rung_mechanism.py - Structural tests for PLAN-AL0 rung-mechanism wiring.

Verifies that proportionality-gate.md's `## Mechanism per rung` section states
the concrete skill call each of the three rungs below `full arc` makes, and
that ideate/SKILL.md and ideate-arc.md cross-reference it. These are
structural-grep tests - they assert the live files contain required section
markers and phrasing, not that any runtime behaviour occurred.

A future edit that drops the mechanism section, reintroduces the hand-set
`target_phase: checked` defect, or drops the sibling status/linked_inputs/
doc-drift dispositions, would fail these assertions.

Origin: PLAN-AL0 Step 5, 2026-08-06.
Run with: python -m pytest .claude/skills/ideate/lib/test_rung_mechanism.py
"""

from __future__ import annotations

import pathlib
import re


def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        if (parent / ".claude" / "skills").is_dir():
            return parent
    raise RuntimeError("could not find repo root")


REPO_ROOT = _find_repo_root()

PROPORTIONALITY_GATE = (
    REPO_ROOT / ".claude" / "skills" / "_shared" / "proportionality-gate.md"
)
IDEATE_SKILL = REPO_ROOT / ".claude" / "skills" / "ideate" / "SKILL.md"
IDEATE_ARC = (
    REPO_ROOT / ".claude" / "skills" / "ideate" / "workflows" / "ideate-arc.md"
)


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _section(text: str, heading: str) -> str:
    """Return the body of a `## heading` section up to the next `## ` heading."""
    match = re.search(rf"^## {re.escape(heading)}\s*$", text, re.MULTILINE)
    assert match, f"heading '## {heading}' not found"
    rest = text[match.end():]
    next_heading = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def _bullet(section_text: str, rung_label: str) -> str:
    """Return the bullet body for a given rung within a Mechanism per rung section."""
    match = re.search(
        rf"\*\*`{re.escape(rung_label)}`.*?\*\*", section_text
    )
    assert match, f"rung bullet for '{rung_label}' not found"
    rest = section_text[match.end():]
    next_bullet = re.search(r"^- \*\*`", rest, re.MULTILINE)
    return rest[: next_bullet.start()] if next_bullet else rest


# ---------------------------------------------------------------------------
# Test 1 - Mechanism per rung heading exists
# ---------------------------------------------------------------------------

def test_proportionality_gate_has_mechanism_per_rung_heading():
    text = _read(PROPORTIONALITY_GATE)
    assert re.search(r"^## Mechanism per rung\s*$", text, re.MULTILINE), (
        "proportionality-gate.md is missing the '## Mechanism per rung' heading."
    )


# ---------------------------------------------------------------------------
# Test 2 - audit it bullet names target_phase: drafted
# ---------------------------------------------------------------------------

def test_audit_it_bullet_names_target_phase_drafted():
    text = _read(PROPORTIONALITY_GATE)
    section = _section(text, "Mechanism per rung")
    bullet = _bullet(section, "audit it")
    assert "target_phase: drafted" in bullet, (
        "the 'audit it' bullet must mention the literal 'target_phase: drafted'."
    )


# ---------------------------------------------------------------------------
# Test 3 - plan it bullet does not hand-set target_phase, and names status
# ---------------------------------------------------------------------------

def test_plan_it_bullet_does_not_hand_set_target_phase():
    text = _read(PROPORTIONALITY_GATE)
    section = _section(text, "Mechanism per rung")
    bullet = _bullet(section, "plan it")
    assert "target_phase:" not in bullet, (
        "the 'plan it' bullet must not contain the literal 'target_phase:' - "
        "hand-setting it (e.g. to 'checked') stamps an un-audited PLAN as audited."
    )
    assert re.search(r"unset", bullet, re.IGNORECASE), (
        "the 'plan it' bullet must state that pipeline_phase stays unset."
    )
    assert re.search(r"status", bullet, re.IGNORECASE), (
        "the 'plan it' bullet must name the status-flip disposition."
    )


# ---------------------------------------------------------------------------
# Test 4 - plan it bullet names linked_inputs and doc-drift dispositions
# ---------------------------------------------------------------------------

def test_plan_it_bullet_names_input_and_drift_dispositions():
    text = _read(PROPORTIONALITY_GATE)
    section = _section(text, "Mechanism per rung")
    bullet = _bullet(section, "plan it")
    assert re.search(r"linked_inputs", bullet, re.IGNORECASE), (
        "the 'plan it' bullet must name the linked_inputs disposition."
    )
    assert re.search(r"drift", bullet, re.IGNORECASE), (
        "the 'plan it' bullet must name the doc-drift-check disposition."
    )


# ---------------------------------------------------------------------------
# Test 5 - just do it bullet names the no-disk-record closure
# ---------------------------------------------------------------------------

def test_just_do_it_bullet_states_no_disk_record():
    text = _read(PROPORTIONALITY_GATE)
    section = _section(text, "Mechanism per rung")
    bullet = _bullet(section, "just do it")
    assert re.search(r"no disk record|no record", bullet, re.IGNORECASE), (
        "the 'just do it' bullet must state explicitly that no disk record "
        "is written for this rung."
    )


# ---------------------------------------------------------------------------
# Test 6 - ideate/SKILL.md and ideate-arc.md cross-reference the section
# ---------------------------------------------------------------------------

def test_ideate_skill_cross_references_mechanism_per_rung():
    text = _read(IDEATE_SKILL)
    assert "Mechanism per rung" in text, (
        "ideate/SKILL.md must cross-reference the 'Mechanism per rung' section."
    )


def test_ideate_arc_cross_references_mechanism_per_rung():
    text = _read(IDEATE_ARC)
    assert "Mechanism per rung" in text, (
        "ideate-arc.md must cross-reference the 'Mechanism per rung' section."
    )
