"""
test_orchestrator_verify_tier.py
Wiring tests for the verify: orchestrator tier (PLAN-AG0).

Asserts:
  (a) A verify: orchestrator item, when processed, produces a durable record in
      orchestrator_attestations with all four required fields
      (item, verdict, evidence, verifier).
  (b) A verify: orchestrator item NEVER appears in human_pending - confirmed via
      classify_verification_items routing: orchestrator_items bucket, not human_items.
  (c) render_outcome_surface, given a human_items entry carrying the optional
      evidence/before/after fields (the Step-5 extended-dict contract), includes
      that evidence inline in the rendered output (present-with-content rule).

Test conventions (H4 checklist):
  - All tests are synchronous (def test_..., no async def, no pytest-asyncio).
  - Fixtures are inline (no file reads; no live-repo dependencies).
  - tmp_path only where a real file on disk is genuinely required (none here).
  - Imports are direct from the sibling module (render_prompts).
  - Platform: POSIX CI baseline (Ubuntu + Python 3.11); portable assertions only.
"""

from __future__ import annotations

import sys
import os

# Allow import from the same lib/ directory when run via pytest from any cwd.
sys.path.insert(0, os.path.dirname(__file__))

from render_prompts import (
    build_orchestrator_attestation,
    classify_verification_items,
    render_outcome_surface,
)


# ---------------------------------------------------------------------------
# (a) build_orchestrator_attestation - four required fields present
# ---------------------------------------------------------------------------

def test_attestation_record_has_all_four_fields():
    """An orchestrator attestation record MUST carry item, verdict, evidence, verifier."""
    record = build_orchestrator_attestation(
        item="Index is up to date (generate_index.py --check exits 0)",
        verdict="pass",
        evidence="$ python generate_index.py --check\nexit code: 0",
        verifier="plan-pipeline-orchestrator",
    )
    assert "item" in record, "attestation record must have 'item' field"
    assert "verdict" in record, "attestation record must have 'verdict' field"
    assert "evidence" in record, "attestation record must have 'evidence' field"
    assert "verifier" in record, "attestation record must have 'verifier' field"


def test_attestation_record_values_are_preserved():
    """Values supplied to build_orchestrator_attestation must be preserved verbatim."""
    record = build_orchestrator_attestation(
        item="All acceptance tests pass",
        verdict="fail",
        evidence="pytest exited with code 1; 2 failures",
        verifier="dispatch-orchestrator",
    )
    assert record["item"] == "All acceptance tests pass"
    assert record["verdict"] == "fail"
    assert record["evidence"] == "pytest exited with code 1; 2 failures"
    assert record["verifier"] == "dispatch-orchestrator"


def test_attestation_verdict_pass():
    """A passing orchestrator check produces verdict='pass'."""
    record = build_orchestrator_attestation(
        item="File exists",
        verdict="pass",
        evidence="os.path.exists returned True",
        verifier="plan-pipeline-orchestrator",
    )
    assert record["verdict"] == "pass"


def test_attestation_verdict_fail():
    """A failing orchestrator check produces verdict='fail'."""
    record = build_orchestrator_attestation(
        item="File exists",
        verdict="fail",
        evidence="os.path.exists returned False",
        verifier="plan-pipeline-orchestrator",
    )
    assert record["verdict"] == "fail"


def test_attestation_verifier_is_never_executor():
    """The verifier field must not identify the plan-executor (invariant check)."""
    record = build_orchestrator_attestation(
        item="INDEX freshness",
        verdict="pass",
        evidence="checked",
        verifier="plan-pipeline-orchestrator",
    )
    # The executor-never-self-certifies invariant: verifier must not be the executor.
    assert record["verifier"] != "plan-executor", (
        "verifier must not be plan-executor - executor-never-self-certifies invariant violated"
    )


# ---------------------------------------------------------------------------
# (b) classify_verification_items - verify: orchestrator NEVER in human_pending
# ---------------------------------------------------------------------------

