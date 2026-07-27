"""
test_ideate.py — Test suite for ideate cadence pipeline library functions.

Tests state.py and render_critique.py.

Run with: python test_ideate.py
Exit 0 on success, non-zero on failure.

Uses plain assertions (no external test framework required).
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — ensure we can import both state.py and render_critique.py
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).parent.resolve()
_SKILLS_ROOT = _THIS_DIR.parent.parent.resolve()  # .claude/skills/
_SEVERITY_LIB = _SKILLS_ROOT / "plan-pipeline" / "lib"

# Add this lib dir and the severity-surface lib dir to sys.path
for _p in [str(_THIS_DIR), str(_SEVERITY_LIB)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import state
import render_critique as rc

# ---------------------------------------------------------------------------
# Minimal PLAN frontmatter template for tests
# ---------------------------------------------------------------------------

_PLAN_FRONTMATTER_TEMPLATE = """\
---
schema_version: 2
title: "Test PLAN for ideate test suite"
type: plan
status: ready
pipeline_phase: drafting
ideate_phase: spec_draft
ideate_critique_addressed: []
ideate_iteration_count:
  self_critique: 0
  spec_refine: 0
  risk_assess_idea: 0
  risk_assess_spec: 0
ideate_reconcile_outcome: ""
---

## Objective
Test plan for the ideate cadence pipeline test suite.

## Steps
1. Step one.
2. Step two.

## Verification
- [ ] Smoke check.
      `verify: test -f /dev/null`
- [ ] Acceptance.
      `acceptance: python -c "print('ok')"`
"""


def _write_plan(tmp_dir: Path, content: str | None = None) -> Path:
    """Write a PLAN file to tmp_dir and return its path."""
    plan_path = tmp_dir / "202605130000_PLAN_ideate-test.md"
    plan_path.write_text(content or _PLAN_FRONTMATTER_TEMPLATE, encoding="utf-8")
    return plan_path


# ---------------------------------------------------------------------------
# Helper assertions
# ---------------------------------------------------------------------------

def assert_eq(actual, expected, label: str = ""):
    if actual != expected:
        raise AssertionError(
            f"FAIL{' [' + label + ']' if label else ''}: expected {expected!r}, got {actual!r}"
        )


def assert_contains(text: str, substring: str, label: str = ""):
    if substring not in text:
        raise AssertionError(
            f"FAIL{' [' + label + ']' if label else ''}: expected {substring!r} in text.\n"
            f"Text (first 500 chars):\n{text[:500]}"
        )


def assert_not_contains(text: str, substring: str, label: str = ""):
    if substring in text:
        raise AssertionError(
            f"FAIL{' [' + label + ']' if label else ''}: expected {substring!r} NOT in text.\n"
            f"Text (first 500 chars):\n{text[:500]}"
        )


# ---------------------------------------------------------------------------
# Tests: state.py
# ---------------------------------------------------------------------------

def test_read_ideate_state_round_trip():
    """read_ideate_state reads ideate fields correctly from frontmatter."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _write_plan(Path(tmp))
        s = state.read_ideate_state(plan_path)

        assert_eq(s["ideate_phase"], "spec_draft", "ideate_phase")
        assert_eq(s["ideate_critique_addressed"], [], "ideate_critique_addressed empty")
        assert_eq(s["ideate_iteration_count"]["self_critique"], 0, "self_critique_count")
        assert_eq(s["ideate_iteration_count"]["spec_refine"], 0, "spec_refine_count")
        assert_eq(s["ideate_reconcile_outcome"], "", "reconcile_outcome")
    print("  PASS: test_read_ideate_state_round_trip")


