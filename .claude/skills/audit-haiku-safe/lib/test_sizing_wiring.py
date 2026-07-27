"""
test_sizing_wiring.py - structural guard for executor t-shirt sizing (shipped in PR #44).

WIRING test, not behavioural: asserts the sizing rubric and its tier-relative
auditing rule are present and cross-referenced across the three files that carry
them, so a future edit that drops the S/M/L/XL table, the "not-haiku-safe is a
sizing outcome not a blocker" rule, or the assigned_to<->size mapping is caught in
CI. Behavioural coverage (a non-haiku-safe PLAN actually being sized up rather
than blocked) lives in test-foundry/scenarios/llm/audit_sizing_non_haiku_safe.md.

Run: python .claude/skills/audit-haiku-safe/lib/test_sizing_wiring.py
"""

from __future__ import annotations

import pathlib
import sys


def _repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".claude").is_dir() and (candidate / "Workbench").is_dir():
            return candidate
    return here.parents[3]


_ROOT = _repo_root()


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_plan_safe_has_sizing_table_mapped_to_tiers():
    """_shared/plan-safe.md defines S/M/L/XL mapped one-to-one to the executor tiers."""
    text = _read(".claude/skills/_shared/plan-safe.md")
    lower = text.lower()
    assert "t-shirt sizing" in lower, "plan-safe.md lost the Executor t-shirt sizing section"
    # Each size present.
    for size in ("**S**", "**M**", "**L**", "**XL**"):
        assert size in text, f"sizing table missing size {size}"
    # Each execution tier present in the section.
    for tier in ("haiku", "sonnet", "opus"):
        assert tier in lower, f"sizing table missing tier {tier}"


def test_plan_safe_states_sizing_is_not_automatically_a_blocker():
    """The load-bearing rule: 'not haiku-safe' is a sizing outcome, not automatically a Blocker."""
    text = _read(".claude/skills/_shared/plan-safe.md").lower()
    assert "sizing outcome" in text, "plan-safe.md must frame not-haiku-safe as a sizing outcome"
    assert "not automatically a blocker" in text or "not a blocker" in text, (
        "plan-safe.md must state a non-haiku-safe step is not automatically a Blocker"
    )
    # The XL escape valve must route, not silently block.
    assert "never silently blocked" in text or "never silently stuck" in text, (
        "plan-safe.md must guarantee an unsizable job is routed, not silently blocked"
    )


def test_plan_safe_documents_sonnet_execution_floor():
    """Recalibration guard: plan-safe.md records the Sonnet execution floor (Haiku retired from execution)."""
    text = _read(".claude/skills/_shared/plan-safe.md").lower()
    assert "execution floor is sonnet" in text, "plan-safe.md must document the Sonnet execution floor"
    assert "retired" in text and "haiku" in text, (
        "plan-safe.md must state Haiku is retired as an execution tier"
    )


def test_audit_haiku_safe_does_tier_relative_auditing():
    """audit-haiku-safe SKILL.md audits against the assigned tier and can size up."""
    text = _read(".claude/skills/audit-haiku-safe/SKILL.md").lower()
    assert "tier-relative" in text, "audit-haiku-safe must document tier-relative auditing"
    assert "assigned tier" in text, "audit-haiku-safe must audit against the assigned tier's bar"
    assert "size up" in text or "re-size" in text, (
        "audit-haiku-safe must offer size-up as a remedy, not only blocking"
    )


def test_assigned_to_reference_carries_tier_to_size_mapping():
    """assigned_to-field.md names the haiku/sonnet/opus tiers and the size mapping."""
    text = _read(".claude/skills/write-plan/references/assigned_to-field.md")
    lower = text.lower()
    for tier in ("haiku", "sonnet", "opus"):
        assert tier in lower, f"assigned_to-field.md missing tier {tier}"
    assert "size" in lower and ("s / m / l" in lower or "s/m/l" in lower or "**s**" in lower or "size **" in lower), (
        "assigned_to-field.md must map tiers to t-shirt sizes"
    )


_TESTS = [
    test_plan_safe_has_sizing_table_mapped_to_tiers,
    test_plan_safe_states_sizing_is_not_automatically_a_blocker,
    test_plan_safe_documents_sonnet_execution_floor,
    test_audit_haiku_safe_does_tier_relative_auditing,
    test_assigned_to_reference_carries_tier_to_size_mapping,
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