def test_orchestrator_item_goes_to_orchestrator_bucket():
    """A verify: orchestrator item must land in orchestrator_items, not human_items."""
    items = [
        {"annotation": "verify: orchestrator", "prose": "INDEX is up to date"},
    ]
    result = classify_verification_items(items)
    assert len(result["orchestrator_items"]) == 1
    assert result["orchestrator_items"][0]["prose"] == "INDEX is up to date"
    assert len(result["human_items"]) == 0, (
        "verify: orchestrator item must NEVER appear in human_items (human_pending) bucket"
    )
    assert len(result["shell_items"]) == 0


def test_verify_human_goes_to_human_bucket():
    """A verify: human item must land in human_items, not orchestrator_items."""
    items = [
        {"annotation": "verify: human", "prose": "Tier boundary is correct"},
    ]
    result = classify_verification_items(items)
    assert len(result["human_items"]) == 1
    assert len(result["orchestrator_items"]) == 0
    assert len(result["shell_items"]) == 0


def test_shell_verify_goes_to_shell_bucket():
    """A verify: shell item must land in shell_items."""
    items = [
        {"annotation": "verify:", "prose": "python -c \"import sys; sys.exit(0)\""},
    ]
    result = classify_verification_items(items)
    assert len(result["shell_items"]) == 1
    assert len(result["orchestrator_items"]) == 0
    assert len(result["human_items"]) == 0


def test_acceptance_item_goes_to_shell_bucket():
    """An acceptance: item must land in shell_items (run via Bash)."""
    items = [
        {"annotation": "acceptance:", "prose": "python -m pytest lib/ -q"},
    ]
    result = classify_verification_items(items)
    assert len(result["shell_items"]) == 1
    assert len(result["orchestrator_items"]) == 0
    assert len(result["human_items"]) == 0


def test_mixed_items_routed_correctly():
    """All four annotation types are routed to the correct buckets independently."""
    items = [
        {"annotation": "verify:", "prose": "grep -r foo bar.py"},
        {"annotation": "acceptance:", "prose": "python -m pytest -q"},
        {"annotation": "verify: orchestrator", "prose": "Check index freshness"},
        {"annotation": "verify: human", "prose": "Inspect the output"},
    ]
    result = classify_verification_items(items)
    assert len(result["shell_items"]) == 2
    assert len(result["orchestrator_items"]) == 1
    assert len(result["human_items"]) == 1


def test_multiple_orchestrator_items_never_in_human_pending():
    """Multiple verify: orchestrator items all stay out of human_items."""
    items = [
        {"annotation": "verify: orchestrator", "prose": "Check A"},
        {"annotation": "verify: orchestrator", "prose": "Check B"},
        {"annotation": "verify: orchestrator", "prose": "Check C"},
    ]
    result = classify_verification_items(items)
    assert len(result["orchestrator_items"]) == 3
    assert len(result["human_items"]) == 0, (
        "verify: orchestrator items must NEVER appear in human_items (human_pending) - "
        "all three items violated the invariant"
    )


def test_empty_items_list():
    """Empty input produces empty output buckets."""
    result = classify_verification_items([])
    assert result["shell_items"] == []
    assert result["orchestrator_items"] == []
    assert result["human_items"] == []


# ---------------------------------------------------------------------------
# (c) render_outcome_surface - present-with-content rule (extended dict)
# ---------------------------------------------------------------------------

def _minimal_plan():
    """Minimal PLAN fixture for render_outcome_surface tests."""
    return {"_filename": "PLAN-AG0_test.md", "title": "Test PLAN"}


def _minimal_verification_state():
    """Minimal verification_state fixture."""
    return {
        "state_pass": 0,
        "state_fail": 0,
        "acceptance_pass": 0,
        "acceptance_fail": 0,
        "human_pending": [],
        "human_verdict": "pending",
        "orchestrator_attestations": [],
    }


def test_render_outcome_surface_includes_evidence_when_present():
    """render_outcome_surface explodes 'evidence' inline when the field is present."""
    plan = _minimal_plan()
    vs = _minimal_verification_state()
    human_items = [
        {
            "id": "H1",
            "prose": "INDEX is up to date",
            "evidence": "generate_index.py --check exited 0; no drift detected",
        }
    ]
    output = render_outcome_surface(
        plan=plan,
        verification_state=vs,
        executor_notes="",
        shell_passes=[],
        shell_failures=[],
        human_items=human_items,
    )
    assert "generate_index.py --check exited 0" in output, (
        "evidence field must appear inline in the rendered output (present-with-content rule)"
    )


