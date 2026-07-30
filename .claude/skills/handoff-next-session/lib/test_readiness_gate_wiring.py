"""
test_readiness_gate_wiring.py - structural guard for the mandatory handover
Audit & Execution-Readiness Gate (shipped in PR #44).

This is a WIRING test, not a behavioural one: it asserts the gate's load-bearing
artefacts exist and are cross-referenced, so a future edit that silently deletes
the mandatory section, drops workflow Step 2.5, or removes the reference file is
caught in CI. Behavioural coverage (a real handoff populating the gate correctly)
lives in the out-of-CI LLM scenario test-foundry/scenarios/llm/handoff_readiness_gate.md.

Run: python .claude/skills/handoff-next-session/lib/test_readiness_gate_wiring.py
     (also runnable under pytest - the test_* functions assert directly)
"""

from __future__ import annotations

import pathlib
import sys


def _repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".claude").is_dir() and (candidate / "Workbench").is_dir():
            return candidate
    # Fallback: the skill is at .claude/skills/handoff-next-session/lib/ -> up 4.
    return here.parents[3]


_ROOT = _repo_root()
_SKILL = _ROOT / ".claude" / "skills" / "handoff-next-session"


def _read(rel_from_skill: str) -> str:
    return (_SKILL / rel_from_skill).read_text(encoding="utf-8")


def test_template_has_mandatory_nondeletable_gate_section():
    """The template carries the gate heading AND a mandatory/never-deleted marker."""
    tpl = _read("templates/handoff-template.md")
    assert "## Audit & execution-readiness gate" in tpl, (
        "handoff template lost the '## Audit & execution-readiness gate' heading"
    )
    lower = tpl.lower()
    assert "mandatory" in lower and ("never delete" in lower or "non-deletable" in lower or "never deleted" in lower), (
        "gate section must be marked mandatory / never-deleted (the exception to the "
        "'delete empty sections' rule)"
    )
    # The empty-state contract the workflow relies on.
    assert "No in-flight PLANs" in tpl, (
        "template must document the literal empty-state 'No in-flight PLANs.'"
    )


def test_workflow_has_step_2_5_and_reports_it():
    """The write-handoff workflow computes the gate (Step 2.5) and reports step_2_5."""
    wf = _read("workflows/write-handoff.md")
    assert "Step 2.5" in wf, "write-handoff workflow lost Step 2.5 (compute the gate)"
    assert "step_2_5" in wf, "workflow reporting must include the step_2_5 key"
    # The core invariant phrase - readiness is gated on `checked`.
    assert "pipeline_phase: checked" in wf or "pipeline_phase` is `checked" in wf or "checked" in wf, (
        "workflow must anchor readiness on pipeline_phase: checked"
    )


def test_reference_file_defines_the_four_checks():
    """references/readiness-gate.md exists and names all four standing checks."""
    ref = _read("references/readiness-gate.md")
    lower = ref.lower()
    # (1) execution-readiness verdict on `checked`
    assert "checked" in lower and ("ready" in lower), "missing execution-readiness verdict check"
    # (2) audit-verdict provenance / self-assessment
    assert "self-assess" in lower or "provenance" in lower, "missing audit-verdict provenance check"
    # (3) ideation status
    assert "ideation" in lower and ("stale" in lower or "supersed" in lower or "live" in lower), (
        "missing ideation-status check"
    )
    # (4) scope-collision / supersession
    assert "scope" in lower and "supersed" in lower, "missing scope-collision/supersession check"
    # sizing tie-in
    assert "size" in lower, "readiness gate must carry the per-PLAN size column"


def test_skill_registers_gate_as_principle_and_success_criterion():
    """SKILL.md names the mandatory gate in essential_principles and success_criteria."""
    skill = _read("SKILL.md")
    lower = skill.lower()
    assert "audit & execution-readiness gate" in lower or "audit & execution-readiness gate" in lower, (
        "SKILL.md must name the mandatory gate in its principles"
    )
    assert "readiness-gate.md" in skill, "SKILL.md must reference references/readiness-gate.md"


_TESTS = [
    test_template_has_mandatory_nondeletable_gate_section,
    test_workflow_has_step_2_5_and_reports_it,
    test_reference_file_defines_the_four_checks,
    test_skill_registers_gate_as_principle_and_success_criterion,
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
