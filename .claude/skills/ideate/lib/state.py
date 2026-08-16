"""
state.py - State management helpers for the ideate cadence pipeline.

Provides read/write operations for ideate_phase frontmatter fields,
critique JSON storage, phase transition validation, and utility functions
for the eight-phase ideate cadence (Gate A onward).

Phases 1-3 are conversational and leave no disk state. This module
is only active from Gate A onward (fires before Phase 4 / Spec-Draft).
Gate A is the first phase to write a non-empty `ideate_phase` value;
Phase 4 (Spec-Draft) remains the first phase to write substantive
PLAN content (Steps, Verification sections).

Reference: .claude/skills/ideate/references/phase-transitions.md
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Valid ideate_phase values
IDEATE_PHASES = {
    "clarify",
    "survey",
    "converge",
    "risk_assess_idea",
    "risk_assess_idea_blocked",
    "spec_draft",
    "risk_assess_spec",
    "risk_assess_spec_blocked",
    "self_critique",
    "spec_refine",
    "cross_spec_reconcile",
    "consolidate",
    "complete",
    "exited_early",
}

# Terminal phases - no transitions allowed out of these
TERMINAL_PHASES = {"complete", "exited_early"}

# pipeline_phase values that indicate an in-flight (non-terminal) PLAN
IN_FLIGHT_PIPELINE_PHASES = {
    "drafting",
    "drafted",
    "checked",
    "executing",
    "outcome-verifying",
}

# Max self_critique iterations before halt
MAX_SELF_CRITIQUE_ITERATIONS = 5

# Max autonomous Gate B revision attempts before surfacing to human
MAX_RISK_ASSESS_SPEC_REVISIONS = 1

# Routing table: current_phase -> set of valid next phases
# Derived from references/phase-transitions.md
VALID_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"risk_assess_idea", "exited_early"},   # Gate A mandatory; direct spec_draft removed
    "": {"risk_assess_idea", "exited_early"},      # Gate A mandatory; direct spec_draft removed
    "clarify": {"survey", "spec_draft", "exited_early"},
    "survey": {"converge", "clarify", "spec_draft", "exited_early"},
    "converge": {"spec_draft", "exited_early"},   # dead code - live source is always None/"" at Converge close
    "risk_assess_idea": {
        "spec_draft",               # clean pass
        "risk_assess_idea_blocked", # show-stopper detected
        "exited_early",
    },
    "risk_assess_idea_blocked": {
        "risk_assess_idea",         # human resolves, re-trigger Gate A
        "exited_early",
    },
    "spec_draft": {"risk_assess_spec", "exited_early"},   # Gate B mandatory; direct self_critique removed
    "risk_assess_spec": {
        "self_critique",            # clean pass
        "risk_assess_spec_blocked", # show-stopper after attempt spent
        "exited_early",
        # Note: no self-loop - Gate B retry is within one risk_assess_spec occupancy (per D7)
    },
    "risk_assess_spec_blocked": {
        "risk_assess_spec",         # human resolves, re-trigger Gate B
        "exited_early",
    },
    "self_critique": {
        "spec_refine",
        "consolidate",  # zero-findings or discard_all short-circuit
        "self_critique",  # additional iteration (loop)
        "exited_early",
    },
    "spec_refine": {
        "cross_spec_reconcile",
        "self_critique",  # back-loop: more critique requested
        "consolidate",  # early-exit "ship it"
        "exited_early",
    },
    "cross_spec_reconcile": {
        "consolidate",
        "spec_refine",  # conflict requires PLAN edit
        "exited_early",
    },
    "consolidate": {"complete"},
    "complete": set(),       # terminal
    "exited_early": set(),   # terminal
}


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

def _read_file(plan_path: Path) -> str:
    """Read plan file text. Raises FileNotFoundError if absent."""
    return plan_path.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[str, str, str]:
    """
    Split a markdown file into (pre_fence, frontmatter_text, body).
    Returns ("---", fm_text, body) or ("", "", full_text) if no frontmatter.
    """
    if not text.startswith("---"):
        return ("", "", text)
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ("", "", text)
    return ("---", parts[1], parts[2])


def _parse_top_level_field(fm_text: str, field: str) -> str | None:
    """
    Parse a single top-level scalar YAML field from frontmatter text.
    Returns the string value or None if absent.
    """
    pattern = re.compile(rf"^{re.escape(field)}:\s*(.*)$", re.MULTILINE)
    m = pattern.search(fm_text)
    if not m:
        return None
    value = m.group(1).strip().strip('"').strip("'")
    if " #" in value:
        value = value[:value.index(" #")].strip()
    return value if value not in ("null", "~", "") else ""


def _parse_nested_int(fm_text: str, parent: str, child: str) -> int:
    """Parse an integer from a nested YAML block field."""
    block_pattern = re.compile(
        rf"^{re.escape(parent)}:.*?\n((?:[ \t]+[^\n]+\n?)*)",
        re.MULTILINE,
    )
    block_m = block_pattern.search(fm_text)
    if not block_m:
        return 0
    block = block_m.group(1)
    sub_pattern = re.compile(rf"^\s+{re.escape(child)}:\s*(\d+)", re.MULTILINE)
    sub_m = sub_pattern.search(block)
    if sub_m:
        return int(sub_m.group(1))
    return 0


def _set_top_level_field(fm_text: str, field: str, value: str) -> str:
    """
    Set a top-level scalar YAML field in frontmatter text.
    If the field exists, replaces its value. If absent, appends it.
    """
    pattern = re.compile(rf"^({re.escape(field)}:).*$", re.MULTILINE)
    replacement = f"{field}: {value}"
    if pattern.search(fm_text):
        return pattern.sub(replacement, fm_text)
    else:
        return fm_text.rstrip("\n") + f"\n{field}: {value}\n"


def _set_nested_int(fm_text: str, parent: str, child: str, new_value: int) -> str:
    """
    Set a nested integer field in a YAML block.
    E.g. parent=ideate_iteration_count, child=self_critique, new_value=2
    """
    block_pattern = re.compile(
        rf"(^{re.escape(parent)}:.*?\n)((?:[ \t]+[^\n]+\n?)*)",
        re.MULTILINE,
    )
    block_m = block_pattern.search(fm_text)
    if not block_m:
        return fm_text

    block_header = block_m.group(1)
    block_body = block_m.group(2)

    sub_pattern = re.compile(rf"(^\s+{re.escape(child)}:)\s*\d+", re.MULTILINE)
    if sub_pattern.search(block_body):
        new_block_body = sub_pattern.sub(
            rf"\g<1> {new_value}", block_body
        )
    else:
        # Append the sub-key if absent
        new_block_body = block_body.rstrip("\n") + f"\n  {child}: {new_value}\n"

    start, end = block_m.span()
    return fm_text[:start] + block_header + new_block_body + fm_text[end:]


def _append_to_list_field(fm_text: str, field: str, value: str) -> str:
    """
    Append a string value to a YAML list field (inline format).
    If the field is an empty list `[]`, convert to single-element.
    If already has items, add to the end.
    """
    # Match inline list pattern: field: [] or field: [item1, item2]
    inline_pattern = re.compile(
        rf"^({re.escape(field)}:\s*)\[([^\]]*)\]",
        re.MULTILINE,
    )
    m = inline_pattern.search(fm_text)
    if m:
        existing = m.group(2).strip()
        if existing:
            new_list = f"[{existing}, {value}]"
        else:
            new_list = f"[{value}]"
        return fm_text[:m.start()] + f"{m.group(1)}{new_list}" + fm_text[m.end():]
    return fm_text


def _write_file(plan_path: Path, fm_text: str, pre: str, body: str) -> None:
    """Reconstruct and write the markdown file from components."""
    if pre:
        content = f"---{fm_text}---{body}"
    else:
        content = body
    plan_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_ideate_state(plan_path: Path) -> dict:
    """
    Read the ideate-related frontmatter fields from a PLAN file.

    Returns a dict with keys:
      ideate_phase: str (empty if absent)
      ideate_critique_addressed: list[str]
      ideate_iteration_count: dict with self_critique: int, spec_refine: int
      ideate_reconcile_outcome: str
    """
    text = _read_file(plan_path)
    _, fm_text, _ = _split_frontmatter(text)

    phase = _parse_top_level_field(fm_text, "ideate_phase") or ""
    reconcile_outcome = _parse_top_level_field(fm_text, "ideate_reconcile_outcome") or ""

    # Parse ideate_critique_addressed (inline list)
    addressed: list[str] = []
    inline_pattern = re.compile(
        r"^ideate_critique_addressed:\s*\[([^\]]*)\]",
        re.MULTILINE,
    )
    m = inline_pattern.search(fm_text)
    if m:
        content = m.group(1).strip()
        if content:
            addressed = [i.strip().strip('"').strip("'") for i in content.split(",") if i.strip()]

    # Parse iteration counts
    sc_count = _parse_nested_int(fm_text, "ideate_iteration_count", "self_critique")
    sr_count = _parse_nested_int(fm_text, "ideate_iteration_count", "spec_refine")
    rai_count = _parse_nested_int(fm_text, "ideate_iteration_count", "risk_assess_idea")
    ras_count = _parse_nested_int(fm_text, "ideate_iteration_count", "risk_assess_spec")

    return {
        "ideate_phase": phase,
        "ideate_critique_addressed": addressed,
        "ideate_iteration_count": {
            "self_critique": sc_count,
            "spec_refine": sr_count,
            "risk_assess_idea": rai_count,
            "risk_assess_spec": ras_count,
        },
        "ideate_reconcile_outcome": reconcile_outcome,
    }


def advance_phase(plan_path: Path, current: str, next_phase: str) -> None:
    """
    Validate the phase transition and write updated ideate_phase to PLAN frontmatter.
    Also increments relevant counters and writes ideate_phase.

    Raises ValueError if the transition is not in the routing table.
    Raises ValueError if current == 'self_critique' and counter == MAX.
    """
    current_norm = current or ""
    valid_nexts = VALID_TRANSITIONS.get(current_norm, set())

    if next_phase not in valid_nexts:
        raise ValueError(
            f"Invalid transition: {current_norm!r} -> {next_phase!r}. "
            f"Valid transitions from {current_norm!r}: {sorted(valid_nexts)}"
        )

    text = _read_file(plan_path)
    pre, fm_text, body = _split_frontmatter(text)
    if not pre:
        raise ValueError(f"No frontmatter found in {plan_path}")

    # Check iteration bound for self_critique loops
    if next_phase == "self_critique" and current_norm == "self_critique":
        current_count = _parse_nested_int(fm_text, "ideate_iteration_count", "self_critique")
        if current_count >= MAX_SELF_CRITIQUE_ITERATIONS:
            raise ValueError(
                f"self_critique iteration bound exceeded ({current_count}/{MAX_SELF_CRITIQUE_ITERATIONS}). "
                "Surface as exception - human must take explicit action (ship / exit / override)."
            )

    # Update ideate_phase
    fm_text = _set_top_level_field(fm_text, "ideate_phase", next_phase)

    # Increment counters based on destination phase (and source where needed)
    if next_phase == "self_critique":
        current_count = _parse_nested_int(fm_text, "ideate_iteration_count", "self_critique")
        fm_text = _set_nested_int(fm_text, "ideate_iteration_count", "self_critique", current_count + 1)
    elif next_phase == "spec_refine":
        current_count = _parse_nested_int(fm_text, "ideate_iteration_count", "spec_refine")
        fm_text = _set_nested_int(fm_text, "ideate_iteration_count", "spec_refine", current_count + 1)
    elif next_phase == "risk_assess_idea" and current_norm == "risk_assess_idea_blocked":
        # Human-initiated re-run: increment counter ONLY on the back-edge, not first entry
        current_count = _parse_nested_int(fm_text, "ideate_iteration_count", "risk_assess_idea")
        fm_text = _set_nested_int(fm_text, "ideate_iteration_count", "risk_assess_idea", current_count + 1)
    elif next_phase == "complete":
        # Terminal: also flip pipeline_phase to drafted
        fm_text = _set_top_level_field(fm_text, "pipeline_phase", "drafted")

    _write_file(plan_path, fm_text, pre, body)


def set_ideate_iteration_count(plan_path: Path, key: str, value: int) -> None:
    """
    Write a single `ideate_iteration_count.<key>` value to PLAN frontmatter.

    This is the only public write path for counter-only updates - i.e., when no
    `ideate_phase` transition is needed. Gate B's risk-assess-spec.md calls this
    after an autonomous revision attempt to persist the attempt count before
    re-running the gate:
        set_ideate_iteration_count(plan_path, 'risk_assess_spec', 1)

    Args:
        plan_path: Path to the PLAN file.
        key: Sub-key under `ideate_iteration_count` (e.g. 'risk_assess_spec').
        value: Integer value to set.
    """
    text = _read_file(plan_path)
    pre, fm_text, body = _split_frontmatter(text)
    if not pre:
        raise ValueError(f"No frontmatter found in {plan_path}")

    fm_text = _set_nested_int(fm_text, "ideate_iteration_count", key, value)
    _write_file(plan_path, fm_text, pre, body)


def write_critique(
    plan_path: Path,
    iteration: int,
    findings: list[dict],
    summary: dict,
) -> Path:
    """
    Write a critique JSON to Workbench/.ideate-critique/<plan-id>-<iter>.json.

    Args:
        plan_path: Path to the PLAN file (used to derive plan-id and workbench dir).
        iteration: 1-based iteration number.
        findings: List of finding dicts per critique-schema.md.
        summary: Summary dict with major_count, minor_count, discarded_count.

    Returns:
        Path to the written critique JSON file.
    """
    plan_id = plan_path.stem
    workbench_dir = plan_path.parent
    critique_dir = workbench_dir / ".ideate-critique"
    critique_dir.mkdir(parents=True, exist_ok=True)

    iter_str = f"{iteration:02d}"
    critique_filename = f"{plan_id}-{iter_str}.json"
    critique_path = critique_dir / critique_filename

    critique_data = {
        "schema_version": 1,
        "phase": "self_critique",
        "iteration": iteration,
        "plan_path": str(plan_path),
        "findings": findings,
        "summary": summary,
    }

    with open(critique_path, "w", encoding="utf-8") as f:
        json.dump(critique_data, f, indent=2)

    # Also update ideate_critique_addressed is NOT done here -
    # that happens in advance_phase when moving to spec_refine.
    # write_critique is pure I/O for the JSON file.

    return critique_path


def read_latest_critique(plan_path: Path) -> dict | None:
    """
    Find and return the most recent critique JSON for this PLAN.

    Returns the parsed dict, or None if no critique files exist.
    """
    plan_id = plan_path.stem
    workbench_dir = plan_path.parent
    critique_dir = workbench_dir / ".ideate-critique"

    if not critique_dir.exists():
        return None

    pattern = re.compile(rf"^{re.escape(plan_id)}-(\d+)\.json$")
    candidates = []
    for f in critique_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            candidates.append((int(m.group(1)), f))

    if not candidates:
        return None

    # Sort descending by iteration, take the latest
    candidates.sort(key=lambda x: x[0], reverse=True)
    latest_path = candidates[0][1]

    try:
        with open(latest_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def compute_fingerprint(
    code: str,
    severity: str,
    category: str,
    location: dict,
) -> str:
    """
    Compute an 8-character SHA-256 fingerprint for a critique finding.

    Formula mirrors the audit fingerprint:
        sha256(code + severity + category + json.dumps(location, sort_keys=True))[:8]

    Note: "severity" maps to "level" in the audit schema.
    In the critique schema, severity is "major" | "minor".
    In render_critique.py, major->error and minor->warning for the wrapped functions.

    Args:
        code: Critique code string, e.g. "C001".
        severity: "major" or "minor".
        category: Category string, e.g. "underspecified".
        location: Location dict, e.g. {"section_id": "Steps", "step_n": 3}.

    Returns:
        8-character lowercase hex string.
    """
    location_str = json.dumps(location, sort_keys=True)
    raw = code + severity + category + location_str
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def estimate_token_budget_percent(context_window: int = 0) -> int:
    """
    Heuristic estimator of context budget consumed.

    Best-effort, not exact. Uses character count of PLAN file reads as a proxy.

    Strategy:
    1. Read IDEATE_CONTEXT_WINDOW env var if set (override).
    2. Otherwise, use the context_window argument if > 0.
    3. Otherwise, default to 1_000_000 (Opus 4.7 / large model default).

    Token estimate: characters_read * 0.286 (characters-per-token ratio, rough).

    Args:
        context_window: Expected context window size in tokens. 0 means use env/default.

    Returns:
        Estimated percentage (0-100+) of context window consumed.
        Returns 0 if no character-count data is available.
    """
    env_window = os.environ.get("IDEATE_CONTEXT_WINDOW", "")
    if env_window:
        try:
            context_window = int(env_window)
        except ValueError:
            pass

    if context_window <= 0:
        context_window = 1_000_000

    # Estimate characters read during the current ideate session.
    # This is a heuristic: sum the sizes of PLAN files we've touched.
    # In practice, callers may pass an explicit char_count argument
    # via a wrapper. Here we provide the formula logic.
    # Without an explicit char count, return 0 (caller should supply it).
    return 0


def estimate_token_budget_percent_from_chars(
    chars_read: int,
    context_window: int = 0,
) -> int:
    """
    Compute token budget percentage from a character count.

    Args:
        chars_read: Total characters of content read in this session.
        context_window: Context window size in tokens. 0 = use env/default.

    Returns:
        Estimated percentage (0-100+) of context window consumed.
    """
    env_window = os.environ.get("IDEATE_CONTEXT_WINDOW", "")
    if env_window:
        try:
            context_window = int(env_window)
        except ValueError:
            pass

    if context_window <= 0:
        context_window = 1_000_000

    tokens_estimated = int(chars_read * 0.286)
    return int((tokens_estimated / context_window) * 100)


def detect_in_flight_plans(workbench_dir: Path, exclude_plan_id: str) -> list[str]:
    """
    Scan Workbench/*.md for PLANs that are actively in-flight (not yet complete or exited).

    In-flight definition (per spec v2, Phase 7 auto-skip detection):
        pipeline_phase ∈ {drafting, drafted, checked, executing, outcome-verifying}
        AND (ideate_phase ∉ {complete, exited_early} OR ideate_phase field absent)

    Args:
        workbench_dir: Path to the Workbench/ directory.
        exclude_plan_id: Plan ID to exclude from results (the current PLAN being ideated).

    Returns:
        List of plan IDs (file stems) that are in-flight.
    """
    in_flight = []
    # Matches legacy timestamp (pre-2026-05-13), active AA-form, and historical-frozen NNN PLAN filenames.
    plan_pattern = re.compile(r"^(?:\d{12}_PLAN_|PLAN-(?:[A-Z]{2}\d|\d{3,4})_)")

    for md_file in sorted(workbench_dir.iterdir()):
        if not md_file.name.endswith(".md"):
            continue
        if not plan_pattern.match(md_file.name):
            continue
        plan_id = md_file.stem
        if plan_id == exclude_plan_id:
            continue

        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        # Quick check: must be a plan type
        if 'type: plan' not in text and "type: plan" not in text:
            continue

        # Parse pipeline_phase (top-level)
        pp_match = re.search(r"^pipeline_phase:\s*(.+)$", text, re.MULTILINE)
        if not pp_match:
            continue
        pp = pp_match.group(1).strip().strip('"').strip("'")
        if " #" in pp:
            pp = pp[:pp.index(" #")].strip()

        if pp not in IN_FLIGHT_PIPELINE_PHASES:
            continue

        # Parse ideate_phase (top-level)
        ip_match = re.search(r"^ideate_phase:\s*(.*)$", text, re.MULTILINE)
        ideate_phase = ""
        if ip_match:
            ideate_phase = ip_match.group(1).strip().strip('"').strip("'")
            if " #" in ideate_phase:
                ideate_phase = ideate_phase[:ideate_phase.index(" #")].strip()

        # In-flight: ideate_phase is absent/empty OR not in terminal set
        terminal_ideate = {"complete", "exited_early"}
        if ideate_phase not in terminal_ideate:
            in_flight.append(plan_id)

    return in_flight