def test_advance_phase_valid_transition():
    """advance_phase writes the new phase to frontmatter and increments counter (two-hop via Gate B)."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _write_plan(Path(tmp))

        # Gate B is now mandatory: spec_draft → risk_assess_spec → self_critique
        # (direct spec_draft → self_critique edge has been removed per PLAN-AH3 D5)
        state.advance_phase(plan_path, "spec_draft", "risk_assess_spec")
        s = state.read_ideate_state(plan_path)
        assert_eq(s["ideate_phase"], "risk_assess_spec", "phase after first hop")

        state.advance_phase(plan_path, "risk_assess_spec", "self_critique")
        s = state.read_ideate_state(plan_path)
        assert_eq(s["ideate_phase"], "self_critique", "phase after second hop")
        assert_eq(s["ideate_iteration_count"]["self_critique"], 1, "counter after advance to self_critique")
    print("  PASS: test_advance_phase_valid_transition")


def test_advance_phase_removed_spec_draft_to_self_critique():
    """advance_phase raises ValueError for spec_draft → self_critique (removed by PLAN-AH3 D5; Gate B mandatory)."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _write_plan(Path(tmp))

        try:
            state.advance_phase(plan_path, "spec_draft", "self_critique")  # removed edge
            raise AssertionError("Expected ValueError for removed edge spec_draft→self_critique but no exception raised")
        except ValueError:
            pass  # expected — Gate B is now mandatory
    print("  PASS: test_advance_phase_removed_spec_draft_to_self_critique")


def test_advance_phase_removed_none_to_spec_draft():
    """advance_phase raises ValueError for None→spec_draft and ''→spec_draft (removed by PLAN-AH3 D5; Gate A mandatory)."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _write_plan(Path(tmp))

        # Frontmatter with empty ideate_phase for the None case
        content = _PLAN_FRONTMATTER_TEMPLATE.replace(
            "ideate_phase: spec_draft",
            'ideate_phase: ""',
        )
        plan_path_empty = _write_plan(Path(tmp), content=content)

        try:
            state.advance_phase(plan_path_empty, None, "spec_draft")  # removed edge
            raise AssertionError("Expected ValueError for removed edge None→spec_draft but no exception raised")
        except ValueError:
            pass  # expected — Gate A is now mandatory

        try:
            state.advance_phase(plan_path_empty, "", "spec_draft")  # removed edge
            raise AssertionError("Expected ValueError for removed edge ''→spec_draft but no exception raised")
        except ValueError:
            pass  # expected — Gate A is now mandatory
    print("  PASS: test_advance_phase_removed_none_to_spec_draft")


def test_advance_phase_invalid_transition_raises():
    """advance_phase raises ValueError for invalid transitions."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _write_plan(Path(tmp))

        try:
            state.advance_phase(plan_path, "spec_draft", "complete")  # invalid
            raise AssertionError("Expected ValueError but no exception was raised")
        except ValueError:
            pass  # expected
    print("  PASS: test_advance_phase_invalid_transition_raises")


def test_advance_phase_to_complete_flips_pipeline_phase():
    """Advancing to 'complete' also flips pipeline_phase to 'drafted'."""
    # Use a plan at consolidate phase
    content = _PLAN_FRONTMATTER_TEMPLATE.replace(
        "ideate_phase: spec_draft",
        "ideate_phase: consolidate",
    ).replace(
        "pipeline_phase: drafting",
        "pipeline_phase: drafting",  # keep drafting initially
    )
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _write_plan(Path(tmp), content=content)
        state.advance_phase(plan_path, "consolidate", "complete")

        text = plan_path.read_text(encoding="utf-8")
        assert_contains(text, "pipeline_phase: drafted", "pipeline_phase flipped")
        assert_contains(text, "ideate_phase: complete", "ideate_phase set")
    print("  PASS: test_advance_phase_to_complete_flips_pipeline_phase")


def test_advance_phase_iteration_bound():
    """advance_phase blocks self_critique → self_critique loop at iteration 5."""
    content = _PLAN_FRONTMATTER_TEMPLATE.replace(
        "ideate_phase: spec_draft",
        "ideate_phase: self_critique",
    ).replace(
        "  self_critique: 0",
        "  self_critique: 5",
    )
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _write_plan(Path(tmp), content=content)
        try:
            state.advance_phase(plan_path, "self_critique", "self_critique")
            raise AssertionError("Expected ValueError for iteration bound but no exception raised")
        except ValueError as e:
            assert_contains(str(e), "bound exceeded", "error message")
    print("  PASS: test_advance_phase_iteration_bound")


