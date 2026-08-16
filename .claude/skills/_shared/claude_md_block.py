"""
claude_md_block.py - Shared helper for managing the plan_foundry sentinel block in CLAUDE.md.

Extracted from init-plan-foundry's _step_claude_md so that plan-foundry-sync can apply
the same replace-between-markers logic without duplicating code.

Sentinel constants match those in run_install.py verbatim; build_block emits the same
WARNING comment and wrapping. apply_operating_rules_block reproduces _step_claude_md
branch-for-branch including returning ("FAIL", ...) without writing the file on
malformed markers.
"""

from __future__ import annotations

import pathlib
from typing import Optional

SENTINEL_START = "<!-- plan-foundry:init-plan-foundry:start -->"
SENTINEL_END = "<!-- plan-foundry:init-plan-foundry:end -->"


def build_block(operating_rules: str) -> str:
    """Return the full sentinel block as a string.

    Byte-identical to the inline block construction in run_install.py:215-222.
    """
    return (
        f"{SENTINEL_START}\n"
        "<!-- WARNING: content between these markers is managed by the plan_foundry init-plan-foundry skill. "
        "Re-running the skill replaces everything between the markers with the current operating-rules.md "
        "from the bundle. Do not hand-edit between markers - edits will be lost on re-run. -->\n\n"
        f"{operating_rules}\n"
        f"{SENTINEL_END}\n"
    )


def apply_operating_rules_block(
    target_root: pathlib.Path, operating_rules: str
) -> tuple[str, str]:
    """Apply (create/append/replace/skip) the sentinel block to <target_root>/CLAUDE.md.

    Reproduces _step_claude_md from run_install.py:223-253 branch-for-branch.

    Returns (cmd_status, cmd_note) where cmd_status is one of:
        "PASS"    - file was written (created, appended, or replaced)
        "SKIPPED" - block already current; file unchanged
        "FAIL"    - malformed markers; file NOT written (non-destructive)
    """
    block = build_block(operating_rules)
    claude_md = target_root / "CLAUDE.md"

    if not claude_md.exists():
        stub = (
            "# CLAUDE.md\n\n"
            "This file provides guidance to Claude Code when working with this repository.\n\n"
            f"{block}"
        )
        claude_md.write_text(stub, encoding="utf-8")
        return "PASS", "created"

    text = claude_md.read_text(encoding="utf-8")
    start_count = text.count(SENTINEL_START)
    end_count = text.count(SENTINEL_END)

    if start_count == 0 and end_count == 0:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        claude_md.write_text(text + sep + block, encoding="utf-8")
        return "PASS", "appended-block"

    if start_count == 1 and end_count == 1:
        s = text.find(SENTINEL_START)
        e = text.find(SENTINEL_END)
        if e < s:
            return "FAIL", "markers malformed (end before start)"
        e_line_end = text.find("\n", e)
        if e_line_end == -1:
            e_line_end = len(text)
        new_text = text[:s] + block + text[e_line_end + 1 :]
        body_between = text[s + len(SENTINEL_START) : e].strip("\n")
        if body_between == operating_rules.strip("\n") or text[s : e_line_end + 1] == block:
            return "SKIPPED", "already current"
        claude_md.write_text(new_text, encoding="utf-8")
        return "PASS", "replaced-block"

    return "FAIL", f"markers malformed (start_count={start_count}, end_count={end_count})"


def _sentinel_body(text: str) -> Optional[str]:
    """Return the body strictly between exactly one pair of sentinel markers
    in `text`, stripped of leading/trailing blank lines, or None when the
    markers are absent, duplicated, or malformed (end before start).
    """
    start_count = text.count(SENTINEL_START)
    end_count = text.count(SENTINEL_END)
    if start_count != 1 or end_count != 1:
        return None
    s = text.find(SENTINEL_START)
    e = text.find(SENTINEL_END)
    if e < s:
        return None
    return text[s + len(SENTINEL_START) : e].strip("\n")


def block_change_report(target_root: pathlib.Path, operating_rules: str) -> dict:
    """Compare the sentinel block currently on disk at <target_root>/CLAUDE.md
    to the block build_block(operating_rules) would put there, without
    writing anything.

    Returns {"status": ..., "removed_lines": [...], "added_lines": [...]}:
      - "additive" - every line present in the outgoing (current) body is
        also present in the incoming body build_block would write. Reordered
        lines still count as additive.
      - "non-additive" - at least one line in the outgoing body is absent
        from the incoming body.
      - "unavailable" - CLAUDE.md is absent, or its sentinel markers are
        missing, duplicated, or malformed (end before start).

    Compares against the body build_block(operating_rules) produces between
    the same markers, not against operating_rules alone - build_block
    prepends a managed-block WARNING comment every real target's block
    carries and operating_rules does not, so comparing against
    operating_rules directly would report that comment as removed on every
    sync. This mirrors apply_operating_rules_block's own
    `text[s:e_line_end + 1] == block` disjunct, which exists for the same
    reason.

    Comparison strips trailing whitespace from each line and ignores blank
    lines. Removed and added lines are returned verbatim, in their original
    order, never counted or truncated.

    Never writes and never raises - any OSError yields "unavailable".
    """
    empty = {"status": "unavailable", "removed_lines": [], "added_lines": []}
    target_root = pathlib.Path(target_root)
    claude_md = target_root / "CLAUDE.md"
    try:
        if not claude_md.exists():
            return dict(empty)
        text = claude_md.read_text(encoding="utf-8")
    except OSError:
        return dict(empty)

    outgoing_body = _sentinel_body(text)
    if outgoing_body is None:
        return dict(empty)

    incoming_block = build_block(operating_rules)
    incoming_body = _sentinel_body(incoming_block)
    if incoming_body is None:
        return dict(empty)

    def _clean_lines(body: str) -> list[str]:
        return [line.rstrip() for line in body.splitlines() if line.strip() != ""]

    outgoing_lines = _clean_lines(outgoing_body)
    incoming_lines = _clean_lines(incoming_body)
    incoming_set = set(incoming_lines)
    outgoing_set = set(outgoing_lines)

    removed_lines = [line for line in outgoing_lines if line not in incoming_set]
    added_lines = [line for line in incoming_lines if line not in outgoing_set]

    status = "non-additive" if removed_lines else "additive"
    return {"status": status, "removed_lines": removed_lines, "added_lines": added_lines}
