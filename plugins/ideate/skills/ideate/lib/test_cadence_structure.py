"""
test_cadence_structure.py — Structural tests for PLAN-AA9 cadence enhancements.

Verifies that the ideate cadence workflow files contain the required F1/F2/F7/F8
mechanism documentation. These are structural-grep tests — they assert the live
workflow file contains required section markers and column specifications.

A future change that removes any of these mechanisms would fail these assertions.

Origin: PLAN-AA9 Step 8, 2026-05-17.
Run with: python -m pytest plugins/ideate/skills/ideate/lib/test_cadence_structure.py
"""

from __future__ import annotations

import pathlib
import re


def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        if (parent / "plugins").is_dir() and (parent / "Workbench").is_dir():
            return parent
    raise RuntimeError("could not find repo root")


REPO_ROOT = _find_repo_root()

CADENCE_PHASES = (
    REPO_ROOT / "plugins" / "ideate" / "skills" / "ideate" / "workflows" / "cadence-phases.md"
)
IDEATE_SKILL = (
    REPO_ROOT / "plugins" / "ideate" / "skills" / "ideate" / "SKILL.md"
)
RESEARCH_TEMPLATE = (
    REPO_ROOT / "plugins" / "plan-foundry-core" / "skills" / "_shared" / "research-prompt-template.md"
)


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Test 1 — F2 expand-explode section in cadence-phases.md
# ---------------------------------------------------------------------------

def test_cadence_phases_has_f2_expand_explode():
    """cadence-phases.md Phase 2 must document the F2 expand-explode sub-step."""
    text = _read(CADENCE_PHASES)
    # Accept: "expand-explode", "expand/explode", "Expand-Explode", or literal "F2"
    has_f2 = bool(
        re.search(r"expand.explode", text, re.IGNORECASE)
        or "F2" in text
    )
    assert has_f2, (
        "cadence-phases.md is missing F2 expand-explode documentation. "
        "Expected 'expand-explode' (or variant) or literal 'F2' in the file."
    )


# ---------------------------------------------------------------------------
# Test 2 — F1 research-anchor section with ≥2-floor trigger
# ---------------------------------------------------------------------------

def test_cadence_phases_has_f1_research_anchor_with_floor():
    """cadence-phases.md must document F1 research-anchor including the ≥2 floor trigger."""
    text = _read(CADENCE_PHASES)
    has_anchor = bool(
        re.search(r"research.anchor", text, re.IGNORECASE)
        or "F1" in text
    )
    assert has_anchor, (
        "cadence-phases.md is missing F1 research-anchor documentation. "
        "Expected 'research-anchor' (or variant) or literal 'F1' in the file."
    )
    # The ≥2 Real-judgement-call floor trigger must be documented
    has_floor = bool(
        re.search(r"[≥>=][ ]?2", text)
        or "2 or more" in text.lower()
        or "two or more" in text.lower()
        or "auto-dispatch threshold" in text.lower()
    )
    assert has_floor, (
        "cadence-phases.md is missing the ≥2 Real-judgement-call floor trigger for research dispatch. "
        "Expected '≥2', '2 or more', 'two or more', or 'auto-dispatch threshold' in the file."
    )


# ---------------------------------------------------------------------------
# Test 3 — F7 triage (decision-tier) column documented
# ---------------------------------------------------------------------------

def test_cadence_phases_has_f7_triage_column():
    """cadence-phases.md must document the F7 decision-tier triage column in Survey/Critique/Reconcile."""
    text = _read(CADENCE_PHASES)
    has_triage = bool(
        re.search(r"decision.tier", text, re.IGNORECASE)
        or re.search(r"triage.column", text, re.IGNORECASE)
    )
    assert has_triage, (
        "cadence-phases.md is missing F7 triage column documentation. "
        "Expected 'decision-tier' or 'triage column' (or variant) in the file."
    )
    # Verify the column appears in at least Phase 2 (Survey), Phase 5 (Self-Critique),
    # and Phase 7 (Cross-Spec-Reconcile) — check that all three phase sections reference it
    # by looking for "decision-tier" appearing at least 3 times
    occurrences = len(re.findall(r"decision.tier", text, re.IGNORECASE))
    assert occurrences >= 3, (
        f"cadence-phases.md has 'decision-tier' only {occurrences} time(s); "
        "expected at least 3 (Survey + Self-Critique + Cross-Spec-Reconcile)."
    )


# ---------------------------------------------------------------------------
# Test 4 — F8 inverted-pyramid format documented
# ---------------------------------------------------------------------------

