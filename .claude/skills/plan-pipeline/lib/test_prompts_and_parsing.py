"""
test_prompts_and_parsing.py — Three worked examples from the severity-surface ADVICE.

Worked examples:
  Example A: 2 errors + 1 warning + 1 note audit reply
  Example B: mixed shell-fail + human items in outcome-verifying
  Example C: MAX_ITERATIONS halt with override + extract reply

Run via:
    python test_prompts_and_parsing.py

Exit 0 on success, non-zero on any assertion failure.

Reference: Workbench/202605130040_ADVICE_severity-classified-human-surface.md
"""

import sys
import os

# Allow imports from this directory
sys.path.insert(0, os.path.dirname(__file__))

# Ensure UTF-8 stdout/stderr on Windows (cp1252 default chokes on → etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import render_prompts  # noqa: F401 — verify: grep import.*render_prompts
import parse_replies   # noqa: F401 — verify: grep import.*parse_replies
import apply_actions   # noqa: F401 — verify: grep import.*apply_actions

from render_prompts import render_audit_surface, render_outcome_surface, render_halt_surface
from parse_replies import parse_audit_reply, parse_outcome_reply, parse_halt_reply
from apply_actions import apply_audit_action, apply_outcome_action, apply_halt_action


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

_failures: list[str] = []


def expect(condition: bool, message: str) -> None:
    """Record a test failure if condition is False."""
    if not condition:
        _failures.append(message)
        print(f"  FAIL: {message}")
    else:
        print(f"  pass: {message}")


def expect_eq(actual, expected, label: str) -> None:
    """Assert equality with a descriptive label."""
    if actual != expected:
        _failures.append(f"{label}: expected {expected!r}, got {actual!r}")
        print(f"  FAIL: {label}: expected {expected!r}, got {actual!r}")
    else:
        print(f"  pass: {label} == {expected!r}")


def expect_contains(text: str, substring: str, label: str) -> None:
    """Assert that substring appears in text."""
    if substring not in text:
        _failures.append(f"{label}: '{substring}' not found in output")
        print(f"  FAIL: {label}: '{substring}' not found in:\n    {text[:200]!r}")
    else:
        print(f"  pass: {label} contains '{substring}'")


# ---------------------------------------------------------------------------
# Example A: 2 errors + 1 warning + 1 note, with recurrence on E1
# ---------------------------------------------------------------------------