def test_write_and_read_critique():
    """write_critique creates the JSON file; read_latest_critique reads it back."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _write_plan(Path(tmp))

        findings = [
            {
                "id": "C1",
                "code": "C001",
                "severity": "major",
                "category": "underspecified",
                "location": {"section_id": "Steps", "step_n": 2},
                "issue": "Step 2 is underspecified.",
                "suggested_fix": "Add concrete file paths.",
                "fingerprint": "abc12345",
            }
        ]
        summary = {"major_count": 1, "minor_count": 0, "discarded_count": 0}

        critique_path = state.write_critique(plan_path, 1, findings, summary)
        assert critique_path.exists(), f"Critique file not created at {critique_path}"

        loaded = state.read_latest_critique(plan_path)
        assert loaded is not None, "read_latest_critique returned None"
        assert_eq(loaded["iteration"], 1, "iteration")
        assert_eq(len(loaded["findings"]), 1, "findings count")
        assert_eq(loaded["findings"][0]["code"], "C001", "finding code")
        assert_eq(loaded["summary"]["major_count"], 1, "major_count")
    print("  PASS: test_write_and_read_critique")


def test_read_latest_critique_returns_none_when_absent():
    """read_latest_critique returns None when no critique files exist."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _write_plan(Path(tmp))
        result = state.read_latest_critique(plan_path)
        assert result is None, f"Expected None, got {result}"
    print("  PASS: test_read_latest_critique_returns_none_when_absent")


def test_compute_fingerprint_determinism():
    """compute_fingerprint produces the same 8-char SHA for the same inputs."""
    fp1 = state.compute_fingerprint("C001", "major", "underspecified", {"section_id": "Steps", "step_n": 3})
    fp2 = state.compute_fingerprint("C001", "major", "underspecified", {"section_id": "Steps", "step_n": 3})
    assert_eq(fp1, fp2, "fingerprint determinism")
    assert_eq(len(fp1), 8, "fingerprint length")
    assert all(c in "0123456789abcdef" for c in fp1), f"fingerprint not hex: {fp1}"
    print("  PASS: test_compute_fingerprint_determinism")


def test_compute_fingerprint_uniqueness():
    """compute_fingerprint produces different results for different inputs."""
    fp_a = state.compute_fingerprint("C001", "major", "underspecified", {"section_id": "Steps", "step_n": 1})
    fp_b = state.compute_fingerprint("C002", "major", "missing-acceptance", {"section_id": "Verification"})
    fp_c = state.compute_fingerprint("C001", "minor", "underspecified", {"section_id": "Steps", "step_n": 1})

    assert fp_a != fp_b, "Different codes should produce different fingerprints"
    assert fp_a != fp_c, "Different severity should produce different fingerprints"
    print("  PASS: test_compute_fingerprint_uniqueness")


def test_detect_in_flight_plans():
    """detect_in_flight_plans returns plan IDs for in-flight PLANs."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Create an in-flight PLAN
        in_flight_content = """\
---
type: plan
schema_version: 2
pipeline_phase: drafted
ideate_phase: spec_draft
---
## Objective
In-flight plan.
"""
        in_flight_path = tmp_path / "202605130001_PLAN_in-flight.md"
        in_flight_path.write_text(in_flight_content, encoding="utf-8")

        # Create a terminal PLAN
        terminal_content = """\
---
type: plan
schema_version: 2
pipeline_phase: drafted
ideate_phase: complete
---
## Objective
Terminal plan.
"""
        terminal_path = tmp_path / "202605130002_PLAN_terminal.md"
        terminal_path.write_text(terminal_content, encoding="utf-8")

        # Create a non-plan file (should be ignored)
        (tmp_path / "LOG_202605.md").write_text("# Log", encoding="utf-8")

        result = state.detect_in_flight_plans(tmp_path, exclude_plan_id="202605130000_PLAN_ideate-test")
        assert "202605130001_PLAN_in-flight" in result, f"Expected in-flight plan in result: {result}"
        assert "202605130002_PLAN_terminal" not in result, f"Terminal plan should not be in result: {result}"
    print("  PASS: test_detect_in_flight_plans")


def test_detect_in_flight_plans_excludes_self():
    """detect_in_flight_plans excludes the current plan from results."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        plan_content = """\
