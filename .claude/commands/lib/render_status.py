"""
render_status.py - Render live executor status, stalled audit summary, and
context fullness for the current session.

Three output sections:
  1. Active executors: one line per heartbeat file in Workbench/.heartbeat/*.json
  2. Stalled audits: PLANs in `drafted` phase with audit_state.last_outcome: revision_needed
     AND > 24 hours since audit_state.last_audit_commit was written.
  3. Context fullness: the resident-token figure from the current session's
     latest assistant message. See the section-3 comment below for the
     metric and why a session-wide sum is wrong.

Usage:
    python render_status.py [workbench_dir]

    workbench_dir defaults to "Workbench" relative to the current working directory.

Exit 0 always (display errors as warnings, never crash).
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Library import - the shared Step-line pattern lives in the plan-pipeline
# skill (PLAN-AJ1). Resolved with the same walk as
# .claude/skills/ideate/lib/render_critique.py:44 - parents[N] to reach the
# target lib directory, insert on sys.path when absent, import inside a try
# that raises a typed ImportError naming the expected location.
# ---------------------------------------------------------------------------

_STEP_RENUMBER_LIB = Path(__file__).resolve().parents[2] / "skills" / "plan-pipeline" / "lib"

if str(_STEP_RENUMBER_LIB) not in sys.path:
    sys.path.insert(0, str(_STEP_RENUMBER_LIB))

try:
    from step_renumber import STEP_LINE_RE
except ImportError as e:
    raise ImportError(
        f"Cannot import STEP_LINE_RE from {_STEP_RENUMBER_LIB}. "
        "Expected it alongside the plan-pipeline skill under "
        ".claude/skills/plan-pipeline/lib/step_renumber.py. "
        f"Original error: {e}"
    ) from e

# dispatch_audit.py already derives the project slug ~/.claude/projects uses
# for this repo, and section 3 below (context fullness) needs the same
# derivation. Reused rather than restated, by the same cross-directory
# import pattern as STEP_LINE_RE above. Both directories ship together in
# every bundle sync, so this import never runs on a consumer install that
# lacks it.
_DISPATCH_AUDIT_LIB = Path(__file__).resolve().parents[2] / "skills" / "_shared"

if str(_DISPATCH_AUDIT_LIB) not in sys.path:
    sys.path.insert(0, str(_DISPATCH_AUDIT_LIB))

try:
    from dispatch_audit import derive_project_slug
except ImportError as e:
    raise ImportError(
        f"Cannot import derive_project_slug from {_DISPATCH_AUDIT_LIB}. "
        "Expected it alongside the _shared skill under "
        ".claude/skills/_shared/dispatch_audit.py. "
        f"Original error: {e}"
    ) from e


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STALE_THRESHOLD_SECONDS = 600       # 10 minutes -> executor considered hung
STALLED_AUDIT_THRESHOLD_SECONDS = 86400  # 24 hours -> audit stalled

# PLAN file pattern - matches both the active PLAN-[A-Z][A-Z][0-9] scheme and
# the frozen PLAN-NNN historical scheme (see .claude/skills/write-plan/
# references/naming-convention.md). Mirrors _LOG_ID_RE in
# .claude/skills/write-plan/scripts/next_id.py.
PLAN_PATTERN = re.compile(r"^PLAN-([A-Z]{2}[0-9]|\d{3,4})_")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _relative_time(ts_str: str, now: datetime) -> str:
    """
    Convert an ISO 8601 UTC string to a human-readable relative time string.
    E.g. "2 min ago", "45 s ago", "1 h 3 min ago".
    Returns "<unknown>" if ts_str is empty or unparseable.
    """
    if not ts_str:
        return "<unknown>"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        delta = now - dt
        secs = int(delta.total_seconds())
        if secs < 0:
            return "just now"
        if secs < 60:
            return f"{secs} s ago"
        mins = secs // 60
        if mins < 60:
            return f"{mins} min ago"
        hours = mins // 60
        remaining_mins = mins % 60
        if remaining_mins == 0:
            return f"{hours} h ago"
        return f"{hours} h {remaining_mins} min ago"
    except (ValueError, TypeError):
        return "<unknown>"


def _parse_frontmatter(text: str) -> dict:
    """
    Parse YAML frontmatter from a markdown file.
    Returns a flat dict of top-level key-value pairs plus '_raw' for the full block.
    Does NOT parse nested blocks.
    """
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    fm_text = parts[1].strip()
    fm = {"_raw": fm_text}

    for line in fm_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line.startswith(" ") or line.startswith("\t"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if " #" in value:
            value = value[:value.index(" #")].strip()
        value = value.strip('"').strip("'")
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        elif value.lower() in ("null", "~", ""):
            value = None
        fm[key] = value

    return fm


def _parse_nested_field(fm_raw: str, field_name: str, sub_key: str) -> str:
    """Parse a value from a nested YAML block."""
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
        if " #" in val:
            val = val[:val.index(" #")].strip()
        return val
    return ""


def _git_commit_timestamp(repo_root: Path, sha: str) -> float:
    """
    Return the Unix timestamp for the given git commit SHA.
    Returns 0.0 if git is unavailable or SHA is empty.
    """
    if not sha:
        return 0.0
    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%ct", sha],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Section 1: Active executors
# ---------------------------------------------------------------------------

def render_active_executors(workbench_dir: Path, now: datetime) -> list[str]:
    """
    Read all .heartbeat/*.json files and render one summary line per executor.
    Returns a list of output lines (not including the section header).
    """
    heartbeat_dir = workbench_dir / ".heartbeat"
    lines = []

    if not heartbeat_dir.exists():
        return lines

    heartbeat_files = sorted(heartbeat_dir.glob("*.json"))
    if not heartbeat_files:
        return lines

    # Count total PLAN steps for the plan (to display step N/M)
    def _count_steps(plan_id: str) -> int:
        """Count the number of steps in a PLAN by reading its body."""
        plan_path = workbench_dir / f"{plan_id}.md"
        if not plan_path.exists():
            return 0
        try:
            text = plan_path.read_text(encoding="utf-8")
            # Count lines that look like "N. " or "## Step N" style headings
            # Simple approach: count top-level numbered items in the Steps section
            steps_section = re.search(r"## Steps\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
            if steps_section:
                return sum(
                    1 for line in steps_section.group(1).splitlines()
                    if STEP_LINE_RE.match(line)
                )
        except OSError:
            pass
        return 0

    for hb_file in heartbeat_files:
        try:
            data = json.loads(hb_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            lines.append(f"  [warning: {hb_file.name} unreadable - {exc}]")
            continue

        plan_id = data.get("plan_id", hb_file.stem)
        phase = data.get("phase", "unknown")
        current_step = data.get("current_step", 0)
        step_summary = data.get("step_summary", "")
        last_tick_at = data.get("last_tick_at", "")

        rel_time = _relative_time(last_tick_at, now)

        # Stale detection: last_tick_at > STALE_THRESHOLD and phase != exited
        stale_label = "active"
        if phase != "exited" and last_tick_at:
            try:
                dt = datetime.fromisoformat(last_tick_at.replace("Z", "+00:00"))
                age = (now - dt).total_seconds()
                if age > STALE_THRESHOLD_SECONDS:
                    stale_label = "stale"
            except (ValueError, TypeError):
                pass

        total_steps = _count_steps(plan_id)
        step_str = f"step {current_step}/{total_steps}" if total_steps > 0 else f"step {current_step}"

        # Truncate step_summary for display
        summary_display = (step_summary[:60] + "...") if len(step_summary) > 63 else step_summary
        if summary_display:
            summary_display = f'"{summary_display}"'

        parts = [plan_id, step_str]
        if summary_display:
            parts.append(summary_display)
        parts.append(f"last tick {rel_time}")
        parts.append(f"[{stale_label}]")

        lines.append("  " + "  ".join(parts))

    return lines


# ---------------------------------------------------------------------------
# Section 2: Stalled audits
# ---------------------------------------------------------------------------

def render_stalled_audits(workbench_dir: Path, repo_root: Path, now: datetime) -> list[str]:
    """
    Scan Workbench/*.md for PLANs in drafted phase with revision_needed audit outcome
    that have been waiting > 24 hours.
    Returns a list of output lines (not including the section header).
    """
    lines = []

    for md_file in sorted(workbench_dir.iterdir()):
        if not md_file.name.endswith(".md"):
            continue
        if md_file.name in ("INDEX.md", ".gitkeep"):
            continue
        if not PLAN_PATTERN.match(md_file.name):
            continue

        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        fm = _parse_frontmatter(text)
        if not fm or fm.get("type") != "plan":
            continue

        pipeline_phase = fm.get("pipeline_phase", "")
        if pipeline_phase != "drafted":
            continue

        fm_raw = fm.get("_raw", "")
        last_outcome = _parse_nested_field(fm_raw, "audit_state", "last_outcome")
        if last_outcome != "revision_needed":
            continue

        # Determine how long it has been since the last audit commit
        last_audit_commit = _parse_nested_field(fm_raw, "audit_state", "last_audit_commit")
        age_secs = 0.0
        if last_audit_commit:
            commit_ts = _git_commit_timestamp(repo_root, last_audit_commit)
            if commit_ts > 0:
                age_secs = (now - datetime.fromtimestamp(commit_ts, tz=timezone.utc)).total_seconds()

        if age_secs < STALLED_AUDIT_THRESHOLD_SECONDS:
            continue

        # Render stalled audit line
        plan_id = md_file.stem
        title = fm.get("title", "(no title)")

        # Count iteration totals
        sufficiency_iter_str = _parse_nested_field(fm_raw, "audit_state", "sufficiency_iterations")
        plan_safety_iter_str = _parse_nested_field(fm_raw, "audit_state", "plan_safety_iterations")
        try:
            suf_iter = int(sufficiency_iter_str)
        except (ValueError, TypeError):
            suf_iter = 0
        try:
            ps_iter = int(plan_safety_iter_str)
        except (ValueError, TypeError):
            ps_iter = 0
        total_iter = suf_iter + ps_iter

        # Relative time
        if age_secs > 0:
            age_hours = age_secs / 3600
            if age_hours < 24:
                age_str = f"{age_hours:.0f} h ago"
            else:
                age_days = age_hours / 24
                age_str = f"{age_days:.1f} d ago"
        else:
            age_str = "<unknown>"

        lines.append(
            f"  {plan_id}  iter {total_iter}/10  "
            f'"audit awaiting human revision"  last commit {age_str}'
        )

    return lines


# ---------------------------------------------------------------------------
# Section 3: Context fullness
# ---------------------------------------------------------------------------
#
# The metric and the reasoning behind it are settled in
# Workbench/FOUNDRYREQ-plan_foundry_dev-20260803-1037-context-fullness-readout-not-a-handoff-alarm.md
# and must not be relitigated here. Context fullness is a level read from the
# LATEST assistant message's usage only - input_tokens + cache_read_input_tokens
# + cache_creation_input_tokens - never a sum across a session's messages.
# cache_read_input_tokens re-counts the whole conversation prefix on every
# turn, so a session-wide sum runs roughly quadratic in turn count and passes
# the window size while the context is still half empty. This section reports
# a number. It adds no threshold, colour, or handoff prompt - that reading
# belongs to the operator.


def _find_latest_transcript(projects_dir: Path) -> tuple[Path | None, str | None]:
    """
    Return (transcript path, unavailable-reason). Exactly one is None.

    The live session transcript sits as a *.jsonl file directly under
    projects_dir, named for the session id - a sibling of the same-named
    directory that holds that session's subagent records, not inside it.
    Among candidates, the most recently modified file is the current
    session's own transcript, since the harness appends to it on every turn.
    """
    if not projects_dir.is_dir():
        return None, f"no project transcript directory found at {projects_dir}"

    candidates = [p for p in projects_dir.iterdir() if p.is_file() and p.suffix == ".jsonl"]
    if not candidates:
        return None, f"no session transcript (*.jsonl) found under {projects_dir}"

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0], None


def _latest_assistant_usage(transcript_path: Path) -> tuple[dict | None, str | None]:
    """
    Return (usage dict, unavailable-reason). Exactly one is None.

    Scans every line of the transcript for an assistant message carrying a
    "usage" field and keeps the last one found, so the result reflects the
    latest message rather than any earlier one. A line that fails to parse
    as JSON is skipped and counted rather than treated as fatal - the read
    only fails when nothing usable turns up anywhere in the file.
    """
    try:
        text = transcript_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"could not read {transcript_path.name}: {exc}"

    latest_usage = None
    malformed = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        message = obj.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            usage = message.get("usage")
            if isinstance(usage, dict):
                latest_usage = usage

    if latest_usage is None:
        reason = f"no assistant message carrying usage found in {transcript_path.name}"
        if malformed:
            reason += f" ({malformed} malformed JSON line(s) skipped)"
        return None, reason

    return latest_usage, None


def compute_context_fullness(repo_root: Path, claude_projects_root: Path | None = None) -> dict:
    """
    Resolve the current session's transcript and read the resident-token
    figure from its latest assistant message.

    Returns a dict with keys available (bool), reason (str, set only when
    available is False), resident_tokens (int or None) and window_tokens
    (int or None). window_tokens is always None: no field in the transcript
    or in the message's model metadata carries a context window size, and
    this function never hardcodes one for a model, because a hardcoded
    figure goes stale the moment a new model ships.

    claude_projects_root defaults to ~/.claude/projects; pass it explicitly
    in tests so nothing here ever reads the real home directory.
    """
    if claude_projects_root is None:
        claude_projects_root = Path.home() / ".claude" / "projects"

    slug = derive_project_slug(repo_root)
    projects_dir = Path(claude_projects_root) / slug

    transcript_path, reason = _find_latest_transcript(projects_dir)
    if transcript_path is None:
        return {"available": False, "reason": reason, "resident_tokens": None, "window_tokens": None}

    usage, reason = _latest_assistant_usage(transcript_path)
    if usage is None:
        return {"available": False, "reason": reason, "resident_tokens": None, "window_tokens": None}

    try:
        resident_tokens = (
            int(usage.get("input_tokens", 0) or 0)
            + int(usage.get("cache_read_input_tokens", 0) or 0)
            + int(usage.get("cache_creation_input_tokens", 0) or 0)
        )
    except (TypeError, ValueError):
        return {
            "available": False,
            "reason": f"usage fields in {transcript_path.name} are not numeric",
            "resident_tokens": None,
            "window_tokens": None,
        }

    return {"available": True, "reason": None, "resident_tokens": resident_tokens, "window_tokens": None}


def render_context_fullness(repo_root: Path, claude_projects_root: Path | None = None) -> list[str]:
    """
    Render the context-fullness readout as a list of output lines (not
    including the section header). Never raises - a failure inside
    compute_context_fullness surfaces as an "unavailable" line, matching the
    fail-open discipline the rest of this module already follows.
    """
    try:
        result = compute_context_fullness(repo_root, claude_projects_root)
    except Exception as exc:  # noqa: BLE001 - fail-open by design, see module docstring
        return [f"  unavailable (unexpected error reading the transcript: {exc})"]

    if not result["available"]:
        return [f"  unavailable ({result['reason']})"]

    resident = result["resident_tokens"]
    window = result["window_tokens"]
    if window:
        pct = resident / window * 100
        return [f"  {resident} tokens resident ({pct:.0f} percent of a {window}-token window)"]
    return [f"  {resident} tokens resident (window size unknown)"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    workbench_arg = sys.argv[1] if len(sys.argv) > 1 else "Workbench"
    workbench_dir = Path(workbench_arg)
    repo_root = workbench_dir.parent

    now = datetime.now(timezone.utc)

    executor_lines = render_active_executors(workbench_dir, now)
    audit_lines = render_stalled_audits(workbench_dir, repo_root, now)
    context_lines = render_context_fullness(repo_root)

    if not executor_lines and not audit_lines:
        print("No active executors or stalled audits.")
    else:
        if executor_lines:
            print("Active executors:")
            for line in executor_lines:
                print(line)
            print()

        if audit_lines:
            print("Stalled audits:")
            for line in audit_lines:
                print(line)
            print()

    print("Context:")
    for line in context_lines:
        print(line)

    sys.exit(0)


if __name__ == "__main__":
    main()