def test_example_a():
    """
    Example A from ADVICE: 2 errors + 1 warning + 1 note.
    Human replies:
        ack W1
        override E1: this step's test-fidelity gap is intentional; covered by the parent PLAN's verification
        fix
    Expected:
        - Parser produces 3 actions: ack(W1), override(E1), fix
        - fix is primary action (supersedes override for state-transition)
        - override E1 mutation IS written (fix does not suppress overrides that pair with explicit IDs unless
          they share the SAME target — per spec "fix wins for that ID" means the PLAN revision takes
          precedence over the override for E1; but per ADVICE example the override IS recorded)
        - ack W1 mutation appended to audit_acknowledgements
        - W2 reference in "ack W1,W2" → W2 doesn't exist → handled gracefully when only W1 present
    """
    print("\n--- Example A: audit-revision surface ---")

    # Build audit_result_json with 2 errors, 1 warning, 1 note
    audit_result = {
        "schema_version": 2,
        "auditor": "sufficiency",
        "iteration": 2,
        "findings": [
            {
                "code": "S104",
                "level": "error",
                "category": "test-fidelity",
                "location": "step 7",
                "message": "Step asserts 'tests pass' without specifying which test suite or command.",
                "suggested_fix": "Add the exact test command to the step.",
                "fingerprint": "ab12cd34",
            },
            {
                "code": "S203",
                "level": "error",
                "category": "acceptance-coverage",
                "location": "step 12",
                "message": "No acceptance: command on a step that produces a Python script.",
                "suggested_fix": "Add acceptance: python <script> with a representative input.",
                "fingerprint": "ef56gh78",
            },
            {
                "code": "S312",
                "level": "warning",
                "category": "freshness",
                "location": "global",
                "message": "PLAN does not declare freshness window for upstream data fixture.",
                "suggested_fix": "Add freshness constraint to the Context section.",
                "fingerprint": "ij90kl12",
            },
            {
                "code": "S401",
                "level": "note",
                "category": "meta-design",
                "location": "step 3",
                "message": "Wording 'should be robust' is meta-design noise.",
                "suggested_fix": "Replace with concrete criterion.",
                "fingerprint": "mn34op56",
            },
        ],
        "summary": {"error_count": 2, "warning_count": 1, "note_count": 1},
    }

    plan = {
        "title": "202605121430_PLAN_audit-and-index-v2.md",
        "_filename": "202605121430_PLAN_audit-and-index-v2.md",
        "audit_state": {
            "sufficiency_iterations": 2,
            "plan_safety_iterations": 0,
            "last_stage": "sufficiency",
            "last_outcome": "revision_needed",
        },
        "audit_acknowledgements": [],
        "audit_disputes": [],
        "audit_overrides": [],
    }

    # Recurring fingerprints: E1 (ab12cd34) recurred from iteration 1
    recurring_fps = ["ab12cd34"]

    # --- Step A1: Render the prompt ---
    prompt = render_audit_surface(
        plan=plan,
        auditor="sufficiency",
        iteration=2,
        max_iterations=5,
        audit_result_json=audit_result,
        prior_audit_json=None,
        recurring_fingerprints=recurring_fps,
    )

    print("\n  Rendered prompt (truncated to 500 chars):")
    print("  " + prompt[:500].replace("\n", "\n  "))

    # Verify prompt content
    expect_contains(prompt, "Audit iteration 2: sufficiency-auditor returned revision_needed", "A: header line")
    expect_contains(prompt, "2 errors · 1 warning · 1 note", "A: summary line")
    expect_contains(prompt, "1 finding(s) have recurred", "A: recurrence banner")
    expect_contains(prompt, "[STUCK ×2]", "A: STUCK badge on E1")
    expect_contains(prompt, "E1", "A: E1 display ID")
    expect_contains(prompt, "E2", "A: E2 display ID")
    expect_contains(prompt, "W1", "A: W1 display ID")
    expect_contains(prompt, "N1", "A: N1 display ID")
    expect_contains(prompt, "S104", "A: S104 code")
    expect_contains(prompt, "S203", "A: S203 code")
    expect_contains(prompt, "fix", "A: action menu contains fix")
    expect_contains(prompt, "ack W1,W3", "A: action menu contains ack")
    expect_contains(prompt, "override E1: <reason>", "A: action menu contains override")

    # --- Step A2: Parse the ADVICE sample reply ---
    human_reply = """ack W1
override E1: this step's test-fidelity gap is intentional; covered by the parent PLAN's verification, not this one
fix"""

    parsed = parse_audit_reply(
        reply_text=human_reply,
        plan_frontmatter=plan,
        audit_result_json=audit_result,
        prior_audit_json=None,
    )

    print(f"\n  Parse result action: {parsed['action']}")
    expect_eq(parsed["action"], "fix", "A: primary action is fix (fix supersedes)")
    expect(parsed["reprompt_text"] is None, "A: no reprompt")

    actions_list = parsed["action_args"].get("actions", [])
    action_names = [a["action"] for a in actions_list]
    expect("ack" in action_names, "A: ack action present")
    expect("override" in action_names, "A: override action present")
    expect("fix" in action_names, "A: fix action present")

    # W1 ack mutation
    ack_mutations = [m for m in parsed["state_mutations"] if m["path"] == "audit_acknowledgements"]
    expect(len(ack_mutations) == 1, "A: 1 ack mutation for W1")
    if ack_mutations:
        expect_eq(ack_mutations[0]["value"]["fingerprint"], "ij90kl12", "A: W1 fingerprint in ack mutation")

    # --- Step A3: Apply the actions ---
    updated_plan = apply_audit_action(
        plan=plan,
        action=parsed["action"],
        action_args=parsed["action_args"],
        audit_result_json=audit_result,
    )

    expect(len(updated_plan["audit_acknowledgements"]) == 1, "A: W1 added to audit_acknowledgements")
    if updated_plan["audit_acknowledgements"]:
        expect_eq(
            updated_plan["audit_acknowledgements"][0]["fingerprint"],
            "ij90kl12",
            "A: W1 fingerprint in acknowledgements",
        )

    # Override E1 should be written (override with rationale and explicit fix are compatible per ADVICE)
    expect(len(updated_plan["audit_overrides"]) >= 1, "A: E1 override written (fix does not suppress override)")
    if updated_plan["audit_overrides"]:
        expect_eq(
            updated_plan["audit_overrides"][0]["fingerprint"],
            "ab12cd34",
            "A: E1 fingerprint in overrides",
        )

    print("\n  Example A: DONE")


