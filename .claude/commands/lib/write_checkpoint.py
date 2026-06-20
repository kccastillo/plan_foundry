"""
write_checkpoint.py — Write an ideate conversation checkpoint to Workbench/.ideate-checkpoint/.

Generates a checkpoint markdown file capturing the current ideate session state.
Invoked by the /checkpoint slash command during ideate phases 1–3.

Usage:
    python write_checkpoint.py [thread_id]

    thread_id (optional): Override the auto-detected thread ID. If not supplied,
        the script detects the active ideate PLAN or generates a timestamp-based ID.

Exit 0 on success, non-zero on error.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Workbench relative to this script: ../../../../Workbench
# (commands/lib/ -> commands/ -> .claude/ -> repo root / Workbench/)
_THIS_DIR = Path(__file__).parent.resolve()
_REPO_ROOT = _THIS_DIR.parent.parent.parent.parent.resolve()
_WORKBENCH_DIR = _REPO_ROOT / "Workbench"

CHECKPOINT_DIR_NAME = ".ideate-checkpoint"
PLAN_PATTERN = re.compile(r"^\d{12}_PLAN_")


# ---------------------------------------------------------------------------
# Active thread detection
# ---------------------------------------------------------------------------

def detect_active_ideate_thread(workbench_dir: Path) -> str | None:
    """
    Scan Workbench/*.md for a PLAN with pipeline_phase: drafting AND ideate_phase: "".

    Returns the plan_id (file stem) of the first matching PLAN, or None if not found.

    A PLAN in this state is in phases 1–3 of the ideate cadence — the conversational
    arc has begun (plan-writer created the PLAN file at Phase 1 exit) but the state
    field has not yet been set (phases 1–3 are lazy; ideate_phase is empty).
    """
    if not workbench_dir.exists():
        return None

    for md_file in sorted(workbench_dir.iterdir()):
        if not md_file.name.endswith(".md"):
            continue
        if not PLAN_PATTERN.match(md_file.name):
            continue

        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        if "type: plan" not in text:
            continue

        # Check pipeline_phase: drafting
        pp_match = re.search(r"^pipeline_phase:\s*(.+)$", text, re.MULTILINE)
        if not pp_match:
            continue
        pp = pp_match.group(1).strip().strip('"').strip("'")
        if " #" in pp:
            pp = pp[:pp.index(" #")].strip()
        if pp != "drafting":
            continue

        # Check ideate_phase: empty or absent
        ip_match = re.search(r"^ideate_phase:\s*(.*)$", text, re.MULTILINE)
        if ip_match:
            ideate_phase = ip_match.group(1).strip().strip('"').strip("'")
            if " #" in ideate_phase:
                ideate_phase = ideate_phase[:ideate_phase.index(" #")].strip()
            if ideate_phase and ideate_phase not in ("", "null", "~"):
                # ideate_phase is set — not in phases 1–3
                continue

        # Found a PLAN in drafting with no ideate_phase
        return md_file.stem

    return None


# ---------------------------------------------------------------------------
# Checkpoint writing
# ---------------------------------------------------------------------------

def generate_thread_id() -> str:
    """Generate a timestamp-based thread ID in YYYYMMDDHHMI format."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d%H%M")


def write_checkpoint(workbench_dir: Path, thread_id: str) -> Path:
    """
    Write a checkpoint file to Workbench/.ideate-checkpoint/<thread-id>.md.

    The file contains a template with placeholders for the user to fill in.

    Args:
        workbench_dir: Path to the Workbench/ directory.
        thread_id: Thread identifier (from active plan detection or timestamp).

    Returns:
        Path to the written checkpoint file.
    """
    checkpoint_dir = workbench_dir / CHECKPOINT_DIR_NAME
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = checkpoint_dir / f"{thread_id}.md"

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    content = f"""\
# Ideate Checkpoint — {thread_id}

_Written by /checkpoint at {now_str}._
_Fill in placeholders below before committing._

---

## Created

{now_str}

## Thread ID

{thread_id}

## Current Phase

_(Human: fill in the current phase — Clarify / Survey / Converge / or the ideate trigger phrase used)_

## Conversation Summary

_(Human: write a 2–5 sentence summary of the ideation progress so far. What problem are we solving? What options were considered? What has been decided?)_

## Open Questions

_(Human: list any questions that are still open and need resolution before the spec can be finalised)_

- [ ]

## Decisions Captured So Far

_(Human: list decisions that have been explicitly locked or affirmed during this session)_

**Already locked (Human-affirmed):**
-

**Mechanically forced:**
-

**Real judgement calls (still open):**
-

## Resumption Notes

_(Human: any context needed to resume this session — e.g. which PLAN file, what the human's last instruction was, what the next step is)_

To resume: "resume ideate {thread_id}" — reads this file, loads the PLAN state, and continues the arc from the recorded phase.
"""

    checkpoint_path.write_text(content, encoding="utf-8")
    return checkpoint_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for write_checkpoint.py.

    Args:
        argv: Command-line arguments (default: sys.argv[1:]).

    Returns:
        0 on success, non-zero on error.
    """
    if argv is None:
        argv = sys.argv[1:]

    workbench_dir = _WORKBENCH_DIR

    # Allow override via environment or argument
    if argv:
        thread_id = argv[0]
    else:
        # Try to detect active ideate thread
        detected = detect_active_ideate_thread(workbench_dir)
        if detected:
            thread_id = detected
            print(f"Active ideate thread detected: {thread_id}")
        else:
            thread_id = generate_thread_id()
            print(f"No active ideate thread found. Using timestamp-based ID: {thread_id}")

    try:
        checkpoint_path = write_checkpoint(workbench_dir, thread_id)
        print(f"Checkpoint written: {checkpoint_path}")
        print(f"Fill in the placeholders in {checkpoint_path.name} before committing.")
        return 0
    except OSError as e:
        print(f"Error writing checkpoint: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
