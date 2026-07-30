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