# ---------------------------------------------------------------------------
# Example B: outcome-verifying with mixed shell-fail + human items
# ---------------------------------------------------------------------------

def test_example_b():
    """
    Example B from ADVICE: shell-fail F1 + human items H1, H2.
    Human replies:
        ack-failure F1: verifier regex expected 5 categories but reference doc lists 6; spec is correct
        ack-human H1
        ack-human H2
    Expected:
        - Parser produces 3 actions: ack-failure(F1), ack-human(H1), ack-human(H2)
        - state_mutations: human_acknowledged_failures appended, human_passed gets H1 and H2
    """
    print("\n--- Example B: outcome-verifying surface ---")

    shell_passes = [
        {"type": "verify", "command": "grep -q 'schema_version' plan.md"},
        {"type": "verify", "command": "test -f INDEX.md"},
        {"type": "acceptance", "command": "python scripts/smoke.py"},
        {"type": "acceptance", "command": "python scripts/validate_schema.py"},
    ]
    # Add more passes to reach 12 verify + 2 acceptance like the ADVICE example
    for i in range(10):
        shell_passes.append({"type": "verify", "command": f"grep -q 'field_{i}' schema.md"})

    shell_failures = [
        {
            "id": "F1",
            "type": "verify:",
            "command": 'grep -E "concreteness|atomicity|..." .../auditor-codes.md | wc -l | grep -q "[5-9]"',
            "exit_code": 1,
        }
    ]

    human_items = [
        {"id": "H1", "prose": "INDEX.md kanban table renders with phase columns; alerts subsections present."},
        {"id": "H2", "prose": "auditor-codes.md categories and example findings are descriptive."},
    ]

    plan = {
        "title": "202605121430_PLAN_audit-and-index-v2.md",
        "_filename": "202605121430_PLAN_audit-and-index-v2.md",
        "pipeline_phase": "outcome-verifying",
        "verification_state": {
            "state_pass": 12,
            "state_fail": 1,
            "acceptance_pass": 2,
            "acceptance_fail": 0,
            "human_pending": [
                {"id": "H1", "prose": "INDEX.md kanban table renders with phase columns; alerts subsections present."},
                {"id": "H2", "prose": "auditor-codes.md categories and example findings are descriptive."},
            ],
            "human_verdict": "pending",
            "human_acknowledged_failures": [],
            "human_passed": [],
        },
    }

    verification_state = plan["verification_state"]

    # --- Step B1: Render the prompt ---
    prompt = render_outcome_surface(
        plan=plan,
        verification_state=verification_state,
        executor_notes="Implemented audit schema v2 and INDEX projection.",
        shell_passes=shell_passes,
        shell_failures=shell_failures,
        human_items=human_items,
        executor_heartbeat=None,  # None-safe: no heartbeat context line
    )

    print("\n  Rendered prompt (truncated to 600 chars):")
    print("  " + prompt[:600].replace("\n", "\n  "))

    expect_contains(prompt, "Outcome verification for", "B: header line")
    expect_contains(prompt, "PASSED (auto-checked)", "B: passed section")
    expect_contains(prompt, "FAILED (shell — need attention)", "B: failed section")
    expect_contains(prompt, "F1", "B: F1 in failed section")
    expect_contains(prompt, "exit 1", "B: exit code in failed section")
    expect_contains(prompt, "HUMAN-JUDGEMENT items", "B: human judgement section")
    expect_contains(prompt, "H1", "B: H1 in human judgement")
    expect_contains(prompt, "H2", "B: H2 in human judgement")
    expect_contains(prompt, "ack-failure", "B: action menu contains ack-failure")
    # Heartbeat line should NOT appear (None was passed)
    expect("Note: executor ran" not in prompt, "B: no heartbeat line (None passed)")

    # --- Step B1b: Test heartbeat rendering ---
    prompt_with_hb = render_outcome_surface(
        plan=plan,
        verification_state=verification_state,
        executor_notes="",
        shell_passes=shell_passes,
        shell_failures=shell_failures,
        human_items=human_items,
        executor_heartbeat={"step": 3, "step_summary": "build index", "duration_minutes": 47},
    )
    expect_contains(prompt_with_hb, "47 minutes on step 3", "B: heartbeat line present when provided")
    expect_contains(prompt_with_hb, "build index", "B: heartbeat step_summary in line")

    # --- Step B2: Parse the ADVICE follow-up reply ---
    human_reply = (
        "ack-failure F1: verifier regex expected 5 categories but reference doc lists 6; "
        "spec is correct, regex needs widening — non-blocking\n"
        "ack-human H1\n"
        "ack-human H2"
    )

    parsed = parse_outcome_reply(
        reply_text=human_reply,
        verification_state=verification_state,
        shell_failures=shell_failures,
    )

    print(f"\n  Parse result action: {parsed['action']}")
    expect_eq(parsed["action"], "ack-failure", "B: primary action is ack-failure")
    expect(parsed["reprompt_text"] is None, "B: no reprompt")

    actions_list = parsed["action_args"].get("actions", [])
    action_names = [a["action"] for a in actions_list]
    expect("ack-failure" in action_names, "B: ack-failure action present")
    expect("ack-human" in action_names, "B: ack-human action present")
    ack_human_count = action_names.count("ack-human")
    expect_eq(ack_human_count, 2, "B: two ack-human actions (H1, H2)")

    # Check state mutations
    haf_mutations = [m for m in parsed["state_mutations"] if m["path"] == "verification_state.human_acknowledged_failures"]
    expect(len(haf_mutations) == 1, "B: 1 ack-failure mutation")
    if haf_mutations:
        expect_eq(haf_mutations[0]["op"], "append", "B: ack-failure mutation op is append")
        expect_eq(haf_mutations[0]["value"]["failure_id"], "F1", "B: F1 in ack-failure mutation")

    hp_mutations = [m for m in parsed["state_mutations"] if m["path"] == "verification_state.human_passed"]
    expect(len(hp_mutations) == 2, "B: 2 human_passed mutations (H1 and H2)")

    # --- Step B3: Apply the actions ---
    updated_plan = apply_outcome_action(
        plan=plan,
        action=parsed["action"],
        action_args=parsed["action_args"],
        verification_state=verification_state,
    )

    vs = updated_plan["verification_state"]
    expect(len(vs["human_acknowledged_failures"]) == 1, "B: F1 in human_acknowledged_failures")
    if vs["human_acknowledged_failures"]:
        expect_eq(vs["human_acknowledged_failures"][0]["check"], "F1", "B: failure ID stored as check")

    expect("H1" in vs["human_passed"], "B: H1 in human_passed")
    expect("H2" in vs["human_passed"], "B: H2 in human_passed")

    print("\n  Example B: DONE")