---
type: plan
schema_version: 2
pipeline_phase: drafting
ideate_phase: spec_draft
---
"""
        plan_path = tmp_path / "202605130001_PLAN_current.md"
        plan_path.write_text(plan_content, encoding="utf-8")

        result = state.detect_in_flight_plans(tmp_path, exclude_plan_id="202605130001_PLAN_current")
        assert "202605130001_PLAN_current" not in result, \
            f"Self should be excluded from in-flight list: {result}"
    print("  PASS: test_detect_in_flight_plans_excludes_self")


def test_detect_in_flight_plans_aa_form():
    """detect_in_flight_plans recognises AA-form PLAN filenames (not just legacy timestamps)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Create an AA-form in-flight PLAN
        in_flight_content = """\
---
type: plan
schema_version: 2
pipeline_phase: drafted
ideate_phase: spec_draft
---
## Objective
AA-form in-flight plan.
"""
        in_flight_path = tmp_path / "PLAN-AA0_in-flight-aa.md"
        in_flight_path.write_text(in_flight_content, encoding="utf-8")

        # Create an AA-form terminal PLAN (should NOT appear in results)
        terminal_content = """\
---
type: plan
schema_version: 2
pipeline_phase: drafted
ideate_phase: complete
---
## Objective
AA-form terminal plan.
"""
        terminal_path = tmp_path / "PLAN-AA1_terminal-aa.md"
        terminal_path.write_text(terminal_content, encoding="utf-8")

        result = state.detect_in_flight_plans(tmp_path, exclude_plan_id="PLAN-AE6_self")
        assert "PLAN-AA0_in-flight-aa" in result, \
            f"AA-form in-flight plan should be detected: {result}"
        assert "PLAN-AA1_terminal-aa" not in result, \
            f"AA-form terminal plan should not be in result: {result}"
    print("  PASS: test_detect_in_flight_plans_aa_form")


# ---------------------------------------------------------------------------
# Tests: render_critique.py
# ---------------------------------------------------------------------------

_SAMPLE_CRITIQUE_JSON = {
    "schema_version": 1,
    "phase": "self_critique",
    "iteration": 1,
    "plan_path": "Workbench/202605130000_PLAN_test.md",
    "findings": [
        {
            "id": "C1",
            "code": "C001",
            "severity": "major",
            "category": "underspecified",
            "location": {"section_id": "Steps", "step_n": 2},
            "issue": "Step 2 is missing concrete file paths.",
            "suggested_fix": "Add the exact file path to the step prose.",
            "fingerprint": "aa001122",
        },
        {
            "id": "C2",
            "code": "C003",
            "severity": "minor",
            "category": "wrong-step-decomposition",
            "location": {"section_id": "Steps", "step_n": 4},
            "issue": "Step 4 combines two independent concerns.",
            "suggested_fix": "Split into Steps 4a and 4b.",
            "fingerprint": "bb334455",
        },
    ],
    "summary": {
        "major_count": 2,
        "minor_count": 1,
        "discarded_count": 0,
    },
}

_SAMPLE_PLAN_FRONTMATTER = {
    "title": "Test plan",
    "pipeline_phase": "drafting",
    "ideate_phase": "self_critique",
    "_filename": "202605130000_PLAN_test.md",
}


def test_render_critique_surface_contains_critique_verbs():
    """render_critique_surface output contains critique-specific action verbs."""
    prompt = rc.render_critique_surface(
        plan=_SAMPLE_PLAN_FRONTMATTER,
        critique_json=_SAMPLE_CRITIQUE_JSON,
        prior_critique_json=None,
    )

    # Check for critique-specific verbs in the action menu
    assert_contains(prompt, "address", "address verb in prompt")
    assert_contains(prompt, "defer", "defer verb in prompt")
    assert_contains(prompt, "discard", "discard verb in prompt")

    # Should NOT contain raw audit verbs in the action menu
    # (the fix, ack, override verbs are replaced)
    # Note: "fix" might appear in "suggested_fix" content — we check the action menu specifically
    assert_contains(prompt, "discard_all", "discard_all action line")

    # Should reference self-critique, not sufficiency-auditor
    assert_contains(prompt, "self-critique", "self-critique label")
    assert_not_contains(prompt, "sufficiency-auditor", "no raw sufficiency-auditor label")
    print("  PASS: test_render_critique_surface_contains_critique_verbs")


