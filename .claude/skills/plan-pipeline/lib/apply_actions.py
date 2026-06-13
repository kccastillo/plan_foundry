"""
apply_actions.py — Frontmatter mutation appliers for the three human surfaces.

Functions:
  apply_audit_action(plan, action, action_args, audit_result_json)
      → mutates PLAN frontmatter (audit_acknowledgements, audit_disputes, audit_overrides)
      → returns updated frontmatter dict

  apply_outcome_action(plan, action, action_args, verification_state)
      → mutates PLAN frontmatter (verification_state.human_acknowledged_failures,
        verification_state.human_passed, pipeline_overrides)
      → returns updated frontmatter dict

  apply_halt_action(plan, action, action_args, exception_state)
      → mutates PLAN frontmatter (halt_log, pipeline_overrides,
        audit_state.preferred_model_override for "different-auditor")
      → returns updated frontmatter dict

All three functions work on a mutable copy of the plan dict and return the updated copy.
The orchestrator applies the returned dict back to the PLAN file's frontmatter.

Reference: Workbench/202605130040_ADVICE_severity-classified-human-surface.md
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    """Return today's date as YYYY-MM-DD."""
    return date.today().isoformat()


def _deep_copy(plan: dict) -> dict:
    """Return a deep copy of the plan dict to avoid mutating the caller's object."""
    return copy.deepcopy(plan)


def _apply_mutations(plan: dict, state_mutations: list[dict]) -> dict:
    """
    Apply a list of state mutations to a plan frontmatter dict.

    Each mutation:
      {"path": "dotted.path", "op": "append"|"set"|"delete", "value": Any}

    Path traversal:
      - "verification_state.human_passed" → plan["verification_state"]["human_passed"]
      - If intermediate keys are absent, they are created as dicts.
      - "delete" op removes the key; other ops set/append.

    Returns the mutated plan dict.
    """
    for mutation in state_mutations:
        path: str = mutation.get("path", "")
        op: str = mutation.get("op", "set")
        value: Any = mutation.get("value")

        if not path:
            continue

        parts = path.split(".")
        # Navigate to the parent container
        container = plan
        for part in parts[:-1]:
            if part not in container or not isinstance(container[part], dict):
                container[part] = {}
            container = container[part]

        leaf = parts[-1]

        if op == "set":
            container[leaf] = value
        elif op == "append":
            if leaf not in container or container[leaf] is None:
                container[leaf] = []
            if isinstance(container[leaf], list):
                container[leaf].append(value)
            else:
                # Scalar → wrap in list
                container[leaf] = [container[leaf], value]
        elif op == "delete":
            container.pop(leaf, None)

    return plan


# ---------------------------------------------------------------------------
# Surface 1: Audit action applier
# ---------------------------------------------------------------------------

def apply_audit_action(
    plan: dict,
    action: str,
    action_args: dict,
    audit_result_json: dict,
) -> dict:
    """
    Apply an audit-surface action to the PLAN frontmatter.

    Mutates:
      - audit_acknowledgements (ack)
      - audit_disputes (dispute)
      - audit_overrides (override)
      - audit_extracted (extract — stuck-triage path)
      - audit_state.preferred_model_override (different-auditor — stuck-triage path)

    Args:
        plan: Parsed PLAN frontmatter dict (will be deep-copied before mutation).
        action: Primary action from parse_audit_reply (e.g. "fix", "ack", "override").
        action_args: Action-specific args dict from parse result.
        audit_result_json: Current audit payload for context (fingerprints, etc.).

    Returns:
        Updated frontmatter dict (mutations applied in-place on the copy).
    """
    plan = _deep_copy(plan)
    today = _today()

    # Initialise lists if absent
    plan.setdefault("audit_acknowledgements", [])
    plan.setdefault("audit_disputes", [])
    plan.setdefault("audit_overrides", [])

    if action in ("fix", "ack", "dispute", "override", "extract", "different-auditor"):
        # Process the sub-actions list
        actions_list = action_args.get("actions", [])
        for act in actions_list:
            sub_action = act.get("action")
            fp = act.get("fingerprint", "")
            rationale = act.get("rationale", "(no rationale)")

            if sub_action in ("fix", None):
                pass  # No mutation for fix — orchestrator awaits PLAN revision

            elif sub_action == "ack":
                if not act.get("suppressed_by_fix"):
                    plan["audit_acknowledgements"].append({
                        "fingerprint": fp,
                        "rationale": rationale,
                        "ack_date": today,
                        "ack_iteration": _current_iteration(plan),
                    })

            elif sub_action == "dispute":
                plan["audit_disputes"].append({
                    "fingerprint": fp,
                    "rationale": rationale,
                    "dispute_date": today,
                    "dispute_iteration": _current_iteration(plan),
                })

            elif sub_action == "override":
                if not act.get("suppressed_by_fix"):
                    plan["audit_overrides"].append({
                        "fingerprint": fp,
                        "rationale": rationale,
                        "override_date": today,
                        "override_iteration": _current_iteration(plan),
                        "scope": "single",
                    })

            elif sub_action == "extract":
                plan.setdefault("audit_extracted", [])
                if isinstance(plan["audit_extracted"], list):
                    plan["audit_extracted"].append({
                        "fingerprint": fp,
                        "did": act.get("did", ""),
                        "extraction_date": today,
                        "child_plan_filename": None,
                    })

        return plan

    # Fallback: apply raw state_mutations if provided
    mutations = action_args.get("state_mutations", [])
    if mutations:
        plan = _apply_mutations(plan, mutations)

    return plan


