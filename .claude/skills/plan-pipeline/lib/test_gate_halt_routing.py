"""
Wiring test for PLAN-AF9: gate-halt outcome_subtype routing contract.

Asserts that:
1. The routing table in phase-state-machine.md contains a row mapping
   `executing | success (subtype: gate-halt)` to `outcome-verifying` (NOT `drafted`).
2. The executor emission logic in execute-steps.md documents:
   (a) the trailing-[Human]-gate DEFER behaviour (executor does NOT exception-halt
       when only [Human] Steps remain), and
   (b) the three-part gate-halt emission condition (all non-[Human] Steps done +
       zero failed + >= 1 [Human] deferred) with its negative cases
       (mid-plan gate -> exception; failed machine Step -> partially-complete).

These are structural/contract tests - they parse markdown rather than running
the routing logic, so they fail the moment a future edit removes the fix.
"""

from __future__ import annotations

import pathlib


def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        if (parent / ".claude").is_dir() and (parent / "Workbench").is_dir():
            return parent
    raise RuntimeError("could not find repo root")


REPO_ROOT = _find_repo_root()
STATE_MACHINE = REPO_ROOT / ".claude/skills/plan-pipeline/references/phase-state-machine.md"
EXECUTE_STEPS = REPO_ROOT / ".claude/skills/execute-plan/workflows/execute-steps.md"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Routing-table contract tests (parse phase-state-machine.md)
# ---------------------------------------------------------------------------


def test_gate_halt_row_exists_in_routing_table():
    """A routing-table row for executing + gate-halt must exist."""
    text = _read(STATE_MACHINE)
    # The row must mention both "gate-halt" and be in the "executing" section
    assert "gate-halt" in text, (
        "phase-state-machine.md has no gate-halt mention - routing row missing"
    )
    # Find the routing table section and check it contains the gate-halt row
    assert "executing" in text and "gate-halt" in text, (
        "phase-state-machine.md routing table missing gate-halt row"
    )


def test_gate_halt_routes_to_outcome_verifying():
    """The gate-halt row must map executing -> outcome-verifying."""
    text = _read(STATE_MACHINE)
    # Find lines that mention both gate-halt and outcome-verifying together
    lines = text.splitlines()
    gate_halt_lines = [ln for ln in lines if "gate-halt" in ln and "executing" in ln]
    assert gate_halt_lines, (
        "No routing-table row found containing both 'executing' and 'gate-halt'"
    )
    # At least one such line must reference outcome-verifying
    routes_forward = any("outcome-verifying" in ln for ln in gate_halt_lines)
    assert routes_forward, (
        f"gate-halt row(s) do not route to outcome-verifying. Found rows: {gate_halt_lines}"
    )


def test_gate_halt_does_not_route_to_drafted():
    """A gate-halt must NOT revert to drafted - that is the bug this fix prevents."""
    text = _read(STATE_MACHINE)
    lines = text.splitlines()
    # Any line that mentions both gate-halt and drafted would be a regression
    gate_halt_drafted = [
        ln for ln in lines
        if "gate-halt" in ln and "drafted" in ln and "NOT" not in ln and "not" not in ln.lower()
    ]
    # The clarifying note says "does NOT revert to drafted" which is fine;
    # flag only lines that affirmatively route gate-halt -> drafted
    affirmative_revert = [
        ln for ln in gate_halt_drafted
        if "revert" in ln.lower() or "-> `drafted`" in ln or "-> drafted" in ln
    ]
    assert not affirmative_revert, (
        f"gate-halt appears to route to drafted - regression detected: {affirmative_revert}"
    )


def test_gate_halt_subtype_in_outcome_subtype_enum_state_machine():
    """phase-state-machine.md must list gate-halt in the outcome_subtype enum comment."""
    text = _read(STATE_MACHINE)
    # The YAML cheat-sheet line should include gate-halt
    assert "outcome_subtype" in text, "outcome_subtype field missing from phase-state-machine.md"
    lines = [ln for ln in text.splitlines() if "outcome_subtype" in ln]
    assert any("gate-halt" in ln for ln in lines), (
        "gate-halt not present in outcome_subtype enum comment in phase-state-machine.md. "
        f"Lines found: {lines}"
    )


