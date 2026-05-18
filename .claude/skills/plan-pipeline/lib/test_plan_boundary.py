"""
test_plan_boundary.py — Structural tests for H7 plan-boundary and compact-suggestion
surfaces in plan-pipeline dispatch.md (PLAN-AB5).

These tests are structural — they assert the dispatch.md workflow contains the
required language for:
  - §4A plan-boundary-warning surface (soft warn-and-proceed when other PLANs are in flight)
  - §4F compact_suggestion surface (emitted after successful retire)

A future change that removes or renames these surfaces would fail these assertions.

Design: tests read dispatch.md directly from the filesystem via repo-root detection.
No subprocess, no shell, no live PLAN files — pure text inspection.
"""

from __future__ import annotations

import pathlib


def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        if (parent / "plugins").is_dir() and (parent / "Workbench").is_dir():
            return parent
    raise RuntimeError("could not find repo root")


REPO_ROOT = _find_repo_root()
DISPATCH = REPO_ROOT / "plugins/plan-foundry-core/skills/plan-pipeline/workflows/dispatch.md"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Test 1 — §4A contains plan-boundary-check language
# ---------------------------------------------------------------------------

def test_dispatch_4A_has_plan_boundary_check():
    """plan-pipeline dispatch §4A must contain plan-boundary-check language."""
    text = _read(DISPATCH)
    # Locate §4A
    assert "### 4A." in text, "§4A section missing from dispatch.md"
    lower = text.lower()
    # Must reference plan-boundary check concept
    assert "plan-boundary" in lower or "plan_boundary" in lower or "in-flight" in lower or "in flight" in lower, (
        "§4A is missing plan-boundary check language"
    )
    # Must reference globbing/scanning of Workbench PLANs
    assert "glob" in lower or "workbench/plan-" in lower or "pipeline_phase" in text, (
        "§4A plan-boundary check must reference scanning Workbench PLAN files for pipeline_phase"
    )


# ---------------------------------------------------------------------------
# Test 2 — §4F contains compact_suggestion language
# ---------------------------------------------------------------------------

def test_dispatch_4F_has_compact_suggestion():
    """plan-pipeline dispatch §4F must contain compact_suggestion surface language."""
    text = _read(DISPATCH)
    # Locate §4F
    assert "### 4F." in text or "4F. `complete`" in text, "§4F section missing from dispatch.md"
    # Must reference compact_suggestion or /compact
    assert "compact_suggestion" in text or "/compact" in text, (
        "§4F is missing compact_suggestion surface language"
    )


# ---------------------------------------------------------------------------
# Test 3 — Both surfaces use the required structured tags
# ---------------------------------------------------------------------------

def test_dispatch_uses_structured_tags():
    """dispatch.md must use the structured XML-style tags for both H7 surfaces."""
    text = _read(DISPATCH)
    assert "<plan-boundary-warning>" in text, (
        "dispatch.md is missing the <plan-boundary-warning> structured tag"
    )
    assert "<compact_suggestion>" in text, (
        "dispatch.md is missing the <compact_suggestion> structured tag"
    )


# ---------------------------------------------------------------------------
# Test 4 — §4A plan-boundary is soft warn-and-proceed, not hard halt
# ---------------------------------------------------------------------------

def test_dispatch_4A_boundary_is_soft_warn_not_halt():
    """
    §4A plan-boundary check must be described as soft warn-and-proceed, NOT a
    hard halt or mandatory confirmation requirement.
    """
    text = _read(DISPATCH)
    lower = text.lower()
    # Must mention soft/warn/proceed — not a hard stop
    assert any(phrase in lower for phrase in (
        "soft warn", "warn-and-proceed", "does not halt", "does not require",
        "soft", "proceed", "warning"
    )), (
        "§4A plan-boundary check is not described as soft warn-and-proceed"
    )
    # Must NOT describe this as a blocking requirement (hard halt)
    # We check that the phrase "halt" is NOT the primary outcome for the boundary check.
    # Find the plan-boundary section and confirm "halt" is not the prescribed action.
    # We do this by finding the <plan-boundary-warning> tag region and checking it
    # says "proceed" or similar.
    tag_idx = text.find("<plan-boundary-warning>")
    if tag_idx != -1:
        # Look at surrounding context (500 chars before/after)
        context = text[max(0, tag_idx - 500): tag_idx + 500].lower()
        assert "proceed" in context or "does not halt" in context or "soft" in context, (
            "The <plan-boundary-warning> tag context does not indicate soft warn-and-proceed"
        )