def _current_iteration(plan: dict) -> int:
    """Extract current iteration count from plan frontmatter."""
    audit_state = plan.get("audit_state", {})
    return max(
        audit_state.get("sufficiency_iterations", 1),
        audit_state.get("plan_safety_iterations", 1),
    )


# ---------------------------------------------------------------------------
# Surface 2: Outcome action applier
# ---------------------------------------------------------------------------

def apply_outcome_action(
    plan: dict,
    action: str,
    action_args: dict,
    verification_state: dict,
) -> dict:
    """
    Apply an outcome-verification-surface action to the PLAN frontmatter.

    Mutates:
      - verification_state.human_acknowledged_failures (ack-failure)
      - verification_state.human_passed (ack-human)
      - verification_state.human_verdict (pass / fail / reject-human)
      - verification_state.human_diagnostics (fail / reject-human)
      - pipeline_overrides (pass with unresolved shell failures → override record)

    Args:
        plan: Parsed PLAN frontmatter dict (will be deep-copied before mutation).
        action: Primary action from parse_outcome_reply.
        action_args: Action-specific args dict from parse result.
        verification_state: Current verification_state dict (used for context checks).

    Returns:
        Updated frontmatter dict.
    """
    plan = _deep_copy(plan)
    today = _today()

    # Ensure verification_state exists in plan
    if "verification_state" not in plan:
        plan["verification_state"] = {}
    vs = plan["verification_state"]
    vs.setdefault("human_acknowledged_failures", [])
    vs.setdefault("human_passed", [])
    vs.setdefault("human_verdict", "pending")
    vs.setdefault("human_diagnostics", "")

    plan.setdefault("pipeline_overrides", [])

    if action in ("pass", "fail", "ack-failure", "ack-human", "details"):
        actions_list = action_args.get("actions", [])
        for act in actions_list:
            sub_action = act.get("action")

            if sub_action == "pass":
                vs["human_verdict"] = "all_pass"
                vs["human_diagnostics"] = ""

            elif sub_action == "fail":
                vs["human_verdict"] = "rejected"
                vs["human_diagnostics"] = act.get("rationale", "(no rationale)")

            elif sub_action == "ack-failure":
                vs["human_acknowledged_failures"].append({
                    "check": act.get("id", ""),
                    "rationale": act.get("rationale", "(no rationale)"),
                    "ack_date": today,
                })

            elif sub_action == "ack-human":
                hid = act.get("id", "")
                if hid not in vs["human_passed"]:
                    vs["human_passed"].append(hid)

            elif sub_action == "reject-human":
                vs["human_verdict"] = "rejected"
                rationale = act.get("rationale", "(no rationale)")
                hid = act.get("id", "")
                existing = vs.get("human_diagnostics", "")
                vs["human_diagnostics"] = (
                    (existing + "; " if existing else "")
                    + f"rejected {hid}: {rationale}"
                )

            elif sub_action == "details":
                pass  # No mutation; orchestrator emits details and re-prompts

        return plan

    # Fallback: apply raw state_mutations if provided
    mutations = action_args.get("state_mutations", [])
    if mutations:
        plan = _apply_mutations(plan, mutations)

    return plan