# ---------------------------------------------------------------------------
# Example C: kanban-halt MAX_ITERATIONS with override + extract reply
# ---------------------------------------------------------------------------

def test_example_c():
    """
    Example C from ADVICE: MAX_ITERATIONS exception on sufficiency iteration 5/5.
    Human replies (combined multi-action):
        3 override: the two stuck findings are intentional design choices documented in linked_decisions; accepting risk
    Then separately:
        extract step 1 to child PLAN
    Expected:
        - First reply: override action, rationale captured, pipeline_overrides mutation
        - Second reply (extract): extract action, audit_extracted mutation
    """
    print("\n--- Example C: kanban-halt surface ---")

    plan = {
        "title": "202605121430_PLAN_audit-and-index-v2.md",
        "_filename": "202605121430_PLAN_audit-and-index-v2.md",
        "pipeline_phase": "drafted",
        "status": "in-progress",
        "audit_state": {
            "sufficiency_iterations": 5,
            "plan_safety_iterations": 0,
            "last_stage": "sufficiency",
            "last_outcome": "exception",
        },
        "pipeline_overrides": [],
        "halt_log": [],
        "audit_extracted": [],
    }

    exception_reason = "Audit loop did not converge after 5 iterations on sufficiency."
    diagnostics = {
        "phase": "drafted",
        "subagent": "sufficiency-auditor",
        "iteration": 5,
        "stage": "sufficiency",
        "last_successful_commit": '9a3f2b1 "plan-pipeline: audit_state update — sufficiency:revision_needed"',
        "wip_commit": 'c4e8d05 "WIP: pipeline halted at drafted for 202605121430_PLAN_audit-and-index-v2.md"',
        "diagnostics_path": "Workbench/.audit/202605121430_PLAN_audit-and-index-v2-5.json",
        "details": [
            "Recurring findings (across iterations 3–5):",
            "  - S104 @ step 7 [STUCK ×3]: test fidelity ambiguity",
            "  - S203 @ step 12 [STUCK ×3]: missing acceptance: on script-producing step",
            "New findings this iteration: 1 (S312 warning, freshness)",
            "Acks recorded: 2  ·  Disputes recorded: 1  ·  Overrides recorded: 0",
        ],
    }

    orchestrator_state = {"pipeline_phase": "drafted"}

    # --- Step C1: Render the halt prompt ---
    prompt = render_halt_surface(
        plan=plan,
        exception_reason=exception_reason,
        diagnostics=diagnostics,
        orchestrator_state=orchestrator_state,
        executor_heartbeat=None,
    )

    print("\n  Rendered halt prompt (truncated to 700 chars):")
    print("  " + prompt[:700].replace("\n", "\n  "))

    expect_contains(prompt, "PIPELINE HALTED at phase: drafted", "C: header line")
    expect_contains(prompt, "202605121430_PLAN_audit-and-index-v2.md", "C: plan filename in header")
    expect_contains(prompt, "Audit loop did not converge after 5 iterations", "C: cause line")
    expect_contains(prompt, "drafted / sufficiency-auditor", "C: where line")
    expect_contains(prompt, "5 (sufficiency)", "C: iteration line")
    expect_contains(prompt, "STUCK ×3", "C: STUCK badge in diagnostics")
    expect_contains(prompt, "9a3f2b1", "C: last successful commit")
    expect_contains(prompt, "c4e8d05", "C: WIP commit")
    expect_contains(prompt, "3) override:", "C: override option")
    expect_contains(prompt, "5) different-auditor", "C: different-auditor option")
    expect_contains(prompt, "7) abandon:", "C: abandon option")

    # Verify heartbeat is absent (None passed)
    expect("heartbeat" not in prompt.lower(), "C: no heartbeat line (None passed)")

    # --- Step C1b: Test heartbeat in halt prompt ---
    prompt_with_hb = render_halt_surface(
        plan=plan,
        exception_reason=exception_reason,
        diagnostics=diagnostics,
        orchestrator_state=orchestrator_state,
        executor_heartbeat={"step": 3, "step_summary": "run auditor", "duration_minutes": 12},
    )
    expect_contains(prompt_with_hb, "heartbeat", "C: heartbeat present when executor_heartbeat provided")

    # --- Step C2: Parse the ADVICE sample reply (override) ---
    human_reply_override = (
        "3 override: the two stuck findings are intentional design choices documented "
        "in linked_decisions; auditor cannot infer that from PLAN text alone. "
        "Accepting risk and moving forward."
    )

    parsed_override = parse_halt_reply(
        reply_text=human_reply_override,
        halt_reason=exception_reason,
    )

    print(f"\n  Parse result action: {parsed_override['action']}")
    expect_eq(parsed_override["action"], "override", "C: override action parsed")
    expect(parsed_override["reprompt_text"] is None, "C: no reprompt for override")

    override_rationale = parsed_override["action_args"].get("rationale", "")
    expect("linked_decisions" in override_rationale, "C: rationale captured in action_args")

    po_mutations = [m for m in parsed_override["state_mutations"] if m["path"] == "pipeline_overrides"]
    expect(len(po_mutations) == 1, "C: 1 pipeline_overrides mutation")
    if po_mutations:
        expect_eq(po_mutations[0]["op"], "append", "C: pipeline_overrides mutation op is append")
        expect("linked_decisions" in po_mutations[0]["value"]["rationale"], "C: rationale in mutation value")

    # --- Step C3: Apply the override action ---
    updated_plan_override = apply_halt_action(
        plan=plan,
        action=parsed_override["action"],
        action_args=parsed_override["action_args"],
        exception_state={"phase": "drafted", "cause": exception_reason},
    )

    expect(len(updated_plan_override["pipeline_overrides"]) == 1, "C: pipeline_overrides has 1 entry")
    if updated_plan_override["pipeline_overrides"]:
        po = updated_plan_override["pipeline_overrides"][0]
        expect_eq(po["action"], "override", "C: override action in pipeline_overrides entry")
        expect("linked_decisions" in po["rationale"], "C: rationale in pipeline_overrides entry")

    # --- Step C4: Parse a separate extract reply ---
    human_reply_extract = "extract step 1 to child PLAN"

    parsed_extract = parse_halt_reply(
        reply_text=human_reply_extract,
        halt_reason=exception_reason,
    )

    print(f"\n  Parse result action (extract): {parsed_extract['action']}")
    expect_eq(parsed_extract["action"], "extract", "C: extract action parsed")

    ae_mutations = [m for m in parsed_extract["state_mutations"] if m["path"] == "audit_extracted"]
    expect(len(ae_mutations) == 1, "C: 1 audit_extracted mutation")
    if ae_mutations:
        expect_eq(ae_mutations[0]["op"], "set", "C: audit_extracted mutation op is set")
        expect("step 1 to child PLAN" in ae_mutations[0]["value"].get("spec", ""), "C: spec in audit_extracted")

    # --- Step C5: Apply the extract action ---
    updated_plan_extract = apply_halt_action(
        plan=plan,
        action=parsed_extract["action"],
        action_args=parsed_extract["action_args"],
        exception_state={"phase": "drafted", "cause": exception_reason},
    )

    audit_extracted = updated_plan_extract.get("audit_extracted", [])
    if isinstance(audit_extracted, list):
        expect(len(audit_extracted) >= 1, "C: audit_extracted list has 1+ entries")
        if audit_extracted:
            expect("step 1 to child PLAN" in audit_extracted[0].get("spec", ""), "C: spec in audit_extracted entry")
    else:
        expect(audit_extracted is not None, "C: audit_extracted is non-null after extract")

    # --- Step C6: Test different-auditor reply ---
    human_reply_diff_auditor = "5 different-auditor opus"
    parsed_da = parse_halt_reply(reply_text=human_reply_diff_auditor, halt_reason=exception_reason)
    expect_eq(parsed_da["action"], "different-auditor", "C: different-auditor action parsed")
    expect_eq(parsed_da["action_args"]["model"], "opus", "C: model 'opus' in action_args")

    da_mutations = [m for m in parsed_da["state_mutations"] if m["path"] == "audit_state.preferred_model_override"]
    expect(len(da_mutations) == 1, "C: 1 preferred_model_override mutation")

    updated_plan_da = apply_halt_action(
        plan=plan,
        action=parsed_da["action"],
        action_args=parsed_da["action_args"],
        exception_state={"phase": "drafted", "cause": exception_reason},
    )
    expect_eq(
        updated_plan_da["audit_state"]["preferred_model_override"],
        "opus",
        "C: preferred_model_override set to opus",
    )
    expect_eq(
        updated_plan_da["audit_state"]["sufficiency_iterations"],
        0,
        "C: sufficiency_iterations reset to 0 after different-auditor",
    )

    print("\n  Example C: DONE")


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------