# ---------------------------------------------------------------------------
# Executor emission-decision tests (parse execute-steps.md)
# ---------------------------------------------------------------------------


def test_gate_halt_subtype_in_outcome_subtype_enum_execute_steps():
    """execute-steps.md must list gate-halt in the outcome_subtype values."""
    text = _read(EXECUTE_STEPS)
    assert "gate-halt" in text, (
        "gate-halt not present in execute-steps.md - enum extension missing"
    )
    # The enum line itself should mention gate-halt alongside the other subtypes
    lines = [ln for ln in text.splitlines() if "outcome_subtype" in ln and "gate-halt" in ln]
    assert lines, (
        "No line in execute-steps.md contains both 'outcome_subtype' and 'gate-halt'"
    )


def test_execute_steps_documents_trailing_gate_defer_behaviour():
    """execute-steps.md must document that a trailing-[Human]-gate defers (not exception-halts)."""
    text = _read(EXECUTE_STEPS)
    text_lower = text.lower()
    # Must mention the trailing/defer concept
    has_trailing = "trailing gate" in text_lower or "trailing-gate" in text_lower
    has_defer = "defer" in text_lower
    assert has_trailing and has_defer, (
        "execute-steps.md is missing the trailing-[Human]-gate DEFER behaviour. "
        f"trailing={has_trailing}, defer={has_defer}"
    )


def test_execute_steps_documents_three_part_gate_halt_condition():
    """execute-steps.md must document the three-part gate-halt emission condition."""
    text = _read(EXECUTE_STEPS)
    text_lower = text.lower()
    # (a) all non-[Human] Steps done
    has_all_done = ("non-`[human]`" in text_lower or "non-[human]" in text_lower)
    # (b) zero failed
    has_zero_failed = "zero failed" in text_lower or "zero steps failed" in text_lower
    # (c) >=1 [Human] deferred
    has_deferred = "deferred" in text_lower and "gate-halt" in text_lower
    assert has_all_done, (
        "execute-steps.md missing gate-halt condition (a): every non-[Human] Step is done"
    )
    assert has_zero_failed, (
        "execute-steps.md missing gate-halt condition (b): zero Steps FAILED"
    )
    assert has_deferred, (
        "execute-steps.md missing gate-halt condition (c): >=1 [Human] Step deferred"
    )


def test_execute_steps_documents_negative_cases():
    """execute-steps.md must document the negative cases: mid-plan gate -> exception,
    failed machine Step -> partially-complete."""
    text = _read(EXECUTE_STEPS)
    text_lower = text.lower()
    # Negative case 1: mid-plan gate -> exception
    has_mid_plan_exception = (
        ("mid-plan" in text_lower or "mid-plan gate" in text_lower)
        and "exception" in text_lower
    )
    # Negative case 2: failed machine Step -> partially-complete
    has_failed_partial = (
        "partially-complete" in text_lower
        and ("failed" in text_lower or "machine step" in text_lower)
    )
    assert has_mid_plan_exception, (
        "execute-steps.md missing negative case: mid-plan [Human] gate -> outcome: exception"
    )
    assert has_failed_partial, (
        "execute-steps.md missing negative case: failed machine Step -> partially-complete"
    )


def test_execute_steps_documents_gate_halt_authoring_convention():
    """execute-steps.md must document the gate-halt authoring convention
    (pair [Human] Steps with verify: human)."""
    text = _read(EXECUTE_STEPS)
    assert "verify: human" in text, (
        "execute-steps.md missing gate-halt authoring convention (pair [Human] with verify: human)"
    )
    assert "gate-halt" in text, (
        "execute-steps.md missing gate-halt authoring convention mention"
    )