# ---------------------------------------------------------------------------
# Surface 3: Halt action applier
# ---------------------------------------------------------------------------

def apply_halt_action(
    plan: dict,
    action: str,
    action_args: dict,
    exception_state: dict,
) -> dict:
    """
    Apply a kanban-halt-surface action to the PLAN frontmatter.

    Mutates:
      - halt_log (dispute, abandon, annotate)
      - pipeline_overrides (override)
      - audit_state.preferred_model_override (different-auditor)
      - status (abandon → "cancelled")
      - pipeline_phase (abandon → "complete")
      - audit_extracted (extract)

    Args:
        plan: Parsed PLAN frontmatter dict (will be deep-copied before mutation).
        action: Primary action from parse_halt_reply.
        action_args: Action-specific args dict from parse result.
        exception_state: Orchestrator exception context (phase, cause, etc.).

    Returns:
        Updated frontmatter dict.
    """
    plan = _deep_copy(plan)
    today = _today()

    plan.setdefault("halt_log", [])
    plan.setdefault("pipeline_overrides", [])

    phase = exception_state.get("phase", plan.get("pipeline_phase", "unknown"))
    halt_reason = exception_state.get("cause", action_args.get("halt_reason", "unspecified"))

    if action == "retry":
        # No frontmatter mutation for retry
        return plan

    elif action == "reset-stage":
        # Reset iteration counter for the current audit stage
        audit_state = plan.setdefault("audit_state", {})
        last_stage = audit_state.get("last_stage", "none")
        if last_stage == "sufficiency":
            audit_state["sufficiency_iterations"] = 0
        elif last_stage == "plan_safety":
            audit_state["plan_safety_iterations"] = 0
        else:
            # Reset both as fallback
            audit_state["sufficiency_iterations"] = 0
            audit_state["plan_safety_iterations"] = 0
        return plan

    elif action == "override":
        rationale = action_args.get("rationale", "(no rationale)")
        plan["pipeline_overrides"].append({
            "phase": phase,
            "action": "override",
            "rationale": rationale,
            "override_date": today,
            "halt_reason": halt_reason,
        })
        return plan

    elif action == "different-auditor":
        model = action_args.get("model", "sonnet")
        audit_state = plan.setdefault("audit_state", {})
        audit_state["preferred_model_override"] = model
        # Reset iteration counter
        last_stage = audit_state.get("last_stage", "none")
        if last_stage == "sufficiency":
            audit_state["sufficiency_iterations"] = 0
        elif last_stage == "plan_safety":
            audit_state["plan_safety_iterations"] = 0
        else:
            audit_state["sufficiency_iterations"] = 0
            audit_state["plan_safety_iterations"] = 0
        return plan

    elif action == "dispute":
        rationale = action_args.get("rationale", "(no rationale)")
        plan["halt_log"].append({
            "phase": phase,
            "timestamp": today + "T00:00:00Z",
            "cause": halt_reason,
            "kind": "dispute",
            "rationale": rationale,
        })
        return plan

    elif action == "abandon":
        rationale = action_args.get("rationale", "(no rationale)")
        plan["halt_log"].append({
            "phase": phase,
            "timestamp": today + "T00:00:00Z",
            "cause": halt_reason,
            "kind": "abandon",
            "rationale": rationale,
        })
        plan["status"] = "cancelled"
        plan["pipeline_phase"] = "complete"
        return plan

    elif action == "extract":
        spec = action_args.get("spec", "")
        plan.setdefault("audit_extracted", [])
        if isinstance(plan["audit_extracted"], list):
            plan["audit_extracted"].append({
                "spec": spec,
                "extraction_date": today,
                "child_plan_filename": None,
            })
        elif plan["audit_extracted"] is None:
            plan["audit_extracted"] = [{
                "spec": spec,
                "extraction_date": today,
                "child_plan_filename": None,
            }]
        return plan

    elif action == "inspect":
        # No mutation; orchestrator emits file contents
        return plan

    elif action == "details":
        # No mutation; orchestrator emits details
        return plan

    # Fallback: apply raw state_mutations
    mutations = action_args.get("state_mutations", [])
    if mutations:
        plan = _apply_mutations(plan, mutations)

    return plan