def test_render_critique_surface_shows_findings():
    """render_critique_surface output shows the critique findings."""
    prompt = rc.render_critique_surface(
        plan=_SAMPLE_PLAN_FRONTMATTER,
        critique_json=_SAMPLE_CRITIQUE_JSON,
        prior_critique_json=None,
    )
    # Finding codes should appear in the output
    assert_contains(prompt, "C001", "C001 code in prompt")
    assert_contains(prompt, "C003", "C003 code in prompt")
    print("  PASS: test_render_critique_surface_shows_findings")


def test_parse_critique_reply_discard_all_short_circuit():
    """parse_critique_reply returns discard_all action immediately without delegation."""
    for variant in ["discard_all", "discard-all", "DISCARD_ALL"]:
        result = rc.parse_critique_reply(
            reply_text=variant,
            plan_frontmatter=_SAMPLE_PLAN_FRONTMATTER,
            critique_json=_SAMPLE_CRITIQUE_JSON,
            prior_critique_json=None,
        )
        assert_eq(result["action"], "discard_all", f"action for {variant}")
        assert_eq(result["state_mutations"], [], f"no mutations for {variant}")
        assert_eq(result["reprompt_text"], None, f"no reprompt for {variant}")
    print("  PASS: test_parse_critique_reply_discard_all_short_circuit")


def test_parse_critique_reply_address_action():
    """parse_critique_reply translates 'address E1' to action='address'."""
    result = rc.parse_critique_reply(
        reply_text="address E1",
        plan_frontmatter=_SAMPLE_PLAN_FRONTMATTER,
        critique_json=_SAMPLE_CRITIQUE_JSON,
        prior_critique_json=None,
    )
    # address maps to fix in audit, which maps back to address
    assert_eq(result["action"], "address", "action is address")
    print("  PASS: test_parse_critique_reply_address_action")


def test_parse_critique_reply_defer_action():
    """parse_critique_reply translates 'defer W1' to action='defer'."""
    result = rc.parse_critique_reply(
        reply_text="defer W1",
        plan_frontmatter=_SAMPLE_PLAN_FRONTMATTER,
        critique_json=_SAMPLE_CRITIQUE_JSON,
        prior_critique_json=None,
    )
    assert_eq(result["action"], "defer", "action is defer")
    # Mutation should target ideate_critique_addressed (not audit_acknowledgements)
    if result["state_mutations"]:
        paths = [m.get("path", "") for m in result["state_mutations"]]
        for path in paths:
            assert "audit_" not in path, f"Found audit_ path: {path}; expected ideate_ path"
    print("  PASS: test_parse_critique_reply_defer_action")


def test_parse_critique_reply_mutation_paths():
    """parse_critique_reply mutation paths use ideate_ prefix, not audit_ prefix."""
    # "defer W1" → ack W1 internally → appends to audit_acknowledgements → translated to ideate_critique_addressed
    result = rc.parse_critique_reply(
        reply_text="defer W1",
        plan_frontmatter=_SAMPLE_PLAN_FRONTMATTER,
        critique_json=_SAMPLE_CRITIQUE_JSON,
        prior_critique_json=None,
    )
    paths = [m.get("path", "") for m in result.get("state_mutations", [])]
    for path in paths:
        assert not path.startswith("audit_"), \
            f"Mutation path starts with 'audit_': {path!r}. Expected 'ideate_' prefix."
    print("  PASS: test_parse_critique_reply_mutation_paths")


# ---------------------------------------------------------------------------
# Worked example: 2 major + 1 minor findings, "address C1; defer C3"
# ---------------------------------------------------------------------------

