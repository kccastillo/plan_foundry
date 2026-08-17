"""
test_claim_carry_gate_wiring.py - structural guard for the Carried-claims
gate added by PLAN-AL1 (closing FOUNDRYREQ-horse-chestnut-brickhouse-
20260805-1701).

This is a WIRING test, not a behavioural one - modelled directly on the
existing test_readiness_gate_wiring.py in this same directory: it asserts
the gate's load-bearing artefacts exist and are cross-referenced, so a
future edit that silently deletes the mandatory section, drops workflow
Step 2.6, or removes the reference file is caught in CI. Behavioural
coverage of the underlying logic lives in test_claim_carry.py and
test_resume_preflight_claim_axis.py under .claude/skills/_shared/lib/.

Run: python .claude/skills/handoff-next-session/lib/test_claim_carry_gate_wiring.py
     (also runnable under pytest)
"""

from __future__ import annotations

import pathlib
import sys


def _repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".claude" / "skills").is_dir():
            return candidate
    return here.parents[4]


_ROOT = _repo_root()
_SKILL = _ROOT / ".claude" / "skills" / "handoff-next-session"


def _read(rel_from_skill: str) -> str:
    return (_SKILL / rel_from_skill).read_text(encoding="utf-8")


def test_template_has_mandatory_nondeletable_claims_baseline_section():
    """The template carries the Carried-claims baseline heading AND a
    mandatory/never-deleted marker, plus the empty-state literal."""
    tpl = _read("templates/handoff-template.md")
    assert "## Carried-claims baseline" in tpl, (
        "handoff template lost the '## Carried-claims baseline' heading"
    )
    lower = tpl.lower()
    assert "mandatory" in lower and ("never delete" in lower or "never deleted" in lower), (
        "Carried-claims baseline section must be marked mandatory / never-deleted"
    )
    assert "CLAIM-<kebab-nickname>" in tpl or "CLAIM-<id>" in tpl, (
        "template must document the CLAIM-<id> grammar somewhere (Constraints & do-nots guidance)"
    )


def test_workflow_has_step_2_6_and_reports_it():
    """The write-handoff workflow computes the claim gate (Step 2.6) and reports step_2_6."""
    wf = _read("workflows/write-handoff.md")
    assert "Step 2.6" in wf, "write-handoff workflow lost Step 2.6 (Carried-claims gate)"
    assert "step_2_6" in wf, "workflow reporting must include the step_2_6 key"


def test_reference_file_defines_grammar_drop_guard_and_threshold():
    """references/claim-carry-gate.md exists and names the grammar, drop guard, and threshold."""
    ref = _read("references/claim-carry-gate.md")
    lower = ref.lower()
    assert "claim-" in lower or "claim_" in lower or "claim-<id>" in lower or "claim-<kebab-nickname>" in lower, (
        "missing CLAIM-<id> grammar"
    )
    assert "drop" in lower, "missing the drop-guard description"
    assert "carried_count" in ref and "3" in ref, (
        "missing the escalation threshold description"
    )
    assert "freeform" in lower and "checkable" in lower, (
        "missing the checkable-vs-freeform split"
    )


def test_skill_registers_gate_as_principle():
    """SKILL.md names the Carried-claims baseline and references claim-carry-gate.md."""
    skill = _read("SKILL.md")
    assert "Carried-claims baseline" in skill, (
        "SKILL.md must name the Carried-claims baseline alongside Plan-state baseline"
    )
    assert "claim-carry-gate.md" in skill, (
        "SKILL.md must reference references/claim-carry-gate.md"
    )


_TESTS = [
    test_template_has_mandatory_nondeletable_claims_baseline_section,
    test_workflow_has_step_2_6_and_reports_it,
    test_reference_file_defines_grammar_drop_guard_and_threshold,
    test_skill_registers_gate_as_principle,
]


if __name__ == "__main__":
    failures = 0
    for t in _TESTS:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failures += 1
    sys.exit(0 if failures == 0 else 1)
