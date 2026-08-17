"""
parse_replies.py - Reply parsers for the three severity-classified human surfaces.

All three parsers return the same canonical dict schema:
  {
    "action": str,              # primary action
    "action_args": dict,        # action-specific args
    "state_mutations": list,    # ordered list of frontmatter mutations to apply
    "reprompt_text": str | None # if action == "ambiguous", text to re-prompt with; else None
  }

Each entry in state_mutations:
  {
    "path": str,   # dotted-path into frontmatter (e.g. "audit_acknowledgements")
    "op": str,     # "append" | "set" | "delete"
    "value": Any   # value to append/set; ignored for delete
  }

Design origin: the severity-classified human-surface note, 2026-05-13.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any


# ---------------------------------------------------------------------------
# Shared parsing utilities
# ---------------------------------------------------------------------------

def _today() -> str:
    """Return today's date as YYYY-MM-DD."""
    return date.today().isoformat()


def _split_lines(text: str) -> list[str]:
    """Split reply text into non-empty stripped lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_id_list(s: str) -> list[str]:
    """
    Parse a comma/space-separated list of IDs.
    "W1,W3" or "W1, W3" or "W1 W3" -> ["W1","W3"]
    """
    return [tok.strip().upper() for tok in re.split(r"[,\s]+", s) if tok.strip()]


def _parse_id_colon_rationale(s: str) -> tuple[str, str]:
    """
    Parse "<ID>: <rationale>" or "<ID> <rationale>" (colon optional).
    Returns (id_upper, rationale_str).
    The rationale may be empty if not provided.
    """
    m = re.match(r"^\s*(\S+?)\s*[:\s]\s*(.*)$", s, re.DOTALL)
    if not m:
        return (s.strip().upper(), "")
    return (m.group(1).upper(), m.group(2).strip())


def _is_help(text: str) -> bool:
    """Return True if the reply is a bare help request."""
    return text.strip().lower() in {"?", "help"}


def _make_result(
    action: str,
    action_args: dict | None = None,
    state_mutations: list | None = None,
    reprompt_text: str | None = None,
) -> dict:
    """Construct the canonical return dict."""
    return {
        "action": action,
        "action_args": action_args or {},
        "state_mutations": state_mutations or [],
        "reprompt_text": reprompt_text,
    }


def _ambiguous(reason: str) -> dict:
    """Return an ambiguous-action result with a reprompt message."""
    reprompt = (
        f"Reply not understood: {reason}\n"
        "Please use one of the listed commands exactly, or reply '?' for help."
    )
    return _make_result("ambiguous", reprompt_text=reprompt)


# ---------------------------------------------------------------------------
# Surface 1: Audit reply parser
# ---------------------------------------------------------------------------

def parse_audit_reply(
    reply_text: str,
    plan_frontmatter: dict,
    audit_result_json: dict,
    prior_audit_json: dict | None,
) -> dict:
    """
    Parse a human reply to the audit-revision surface prompt.

    Actions: fix, ack, dispute, override, extract, help, ambiguous.

    The parser maps display IDs (E1, W1, N1) to fingerprints via audit_result_json findings.
    Display IDs are assigned in the same order as render_audit_surface: errors, then warnings,
    then notes; each level numbered starting from 1.

    Args:
        reply_text: Raw human reply string.
        plan_frontmatter: PLAN frontmatter dict (for current iteration, ack list, etc.).
        audit_result_json: v2 audit payload (findings, summary).
        prior_audit_json: Prior iteration's audit payload, or None.

    Returns:
        Canonical result dict with action in {fix, ack, dispute, override, extract,
        details, stuck, help, ambiguous}.
    """
    if _is_help(reply_text):
        usage = (
            "Audit surface commands:\n"
            "  fix              -> revise the PLAN and re-invoke\n"
            "  ack W1,W3        -> acknowledge warnings\n"
            "  dispute E2: <reason>   -> dispute a finding\n"
            "  override E1: <reason>  -> override a finding\n"
            "  details <ID>     -> show full details for a finding\n"
            "  stuck            -> show triage for recurring findings\n"
            "  ?                -> this help"
        )
        return _make_result("help", action_args={"usage_text": usage})

    # Build display-ID -> fingerprint map from audit_result_json
    findings: list[dict] = audit_result_json.get("findings", [])
    errors = [f for f in findings if f.get("level") == "error"]
    warnings = [f for f in findings if f.get("level") == "warning"]
    notes = [f for f in findings if f.get("level") == "note"]

    id_to_fp: dict[str, str] = {}
    id_to_level: dict[str, str] = {}
    id_to_finding: dict[str, dict] = {}

    for i, f in enumerate(errors, 1):
        did = f"E{i}"
        fp = f.get("fingerprint", f"no-fp-{i}")
        id_to_fp[did] = fp
        id_to_level[did] = "error"
        id_to_finding[did] = f

    for i, f in enumerate(warnings, 1):
        did = f"W{i}"
        fp = f.get("fingerprint", f"no-fp-w{i}")
        id_to_fp[did] = fp
        id_to_level[did] = "warning"
        id_to_finding[did] = f

    for i, f in enumerate(notes, 1):
        did = f"N{i}"
        fp = f.get("fingerprint", f"no-fp-n{i}")
        id_to_fp[did] = fp
        id_to_level[did] = "note"
        id_to_finding[did] = f

    valid_ids = set(id_to_fp.keys())

    # Check for "stuck" reply (stuck-triage sub-prompt)
    if reply_text.strip().lower() == "stuck":
        return _make_result("help", action_args={"usage_text": "stuck-triage", "show_stuck": True})

    lines = _split_lines(reply_text)
    if not lines:
        return _ambiguous("empty reply")

    # Track what we collect across all lines
    actions_collected: list[dict] = []
    mutations: list[dict] = []
    today = _today()
    iteration = plan_frontmatter.get("audit_state", {}).get(
        "sufficiency_iterations",
        plan_frontmatter.get("audit_state", {}).get("plan_safety_iterations", 1),
    )

    # Track IDs that have "fix" applied (fix supersedes override on same ID)
    fix_ids: set[str] = set()
    # Track override actions before finalising (to filter out if fix also present)
    pending_overrides: list[tuple[str, str, dict]] = []  # (did, rationale, mutation)

    # Track if we saw "fix" anywhere
    has_fix = False

    for line in lines:
        cmd, _, rest = line.partition(" ")
        cmd_lower = cmd.lower()

        if cmd_lower == "fix":
            has_fix = True
            actions_collected.append({"action": "fix"})

        elif cmd_lower == "ack":
            ids = _parse_id_list(rest)
            if not ids:
                return _ambiguous("ack requires at least one ID, e.g. 'ack W1'")
            for did in ids:
                did = did.upper()
                if did not in valid_ids:
                    return _ambiguous(
                        f"ID {did} not in this iteration. Valid IDs: {sorted(valid_ids)}"
                    )
                if id_to_level.get(did) == "error":
                    return _ambiguous(
                        f"Errors cannot be acknowledged - use 'override {did}: <reason>' or 'fix'."
                    )
                fp = id_to_fp[did]
                # Check if optional rationale included: "ack W1: reason"
                rationale = "(no rationale)"
                if ":" in rest:
                    # Could be "W1: reason" or "W1,W2: combined reason"
                    id_part, _, rat_part = rest.partition(":")
                    if len(_parse_id_list(id_part)) == 1:
                        rationale = rat_part.strip() or "(no rationale)"

                actions_collected.append({"action": "ack", "fingerprint": fp, "did": did})
                mutations.append({
                    "path": "audit_acknowledgements",
                    "op": "append",
                    "value": {
                        "fingerprint": fp,
                        "rationale": rationale,
                        "ack_date": today,
                        "ack_iteration": iteration,
                    },
                })

        elif cmd_lower == "dispute":
            if not rest.strip():
                return _ambiguous("dispute requires an ID and rationale, e.g. 'dispute E2: reason'")
            did, rationale = _parse_id_colon_rationale(rest)
            if did not in valid_ids:
                return _ambiguous(
                    f"ID {did} not in this iteration. Valid IDs: {sorted(valid_ids)}"
                )
            if not rationale:
                return _ambiguous(
                    f"dispute requires rationale: 'dispute {did}: <reason>'"
                )
            fp = id_to_fp[did]
            actions_collected.append({"action": "dispute", "fingerprint": fp, "did": did})
            mutations.append({
                "path": "audit_disputes",
                "op": "append",
                "value": {
                    "fingerprint": fp,
                    "rationale": rationale,
                    "dispute_date": today,
                    "dispute_iteration": iteration,
                },
            })

        elif cmd_lower == "override":
            if not rest.strip():
                return _ambiguous("override requires an ID and rationale, e.g. 'override E1: reason'")
            did, rationale = _parse_id_colon_rationale(rest)
            if did not in valid_ids:
                return _ambiguous(
                    f"ID {did} not in this iteration. Valid IDs: {sorted(valid_ids)}"
                )
            if not rationale:
                return _ambiguous(
                    f"override requires rationale: 'override {did}: <reason>'"
                )
            fp = id_to_fp[did]
            mutation = {
                "path": "audit_overrides",
                "op": "append",
                "value": {
                    "fingerprint": fp,
                    "rationale": rationale,
                    "override_date": today,
                    "override_iteration": iteration,
                    "scope": "single",
                },
            }
            pending_overrides.append((did, rationale, mutation))
            actions_collected.append({"action": "override", "fingerprint": fp, "did": did})

        elif cmd_lower == "extract":
            # Stuck-triage path: extract <ID> (create child PLAN for this step)
            did = rest.strip().upper()
            fp = id_to_fp.get(did, "")
            actions_collected.append({"action": "extract", "fingerprint": fp, "did": did})
            mutations.append({
                "path": "audit_extracted",
                "op": "append",
                "value": {
                    "fingerprint": fp,
                    "did": did,
                    "extraction_date": today,
                    "child_plan_filename": None,  # orchestrator fills this in
                },
            })

        elif cmd_lower == "details":
            did = rest.strip().upper()
            fp = id_to_fp.get(did, "")
            finding = id_to_finding.get(did, {})
            actions_collected.append({
                "action": "details",
                "fingerprint": fp,
                "did": did,
                "message": finding.get("message", ""),
                "suggested_fix": finding.get("suggested_fix", ""),
            })

        else:
            return _ambiguous(
                f"unrecognised command: '{cmd_lower}'. Reply '?' for help."
            )

    if not actions_collected:
        return _ambiguous("empty reply")

    # Apply fix-supersedes-override rule:
    # If "fix" is present AND the same ID has an override action, drop the override.
    if has_fix:
        suppressed_overrides: list[str] = []
        final_mutations: list[dict] = []
        for m in mutations:
            # Check if this is an override mutation that should be suppressed
            is_suppressed = False
            if m["path"] == "audit_overrides" and m["op"] == "append":
                # All overrides are suppressed when fix is present
                # (per ADVICE: "fix wins for that ID")
                is_suppressed = True
                suppressed_overrides.append(m["value"].get("fingerprint", ""))
            if not is_suppressed:
                final_mutations.append(m)
        mutations = final_mutations

        if suppressed_overrides:
            # Surface a note in action_args
            for act in actions_collected:
                if act.get("action") == "override":
                    act["suppressed_by_fix"] = True

    # Determine primary action (first non-details action, or "fix" if present)
    primary_action = "fix" if has_fix else (actions_collected[0]["action"] if actions_collected else "ambiguous")

    return _make_result(
        action=primary_action,
        action_args={"actions": actions_collected},
        state_mutations=mutations,
        reprompt_text=None,
    )


# ---------------------------------------------------------------------------
# Surface 2: Outcome reply parser
# ---------------------------------------------------------------------------

def parse_outcome_reply(
    reply_text: str,
    verification_state: dict,
    shell_failures: list[dict],
) -> dict:
    """
    Parse a human reply to the outcome-verification surface prompt.

    Actions: ack-failure, dispute, pass, fail, details, help, ambiguous.

    Args:
        reply_text: Raw human reply string.
        verification_state: Current verification_state dict from PLAN frontmatter.
        shell_failures: List of shell failures from verification run.
            Each entry: {"id": "F1", "type": "verify:|acceptance:", "command": str, "exit_code": int}.

    Returns:
        Canonical result dict.
    """
    if _is_help(reply_text):
        usage = (
            "Outcome verification commands:\n"
            "  pass                       -> mark verdict as all_pass and retire\n"
            "  fail: <reason>             -> reject; revert to drafted\n"
            "  ack-failure F1: <reason>   -> accept this shell failure as non-blocking\n"
            "  ack-human H1               -> accept this human-judgement item as passed\n"
            "  reject-human H1: <reason>  -> reject this human-judgement item\n"
            "  details F1 | H1            -> show full output / item prose\n"
            "  ?                          -> this help"
        )
        return _make_result("help", action_args={"usage_text": usage})

    # Build ID maps
    failure_ids: set[str] = {f.get("id", "") for f in shell_failures}
    id_to_check: dict[str, str] = {f.get("id", ""): f.get("command", "") for f in shell_failures}

    human_pending: list[str | dict] = verification_state.get("human_pending", [])
    # human_pending items may be strings or dicts; normalise to dict with id and prose
    human_items_map: dict[str, str] = {}
    for i, item in enumerate(human_pending, 1):
        if isinstance(item, dict):
            hid = item.get("id", f"H{i}")
            prose = item.get("prose", str(item))
        else:
            hid = f"H{i}"
            prose = str(item)
        human_items_map[hid] = prose

    lines = _split_lines(reply_text)
    if not lines:
        return _ambiguous("empty reply")

    actions_collected: list[dict] = []
    mutations: list[dict] = []
    today = _today()
    primary_action: str | None = None

    for line in lines:
        cmd, _, rest = line.partition(" ")
        cmd_lower = cmd.lower()

        if cmd_lower == "pass":
            actions_collected.append({"action": "pass"})
            mutations.append({
                "path": "verification_state.human_verdict",
                "op": "set",
                "value": "all_pass",
            })
            mutations.append({
                "path": "verification_state.human_diagnostics",
                "op": "set",
                "value": "",
            })
            if primary_action is None:
                primary_action = "pass"

        elif cmd_lower == "fail":
            # "fail: reason" or "fail reason"
            rationale = rest.lstrip(":").strip() or "(no rationale)"
            actions_collected.append({"action": "fail", "rationale": rationale})
            mutations.append({
                "path": "verification_state.human_verdict",
                "op": "set",
                "value": "rejected",
            })
            mutations.append({
                "path": "verification_state.human_diagnostics",
                "op": "set",
                "value": rationale,
            })
            if primary_action is None:
                primary_action = "fail"

        elif cmd_lower == "ack-failure":
            if not rest.strip():
                return _ambiguous("ack-failure requires an ID and rationale, e.g. 'ack-failure F1: reason'")
            fid, rationale = _parse_id_colon_rationale(rest)
            if fid not in failure_ids:
                return _ambiguous(
                    f"{fid} not a failed item. Valid failure IDs: {sorted(failure_ids)}"
                )
            if not rationale:
                return _ambiguous(
                    f"ack-failure requires rationale: 'ack-failure {fid}: <reason>'"
                )
            check = id_to_check.get(fid, fid)
            actions_collected.append({"action": "ack-failure", "id": fid, "rationale": rationale})
            mutations.append({
                "path": "verification_state.human_acknowledged_failures",
                "op": "append",
                "value": {
                    "check": check,
                    "failure_id": fid,
                    "rationale": rationale,
                    "ack_date": today,
                },
            })
            if primary_action is None:
                primary_action = "ack-failure"

        elif cmd_lower == "ack-human":
            hid = rest.strip().upper()
            if hid not in human_items_map:
                return _ambiguous(
                    f"{hid} not a pending human-judgement item. Valid IDs: {sorted(human_items_map.keys())}"
                )
            item = human_items_map[hid]
            actions_collected.append({"action": "ack-human", "id": hid, "item": item})
            mutations.append({
                "path": "verification_state.human_passed",
                "op": "append",
                "value": hid,
            })
            if primary_action is None:
                primary_action = "ack-human"

        elif cmd_lower == "reject-human":
            hid, rationale = _parse_id_colon_rationale(rest)
            hid = hid.upper()
            if hid not in human_items_map:
                return _ambiguous(
                    f"{hid} not a pending human-judgement item. Valid IDs: {sorted(human_items_map.keys())}"
                )
            item = human_items_map[hid]
            actions_collected.append({
                "action": "reject-human",
                "id": hid,
                "item": item,
                "rationale": rationale or "(no rationale)",
            })
            mutations.append({
                "path": "verification_state.human_verdict",
                "op": "set",
                "value": "rejected",
            })
            mutations.append({
                "path": "verification_state.human_diagnostics",
                "op": "set",
                "value": f"Human rejected item {hid}: {rationale or '(no rationale)'}",
            })
            if primary_action is None:
                primary_action = "fail"

        elif cmd_lower == "details":
            fid = rest.strip().upper()
            actions_collected.append({"action": "details", "id": fid})
            if primary_action is None:
                primary_action = "details"

        else:
            return _ambiguous(
                f"unrecognised command: '{cmd_lower}'. Reply '?' for help."
            )

    if not actions_collected:
        return _ambiguous("empty reply")

    return _make_result(
        action=primary_action or actions_collected[0]["action"],
        action_args={"actions": actions_collected},
        state_mutations=mutations,
        reprompt_text=None,
    )


# ---------------------------------------------------------------------------
# Surface 3: Halt reply parser
# ---------------------------------------------------------------------------

def parse_halt_reply(
    reply_text: str,
    halt_reason: str,
) -> dict:
    """
    Parse a human reply to the kanban-halt surface prompt.

    Actions: override, extract, dispute, different-auditor, manual, help, ambiguous.
    Also handles: retry, reset-stage, abandon, inspect.

    Args:
        reply_text: Raw human reply string.
        halt_reason: The exception reason string (for context in mutations).

    Returns:
        Canonical result dict.
    """
    if _is_help(reply_text):
        usage = (
            "Kanban-halt commands:\n"
            "  1) inspect <path>        -> view full diagnostics file\n"
            "  2) retry                 -> re-invoke the failing dispatch as-is\n"
            "  3) override: <reason>    -> bypass this failure; resume next phase\n"
            "  4) reset-stage           -> reset this phase's iteration counter to 0; retry\n"
            "  5) different-auditor <m> -> swap auditor model (haiku/sonnet/opus)\n"
            "  6) dispute: <reason>     -> annotate halt; remains halted\n"
            "  7) abandon: <reason>     -> cancel this PLAN\n"
            "  ?                        -> this help"
        )
        return _make_result("help", action_args={"usage_text": usage})

    today = _today()
    text = reply_text.strip()

    # First token is the option number or named alias
    head, _, tail = text.partition(" ")
    head_lower = head.lower()

    # When head is a digit, tail may start with the named alias (e.g. "7 abandon: reason")
    # Strip the named alias prefix from tail if present so parsers only see the slot.
    _named_aliases = {
        "1": "inspect",
        "2": "retry",
        "3": "override",
        "4": "reset-stage",
        "5": "different-auditor",
        "6": "dispute",
        "7": "abandon",
    }
    if head_lower in _named_aliases:
        alias = _named_aliases[head_lower]
        tail_stripped = tail.strip()
        # If tail starts with the alias (case-insensitive), remove it
        if tail_stripped.lower().startswith(alias):
            tail = tail_stripped[len(alias):].lstrip(": ").strip()

    if head_lower in ("1", "inspect"):
        path = tail.strip() or "(see diagnostics)"
        return _make_result(
            "inspect",
            action_args={"path": path},
        )

    elif head_lower in ("2", "retry"):
        return _make_result("retry")

    elif head_lower in ("3", "override"):
        rationale = tail.lstrip(":").strip()
        if not rationale:
            return _ambiguous("override requires rationale, e.g. '3 override: <reason>'")
        mutations = [
            {
                "path": "pipeline_overrides",
                "op": "append",
                "value": {
                    "phase": "halt",
                    "action": "override",
                    "rationale": rationale,
                    "override_date": today,
                    "halt_reason": halt_reason,
                },
            }
        ]
        return _make_result(
            "override",
            action_args={"rationale": rationale},
            state_mutations=mutations,
        )

    elif head_lower in ("4", "reset-stage"):
        return _make_result(
            "reset-stage",
            action_args={"halt_reason": halt_reason},
        )

    elif head_lower in ("5", "different-auditor"):
        # When head is "5", tail may be "different-auditor opus" or just "opus"
        # When head is "different-auditor", tail is the model
        if head_lower == "5":
            # tail might be "opus" or "different-auditor opus"
            parts = tail.strip().lower().split()
            if parts and parts[0] == "different-auditor":
                model = parts[1] if len(parts) > 1 else ""
            elif parts:
                model = parts[0]
            else:
                model = ""
        else:
            model = tail.strip().lower()
        if model not in {"haiku", "sonnet", "opus"}:
            return _ambiguous(
                f"model must be haiku, sonnet, or opus; got '{model!r}'"
            )
        mutations = [
            {
                "path": "audit_state.preferred_model_override",
                "op": "set",
                "value": model,
            }
        ]
        return _make_result(
            "different-auditor",
            action_args={"model": model},
            state_mutations=mutations,
        )

    elif head_lower in ("6", "dispute"):
        rationale = tail.lstrip(":").strip() or "(no rationale)"
        mutations = [
            {
                "path": "halt_log",
                "op": "append",
                "value": {
                    "phase": "halt",
                    "timestamp": today + "T00:00:00Z",
                    "cause": halt_reason,
                    "kind": "dispute",
                    "rationale": rationale,
                },
            }
        ]
        return _make_result(
            "dispute",
            action_args={"rationale": rationale},
            state_mutations=mutations,
        )

    elif head_lower in ("7", "abandon"):
        rationale = tail.lstrip(":").strip() or "(no rationale)"
        mutations = [
            {
                "path": "halt_log",
                "op": "append",
                "value": {
                    "phase": "halt",
                    "timestamp": today + "T00:00:00Z",
                    "cause": halt_reason,
                    "kind": "abandon",
                    "rationale": rationale,
                },
            },
            {
                "path": "status",
                "op": "set",
                "value": "cancelled",
            },
            {
                "path": "pipeline_phase",
                "op": "set",
                "value": "complete",
            },
        ]
        return _make_result(
            "abandon",
            action_args={"rationale": rationale},
            state_mutations=mutations,
        )

    # Handle "extract" as a named alias (from stuck-triage sub-prompt)
    elif head_lower == "extract":
        # "extract step 1 to child PLAN" style
        return _make_result(
            "extract",
            action_args={"spec": tail.strip()},
            state_mutations=[
                {
                    "path": "audit_extracted",
                    "op": "set",
                    "value": {
                        "spec": tail.strip(),
                        "extraction_date": today,
                        "child_plan_filename": None,
                    },
                }
            ],
        )

    else:
        return _ambiguous(
            f"unrecognised option: '{head_lower}'. Reply with option number 1-7 or '?'."
        )