def test_worked_example_address_and_defer():
    """
    Worked example from the PLAN spec:
      - Critique: 2 major findings (C1=code C001, C2=code C005) + 1 minor (C3=code C003)
      - Human reply: "address E1\ndefer W1"
      - Expect: action='address', state mutations append to ideate_critique_addressed

    Note: The critique JSON has 2 major (→ E1, E2) and 1 minor (→ W1).
    The human addresses E1 and defers W1.
    Since E2 is unaddressed and E2 is an error, the primary action should be 'address' (fix).
    """
    critique = {
        "schema_version": 1,
        "phase": "self_critique",
        "iteration": 1,
        "plan_path": "Workbench/202605130000_PLAN_test.md",
        "findings": [
            {
                "id": "C1",
                "code": "C001",
                "severity": "major",
                "category": "underspecified",
                "location": {"section_id": "Steps", "step_n": 2},
                "issue": "Step 2 lacks concrete file paths.",
                "suggested_fix": "Add paths.",
                "fingerprint": state.compute_fingerprint("C001", "major", "underspecified",
                                                         {"section_id": "Steps", "step_n": 2}),
            },
            {
                "id": "C2",
                "code": "C005",
                "severity": "major",
                "category": "design-issue",
                "location": {"section_id": "Context"},
                "issue": "Design has a circular dependency risk.",
                "suggested_fix": "Break the dependency.",
                "fingerprint": state.compute_fingerprint("C005", "major", "design-issue",
                                                         {"section_id": "Context"}),
            },
            {
                "id": "C3",
                "code": "C003",
                "severity": "minor",
                "category": "wrong-step-decomposition",
                "location": {"section_id": "Steps", "step_n": 5},
                "issue": "Step 5 combines two concerns.",
                "suggested_fix": "Split into 5a and 5b.",
                "fingerprint": state.compute_fingerprint("C003", "minor", "wrong-step-decomposition",
                                                         {"section_id": "Steps", "step_n": 5}),
            },
        ],
        "summary": {"major_count": 2, "minor_count": 1, "discarded_count": 0},
    }

    plan_fm = {
        "title": "Worked example PLAN",
        "pipeline_phase": "drafting",
        "ideate_phase": "self_critique",
        "_filename": "202605130000_PLAN_test.md",
        "audit_state": {"sufficiency_iterations": 1},
    }

    # Human reply: address E1 (major C001), defer W1 (minor C003)
    # Note: E2 (C005) is not addressed — so 'fix' is the primary action from parse_audit_reply
    reply = "address E1\ndefer W1"
    result = rc.parse_critique_reply(
        reply_text=reply,
        plan_frontmatter=plan_fm,
        critique_json=critique,
        prior_critique_json=None,
    )

    # Primary action should be 'address' (translated from 'fix')
    assert result["action"] == "address", \
        f"Expected action='address', got {result['action']!r}"

    # State mutations should contain a defer mutation targeting ideate_critique_addressed
    paths = [m.get("path", "") for m in result.get("state_mutations", [])]
    assert any("ideate_" in p for p in paths), \
        f"Expected ideate_ path in mutations: {paths}"

    # No mutation should have audit_ prefix
    for path in paths:
        assert not path.startswith("audit_"), \
            f"Found audit_ path in critique reply mutations: {path!r}"

    print("  PASS: test_worked_example_address_and_defer")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_all_tests():
    """Run all tests and report results."""
    tests = [
        test_read_ideate_state_round_trip,
        test_advance_phase_valid_transition,
        test_advance_phase_removed_spec_draft_to_self_critique,
        test_advance_phase_removed_none_to_spec_draft,
        test_advance_phase_invalid_transition_raises,
        test_advance_phase_to_complete_flips_pipeline_phase,
        test_advance_phase_iteration_bound,
        test_write_and_read_critique,
        test_read_latest_critique_returns_none_when_absent,
        test_compute_fingerprint_determinism,
        test_compute_fingerprint_uniqueness,
        test_detect_in_flight_plans,
        test_detect_in_flight_plans_excludes_self,
        test_detect_in_flight_plans_aa_form,
        test_render_critique_surface_contains_critique_verbs,
        test_render_critique_surface_shows_findings,
        test_parse_critique_reply_discard_all_short_circuit,
        test_parse_critique_reply_address_action,
        test_parse_critique_reply_defer_action,
        test_parse_critique_reply_mutation_paths,
        test_worked_example_address_and_defer,
    ]

    failures = []
    print(f"Running {len(tests)} tests...\n")

    for test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            failures.append((test_fn.__name__, e))
            print(f"  FAIL: {test_fn.__name__}")
            traceback.print_exc(limit=3)
            print()

    print(f"\n{'=' * 50}")
    if failures:
        print(f"FAILED: {len(failures)}/{len(tests)} tests failed.")
        for name, err in failures:
            print(f"  - {name}: {err}")
        sys.exit(1)
    else:
        print(f"PASSED: All {len(tests)} tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    run_all_tests()
