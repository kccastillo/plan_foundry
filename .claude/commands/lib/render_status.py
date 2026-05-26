"""
render_status.py — Render live executor status and stalled audit summary.

Two output sections:
  1. Active executors: one line per heartbeat file in Workbench/.heartbeat/*.json
  2. Stalled audits: PLANs in `drafted` phase with audit_state.last_outcome: revision_needed
     AND > 24 hours since audit_state.last_audit_commit was written.

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
# Constants
# ---------------------------------------------------------------------------

STALE_THRESHOLD_SECONDS = 600       # 10 minutes → executor considered hung
STALLED_AUDIT_THRESHOLD_SECONDS = 86400  # 24 hours → audit stalled

# LOG file pattern (to skip)
LOG_PATTERN = re.compile(r"^\d{12}_LOG_")
# PLAN file pattern
PLAN_PATTERN = re.compile(r"^\d{12}_PLAN_")


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
                return len(re.findall(r"^\d+\.", steps_section.group(1), re.MULTILINE))
        except OSError:
            pass
        return 0

    for hb_file in heartbeat_files:
        try:
            data = json.loads(hb_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            lines.append(f"  [warning: {hb_file.name} unreadable — {exc}]")
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
        if LOG_PATTERN.match(md_file.name):
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
# Main
# ---------------------------------------------------------------------------

def main():
    workbench_arg = sys.argv[1] if len(sys.argv) > 1 else "Workbench"
    workbench_dir = Path(workbench_arg)
    repo_root = workbench_dir.parent

    now = datetime.now(timezone.utc)

    executor_lines = render_active_executors(workbench_dir, now)
    audit_lines = render_stalled_audits(workbench_dir, repo_root, now)

    if not executor_lines and not audit_lines:
        print("No active executors or stalled audits.")
        sys.exit(0)

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

    sys.exit(0)


if __name__ == "__main__":
    main()
