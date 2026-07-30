"""
build_index.py - Regenerate Workbench/INDEX.md and Workbench/.index.json.

Pure projection from PLAN frontmatter + .audit/ files. Deterministic. No LLM in generation path.

Usage:
    python build_index.py [workbench_dir]

    workbench_dir defaults to "Workbench" relative to the current working directory.

Writes:
    <workbench_dir>/INDEX.md
    <workbench_dir>/.index.json

Exit 0 on success, non-zero on error.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
GENERATED_BY = "build_index.py v1"

# Alert thresholds (hardcoded in v1; configurability tracked for future dev)
THRESHOLD_LONG_BLOCKED_DAYS = 7
THRESHOLD_VERIFICATION_PENDING_HOURS = 24
THRESHOLD_STUCK_AUDIT_ITERATIONS = 3
THRESHOLD_EXECUTOR_HUNG_SECONDS = 600  # 10 minutes
THRESHOLD_STUCK_IDEATION_HOURS = 24   # stuck_ideation: ideate_phase non-terminal for > 24h

# Status columns for kanban (includes virtual "ideating" column)
KANBAN_PHASES = [
    "drafting",
    "drafted",
    "checked",
    "executing",
    "outcome-verifying",
    "complete",
]

# ideate_phase values that are non-terminal (PLAN still being ideated)
IDEATE_NON_TERMINAL_PHASES = {
    "clarify",
    "survey",
    "converge",
    "spec_draft",
    "self_critique",
    "spec_refine",
    "cross_spec_reconcile",
    "consolidate",
}

# ideate_phase values that are terminal (ideate complete or exited)
IDEATE_TERMINAL_PHASES = {"complete", "exited_early"}

TERMINAL_STATUSES = {"done", "cancelled", "partially-complete", "closed"}

# Files to skip in Workbench/
SKIP_FILENAMES = {"INDEX.md", ".gitkeep"}

# PLAN file pattern - supports legacy timestamp-prefix (pre-2026-05-13), new
# numeric sequential (PLAN-NNN_, 3-4 digits), AA-form sequential (PLAN-AA0-ZZ9),
# and numeric ADVICE/RESEARCH. AA-form support added by PLAN-AA1 (R2 fix).
PLAN_PATTERN = re.compile(r"^(?:\d{12}_(?:PLAN|ADVICE|RESEARCH)_|(?:PLAN-(?:\d{3,4}|[A-Z]{2}[0-9])|(?:ADVICE|RESEARCH)-\d{3,4})_)")


# ---------------------------------------------------------------------------
# Canonical plan-id helpers (deliberately synced copy of audit_loop._extract_plan_id
# and build_brief._short_plan_id - D1 Single-Owner per PLAN-AF0).
# These three copies (audit_loop, build_brief, build_index) are kept in sync by
# convention; if the id scheme changes, update all three together.
# ---------------------------------------------------------------------------

def _canonical_plan_id(stem: str) -> str:
    """
    Derive the canonical short plan-id from a PLAN file stem.

    If the stem matches the AA-form PLAN-XX# prefix (e.g. "PLAN-AA4_slug"),
    return just the short id ("PLAN-AA4"). Otherwise return the stem unchanged
    (legacy timestamp PLANs and any non-AA id keep their full stem, matching
    the audit_loop / build_brief fallback convention).

    Mirrors audit_loop.PLAN_ID_RE and build_brief._short_plan_id (PLAN-AE10).
    """
    m = re.match(r"(PLAN-[A-Z]{2}\d)_", stem)
    return m.group(1) if m else stem


def _bare_plan_id(s: str) -> str:
    """
    Reduce any of {a full file stem, a path, a bare id} to its leading
    PLAN-XX# (AA-form) or PLAN-NNN (legacy numeric) token.

    Examples:
        "PLAN-AF6_turn-a-batch-slug" -> "PLAN-AF6"
        "PLAN-AF6"                   -> "PLAN-AF6"
        "Workbench/PLAN-AF6_foo.md"  -> "PLAN-AF6"
        "PLAN-123_some-plan"         -> "PLAN-123"
        ""                           -> ""
    """
    if not s:
        return ""
    # Strip path separators and .md extension to get a bare stem
    stem = Path(s).stem if ("/" in s or "\\" in s or s.endswith(".md")) else s
    # Also strip .md from a bare filename like "PLAN-AF6_foo.md"
    if stem.endswith(".md"):
        stem = stem[:-3]
    m = re.match(r"(PLAN-(?:[A-Z]{2}\d|\d{3,4}))", stem)
    return m.group(1) if m else s


def _audit_file_plan_id(name: str) -> str | None:
    """
    Return the canonical plan-id an audit file belongs to, or None if the
    filename is not a PLAN audit file.

    Accepts all current and legacy audit filename shapes:
      - PLAN-AA4-sufficiency-1.json        -> "PLAN-AA4"   (short-id + stage)
      - PLAN-AA4-plan_safety-1.json        -> "PLAN-AA4"   (short-id + stage)
      - PLAN-AA4-1.json                    -> "PLAN-AA4"   (short-id, no stage)
      - PLAN-AA4_slug-plan-safety-2.json   -> "PLAN-AA4"   (full-stem + legacy stage)
      - PLAN-AB9_slug-1.json               -> "PLAN-AB9_slug"  (legacy full-stem)
      - audit-findings-aecbc8c.json        -> None   (not a PLAN audit file)
      - recovery-inventory-7e4cb36.json    -> None   (not a PLAN audit file)

    The trailing "-<digits>.json" requirement is what excludes non-audit files
    (audit-findings-*.json, recovery-*.json, release-dryrun-evidence.md).

    Implementation: matches the base (pre-iter) portion against the AA-form
    short-id regex first; if it matches, the short id is returned directly
    (robust to any stage token shape). If not, legacy stage tokens are stripped
    from the full stem before returning.
    """
    # Must end in -<digits>.json
    m = re.match(r"^(?P<rest>.+)-(?P<iter>\d+)\.json$", name)
    if not m:
        return None

    rest = m.group("rest")

    # If rest starts with an AA-form PLAN id, return just that short id.
    # This handles all stage-suffix variants without needing to parse the stage.
    m2 = re.match(r"(PLAN-[A-Z]{2}\d)", rest)
    if m2:
        return m2.group(1)

    # Legacy full-stem shape (e.g. PLAN-AB9_log-vs-index-rationalisation).
    # Strip any trailing legacy stage token to recover the original stem.
    for stage_token in ("-sufficiency", "-plan_safety", "-plan-safety"):
        if rest.endswith(stage_token):
            return rest[: -len(stage_token)]

    return rest


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict:
    """
    Parse YAML frontmatter from a markdown file.
    Returns a flat dict of top-level key-value pairs.
    Handles simple scalar values, quoted strings, and boolean-like values.
    Does NOT parse nested blocks (audit_state, verification_state) as dicts -
    those are accessed via string presence checks.
    """
    if not text.startswith("---"):
        return {}

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    fm_text = parts[1].strip()
    fm = {"_raw": fm_text}

    for line in fm_text.splitlines():
        # Skip blank lines, comments, and indented lines (nested blocks)
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line.startswith(" ") or line.startswith("\t"):
            continue
        if ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Remove inline comments
        if " #" in value:
            value = value[:value.index(" #")].strip()

        # Strip quotes
        value = value.strip('"').strip("'")

        # Parse boolean-like
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        elif value.lower() in ("null", "~", ""):
            value = None

        fm[key] = value

    return fm


def _parse_list_field(fm_raw: str, field_name: str) -> list:
    """
    Parse a simple YAML list field (e.g. triggers_plans: [...] or multi-line).
    Returns a list of strings.
    """
    # Match inline list: field_name: [item1, item2]
    inline = re.search(
        rf"^{re.escape(field_name)}:\s*\[([^\]]*)\]",
        fm_raw,
        re.MULTILINE,
    )
    if inline:
        content = inline.group(1).strip()
        if not content:
            return []
        items = [i.strip().strip('"').strip("'") for i in content.split(",")]
        return [i for i in items if i]

    # Match block list:
    # field_name:
    #   - item1
    #   - item2
    block = re.search(
        rf"^{re.escape(field_name)}:\s*\n((?:[ \t]+-[^\n]*\n?)+)",
        fm_raw,
        re.MULTILINE,
    )
    if block:
        lines = block.group(1).splitlines()
        items = []
        for line in lines:
            m = re.match(r"^\s+-\s+(.*)", line)
            if m:
                items.append(m.group(1).strip().strip('"').strip("'"))
        return items

    return []


def _parse_nested_field(fm_raw: str, field_name: str, sub_key: str) -> str:
    """
    Parse a value from a nested YAML block.
    E.g. audit_state:\n  last_audit_commit: abc1234
    Returns the string value or "" if not found.
    """
    pattern = re.compile(
        rf"^{re.escape(field_name)}:.*?\n((?:[ \t]+[^\n]+\n?)*)",
        re.MULTILINE,
    )
    block_match = pattern.search(fm_raw)
    if not block_match:
        return ""

    block_text = block_match.group(1)
    sub_pattern = re.compile(rf"^\s+{re.escape(sub_key)}:\s*(.+)", re.MULTILINE)
    sub_match = sub_pattern.search(block_text)
    if sub_match:
        val = sub_match.group(1).strip().strip('"').strip("'")
        # Remove inline comment
        if " #" in val:
            val = val[:val.index(" #")].strip()
        return val
    return ""


def _parse_int_field(fm_raw: str, field_name: str, sub_key: str) -> int:
    """Parse an integer from a nested YAML field."""
    val = _parse_nested_field(fm_raw, field_name, sub_key)
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# PLAN loading
# ---------------------------------------------------------------------------

def load_plan(plan_path: Path) -> dict | None:
    """
    Load and parse a PLAN file. Returns a plan dict or None if malformed/skipped.
    """
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm = _parse_frontmatter(text)
    if not fm or fm.get("type") != "plan":
        return None

    fm_raw = fm.get("_raw", "")
    plan_id = plan_path.stem

    return {
        "plan_id": plan_id,
        "path": str(plan_path),
        "title": fm.get("title", "(no title)"),
        "status": fm.get("status", "ready"),
        "assigned_to": fm.get("assigned_to", ""),
        "priority": fm.get("priority", "medium"),
        "pipeline_phase": fm.get("pipeline_phase", ""),
        "schema_version": fm.get("schema_version"),
        "created": fm.get("created", ""),
        "due": fm.get("due", ""),
        "blocked_by": fm.get("blocked_by", ""),
        "closes_thread": fm.get("closes_thread", ""),
        "advances_thread": fm.get("advances_thread", ""),
        "parent_plan_of_plans": fm.get("parent_plan_of_plans", ""),
        "parent": fm.get("parent", ""),
        "repeatable": fm.get("repeatable", False),
        "triggers_plans": _parse_list_field(fm_raw, "triggers_plans"),
        "linked_inputs": _parse_list_field(fm_raw, "linked_inputs"),
        "tags": _parse_list_field(fm_raw, "tags"),
        "files_touched": _parse_list_field(fm_raw, "files_touched"),
        # ideate cadence fields
        "ideate_phase": fm.get("ideate_phase", "") or "",
        # audit_state sub-fields
        "audit_sufficiency_iterations": _parse_int_field(fm_raw, "audit_state", "sufficiency_iterations"),
        "audit_plan_safety_iterations": _parse_int_field(fm_raw, "audit_state", "plan_safety_iterations"),
        "audit_last_stage": _parse_nested_field(fm_raw, "audit_state", "last_stage") or "none",
        "audit_last_outcome": _parse_nested_field(fm_raw, "audit_state", "last_outcome") or "none",
        "audit_last_commit": _parse_nested_field(fm_raw, "audit_state", "last_audit_commit") or "",
        # verification_state
        "human_verdict": _parse_nested_field(fm_raw, "verification_state", "human_verdict") or "pending",
        # raw text (for body extraction)
        "_text": text,
    }


# ---------------------------------------------------------------------------
# Audit file loading
# ---------------------------------------------------------------------------

def load_audit_history(workbench_dir: Path, plan_id: str) -> list:
    """
    Load all audit JSON files for a PLAN from Workbench/.audit/.

    D3 - Per-Stage-Recurrence (PLAN-AF0): stage-aware and short-id-aware.
    Derives the canonical short-id from plan_id so the pattern matches both
    the current short-id naming (PLAN-AA4-sufficiency-1.json, post-AE10) and
    legacy full-stem naming. Tags each loaded dict with _stage (str, may be "")
    and _iteration (int). Returns sorted by (stage, iteration) so recurring_blockers
    can compare consecutive entries within the same audit ladder without
    interleaving sufficiency and plan_safety iterations.
    """
    audit_dir = workbench_dir / ".audit"
    if not audit_dir.exists():
        return []

    # Canonicalise: match on short-id for AA-form PLANs; full stem otherwise.
    canonical = _canonical_plan_id(plan_id)
    # Match: <canonical>[-<stage>]-<iter>.json
    # Stage is optional (some audit files omit it; legacy files pre-date stage segments).
    pattern = re.compile(
        rf"^{re.escape(canonical)}"
        r"(?:-(?P<stage>sufficiency|plan_safety|plan-safety))?-(?P<iter>\d+)\.json$"
    )

    results = []
    for audit_file in sorted(audit_dir.iterdir()):
        m = pattern.match(audit_file.name)
        if not m:
            continue
        try:
            with open(audit_file, encoding="utf-8") as f:
                data = json.load(f)
            data["_iteration"] = int(m.group("iter"))
            data["_stage"] = m.group("stage") or ""
            data["_file"] = str(audit_file)
            results.append(data)
        except (json.JSONDecodeError, OSError):
            pass

    return sorted(results, key=lambda x: (x.get("_stage", ""), x.get("_iteration", 0)))


# ---------------------------------------------------------------------------
# Alert detection
# ---------------------------------------------------------------------------

def load_heartbeat(heartbeat_path: Path) -> dict | None:
    """
    Load and parse a heartbeat JSON file.
    Returns the parsed dict or None if unreadable/malformed.
    """
    try:
        with open(heartbeat_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def compute_alerts(plans: list, workbench_dir: Path) -> dict:
    """
    Compute all fifteen alert categories.
    Returns a dict: alert_type -> list of {plan_id, detail}.
    """
    now = datetime.now(timezone.utc)
    alerts = {
        "stuck_audits": [],
        "long_blocked": [],
        "recurring_blockers": [],
        "orphaned_audit_files": [],
        "circular_dependencies": [],
        "verification_pending_too_long": [],
        "orphaned_threads": [],
        "malformed_frontmatter": [],
        "executor_hung": [],
        "orphan_heartbeat": [],
        "stuck_ideation": [],
        "orphaned_input": [],
        "dangling_linked_input": [],
        "reference_review_due": [],
        "plan_of_plans_linkage_mismatch": [],
    }

    plan_ids = {p["plan_id"] for p in plans}

    for plan in plans:
        pid = plan["plan_id"]

        # stuck_audits: sufficiency or plan_safety iterations >= threshold
        max_iter = max(
            plan.get("audit_sufficiency_iterations", 0),
            plan.get("audit_plan_safety_iterations", 0),
        )
        if max_iter >= THRESHOLD_STUCK_AUDIT_ITERATIONS:
            alerts["stuck_audits"].append({
                "plan_id": pid,
                "detail": f"Audit iterations: sufficiency={plan.get('audit_sufficiency_iterations', 0)}, "
                          f"plan_safety={plan.get('audit_plan_safety_iterations', 0)}",
            })

        # long_blocked: status == blocked and created date is old
        if plan.get("status") == "blocked" and plan.get("blocked_by"):
            created_str = plan.get("created", "")
            if created_str:
                try:
                    created_dt = datetime.fromisoformat(created_str).replace(tzinfo=timezone.utc)
                    age_days = (now - created_dt).days
                    if age_days >= THRESHOLD_LONG_BLOCKED_DAYS:
                        alerts["long_blocked"].append({
                            "plan_id": pid,
                            "detail": f"Blocked for {age_days} days (threshold: {THRESHOLD_LONG_BLOCKED_DAYS}). "
                                      f"Blocked by: {plan.get('blocked_by')}",
                        })
                except ValueError:
                    pass

        # recurring_blockers: same error fingerprint in 2+ consecutive audit iterations
        # within the same stage (D3 - Per-Stage-Recurrence, PLAN-AF0).
        # Cross-stage adjacencies (sufficiency -> plan_safety) are skipped so a
        # fingerprint must recur on the same audit ladder to fire the alert.
        audit_history = load_audit_history(workbench_dir, pid)
        if len(audit_history) >= 2:
            # Walk consecutive pairs; only compare entries with equal _stage values.
            found_recurring = False
            for i in range(1, len(audit_history)):
                prev = audit_history[i - 1]
                curr = audit_history[i]
                # Skip cross-stage adjacencies (e.g. sufficiency -> plan_safety)
                if prev.get("_stage", "") != curr.get("_stage", ""):
                    continue
                prev_fps = {
                    f.get("fingerprint")
                    for f in prev.get("findings", [])
                    if f.get("level") == "error" and f.get("fingerprint")
                }
                curr_fps = {
                    f.get("fingerprint")
                    for f in curr.get("findings", [])
                    if f.get("level") == "error" and f.get("fingerprint")
                }
                recurring = curr_fps & prev_fps
                if recurring:
                    stage_label = curr.get("_stage", "") or "unknown"
                    iter_prev = prev.get("_iteration", i)
                    iter_curr = curr.get("_iteration", i + 1)
                    alerts["recurring_blockers"].append({
                        "plan_id": pid,
                        "detail": (
                            f"Error fingerprint(s) recur across {stage_label} audit "
                            f"iterations {iter_prev} and {iter_curr}: "
                            + ", ".join(sorted(recurring))
                        ),
                    })
                    found_recurring = True
                    break  # one alert per plan is enough

        # verification_pending_too_long: pipeline_phase == outcome-verifying and human_verdict == pending
        if (
            plan.get("pipeline_phase") == "outcome-verifying"
            and plan.get("human_verdict") == "pending"
        ):
            created_str = plan.get("created", "")
            if created_str:
                try:
                    created_dt = datetime.fromisoformat(created_str).replace(tzinfo=timezone.utc)
                    age_hours = (now - created_dt).total_seconds() / 3600
                    if age_hours >= THRESHOLD_VERIFICATION_PENDING_HOURS:
                        alerts["verification_pending_too_long"].append({
                            "plan_id": pid,
                            "detail": f"Awaiting human verification for {age_hours:.1f} hours "
                                      f"(threshold: {THRESHOLD_VERIFICATION_PENDING_HOURS}h).",
                        })
                except ValueError:
                    pass

        # malformed_frontmatter: schema_version missing or not 2 (warn but don't error)
        sv = plan.get("schema_version")
        if sv is None:
            alerts["malformed_frontmatter"].append({
                "plan_id": pid,
                "detail": "Missing schema_version field. Expected schema_version: 2.",
            })
        elif str(sv) != "2":
            alerts["malformed_frontmatter"].append({
                "plan_id": pid,
                "detail": f"schema_version is '{sv}', expected 2.",
            })

        # stuck_ideation: ideate_phase is non-terminal AND last commit modifying this PLAN was > 24h ago
        ideate_phase = plan.get("ideate_phase", "") or ""
        if ideate_phase and ideate_phase not in IDEATE_TERMINAL_PHASES:
            # Use git log to find the last commit touching this PLAN file
            plan_path_str = plan.get("path", "")
            mtime_ok = False
            if plan_path_str:
                try:
                    git_result = subprocess.run(
                        [
                            "git", "log", "-1",
                            "--pretty=format:%ci",
                            "--",
                            plan_path_str,
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        cwd=str(workbench_dir.parent),
                        timeout=10,
                    )
                    if git_result.returncode == 0 and git_result.stdout.strip():
                        last_commit_ts = git_result.stdout.strip()
                        # Parse ISO timestamp (git --pretty=format:%ci gives "YYYY-MM-DD HH:MM:SS +ZONE")
                        # Normalise to timezone-aware datetime
                        try:
                            # Replace space before timezone with +
                            ts_normalised = last_commit_ts.replace(" +", "+").replace(" -", "-")
                            # Handle "YYYY-MM-DD HH:MM:SS +HHMM" format
                            import re as _re
                            ts_match = _re.match(
                                r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([+-]\d{4})",
                                last_commit_ts,
                            )
                            if ts_match:
                                base = ts_match.group(1)
                                tz_str = ts_match.group(2)
                                sign = 1 if tz_str[0] == "+" else -1
                                tz_hours = int(tz_str[1:3])
                                tz_mins = int(tz_str[3:5])
                                from datetime import timedelta
                                tz_offset = timezone(timedelta(hours=sign * tz_hours, minutes=sign * tz_mins))
                                commit_dt = datetime.strptime(base, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz_offset)
                                age_hours = (now - commit_dt).total_seconds() / 3600
                                if age_hours >= THRESHOLD_STUCK_IDEATION_HOURS:
                                    alerts["stuck_ideation"].append({
                                        "plan_id": pid,
                                        "detail": (
                                            f"ideate_phase={ideate_phase!r} (non-terminal) and last commit was "
                                            f"{age_hours:.1f}h ago (threshold: {THRESHOLD_STUCK_IDEATION_HOURS}h). "
                                            "Ideate may be stalled. Check in or /checkpoint."
                                        ),
                                    })
                        except (ValueError, TypeError):
                            pass
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass

        # orphaned_threads: closes_thread or advances_thread set but thread not in ROADMAP
        # (v1: detect if thread id is non-empty; ROADMAP.md validation deferred to future dev)
        # orphaned_threads is detected by thread grouping below

        # dangling_linked_input: a PLAN whose linked_inputs references a file absent
        # from both Workbench/ and Retired/**
        for input_ref in plan.get("linked_inputs", []):
            input_basename = Path(input_ref).name if input_ref else ""
            if not input_basename:
                continue
            in_workbench = (workbench_dir / input_basename).exists()
            in_retired = any(
                True
                for _ in sorted(workbench_dir.parent.rglob(f"Retired/**/{input_basename}"))
            ) or (workbench_dir.parent / "Retired" / input_basename).exists()
            # Also check direct Retired/ child
            retired_dir = workbench_dir.parent / "Retired"
            if not in_retired and retired_dir.exists():
                for candidate in sorted(retired_dir.rglob(input_basename)):
                    if candidate.name == input_basename:
                        in_retired = True
                        break
            if not in_workbench and not in_retired:
                alerts["dangling_linked_input"].append({
                    "plan_id": pid,
                    "detail": (
                        f"linked_inputs references absent file: {input_basename} "
                        f"(not in Workbench/ or Retired/)."
                    ),
                })

    # orphaned_audit_files: audit files in .audit/ with no matching PLAN.
    # D2 - Symmetric-Canonicalisation (PLAN-AF0): compare on canonical short-id
    # on both sides so short-id audit names (post-AE10) and legacy full-stem names
    # both resolve correctly without false orphan alerts.
    audit_dir = workbench_dir / ".audit"
    if audit_dir.exists():
        # Build a canonical-id comparison set from the loaded plans.
        plan_canonical_ids = {_canonical_plan_id(p["plan_id"]) for p in plans}

        # sorted() keeps orphaned_audit_files order deterministic across
        # filesystems - the array is a structural field the INDEX-freshness
        # check compares without masking, so raw iterdir() order would flake.
        for audit_file in sorted(audit_dir.iterdir()):
            # _audit_file_plan_id filters non-audit files (audit-findings-*.json,
            # recovery-*.json, etc.) and returns the canonical plan-id or None.
            file_plan_id = _audit_file_plan_id(audit_file.name)
            if file_plan_id is None:
                continue
            if file_plan_id not in plan_canonical_ids:
                alerts["orphaned_audit_files"].append({
                    "plan_id": file_plan_id,
                    "detail": f"Audit file {audit_file.name} has no corresponding PLAN in Workbench/.",
                })

    # executor_hung and orphan_heartbeat: scan Workbench/.heartbeat/*.json
    heartbeat_dir = workbench_dir / ".heartbeat"
    if heartbeat_dir.exists():
        for hb_file in sorted(heartbeat_dir.iterdir()):
            if not hb_file.name.endswith(".json"):
                continue

            hb_data = load_heartbeat(hb_file)
            if hb_data is None:
                # Malformed or unreadable - skip silently
                print(
                    f"  [build_index] heartbeat {hb_file.name} unreadable/malformed - skipping",
                    file=sys.stderr,
                )
                continue

            hb_plan_id = hb_data.get("plan_id") or hb_file.stem

            # orphan_heartbeat: no corresponding PLAN in Workbench/
            if hb_plan_id not in plan_ids:
                alerts["orphan_heartbeat"].append({
                    "plan_id": hb_plan_id,
                    "detail": (
                        f"Heartbeat file {hb_file.name} has no corresponding PLAN in Workbench/. "
                        "File deleted."
                    ),
                })
                # Garbage-collect: delete the orphaned heartbeat file
                try:
                    hb_file.unlink()
                except OSError as exc:
                    print(
                        f"  [build_index] could not delete orphan heartbeat {hb_file.name}: {exc}",
                        file=sys.stderr,
                    )
                continue

            # executor_hung: phase == running AND last_tick_at > threshold
            hb_phase = hb_data.get("phase", "")
            hb_last_tick = hb_data.get("last_tick_at", "")
            if hb_phase == "running" and hb_last_tick:
                try:
                    tick_dt = datetime.fromisoformat(hb_last_tick.replace("Z", "+00:00"))
                    age_secs = (now - tick_dt).total_seconds()
                    if age_secs > THRESHOLD_EXECUTOR_HUNG_SECONDS:
                        age_min = age_secs / 60
                        step_info = f"step {hb_data.get('current_step', '?')}"
                        alerts["executor_hung"].append({
                            "plan_id": hb_plan_id,
                            "detail": (
                                f"Executor heartbeat stale for {age_min:.1f} min "
                                f"(last tick: {hb_last_tick}). Phase: running, {step_info}."
                            ),
                        })
                except (ValueError, TypeError):
                    pass

    # circular_dependencies: triggers_plans -> detect cycles (v1: simple DFS)
    dep_map = {p["plan_id"]: p.get("triggers_plans", []) for p in plans}
    visited = set()
    in_stack = set()
    cycle_pairs = set()

    def dfs(node):
        visited.add(node)
        in_stack.add(node)
        for child in dep_map.get(node, []):
            # Resolve partial name matches
            child_id = None
            for pid2 in dep_map:
                if pid2.endswith(child) or child.endswith(pid2) or child == pid2:
                    child_id = pid2
                    break
            if child_id is None:
                continue
            if child_id not in visited:
                dfs(child_id)
            elif child_id in in_stack:
                cycle_pairs.add((node, child_id))
        in_stack.discard(node)

    for pid in dep_map:
        if pid not in visited:
            dfs(pid)

    for a, b in cycle_pairs:
        alerts["circular_dependencies"].append({
            "plan_id": a,
            "detail": f"Circular dependency detected: {a} -> {b}",
        })

    # --- Input-file scan pass ---
    # Separate from the PLAN scan: load_plan returns None for type != "plan",
    # so input files need their own pass. Reads with encoding="utf-8",
    # errors="replace" so a malformed input byte-sequence degrades gracefully.

    def _basename_in_retired(basename: str) -> bool:
        """Return True if a file with this basename exists anywhere under Retired/."""
        if not basename:
            return False
        retired_dir = workbench_dir.parent / "Retired"
        if not retired_dir.exists():
            return False
        for candidate in sorted(retired_dir.rglob("*")):
            if candidate.name == basename:
                return True
        return False

    input_file_pattern = re.compile(
        r"^(?:RESEARCH|ADVICE)-\d{3,4}_"  # legacy numeric: RESEARCH-001_slug.md
        r"|^(?:RESEARCH|ADVICE)-\d{8}-\d{4}-",  # datetime: RESEARCH-20260712-1400-slug.md
    )

    for md_file in sorted(workbench_dir.iterdir()):
        if not md_file.name.endswith(".md"):
            continue
        if not input_file_pattern.match(md_file.name):
            continue

        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # unreadable - skip silently

        try:
            fm = _parse_frontmatter(text)
        except Exception:
            continue  # malformed frontmatter - skip silently

        if not fm:
            continue

        file_type = fm.get("type", "")
        if file_type not in ("research", "advice"):
            continue

        fm_raw = fm.get("_raw", "")
        input_id = md_file.name

        # feeds_plan / advises_plan
        feeds_plan = fm.get("feeds_plan", "") or ""
        advises_plan = fm.get("advises_plan", "") or ""
        consuming_ref = feeds_plan if file_type == "research" else advises_plan

        # orphaned_input: empty or dangling consuming reference
        if not consuming_ref:
            alerts["orphaned_input"].append({
                "plan_id": input_id,
                "detail": "Input orphaned: feeds_plan/advises_plan is empty.",
            })
        else:
            consuming_basename = Path(consuming_ref).name
            in_workbench = (workbench_dir / consuming_basename).exists()
            in_retired = _basename_in_retired(consuming_basename)
            if not in_workbench and not in_retired:
                alerts["orphaned_input"].append({
                    "plan_id": input_id,
                    "detail": (
                        f"Input orphaned: feeds_plan/advises_plan names absent PLAN "
                        f"'{consuming_ref}' (not in Workbench/ or Retired/)."
                    ),
                })

        # reference_review_due: lifecycle_mode: reference + non-empty review_by + today >= review_by
        lifecycle_mode = fm.get("lifecycle_mode", "") or ""
        review_by = fm.get("review_by", "") or ""
        if lifecycle_mode == "reference" and review_by:
            try:
                from datetime import date as _date
                review_dt = _date.fromisoformat(review_by)
                if _date.today() >= review_dt:
                    alerts["reference_review_due"].append({
                        "plan_id": input_id,
                        "detail": (
                            f"Reference-mode input review due: "
                            f"review_by={review_by} (today >= review_by)."
                        ),
                    })
            except ValueError:
                pass  # malformed date - skip silently

    # --- plan_of_plans_linkage_mismatch ---
    # Operates on the already-loaded PLAN records (type == plan) - does NOT
    # re-read any file. Checks both directions of every parent/child edge.

    by_bare_id = {_bare_plan_id(p["plan_id"]): p for p in plans}

    # Collect bare ids of plans present in Retired/ so we can distinguish
    # "retired child" from "genuinely absent child".
    retired_dir_pop = workbench_dir.parent / "Retired"
    retired_bare_ids: set[str] = set()
    if retired_dir_pop.exists():
        for ret_file in sorted(retired_dir_pop.rglob("*.md")):
            bare = _bare_plan_id(ret_file.stem)
            if bare:
                retired_bare_ids.add(bare)

    # Track emitted pairs so a single broken edge is not double-reported.
    emitted_mismatch_pairs: set[tuple[str, str]] = set()

    def _emit_mismatch(parent_bare: str, child_bare: str, detail: str) -> None:
        key = tuple(sorted((parent_bare, child_bare)))
        if key not in emitted_mismatch_pairs:
            emitted_mismatch_pairs.add(key)
            alerts["plan_of_plans_linkage_mismatch"].append({
                "plan_id": parent_bare,
                "detail": detail,
            })

    # Direction (i): child claims a parent that doesn't trigger it
    for plan in plans:
        child_bare = _bare_plan_id(plan["plan_id"])
        for parent_field in ("parent_plan_of_plans", "parent"):
            parent_ref = plan.get(parent_field, "") or ""
            if not parent_ref:
                continue
            parent_bare = _bare_plan_id(parent_ref)
            if not parent_bare or parent_bare == child_bare:
                continue
            parent_plan = by_bare_id.get(parent_bare)
            if parent_plan is not None:
                parent_triggers_bare = [
                    _bare_plan_id(x) for x in parent_plan.get("triggers_plans", [])
                ]
                if child_bare not in parent_triggers_bare:
                    _emit_mismatch(
                        parent_bare,
                        child_bare,
                        f"child {child_bare} names parent {parent_bare} but "
                        f"{parent_bare}.triggers_plans omits {child_bare}",
                    )

    # Direction (ii): parent triggers a child that doesn't back-reference it,
    # or child is absent from both Workbench/ and Retired/
    for plan in plans:
        parent_bare = _bare_plan_id(plan["plan_id"])
        for child_ref in plan.get("triggers_plans", []):
            child_bare = _bare_plan_id(child_ref)
            if not child_bare or child_bare == parent_bare:
                continue
            child_plan = by_bare_id.get(child_bare)
            if child_plan is None:
                if child_bare not in retired_bare_ids:
                    _emit_mismatch(
                        parent_bare,
                        child_bare,
                        f"parent {parent_bare} triggers {child_bare} but "
                        f"{child_bare} is absent from Workbench/ and Retired/",
                    )
            else:
                back_refs = [
                    _bare_plan_id(child_plan.get(f, "") or "")
                    for f in ("parent_plan_of_plans", "parent")
                ]
                if parent_bare not in back_refs:
                    _emit_mismatch(
                        parent_bare,
                        child_bare,
                        f"parent {parent_bare} triggers {child_bare} but "
                        f"{child_bare} does not back-reference {parent_bare}",
                    )

    return alerts


# ---------------------------------------------------------------------------
# Thread and dependency aggregation
# ---------------------------------------------------------------------------

def compute_threads(plans: list) -> list:
    """
    Group plans by thread (closes_thread / advances_thread).
    Returns a list of thread dicts: {thread_id, plans, status}.
    """
    threads: dict[str, dict] = {}

    for plan in plans:
        ct = plan.get("closes_thread", "")
        at = plan.get("advances_thread", "")

        for thread_id in filter(None, [ct, at]):
            if thread_id not in threads:
                threads[thread_id] = {
                    "thread_id": thread_id,
                    "plans": [],
                    "closed_by": None,
                }
            threads[thread_id]["plans"].append(plan["plan_id"])
            if ct == thread_id and plan.get("status") == "done":
                threads[thread_id]["closed_by"] = plan["plan_id"]

    result = []
    for thread_id, data in sorted(threads.items()):
        result.append({
            "thread_id": thread_id,
            "plans": data["plans"],
            "status": "closed" if data["closed_by"] else "open",
            "closed_by": data["closed_by"],
        })
    return result


def compute_dependencies(plans: list) -> list:
    """
    Build a list of dependency edges from triggers_plans and blocked_by.
    Returns a list of {from_plan, to_plan, type} dicts.
    """
    deps = []
    for plan in plans:
        pid = plan["plan_id"]
        for child in plan.get("triggers_plans", []):
            deps.append({"from_plan": pid, "to_plan": child, "type": "triggers"})
        blocked = plan.get("blocked_by", "")
        if blocked:
            deps.append({"from_plan": blocked, "to_plan": pid, "type": "blocks"})
    return deps


# ---------------------------------------------------------------------------
# Summary computation
# ---------------------------------------------------------------------------

def compute_summary(plans: list) -> dict:
    """Compute aggregate counts by phase, status, assigned_to, priority."""
    by_phase = {}
    by_status = {}
    by_assigned_to = {}
    by_priority = {}

    for plan in plans:
        phase = plan.get("pipeline_phase") or "no-phase"
        status = plan.get("status", "unknown")
        assigned = plan.get("assigned_to") or "unassigned"
        priority = plan.get("priority", "medium")

        by_phase[phase] = by_phase.get(phase, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        by_assigned_to[assigned] = by_assigned_to.get(assigned, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1

    return {
        "total_plans": len(plans),
        "by_phase": by_phase,
        "by_status": by_status,
        "by_assigned_to": by_assigned_to,
        "by_priority": by_priority,
    }


# ---------------------------------------------------------------------------
# Recent transitions (git log)
# ---------------------------------------------------------------------------

def get_recent_transitions(repo_root: Path, max_count: int = 10) -> list:
    """
    Get recent plan-pipeline commits from git log.
    Returns a list of {sha, date, message} dicts.
    """
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--max-count={max_count}",
                "--grep=plan-pipeline:",
                "--pretty=format:%h|%ci|%s",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(repo_root),
            timeout=15,
        )
        if result.returncode != 0:
            return []
        lines = [l for l in result.stdout.strip().splitlines() if l]
        transitions = []
        for line in lines:
            parts = line.split("|", 2)
            if len(parts) == 3:
                transitions.append({
                    "sha": parts[0].strip(),
                    "date": parts[1].strip(),
                    "message": parts[2].strip(),
                })
        return transitions
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def get_recent_retires(repo_root: Path, max_count: int = 10) -> list:
    """
    Get recent retire commits from git log. Returns a list of
    {sha, date, plan_id} dicts. Sources retirements from git history rather
    than the Retired/ filesystem so the section is deterministic across
    machines (the filesystem can drift across operators even though Retired/
    is now tracked per PLAN-AD0 D2-A 2026-05-22 - git log remains the
    canonical chronology of retire events).

    Matches two commit-message patterns used by the foundry:
      - "chore: retire PLAN-<id>"  (orchestrator retire commits)
      - "plan-pipeline: retired PLAN-<id>" or "plan-pipeline: PLAN-<id> ... retired"
    """
    # Match PLAN-ID with optional slug; commit messages often use bare IDs.
    pattern = re.compile(r"PLAN-(?:[A-Z]{2}[0-9]|\d{3,4})(?:_[a-z0-9\-]+)?", re.IGNORECASE)
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--max-count={max_count * 3}",  # over-fetch; filter below
                "--grep=retire",
                "-i",
                "--pretty=format:%h|%ci|%s",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(repo_root),
            timeout=15,
        )
        if result.returncode != 0:
            return []
        retires = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            sha, date, message = parts[0].strip(), parts[1].strip(), parts[2].strip()
            # Only commits that actually retire a PLAN (filter out "post-retire"
            # commits like "fix(retire): post-condition verification...")
            lower = message.lower()
            if not (
                lower.startswith("chore: retire")
                or "plan-pipeline: retired" in lower
                or "plan-pipeline: pipeline complete; retired" in lower
            ):
                continue
            m = pattern.search(message)
            plan_id = m.group(0) if m else "(unknown)"
            retires.append({"sha": sha, "date": date, "plan_id": plan_id})
            if len(retires) >= max_count:
                break
        return retires
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_markdown(
    plans: list,
    alerts: dict,
    threads: list,
    dependencies: list,
    recent_transitions: list,
    generated_at: str,
    workbench_dir: Path,
) -> str:
    """Render the INDEX.md markdown document."""
    lines = []

    # Header
    lines += [
        "# Workbench INDEX",
        "",
        f"_Generated: {generated_at} by {GENERATED_BY}_",
        "",
        "This document is a deterministic projection of all PLAN files in `Workbench/`. "
        "Regenerated automatically after every phase transition. "
        "Do not edit manually - changes will be overwritten.",
        "",
    ]

    # Summary
    total = len(plans)
    non_terminal = sum(1 for p in plans if p.get("status") not in TERMINAL_STATUSES)
    terminal = total - non_terminal
    lines += [
        "## Summary",
        "",
        f"| Metric | Count |",
        "|---|---|",
        f"| Total PLANs | {total} |",
        f"| Active (non-terminal) | {non_terminal} |",
        f"| Terminal (done/cancelled/etc.) | {terminal} |",
        "",
    ]

    # Kanban table
    lines += [
        "## Kanban",
        "",
        "PLANs grouped by `pipeline_phase`. Terminal-status PLANs appear in the Done column regardless of phase.",
        "",
    ]

    # Group plans by phase
    phase_buckets: dict[str, list] = {p: [] for p in KANBAN_PHASES}
    phase_buckets["done"] = []
    phase_buckets["other"] = []
    phase_buckets["ideating"] = []  # virtual bucket: drafting + non-terminal ideate_phase

    for plan in plans:
        status = plan.get("status", "ready")
        phase = plan.get("pipeline_phase", "") or ""
        ideate_phase = plan.get("ideate_phase", "") or ""
        repeatable = bool(plan.get("repeatable", False))

        if status in TERMINAL_STATUSES:
            phase_buckets["done"].append(plan)
        elif (
            phase == "drafting"
            and ideate_phase
            and ideate_phase not in IDEATE_TERMINAL_PHASES
        ):
            # PLAN is actively being ideated - show in "Ideating" virtual column
            phase_buckets["ideating"].append(plan)
        elif phase in KANBAN_PHASES:
            phase_buckets[phase].append(plan)
        elif phase == "" and repeatable:
            # Recurring backstop tasks (RECUR-) with no lifecycle phase.
            phase_buckets["other"].append(plan)
        else:
            # pipeline_phase == "" and not repeatable: conceptually drafted but
            # not yet picked up by the orchestrator. Show in Drafted so the
            # human sees them awaiting audit.
            phase_buckets["drafted"].append(plan)

    def plan_row(p):
        pid = p["plan_id"]
        title = p.get("title", "(no title)")
        if len(title) > 60:
            title = title[:57] + "..."
        status = p.get("status", "")
        priority = p.get("priority", "")
        assigned = p.get("assigned_to", "") or "-"
        return f"| {pid} | {title} | {status} | {priority} | {assigned} |"

    col_header = "| Plan ID | Title | Status | Priority | Assigned |"
    col_sep = "|---|---|---|---|---|"

    # Render the "Ideating" virtual bucket first (most human-attention needed)
    ideating_bucket = phase_buckets["ideating"]
    ideating_count = len(ideating_bucket)
    lines += [f"### Ideating ({ideating_count})", ""]
    lines.append("_PLANs with `pipeline_phase: drafting` and a non-terminal `ideate_phase` - "
                 "actively being shaped by the ideate cadence._")
    lines.append("")
    if ideating_bucket:
        lines += [col_header, col_sep]
        for p in sorted(ideating_bucket, key=lambda x: x["plan_id"], reverse=True):
            ip = p.get("ideate_phase", "") or ""
            row = plan_row(p)
            # Annotate with ideate_phase
            row = row.rstrip("|") + f" _(ideate: {ip})_ |"
            lines.append(row)
    else:
        lines.append("_No PLANs currently being ideated._")
    lines.append("")

    for phase in KANBAN_PHASES:
        bucket = phase_buckets[phase]
        count = len(bucket)
        lines += [f"### {phase.title()} ({count})", ""]
        if bucket:
            lines += [col_header, col_sep]
            for p in sorted(bucket, key=lambda x: x["plan_id"], reverse=True):
                lines.append(plan_row(p))
        else:
            lines.append("_No PLANs in this phase._")
        lines.append("")

    # Recurring / Ad-hoc bucket - active PLANs with empty pipeline_phase.
    # These are typically RECUR- monthly/weekly tasks or operational backstops
    # that don't move through the lifecycle but should still be visible.
    other_bucket = phase_buckets["other"]
    lines += [f"### Recurring / Ad-hoc ({len(other_bucket)})", ""]
    lines.append("_Active PLANs with `pipeline_phase: \"\"` - recurring tasks or operational backstops "
                 "that don't walk the lifecycle. Tracked here for visibility; cadence managed in the LOG._")
    lines.append("")
    if other_bucket:
        lines += [col_header, col_sep]
        for p in sorted(other_bucket, key=lambda x: x["plan_id"], reverse=True):
            lines.append(plan_row(p))
    else:
        lines.append("_No recurring or ad-hoc PLANs._")
    lines.append("")

    # Done bucket
    done_bucket = phase_buckets["done"]
    lines += [f"### Done / Terminal ({len(done_bucket)})", ""]
    if done_bucket:
        lines += [col_header, col_sep]
        for p in sorted(done_bucket, key=lambda x: x["plan_id"], reverse=True)[:20]:
            lines.append(plan_row(p))
        if len(done_bucket) > 20:
            lines.append(f"_... and {len(done_bucket) - 20} more terminal PLANs._")
    else:
        lines.append("_No terminal PLANs._")
    lines.append("")

    # Alerts
    lines += ["## Alerts", ""]
    total_alerts = sum(len(v) for v in alerts.values())
    if total_alerts == 0:
        lines += ["_No active alerts._", ""]
    else:
        lines += [f"_{total_alerts} alert(s) detected._", ""]

    alert_labels = {
        "stuck_audits": "Stuck Audits",
        "long_blocked": "Long Blocked",
        "recurring_blockers": "Recurring Blockers",
        "orphaned_audit_files": "Orphaned Audit Files",
        "circular_dependencies": "Circular Dependencies",
        "verification_pending_too_long": "Verification Pending Too Long",
        "orphaned_threads": "Orphaned Threads",
        "malformed_frontmatter": "Malformed Frontmatter",
        "executor_hung": "Executor Hung",
        "orphan_heartbeat": "Orphan Heartbeat",
        "stuck_ideation": "Stuck Ideation",
        "orphaned_input": "Orphaned Input",
        "dangling_linked_input": "Dangling Linked Input",
        "reference_review_due": "Reference Review Due",
        "plan_of_plans_linkage_mismatch": "Plan-of-Plans Linkage Mismatch",
    }

    for alert_key, alert_label in alert_labels.items():
        items = alerts.get(alert_key, [])
        lines += [f"### {alert_label} ({len(items)})", ""]
        if items:
            for item in items:
                lines.append(f"- **{item['plan_id']}**: {item['detail']}")
        else:
            lines.append("_None._")
        lines.append("")

    # Threads
    lines += ["## Threads", ""]
    if threads:
        lines += [
            "| Thread ID | Status | Plans | Closed By |",
            "|---|---|---|---|",
        ]
        for t in threads:
            plans_str = ", ".join(t["plans"])
            closed_by = t.get("closed_by") or "-"
            status = t.get("status", "open")
            lines.append(f"| {t['thread_id']} | {status} | {plans_str} | {closed_by} |")
    else:
        lines.append("_No threads defined._")
    lines.append("")

    # Dependency Graph
    lines += ["## Dependency Graph", ""]
    if dependencies:
        lines += ["```", ""]
        dep_by_from: dict[str, list] = {}
        for d in dependencies:
            dep_by_from.setdefault(d["from_plan"], []).append(d)
        for from_plan, edges in sorted(dep_by_from.items()):
            for edge in edges:
                arrow = "->" if edge["type"] == "triggers" else "⊣"
                lines.append(f"  {from_plan} {arrow} {edge['to_plan']}  ({edge['type']})")
        lines += ["```", ""]
    else:
        lines += ["_No dependencies defined._", ""]

    # Recent Activity
    lines += ["## Recent Activity", ""]
    if recent_transitions:
        lines += [
            "| SHA | Date | Commit Message |",
            "|---|---|---|",
        ]
        for t in recent_transitions:
            sha = t.get("sha", "-")
            date = t.get("date", "-")[:10]  # date portion only
            msg = t.get("message", "-")
            if len(msg) > 80:
                msg = msg[:77] + "..."
            lines.append(f"| `{sha}` | {date} | {msg} |")
    else:
        lines.append("_No recent plan-pipeline commits found._")
    lines.append("")

    # Recently Retired - sourced from git log (deterministic across machines),
    # not from Retired/ filesystem (Retired/ is now tracked per PLAN-AD0 D2-A
    # 2026-05-22 but git log remains the canonical chronology of retire events).
    # Matches commit messages with "retire PLAN-" or "plan-pipeline: retired".
    lines += ["## Recently Retired", ""]
    retired_commits = get_recent_retires(workbench_dir.parent, max_count=10)
    if retired_commits:
        lines += [
            "| Commit | Date | Retired PLAN |",
            "|---|---|---|",
        ]
        for rc in retired_commits:
            lines.append(f"| `{rc['sha']}` | {rc['date'][:10]} | {rc['plan_id']} |")
    else:
        lines.append("_No retire commits found in git history._")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def render_json(
    plans: list,
    alerts: dict,
    threads: list,
    dependencies: list,
    recent_transitions: list,
    generated_at: str,
    workbench_root: str,
) -> dict:
    """Build the .index.json data structure."""
    summary = compute_summary(plans)

    # Build plan records for JSON (include audit history summary)
    plan_records = []
    for plan in plans:
        record = {
            "plan_id": plan["plan_id"],
            "title": plan.get("title", ""),
            "status": plan.get("status", ""),
            "assigned_to": plan.get("assigned_to", ""),
            "priority": plan.get("priority", ""),
            "pipeline_phase": plan.get("pipeline_phase", ""),
            "schema_version": plan.get("schema_version"),
            "created": plan.get("created", ""),
            "due": plan.get("due", ""),
            "blocked_by": plan.get("blocked_by", ""),
            "closes_thread": plan.get("closes_thread", ""),
            "advances_thread": plan.get("advances_thread", ""),
            "triggers_plans": plan.get("triggers_plans", []),
            "tags": plan.get("tags", []),
            "files_touched": plan.get("files_touched", []),
            "audit_history": {
                "sufficiency_iterations": plan.get("audit_sufficiency_iterations", 0),
                "plan_safety_iterations": plan.get("audit_plan_safety_iterations", 0),
                "last_stage": plan.get("audit_last_stage", "none"),
                "last_outcome": plan.get("audit_last_outcome", "none"),
            },
            "ideate_phase": plan.get("ideate_phase", "") or "",
        }
        plan_records.append(record)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "generated_by": GENERATED_BY,
        "workbench_root": workbench_root,
        "summary": summary,
        "alerts": alerts,
        "plans": plan_records,
        "threads": threads,
        "dependencies": dependencies,
        "recent_transitions": recent_transitions,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_index(workbench: Path) -> tuple[str, dict]:
    """
    Build the INDEX from the given Workbench directory.

    Args:
        workbench: Path to the Workbench directory.

    Returns:
        (markdown_text, json_data) tuple.
        Also writes INDEX.md and .index.json to disk.
    """
    workbench = workbench.resolve()
    if not workbench.exists():
        raise FileNotFoundError(f"Workbench directory not found: {workbench}")

    # Find repo root (parent of Workbench, where git repo lives)
    repo_root = workbench.parent

    # Load all PLAN files
    plans = []
    for md_file in sorted(workbench.iterdir()):
        if not md_file.name.endswith(".md"):
            continue
        if md_file.name in SKIP_FILENAMES:
            continue
        if not PLAN_PATTERN.match(md_file.name):
            continue

        plan = load_plan(md_file)
        if plan is not None:
            plans.append(plan)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    alerts = compute_alerts(plans, workbench)
    threads = compute_threads(plans)
    dependencies = compute_dependencies(plans)
    recent_transitions = get_recent_transitions(repo_root)

    markdown = render_markdown(
        plans, alerts, threads, dependencies, recent_transitions,
        generated_at, workbench,
    )
    json_data = render_json(
        plans, alerts, threads, dependencies, recent_transitions,
        generated_at, workbench.name,
    )

    # Idempotent write: only update on real content change. Without this, every
    # regen would rewrite generated_at and produce a no-op diff - making the
    # drift-check pre-commit hook noisy. We compare content modulo the timestamp
    # field; if identical, keep the existing file's timestamp.
    index_md = workbench / "INDEX.md"
    index_json = workbench / ".index.json"

    _TS_MD_RE = re.compile(r"_Generated: \S+ by ")
    # Volatile fields (timestamp, workbench_root) are normalised out before the
    # content-comparison so the script is idempotent across machines with
    # different cwds. Without this, CI and local would always disagree on the
    # workbench absolute-path field - failing the INDEX-freshness check.
    _VOLATILE_JSON_KEYS = {"generated_at", "workbench_root"}
    def _strip_ts_md(text: str) -> str:
        return _TS_MD_RE.sub("_Generated: TS by ", text, count=1)
    def _strip_ts_json(data: dict) -> dict:
        return {k: v for k, v in data.items() if k not in _VOLATILE_JSON_KEYS}

    if index_md.exists() and _strip_ts_md(index_md.read_text(encoding="utf-8")) == _strip_ts_md(markdown):
        pass  # no content change - preserve existing file (and its timestamp)
    else:
        index_md.write_text(markdown, encoding="utf-8")

    json_unchanged = False
    if index_json.exists():
        try:
            existing_json = json.loads(index_json.read_text(encoding="utf-8"))
            if _strip_ts_json(existing_json) == _strip_ts_json(json_data):
                json_unchanged = True
        except (json.JSONDecodeError, OSError):
            pass  # malformed or unreadable - rewrite

    if not json_unchanged:
        with open(index_json, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)

    return markdown, json_data


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Regenerate Workbench/INDEX.md and Workbench/.index.json from PLAN frontmatter.",
    )
    parser.add_argument(
        "workbench_dir",
        nargs="?",
        default="Workbench",
        help="Path to the Workbench directory (default: Workbench)",
    )
    args = parser.parse_args()

    workbench = Path(args.workbench_dir)

    try:
        markdown, json_data = build_index(workbench)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    plan_count = len(json_data.get("plans", []))
    alert_count = sum(len(v) for v in json_data.get("alerts", {}).values())
    print(
        f"INDEX built: {plan_count} plans, {alert_count} alerts. "
        f"Wrote {workbench}/INDEX.md and {workbench}/.index.json"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
