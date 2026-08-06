"""
render_prompts.py - Prompt renderers for the three severity-classified human surfaces.

Surfaces:
  1. render_audit_surface     - audit-revision loop (drafted phase, branch 4B)
  2. render_outcome_surface   - outcome-verifying phase (branch 4C/4E)
  3. render_halt_surface      - kanban-halt exception path (any phase)

All three return markdown strings intended for display to the human.
Output is scannable (<=30 lines for typical cases per ADVICE spec).

Design origin: the severity-classified human-surface note, 2026-05-13.
"""

from __future__ import annotations

import textwrap
from typing import Literal


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int = 80) -> str:
    """Truncate a string to max_len characters, appending '...' if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Verification tier routing helpers (verify: orchestrator support)
# ---------------------------------------------------------------------------

def build_orchestrator_attestation(
    item: str,
    verdict: str,
    evidence: str,
    verifier: str,
) -> dict:
    """
    Build a single orchestrator attestation record with the four required fields.

    This is the canonical record shape for verification_state.orchestrator_attestations.
    The verifier field MUST NOT name the plan-executor - the executor-never-self-certifies
    invariant requires the verifier to be the orchestrator or a non-executor agent.

    Args:
        item:     The verification prose being attested (e.g. the verify: orchestrator prose).
        verdict:  "pass" or "fail".
        evidence: Concrete evidence string - command output, enumerated match set,
                  line-by-line check result, etc.
        verifier: Agent identity that performed the check.  Never "plan-executor".
    """
    return {
        "item": item,
        "verdict": verdict,
        "evidence": evidence,
        "verifier": verifier,
    }


def classify_verification_items(items: list[dict]) -> dict:
    """
    Route parsed verification items into their processing buckets.

    This is the canonical routing contract for the three-tier verification vocabulary.
    Routing rules:
      - annotation == "verify: orchestrator"  -> orchestrator_items bucket
          (NEVER added to human_pending; handled by non-executor agent)
      - annotation == "verify: human"          -> human_items bucket
          (surfaced via attestation-then-assent when checkable, else raw human_pending)
      - annotation == "verify:" or "acceptance:" -> shell_items bucket
          (run via Bash by orchestrator; tallied as pass/fail)

    Args:
        items: List of dicts, each with:
            "annotation": str  - one of "verify:", "acceptance:", "verify: orchestrator",
                                  "verify: human"
            "prose": str       - the prose description or shell command

    Returns:
        {
            "shell_items":        list of {"annotation": str, "prose": str}
            "orchestrator_items": list of {"annotation": str, "prose": str}
            "human_items":        list of {"annotation": str, "prose": str}
        }
    """
    shell_items = []
    orchestrator_items = []
    human_items = []

    for item in items:
        annotation = item.get("annotation", "")
        if annotation == "verify: orchestrator":
            orchestrator_items.append(item)
        elif annotation == "verify: human":
            human_items.append(item)
        else:
            # "verify:" and "acceptance:" - shell-runnable
            shell_items.append(item)

    return {
        "shell_items": shell_items,
        "orchestrator_items": orchestrator_items,
        "human_items": human_items,
    }


def _level_sigil(level: str) -> str:
    """Return the display sigil for a finding level."""
    return {"error": "!!", "warning": "! ", "note": "* "}.get(level, "??")


def _assign_display_ids(findings: list[dict]) -> dict[str, str]:
    """
    Assign per-prompt human-friendly IDs (E1, E2, W1, W2, N1, ...) to findings.
    Returns a dict mapping display_id -> fingerprint.
    """
    id_to_fp: dict[str, str] = {}
    counters: dict[str, int] = {"error": 0, "warning": 0, "note": 0}
    prefix: dict[str, str] = {"error": "E", "warning": "W", "note": "N"}

    for finding in findings:
        level = finding.get("level", "note")
        if level not in counters:
            level = "note"
        counters[level] += 1
        display_id = f"{prefix[level]}{counters[level]}"
        fp = finding.get("fingerprint", "")
        id_to_fp[display_id] = fp

    return id_to_fp


def _render_finding_row(
    display_id: str,
    finding: dict,
    recurring_fingerprints: list[str],
    recurring_counts: dict[str, int] | None = None,
) -> str:
    """Render a single finding as a compact row string."""
    level = finding.get("level", "note")
    sigil = _level_sigil(level)
    code = finding.get("code", "???")
    location = finding.get("location", "global")
    message = _truncate(finding.get("message", "(no message)"), 80)
    fp = finding.get("fingerprint", "")

    stuck_badge = ""
    if fp in recurring_fingerprints:
        count = (recurring_counts or {}).get(fp, 2)
        stuck_badge = f" [STUCK x{count}]"

    return f"  {display_id} [{sigil}] {code} @ {location}: {message}{stuck_badge}"


# ---------------------------------------------------------------------------
# Surface 1: Audit revision loop
# ---------------------------------------------------------------------------

def render_audit_surface(
    plan: dict,
    auditor: Literal["sufficiency", "plan_safety"],
    iteration: int,
    max_iterations: int,
    audit_result_json: dict,
    prior_audit_json: dict | None,
    recurring_fingerprints: list[str],
) -> str:
    """
    Returns the full prompt text for the audit-revision surface.

    Args:
        plan: Parsed PLAN frontmatter + body dict.
        auditor: "sufficiency" or "plan_safety".
        iteration: Current audit iteration number (1-based).
        max_iterations: Maximum allowed iterations (typically 5).
        audit_result_json: v2 audit payload dict (findings, summary).
        prior_audit_json: Prior iteration's audit payload, or None on iteration 1.
        recurring_fingerprints: Fingerprints that recurred from prior iteration.
            Computed by orchestrator (fingerprint comparison across iterations).
    """
    auditor_label = "sufficiency-auditor" if auditor == "sufficiency" else "plan-safety-auditor"
    findings: list[dict] = audit_result_json.get("findings", [])
    summary: dict = audit_result_json.get("summary", {})

    error_count: int = summary.get("error_count", 0)
    warning_count: int = summary.get("warning_count", 0)
    note_count: int = summary.get("note_count", 0)

    errors = [f for f in findings if f.get("level") == "error"]
    warnings = [f for f in findings if f.get("level") == "warning"]
    notes = [f for f in findings if f.get("level") == "note"]

    # Assign display IDs across all findings in severity order
    all_findings_ordered = errors + warnings + notes
    id_to_fp = _assign_display_ids(all_findings_ordered)
    # Build reverse map for rendering
    fp_to_id: dict[str, str] = {v: k for k, v in id_to_fp.items()}

    # Compute recurring counts from prior audit if available
    recurring_counts: dict[str, int] = {}
    if prior_audit_json and recurring_fingerprints:
        # We count 2 for "recurred once" (appeared in both prior and current)
        for fp in recurring_fingerprints:
            recurring_counts[fp] = 2

    # Recurrence banner
    stuck_count = len(recurring_fingerprints)
    recurrence_banner = ""
    if stuck_count > 0:
        recurrence_banner = (
            f"NOTE: {stuck_count} finding(s) have recurred across 2+ iterations.\n"
            "Consider: extract the disputed step into a child PLAN, override with rationale,\n"
            "or request a different auditor model. Reply 'stuck' for guided triage.\n"
        )

    def render_section(section_findings: list[dict], label: str) -> str:
        if not section_findings:
            return ""
        lines = [f"{label}:"]
        for f in section_findings:
            fp = f.get("fingerprint", "")
            display_id = fp_to_id.get(fp, "?")
            lines.append(
                _render_finding_row(display_id, f, recurring_fingerprints, recurring_counts)
            )
        return "\n".join(lines) + "\n"

    error_section = render_section(
        errors, "ERRORS (MUST fix before this PLAN can advance)"
    )
    warning_section = render_section(
        warnings, "WARNINGS (SHOULD fix; you may acknowledge to carry forward)"
    )
    note_section = render_section(
        notes, "NOTES (FYI; no action required, listed for transparency)"
    )

    # Build sections list, omitting empty ones
    body_parts = []
    if error_section:
        body_parts.append(error_section)
    if warning_section:
        body_parts.append(warning_section)
    if note_section:
        body_parts.append(note_section)
    body = "\n".join(body_parts)

    def _plural(n: int, singular: str, plural: str) -> str:
        return f"{n} {singular if n == 1 else plural}"

    prompt = (
        f"Audit iteration {iteration}: {auditor_label} returned revision_needed.\n"
        "\n"
        f"Summary: {_plural(error_count, 'error', 'errors')} * "
        f"{_plural(warning_count, 'warning', 'warnings')} * "
        f"{_plural(note_count, 'note', 'notes')}\n"
    )
    if recurrence_banner:
        prompt += recurrence_banner
    prompt += "\n"
    prompt += body
    prompt += textwrap.dedent("""
        Reply with one or more of:
          fix              -> I'll revise the PLAN. Re-invoke me to re-audit.
          ack W1,W3        -> acknowledge warnings (carry forward, no fix)
          dispute E2: <reason>   -> dispute a finding (auditor reconsiders next iteration)
          override E1: <reason>  -> override (bypass; recorded with rationale)
          details <ID>     -> show full message + suggested_fix for a single finding
          stuck            -> show guided triage for recurring findings
          ?                -> show this help again

        If you reply 'fix', revise the PLAN file, then re-invoke me.
    """)

    return prompt.strip()


# ---------------------------------------------------------------------------
# Surface 2: Outcome verification
# ---------------------------------------------------------------------------

def render_outcome_surface(
    plan: dict,
    verification_state: dict,
    executor_notes: str,
    shell_passes: list[dict],
    shell_failures: list[dict],
    human_items: list[dict],
    executor_heartbeat: dict | None = None,
) -> str:
    """
    Returns the outcome-verifying prompt.

    Args:
        plan: Parsed PLAN frontmatter + body dict.
        verification_state: Current verification_state dict from PLAN frontmatter.
        executor_notes: Executor notes string from last_executor_outcome.
        shell_passes: List of passed shell checks, each {"type": "verify"|"acceptance", "command": str}.
        shell_failures: List of failed checks, each {"id": "F1", "type": str, "command": str, "exit_code": int}.
        human_items: List of human-judgement items, each {"id": "H1", "prose": str}.
        executor_heartbeat: Optional heartbeat metadata dict; None if not available.
            If provided, may include {"step": int, "step_summary": str, "duration_minutes": float}.
            None-safe: if None, the heartbeat context line is omitted entirely.
    """
    plan_filename = plan.get("_filename", plan.get("title", "PLAN"))

    state_pass = verification_state.get("state_pass", len(shell_passes))
    acceptance_pass = verification_state.get("acceptance_pass", 0)

    verify_pass_count = sum(1 for p in shell_passes if p.get("type") == "verify")
    acceptance_pass_count = sum(1 for p in shell_passes if p.get("type") == "acceptance")

    header = f"Outcome verification for {plan_filename}:\n"
    passed_line = (
        f"\nPASSED (auto-checked):\n"
        f"  {verify_pass_count} verify: commands  *  {acceptance_pass_count} acceptance: commands\n"
    )

    # Failed section
    failed_section = ""
    if shell_failures:
        failed_lines = ["", "FAILED (shell - need attention):"]
        for failure in shell_failures:
            fid = failure.get("id", "F?")
            ftype = failure.get("type", "verify:")
            cmd = failure.get("command", "")
            exit_code = failure.get("exit_code", 1)
            failed_lines.append(
                f"  {fid} [{ftype}]     `{cmd}`   exit {exit_code}"
            )
        failed_section = "\n".join(failed_lines) + "\n"

    # Human-judgement section
    # Each item: {"id": str, "prose": str} plus optional evidence/before/after fields.
    # When evidence/before/after are present (present-with-content rule), they are exploded
    # inline beneath the item's prose so the operator sees the actual content, not a reading
    # assignment. Backwards-compatible: items without these fields render exactly as before.
    human_section = ""
    if human_items:
        human_lines = ["", "HUMAN-JUDGEMENT items (you must eyeball):"]
        for item in human_items:
            hid = item.get("id", "H?")
            prose = item.get("prose", "")
            evidence = item.get("evidence", "")
            before = item.get("before", "")
            after = item.get("after", "")
            human_lines.append(f"  {hid} {prose}")
            if evidence:
                human_lines.append(f"      Evidence:")
                for line in evidence.splitlines():
                    human_lines.append(f"        {line}")
            if before:
                human_lines.append(f"      Before:")
                for line in before.splitlines():
                    human_lines.append(f"        {line}")
            if after:
                human_lines.append(f"      After:")
                for line in after.splitlines():
                    human_lines.append(f"        {line}")
            if evidence or before or after:
                human_lines.append(
                    f"      Reply: accept-attestation {hid} | veto {hid}: <reason> | dig-into {hid}"
                )
        human_section = "\n".join(human_lines) + "\n"

    # Heartbeat context line - only if executor_heartbeat is not None
    heartbeat_line = ""
    if executor_heartbeat is not None:
        step = executor_heartbeat.get("step")
        step_summary = executor_heartbeat.get("step_summary", "")
        duration = executor_heartbeat.get("duration_minutes")
        if step is not None and duration is not None:
            heartbeat_line = (
                f"\nNote: executor ran {duration:.0f} minutes on step {step}"
                + (f" ('{step_summary}')" if step_summary else "")
                + "; verification is load-bearing here.\n"
            )

    # Reply legend
    legend = textwrap.dedent("""
        Reply with one or more of:
          pass                       -> all good; mark verdict as all_pass and retire
          fail: <reason>             -> reject; revert to drafted with diagnostics
          ack-failure F1: <reason>   -> accept this shell failure as non-blocking (records rationale)
          ack-human H1               -> accept this human-judgement item as passed
          reject-human H1: <reason>  -> reject this human-judgement item
          details F1 | H1            -> show full command output / item prose
          ?                          -> show this help again
    """)

    prompt = header + passed_line + failed_section + human_section + heartbeat_line + legend

    return prompt.strip()


# ---------------------------------------------------------------------------
# Surface 3: Kanban halt
# ---------------------------------------------------------------------------

def render_halt_surface(
    plan: dict,
    exception_reason: str,
    diagnostics: dict,
    orchestrator_state: dict,
    executor_heartbeat: dict | None = None,
) -> str:
    """
    Returns the kanban-halt prompt with recovery options.

    Args:
        plan: Parsed PLAN frontmatter + body dict.
        exception_reason: One-line cause summary string.
        diagnostics: Diagnostics dict with keys like "phase", "subagent", "iteration",
            "stage", "last_successful_commit", "wip_commit", "diagnostics_path",
            and optionally "details" (list of strings or single string).
        orchestrator_state: Current orchestrator state dict with "pipeline_phase" etc.
        executor_heartbeat: Optional heartbeat metadata dict; None-safe - if None,
            no heartbeat context is included in diagnostics.
    """
    plan_filename = plan.get("_filename", plan.get("title", "PLAN"))
    phase = diagnostics.get("phase", orchestrator_state.get("pipeline_phase", "unknown"))
    subagent = diagnostics.get("subagent", "orchestrator")
    iteration = diagnostics.get("iteration", "n/a")
    stage = diagnostics.get("stage", "n/a")
    last_commit = diagnostics.get("last_successful_commit", "(none)")
    wip_commit = diagnostics.get("wip_commit", "(none)")
    diagnostics_path = diagnostics.get("diagnostics_path", "Workbench/.audit/")

    # Build diagnostics block
    details = diagnostics.get("details", [])
    if isinstance(details, str):
        detail_lines = details.strip().splitlines()
    else:
        detail_lines = list(details)

    # Include heartbeat in diagnostics if present
    if executor_heartbeat is not None:
        step = executor_heartbeat.get("step")
        step_summary = executor_heartbeat.get("step_summary", "")
        duration = executor_heartbeat.get("duration_minutes")
        if step is not None:
            hb_line = f"Executor heartbeat: halted at step {step}"
            if step_summary:
                hb_line += f" ('{step_summary}')"
            if duration is not None:
                hb_line += f" after {duration:.0f} min"
            detail_lines.append(hb_line)

    # Truncate diagnostics to 15 lines
    truncated = False
    if len(detail_lines) > 15:
        detail_lines = detail_lines[:15]
        truncated = True

    diag_block = ""
    if detail_lines:
        diag_block = "\n".join(f"  {line}" for line in detail_lines)
        if truncated:
            diag_block += f"\n  ...full diagnostics in {diagnostics_path}"
    else:
        diag_block = "  (no additional diagnostics)"

    iter_display = f"{iteration} ({stage})" if stage != "n/a" else "n/a"

    prompt = (
        f"PIPELINE HALTED at phase: {phase} on {plan_filename}\n"
        "\n"
        f"Cause: {exception_reason}\n"
        f"Where: {phase} / {subagent}\n"
        f"Iteration: {iter_display}\n"
        "\n"
        "Diagnostics:\n"
        f"{diag_block}\n"
        "\n"
        f"Last successful commit: {last_commit}\n"
        f"WIP commit: {wip_commit}\n"
        "\n"
        "Suggested actions (in order of usual usefulness):\n"
        f"  1) inspect {diagnostics_path}   -> view full diagnostics file\n"
        "  2) retry                          -> re-invoke the failing dispatch as-is\n"
        "  3) override: <reason>             -> bypass this failure; resume next phase\n"
        "  4) reset-stage                    -> reset this phase's iteration counter to 0; retry from scratch\n"
        "  5) different-auditor <m>          -> swap auditor model (sonnet/opus); reset counter; retry\n"
        "  6) dispute: <reason>              -> tag this halt as a false-positive; halt remains but is annotated\n"
        "  7) abandon: <reason>              -> mark this PLAN as cancelled; close the thread\n"
        "\n"
        "Reply with the option number + any required slot, or '?' for help."
    )

    return prompt
