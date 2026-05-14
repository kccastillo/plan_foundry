"""
render_critique.py — Thin wrappers over the severity-surface library for critique-specific shape.

This module translates between the self-critique schema (severity: major|minor, actions:
address|defer|dispute|discard|discard_all) and the audit-result v2 schema (level:
error|warning|note, actions: fix|ack|dispute|override) expected by the severity-surface
library functions.

Design choice: `auditor="sufficiency"` is passed as the literal value to the wrapped
functions. Rationale: the wrapped function's signature requires one of `sufficiency |
plan_safety`. The "sufficiency" auditor is the semantically closer match for self-critique
because self-critique asks "is this spec sufficient?" — the same question the sufficiency
auditor asks. plan_safety is more mechanical (concrete steps, atomic, unambiguous checks),
whereas self-critique includes design-issue and architectural concerns that are sufficiency-
flavoured. The choice is frozen here in code to make it explicit and easy to override in a
future version.

NO modifications are made to the severity-surface library modules. This module is pure
composition.

Reference:
    plugins/plan-foundry-core/skills/plan-pipeline/lib/render_prompts.py
    plugins/plan-foundry-core/skills/plan-pipeline/lib/parse_replies.py
    plugins/ideate/skills/ideate/references/critique-schema.md
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Library import — severity-surface modules live in plan-foundry-core
# ---------------------------------------------------------------------------

_SEVERITY_SURFACE_LIB = Path(__file__).parent.parent.parent.parent.parent / \
    "plan-foundry-core" / "skills" / "plan-pipeline" / "lib"

if str(_SEVERITY_SURFACE_LIB) not in sys.path:
    sys.path.insert(0, str(_SEVERITY_SURFACE_LIB))

try:
    from render_prompts import render_audit_surface
    from parse_replies import parse_audit_reply
except ImportError as e:
    raise ImportError(
        f"Cannot import severity-surface library from {_SEVERITY_SURFACE_LIB}. "
        "Ensure plan-foundry-core plugin is installed. "
        f"Original error: {e}"
    ) from e


# ---------------------------------------------------------------------------
# Schema translation helpers
# ---------------------------------------------------------------------------

_SEVERITY_TO_LEVEL = {
    "major": "error",
    "minor": "warning",
}

_LEVEL_TO_SEVERITY = {
    "error": "major",
    "warning": "minor",
    "note": "minor",  # notes downgrade to minor (no 'note' severity in critique schema)
}

# Critique action → audit action (for delegation to parse_audit_reply)
_CRITIQUE_TO_AUDIT_ACTION = {
    "address": "fix",
    "defer": "ack",
    "dispute": "dispute",
    "discard": "override",
}

# Audit action → critique action (reverse translation of results)
_AUDIT_TO_CRITIQUE_ACTION = {
    "fix": "address",
    "ack": "defer",
    "dispute": "dispute",
    "override": "discard",
}


def _translate_finding_to_audit(finding: dict) -> dict:
    """
    Translate a critique finding dict to an audit-result finding dict.

    Critique:  {id, code, severity, category, location, issue, suggested_fix, fingerprint}
    Audit v2:  {code, level, category, location, message, suggested_fix, fingerprint}
    """
    severity = finding.get("severity", "minor")
    level = _SEVERITY_TO_LEVEL.get(severity, "warning")

    # Flatten location to a string (audit surface expects a string or simple dict)
    location = finding.get("location", {})
    if isinstance(location, dict):
        section = location.get("section_id", "")
        step_n = location.get("step_n")
        if step_n is not None:
            location_str = f"{section} / Step {step_n}" if section else f"Step {step_n}"
        else:
            location_str = section or "global"
    else:
        location_str = str(location)

    return {
        "code": finding.get("code", "C???"),
        "level": level,
        "category": finding.get("category", "other"),
        "location": location_str,
        "message": finding.get("issue", "(no description)"),
        "suggested_fix": finding.get("suggested_fix", ""),
        "fingerprint": finding.get("fingerprint", ""),
    }


def _translate_summary_to_audit(summary: dict) -> dict:
    """
    Translate a critique summary dict to an audit-result summary dict.

    Critique:  {major_count, minor_count, discarded_count}
    Audit v2:  {error_count, warning_count, note_count}
    """
    return {
        "error_count": summary.get("major_count", 0),
        "warning_count": summary.get("minor_count", 0),
        "note_count": 0,
    }


def _build_audit_result_shape(critique_json: dict) -> dict:
    """
    Convert a critique JSON dict into an audit-result-like shape for the wrapped functions.
    """
    findings = critique_json.get("findings", [])
    summary = critique_json.get("summary", {})

    audit_findings = [_translate_finding_to_audit(f) for f in findings]
    audit_summary = _translate_summary_to_audit(summary)

    return {
        "findings": audit_findings,
        "summary": audit_summary,
    }


def _substitute_audit_labels_with_critique_labels(prompt_text: str) -> str:
    """
    Post-process the rendered audit surface output to replace audit-specific
    labels and action verbs with critique-specific ones.

    Replacements:
      "sufficiency-auditor" → "self-critique"
      "Audit iteration N: sufficiency-auditor returned revision_needed." → reformatted
      "fix" (action verb in menu) → "address"
      "ack" → "defer"
      "override" → "discard"
    Also inserts a "discard_all" action line in the action menu.
    """
    text = prompt_text

    # Replace auditor label
    text = text.replace("sufficiency-auditor", "self-critique")

    # Replace "returned revision_needed" with critique framing
    text = text.replace(
        "returned revision_needed.",
        "returned findings for review.",
    )

    # Replace action menu verbs (careful: only in the action menu lines)
    # The menu lines from render_audit_surface look like:
    #   fix              → I'll revise the PLAN. Re-invoke me to re-audit.
    #   ack W1,W3        → acknowledge warnings (carry forward, no fix)
    #   ...
    text = text.replace(
        "  fix              → I'll revise the PLAN. Re-invoke me to re-audit.",
        "  address          → I'll revise the PLAN to fix this finding.",
    )
    text = text.replace(
        "  ack W1,W3        → acknowledge warnings (carry forward, no fix)",
        "  defer W1,W3      → acknowledge but don't fix this iteration (carry forward)",
    )
    text = text.replace(
        "  override E1: <reason>  → override (bypass; recorded with rationale)",
        "  discard E1: <reason>  → discard this finding (no fix, no carry-forward)",
    )
    text = text.replace(
        "If you reply 'fix', revise the PLAN file, then re-invoke me.",
        "  discard_all      → discard all findings; advance directly to Consolidate.\n\n"
        "If you reply 'address', revise the PLAN and re-invoke me.",
    )

    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_critique_surface(
    plan: dict,
    critique_json: dict,
    prior_critique_json: dict | None,
) -> str:
    """
    Render the human-facing self-critique prompt for Phase 5 (Self-Critique).

    Converts the critique JSON to an audit-result-like shape, delegates to
    render_audit_surface() with auditor="sufficiency" (see module docstring for
    rationale), then applies string substitution to use critique-specific labels
    and action verbs.

    Args:
        plan: Parsed PLAN frontmatter + body dict (passed through to render_audit_surface).
        critique_json: Critique JSON dict per critique-schema.md
            (schema_version, phase, iteration, plan_path, findings, summary).
        prior_critique_json: Prior iteration's critique JSON, or None on iteration 1.
            Used to compute recurring fingerprints (same algorithm as audit recurrence).

    Returns:
        Rendered markdown prompt string for display to the human.
    """
    iteration = critique_json.get("iteration", 1)
    max_iterations = 5  # bounded per phase-transitions.md

    audit_result = _build_audit_result_shape(critique_json)
    prior_audit_result = _build_audit_result_shape(prior_critique_json) if prior_critique_json else None

    # Compute recurring fingerprints (major findings that recur from prior iteration)
    recurring_fingerprints: list[str] = []
    if prior_audit_result:
        prior_fps = {
            f.get("fingerprint", "")
            for f in prior_audit_result.get("findings", [])
            if f.get("level") == "error" and f.get("fingerprint")
        }
        current_fps = {
            f.get("fingerprint", "")
            for f in audit_result.get("findings", [])
            if f.get("level") == "error" and f.get("fingerprint")
        }
        recurring_fingerprints = sorted(prior_fps & current_fps)

    # Delegate to severity-surface library
    # auditor="sufficiency" — see module-level docstring for rationale
    prompt = render_audit_surface(
        plan=plan,
        auditor="sufficiency",
        iteration=iteration,
        max_iterations=max_iterations,
        audit_result_json=audit_result,
        prior_audit_json=prior_audit_result,
        recurring_fingerprints=recurring_fingerprints,
    )

    # Apply critique-specific label substitutions
    prompt = _substitute_audit_labels_with_critique_labels(prompt)

    return prompt


def parse_critique_reply(
    reply_text: str,
    plan_frontmatter: dict,
    critique_json: dict,
    prior_critique_json: dict | None,
) -> dict:
    """
    Parse a human reply to the self-critique surface prompt.

    Handles discard_all as a first-class action (short-circuits before delegation):
    - If reply matches ^discard[_-]all$ (case-insensitive), returns immediately with
      action="discard_all", no state mutations (orchestrator handles the phase advance).

    For all other replies, delegates to parse_audit_reply() after translating
    action verbs to audit equivalents, then translates the result back to
    critique-specific action enum.

    Action translations:
      Human reply "address" → parse_audit_reply sees "fix"
      Human reply "defer"   → parse_audit_reply sees "ack"
      Human reply "dispute" → parse_audit_reply sees "dispute" (unchanged)
      Human reply "discard" → parse_audit_reply sees "override"

    Result action translations (reverse):
      parse_audit_reply "fix"      → returned as "address"
      parse_audit_reply "ack"      → returned as "defer"
      parse_audit_reply "dispute"  → returned as "dispute"
      parse_audit_reply "override" → returned as "discard"

    State mutations target `ideate_critique_addressed` (not `audit_acknowledgements`).
    The "path" field in mutations is rewritten accordingly.

    Args:
        reply_text: Raw human reply string.
        plan_frontmatter: PLAN frontmatter dict (for iteration counts, addressed list, etc.).
        critique_json: Current iteration's critique JSON dict.
        prior_critique_json: Prior iteration's critique JSON, or None.

    Returns:
        Canonical result dict:
          {
            "action": str,               # address|defer|dispute|discard|discard_all|details|stuck|help|ambiguous
            "action_args": dict,
            "state_mutations": list,     # mutations targeting ideate_critique_addressed
            "reprompt_text": str | None
          }
    """
    # --- discard_all short-circuit ---
    import re
    stripped = reply_text.strip()
    if re.match(r"^discard[_\-]all$", stripped, re.IGNORECASE):
        return {
            "action": "discard_all",
            "action_args": {},
            "state_mutations": [],
            "reprompt_text": None,
        }

    # --- Translate critique action verbs to audit action verbs in the reply ---
    translated_reply = _translate_reply_to_audit_verbs(reply_text)

    # --- Build the audit-result shape for delegation ---
    audit_result = _build_audit_result_shape(critique_json)
    prior_audit_result = _build_audit_result_shape(prior_critique_json) if prior_critique_json else None

    # --- Delegate to parse_audit_reply ---
    result = parse_audit_reply(
        reply_text=translated_reply,
        plan_frontmatter=plan_frontmatter,
        audit_result_json=audit_result,
        prior_audit_json=prior_audit_result,
    )

    # --- Translate primary action back to critique vocabulary ---
    primary_action = result.get("action", "ambiguous")
    result["action"] = _AUDIT_TO_CRITIQUE_ACTION.get(primary_action, primary_action)

    # --- Translate action_args["actions"] back ---
    actions_list = result.get("action_args", {}).get("actions", [])
    for act in actions_list:
        act_action = act.get("action", "")
        act["action"] = _AUDIT_TO_CRITIQUE_ACTION.get(act_action, act_action)

    # --- Translate state mutation paths ---
    # Mutations from parse_audit_reply use "audit_acknowledgements", "audit_disputes",
    # "audit_overrides". Translate to critique equivalents.
    path_translations = {
        "audit_acknowledgements": "ideate_critique_addressed",
        "audit_disputes": "ideate_critique_disputes",
        "audit_overrides": "ideate_critique_discarded",
    }
    for mutation in result.get("state_mutations", []):
        old_path = mutation.get("path", "")
        if old_path in path_translations:
            mutation["path"] = path_translations[old_path]

    return result


def _translate_reply_to_audit_verbs(reply_text: str) -> str:
    """
    Translate critique action verbs to audit action verbs in a human reply,
    so it can be parsed by parse_audit_reply() without modification.

    Critique → audit verb mapping:
      address → fix
      defer   → ack
      discard → override
      dispute → dispute (unchanged)

    Applies line-by-line to handle multi-line replies.
    """
    import re
    lines = reply_text.splitlines()
    translated = []
    for line in lines:
        stripped = line.strip().lower()
        # Match verb-first patterns (e.g. "address E1", "defer W2", "discard E1: reason")
        if re.match(r"^address\b", stripped):
            line = re.sub(r"^address\b", "fix", line, flags=re.IGNORECASE)
        elif re.match(r"^defer\b", stripped):
            line = re.sub(r"^defer\b", "ack", line, flags=re.IGNORECASE)
        elif re.match(r"^discard\b", stripped):
            # Translate "discard" but NOT "discard_all" / "discard-all" (those are caught earlier)
            if not re.match(r"^discard[_\-]all\b", stripped):
                line = re.sub(r"^discard\b", "override", line, flags=re.IGNORECASE)
        # "dispute" and "details" pass through unchanged
        translated.append(line)
    return "\n".join(translated)