def test_edge_cases():
    """Additional edge-case tests for parser robustness."""
    print("\n--- Edge cases ---")

    # Audit parser: help reply
    result = parse_audit_reply("?", {}, {"findings": [], "summary": {}}, None)
    expect_eq(result["action"], "help", "Edge: audit '?' returns help")
    expect("usage_text" in result["action_args"], "Edge: help returns usage_text")

    # Audit parser: ambiguous reply
    result = parse_audit_reply("maybe fix it?", {}, {"findings": [], "summary": {}}, None)
    expect_eq(result["action"], "ambiguous", "Edge: unrecognised verb returns ambiguous")
    expect(result["reprompt_text"] is not None, "Edge: ambiguous has reprompt_text")

    # Audit parser: ack on non-existent ID
    audit_result = {
        "findings": [{"code": "S104", "level": "error", "fingerprint": "abc123", "location": "step 1", "message": "test"}],
        "summary": {"error_count": 1, "warning_count": 0, "note_count": 0},
    }
    result = parse_audit_reply("ack W9", {}, audit_result, None)
    expect_eq(result["action"], "ambiguous", "Edge: ack on non-existent ID returns ambiguous")

    # Audit parser: attempt to ack an error
    audit_result_w = {
        "findings": [{"code": "S104", "level": "error", "fingerprint": "abc123", "location": "step 1", "message": "test"}],
        "summary": {"error_count": 1, "warning_count": 0, "note_count": 0},
    }
    result = parse_audit_reply("ack E1", {}, audit_result_w, None)
    expect_eq(result["action"], "ambiguous", "Edge: ack on error returns ambiguous (errors cannot be acked)")

    # Outcome parser: help reply
    result = parse_outcome_reply("help", {}, [])
    expect_eq(result["action"], "help", "Edge: outcome 'help' returns help")

    # Outcome parser: ack-failure without rationale
    failures = [{"id": "F1", "type": "verify:", "command": "test", "exit_code": 1}]
    result = parse_outcome_reply("ack-failure F1", {}, failures)
    expect_eq(result["action"], "ambiguous", "Edge: ack-failure without rationale returns ambiguous")

    # Outcome parser: ack-failure on non-existent ID
    result = parse_outcome_reply("ack-failure F99: reason", {}, failures)
    expect_eq(result["action"], "ambiguous", "Edge: ack-failure on non-existent ID returns ambiguous")

    # Halt parser: help reply
    result = parse_halt_reply("?", "test cause")
    expect_eq(result["action"], "help", "Edge: halt '?' returns help")

    # Halt parser: abandon
    result = parse_halt_reply("7 abandon: not worth it", "test cause")
    expect_eq(result["action"], "abandon", "Edge: abandon action parsed")
    expect_eq(result["action_args"]["rationale"], "not worth it", "Edge: abandon rationale captured")
    status_mutations = [m for m in result["state_mutations"] if m["path"] == "status"]
    expect(len(status_mutations) == 1, "Edge: abandon sets status")
    expect_eq(status_mutations[0]["value"], "cancelled", "Edge: abandon sets status to cancelled")

    # Halt parser: different-auditor invalid model
    result = parse_halt_reply("5 different-auditor gpt4", "test cause")
    expect_eq(result["action"], "ambiguous", "Edge: different-auditor with invalid model returns ambiguous")

    # Halt parser: retry
    result = parse_halt_reply("retry", "test cause")
    expect_eq(result["action"], "retry", "Edge: retry action (named alias) parsed")
    expect_eq(result["state_mutations"], [], "Edge: retry has no mutations")

    print("\n  Edge cases: DONE")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("test_prompts_and_parsing.py")
    print("Three worked examples + edge cases from the severity-surface ADVICE")
    print("=" * 60)

    test_example_a()
    test_example_b()
    test_example_c()
    test_edge_cases()

    print("\n" + "=" * 60)
    if _failures:
        print(f"FAILED: {len(_failures)} assertion(s):")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