def test_cadence_phases_has_f8_inverted_pyramid():
    """cadence-phases.md must document F8 inverted-pyramid output format."""
    text = _read(CADENCE_PHASES)
    has_pyramid = bool(
        re.search(r"inverted.pyramid", text, re.IGNORECASE)
        or re.search(r"headline.summary", text, re.IGNORECASE)
        or re.search(r"tradeoff.table", text, re.IGNORECASE)
    )
    assert has_pyramid, (
        "cadence-phases.md is missing F8 inverted-pyramid format documentation. "
        "Expected 'inverted-pyramid', 'headline summary', or 'tradeoff table' (or variant) in the file."
    )


# ---------------------------------------------------------------------------
# Test 5 — research-prompt-template has all four sub-questions
# ---------------------------------------------------------------------------

def test_research_prompt_template_has_all_four_sub_questions():
    """research-prompt-template.md must contain all four required sub-questions."""
    text = _read(RESEARCH_TEMPLATE)
    required_markers = [
        "Public API Surface",
        "Prior-Art Citations",
        "Lean-Reversibility",
        "Verdict Line",
    ]
    missing = [m for m in required_markers if m not in text]
    assert not missing, (
        "research-prompt-template.md is missing the following sub-question markers: "
        + ", ".join(missing)
    )


# ---------------------------------------------------------------------------
# Test 6 — Phase 5 Self-Critique has F7/F8 requirements
# ---------------------------------------------------------------------------

def test_phase_5_self_critique_has_f7_f8():
    """cadence-phases.md Phase 5 (Self-Critique) must document F7 triage column + F8 inverted-pyramid."""
    text = _read(CADENCE_PHASES)

    # Locate Phase 5 section
    phase5_match = re.search(r"## Phase 5 —", text)
    assert phase5_match, "Phase 5 section not found in cadence-phases.md"

    # Find next Phase boundary (## Phase 6 —)
    phase6_match = re.search(r"## Phase 6 —", text)
    assert phase6_match, "Phase 6 section not found in cadence-phases.md (needed to bound Phase 5)"

    phase5_text = text[phase5_match.start():phase6_match.start()]

    # F7: decision-tier column required in Phase 5
    has_triage = bool(re.search(r"decision.tier", phase5_text, re.IGNORECASE))
    assert has_triage, (
        "Phase 5 (Self-Critique) in cadence-phases.md is missing the F7 decision-tier triage column. "
        "Expected 'decision-tier' (or variant) in the Phase 5 section."
    )

    # F8: inverted-pyramid or headline-summary required in Phase 5
    has_pyramid = bool(
        re.search(r"inverted.pyramid", phase5_text, re.IGNORECASE)
        or re.search(r"headline.summary", phase5_text, re.IGNORECASE)
        or re.search(r"tradeoff.table", phase5_text, re.IGNORECASE)
        or "F8" in phase5_text
    )
    assert has_pyramid, (
        "Phase 5 (Self-Critique) in cadence-phases.md is missing F8 inverted-pyramid format. "
        "Expected 'inverted-pyramid', 'headline summary', 'tradeoff table', or 'F8' in the Phase 5 section."
    )


# ---------------------------------------------------------------------------
# Test 7 — Phase 7 Cross-Spec-Reconcile has F7/F8 requirements
# ---------------------------------------------------------------------------

def test_phase_7_cross_spec_reconcile_has_f7_f8():
    """cadence-phases.md Phase 7 (Cross-Spec-Reconcile) must document F7 triage column + F8 inverted-pyramid."""
    text = _read(CADENCE_PHASES)

    # Locate Phase 7 section
    phase7_match = re.search(r"## Phase 7 —", text)
    assert phase7_match, "Phase 7 section not found in cadence-phases.md"

    # Find next Phase boundary (## Phase 8 —)
    phase8_match = re.search(r"## Phase 8 —", text)
    assert phase8_match, "Phase 8 section not found in cadence-phases.md (needed to bound Phase 7)"

    phase7_text = text[phase7_match.start():phase8_match.start()]

    # F7: decision-tier column required in Phase 7
    has_triage = bool(re.search(r"decision.tier", phase7_text, re.IGNORECASE))
    assert has_triage, (
        "Phase 7 (Cross-Spec-Reconcile) in cadence-phases.md is missing the F7 decision-tier triage column. "
        "Expected 'decision-tier' (or variant) in the Phase 7 section."
    )

    # F8: inverted-pyramid or headline-summary required in Phase 7
    has_pyramid = bool(
        re.search(r"inverted.pyramid", phase7_text, re.IGNORECASE)
        or re.search(r"headline.summary", phase7_text, re.IGNORECASE)
        or re.search(r"tradeoff.table", phase7_text, re.IGNORECASE)
        or "F8" in phase7_text
    )
    assert has_pyramid, (
        "Phase 7 (Cross-Spec-Reconcile) in cadence-phases.md is missing F8 inverted-pyramid format. "
        "Expected 'inverted-pyramid', 'headline summary', 'tradeoff table', or 'F8' in the Phase 7 section."
    )