def test_render_outcome_surface_includes_before_when_present():
    """render_outcome_surface explodes 'before' inline when the field is present."""
    plan = _minimal_plan()
    vs = _minimal_verification_state()
    human_items = [
        {
            "id": "H1",
            "prose": "Verify tier boundary text is correct",
            "before": "old tier boundary text",
            "after": "new tier boundary text",
        }
    ]
    output = render_outcome_surface(
        plan=plan,
        verification_state=vs,
        executor_notes="",
        shell_passes=[],
        shell_failures=[],
        human_items=human_items,
    )
    assert "old tier boundary text" in output, (
        "'before' field must appear inline in the rendered output"
    )
    assert "new tier boundary text" in output, (
        "'after' field must appear inline in the rendered output"
    )


def test_render_outcome_surface_attestation_reply_hint_present():
    """When evidence/before/after are present, the reply hint includes accept-attestation."""
    plan = _minimal_plan()
    vs = _minimal_verification_state()
    human_items = [
        {
            "id": "H1",
            "prose": "Fidelity check",
            "evidence": "All lines match expected content",
        }
    ]
    output = render_outcome_surface(
        plan=plan,
        verification_state=vs,
        executor_notes="",
        shell_passes=[],
        shell_failures=[],
        human_items=human_items,
    )
    assert "accept-attestation" in output, (
        "attestation reply hint (accept-attestation) must appear in output when evidence is present"
    )


def test_render_outcome_surface_backwards_compat_without_evidence():
    """Items without evidence/before/after render exactly as before (backwards compat)."""
    plan = _minimal_plan()
    vs = _minimal_verification_state()
    human_items = [
        {"id": "H1", "prose": "Eyeball the output"},
    ]
    output = render_outcome_surface(
        plan=plan,
        verification_state=vs,
        executor_notes="",
        shell_passes=[],
        shell_failures=[],
        human_items=human_items,
    )
    # Prose must appear; attestation-specific tokens must NOT appear for plain items.
    assert "Eyeball the output" in output
    assert "accept-attestation" not in output, (
        "accept-attestation must not appear for items without evidence (backwards compat)"
    )
    assert "Evidence:" not in output, (
        "Evidence: block must not appear for items without evidence field"
    )


def test_render_outcome_surface_all_three_optional_fields():
    """All three optional fields (evidence, before, after) are exploded when all present."""
    plan = _minimal_plan()
    vs = _minimal_verification_state()
    human_items = [
        {
            "id": "H2",
            "prose": "Verify refactored function signature",
            "evidence": "function signature matches spec",
            "before": "def foo(x):",
            "after": "def foo(x: int) -> str:",
        }
    ]
    output = render_outcome_surface(
        plan=plan,
        verification_state=vs,
        executor_notes="",
        shell_passes=[],
        shell_failures=[],
        human_items=human_items,
    )
    assert "function signature matches spec" in output
    assert "def foo(x):" in output
    assert "def foo(x: int) -> str:" in output
    assert "accept-attestation" in output


def test_render_outcome_surface_multiple_items_mixed():
    """Mixed plain and evidence-carrying items are each rendered correctly."""
    plan = _minimal_plan()
    vs = _minimal_verification_state()
    human_items = [
        {"id": "H1", "prose": "Plain eyeball item"},
        {
            "id": "H2",
            "prose": "Attested item",
            "evidence": "orchestrator confirmed: exit 0",
        },
    ]
    output = render_outcome_surface(
        plan=plan,
        verification_state=vs,
        executor_notes="",
        shell_passes=[],
        shell_failures=[],
        human_items=human_items,
    )
    assert "Plain eyeball item" in output
    assert "Attested item" in output
    assert "orchestrator confirmed: exit 0" in output
    # accept-attestation should appear (H2 has evidence) but not for H1 specifically
    assert "accept-attestation H2" in output
