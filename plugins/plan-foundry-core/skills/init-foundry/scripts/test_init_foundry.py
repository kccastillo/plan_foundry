#!/usr/bin/env python3
"""
test_init_foundry.py — Smoke test for the init-foundry skill.

The skill itself is markdown prose interpreted by Claude Code. This test
does NOT invoke an LLM. It does two things:

1. **Static contract checks** — assert the skill's artifacts are coherent:
   - Plugin's `operating-rules.md` exists
   - SKILL.md, workflow doc, and template reference the same sentinel markers
   - Template has the {{OPERATING_RULES_CONTENT}} placeholder

2. **Mechanical simulation** — a Python translation of the 6-step bootstrap
   from workflows/init-steps.md, run against a temp dir. Asserts the
   expected files/contents are produced; runs the simulation TWICE and
   asserts idempotency.

The simulation is NOT a replacement for Claude executing the skill — it's
a contract test that the *mechanical effects described by the spec* are
deterministically reproducible. If the prose spec changes, this test
should be updated to match.

Run from the repo root:
    python3 plugins/plan-foundry-core/skills/init-foundry/scripts/test_init_foundry.py

Exit 0 = all assertions pass; non-zero on failure.
"""

from __future__ import annotations

import datetime
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_repo_root() -> Path:
    """Walk up from this file to find plan-foundry's repo root."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".claude-plugin" / "marketplace.json").exists():
            return current
        current = current.parent
    raise SystemExit("ERROR: could not locate plan-foundry repo root.")


REPO_ROOT = find_repo_root()
PLUGIN_ROOT = REPO_ROOT / "plugins" / "plan-foundry-core"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "init-foundry"

SENTINEL_START = "<!-- plan-foundry:init-foundry:start -->"
SENTINEL_END = "<!-- plan-foundry:init-foundry:end -->"


# ---------------------------------------------------------------------------
# Test harness (lightweight)
# ---------------------------------------------------------------------------

_failures: list[str] = []
_passes: list[str] = []


def expect(condition: bool, label: str) -> None:
    if condition:
        _passes.append(label)
        print(f"  PASS: {label}")
    else:
        _failures.append(label)
        print(f"  FAIL: {label}", file=sys.stderr)


def expect_equal(actual, expected, label: str) -> None:
    if actual == expected:
        _passes.append(label)
        print(f"  PASS: {label}")
    else:
        _failures.append(f"{label}: expected {expected!r}, got {actual!r}")
        print(f"  FAIL: {label}: expected {expected!r}, got {actual!r}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Part 1: Static contract checks
# ---------------------------------------------------------------------------

def test_static_artifacts():
    print("\n── Static contract checks ──")

    skill_md = SKILL_ROOT / "SKILL.md"
    workflow_md = SKILL_ROOT / "workflows" / "init-steps.md"
    template_md = SKILL_ROOT / "templates" / "claude-md-stub.md"
    operating_rules = PLUGIN_ROOT / "operating-rules.md"

    expect(skill_md.exists(), "init-foundry SKILL.md exists")
    expect(workflow_md.exists(), "init-foundry workflows/init-steps.md exists")
    expect(template_md.exists(), "init-foundry templates/claude-md-stub.md exists")
    expect(operating_rules.exists(), "plan-foundry-core/operating-rules.md exists")

    if template_md.exists():
        template = template_md.read_text(encoding="utf-8")
        expect(SENTINEL_START in template, "template contains start sentinel")
        expect(SENTINEL_END in template, "template contains end sentinel")
        expect("{{OPERATING_RULES_CONTENT}}" in template,
               "template has {{OPERATING_RULES_CONTENT}} placeholder")

    if workflow_md.exists():
        workflow = workflow_md.read_text(encoding="utf-8")
        expect(SENTINEL_START in workflow, "workflow doc references start sentinel")
        expect(SENTINEL_END in workflow, "workflow doc references end sentinel")
        expect(SENTINEL_START in workflow and workflow.index(SENTINEL_START) < workflow.index(SENTINEL_END),
               "workflow doc: start sentinel appears before end sentinel")

    if skill_md.exists():
        skill = skill_md.read_text(encoding="utf-8")
        expect(SENTINEL_START in skill, "SKILL.md references start sentinel")
        expect(SENTINEL_END in skill, "SKILL.md references end sentinel")


# ---------------------------------------------------------------------------
# Part 2: Mechanical 6-step simulation
# ---------------------------------------------------------------------------

LOG_TEMPLATE = """---
title: "[Project Name] Work Log — {month_label}"
type: log
month: {yyyy_mm}
status: open
created: {yyyy_mm_dd}
last_updated: {yyyy_mm_dd}
---

## Status Table

| Plan File | Title | Assigned | Priority | Status | Due |
|---|---|---|---|---|---|

## Recurring Task Tracker

| Task | Slug | Cadence | Last Done | Next Due | Status |
|---|---|---|---|---|---|

## Context Inputs This Month

| Input File | Type | From | Feeds Plan | Integrated? |
|---|---|---|---|---|

## Lessons Learned

_(none carried forward)_
"""


def simulate_init_foundry(target_dir: Path, operating_rules_content: str) -> dict:
    """Translate the 6-step workflow into Python. Operates on target_dir.
    Returns step_results dict matching the skill's expected return shape."""
    results: dict[str, str] = {}

    # Step 1: Resolve plugin install path — in the simulation, we pass the
    # operating-rules content directly. The real skill globs ~/.claude/plugins/...
    # We mark Step 1 as PASS because the content was provided.
    results["step_1"] = "PASS"

    # Step 2: Ensure Workbench/ directory
    workbench = target_dir / "Workbench"
    if workbench.is_dir():
        results["step_2"] = "SKIPPED"
    else:
        workbench.mkdir(parents=True)
        (workbench / ".gitkeep").write_text("", encoding="utf-8")
        results["step_2"] = "PASS"

    # Step 3: Ensure current-month LOG
    now = datetime.datetime.now()
    yyyymm = now.strftime("%Y%m")
    yyyy_mm = now.strftime("%Y-%m")
    yyyy_mm_dd = now.strftime("%Y-%m-%d")
    month_label = now.strftime("%B %Y")

    existing_logs = list(workbench.glob(f"*_LOG_{yyyymm}.md"))
    if existing_logs:
        results["step_3"] = "SKIPPED"
    else:
        stamp = now.strftime("%Y%m%d%H%M")
        log_path = workbench / f"{stamp}_LOG_{yyyymm}.md"
        log_path.write_text(
            LOG_TEMPLATE.format(
                month_label=month_label, yyyy_mm=yyyy_mm, yyyy_mm_dd=yyyy_mm_dd
            ),
            encoding="utf-8",
        )
        results["step_3"] = "PASS"

    # Step 4: Ensure Retired/ directory
    retired = target_dir / "Retired"
    if retired.is_dir():
        results["step_4"] = "SKIPPED"
    else:
        retired.mkdir(parents=True)
        (retired / ".gitkeep").write_text("", encoding="utf-8")
        results["step_4"] = "PASS"

    # Step 5: Ensure .gitignore entries
    gitignore = target_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("", encoding="utf-8")
    text = gitignore.read_text(encoding="utf-8")
    entries_needed = ["Retired/", "Workbench/.heartbeat/"]
    missing = [e for e in entries_needed if e not in text.splitlines()]
    if not missing:
        results["step_5"] = "SKIPPED"
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n".join(missing) + "\n"
        gitignore.write_text(text, encoding="utf-8")
        results["step_5"] = "PASS"

    # Step 6: Ensure CLAUDE.md awareness
    claude_md = target_dir / "CLAUDE.md"
    stub_template_path = SKILL_ROOT / "templates" / "claude-md-stub.md"
    stub_template = stub_template_path.read_text(encoding="utf-8")

    if not claude_md.exists():
        claude_md.write_text(
            stub_template.replace("{{OPERATING_RULES_CONTENT}}", operating_rules_content),
            encoding="utf-8",
        )
        results["step_6"] = "PASS"
    else:
        existing = claude_md.read_text(encoding="utf-8")
        start_count = existing.count(SENTINEL_START)
        end_count = existing.count(SENTINEL_END)
        if start_count == 0 and end_count == 0:
            # Append sentinel block at end
            block = (
                f"\n{SENTINEL_START}\n"
                "<!-- WARNING: content between these markers is managed by the plan-foundry init-foundry skill. Re-running the skill replaces everything between the markers with the current operating-rules.md from the plugin. Do not hand-edit between markers — edits will be lost on re-run. To customise, edit the plugin's operating-rules.md or move the content outside the markers. -->\n\n"
                f"{operating_rules_content}\n"
                f"{SENTINEL_END}\n"
            )
            if not existing.endswith("\n"):
                existing += "\n"
            claude_md.write_text(existing + block, encoding="utf-8")
            results["step_6"] = "PASS"
        elif start_count == 1 and end_count == 1 and existing.index(SENTINEL_START) < existing.index(SENTINEL_END):
            start_pos = existing.index(SENTINEL_START) + len(SENTINEL_START)
            end_pos = existing.index(SENTINEL_END)
            between = existing[start_pos:end_pos]
            # Strip the warning comment then check if operating_rules_content matches.
            # The skill's idempotency rule: compare byte-for-byte against operating_rules_content.
            # Our simulation is simpler: rebuild the block fresh; if identical bytes, SKIPPED.
            new_block_inner = (
                "\n"
                "<!-- WARNING: content between these markers is managed by the plan-foundry init-foundry skill. Re-running the skill replaces everything between the markers with the current operating-rules.md from the plugin. Do not hand-edit between markers — edits will be lost on re-run. To customise, edit the plugin's operating-rules.md or move the content outside the markers. -->\n\n"
                f"{operating_rules_content}\n"
            )
            if between == new_block_inner:
                results["step_6"] = "SKIPPED"
            else:
                rebuilt = (
                    existing[:existing.index(SENTINEL_START)]
                    + SENTINEL_START
                    + new_block_inner
                    + SENTINEL_END
                    + existing[end_pos + len(SENTINEL_END):]
                )
                claude_md.write_text(rebuilt, encoding="utf-8")
                results["step_6"] = "PASS"
        else:
            results["step_6"] = "FAIL"

    return results


def test_simulation_fresh_dir():
    print("\n── Mechanical simulation: fresh dir ──")
    operating_rules = (PLUGIN_ROOT / "operating-rules.md").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        results = simulate_init_foundry(tmp, operating_rules)
        expect_equal(results["step_1"], "PASS", "Step 1: plugin path resolved")
        expect_equal(results["step_2"], "PASS", "Step 2: Workbench/ created")
        expect_equal(results["step_3"], "PASS", "Step 3: monthly LOG created")
        expect_equal(results["step_4"], "PASS", "Step 4: Retired/ created")
        expect_equal(results["step_5"], "PASS", "Step 5: .gitignore entries added")
        expect_equal(results["step_6"], "PASS", "Step 6: CLAUDE.md created from template")

        # Verify expected artifacts
        expect((tmp / "Workbench").is_dir(), "Workbench/ exists after Step 2")
        expect(any((tmp / "Workbench").glob("*_LOG_*.md")), "Workbench has monthly LOG")
        expect((tmp / "Retired").is_dir(), "Retired/ exists after Step 4")
        gi = (tmp / ".gitignore").read_text(encoding="utf-8")
        expect("Retired/" in gi.splitlines(), ".gitignore contains Retired/")
        expect("Workbench/.heartbeat/" in gi.splitlines(), ".gitignore contains Workbench/.heartbeat/")
        claude_md = (tmp / "CLAUDE.md").read_text(encoding="utf-8")
        expect(SENTINEL_START in claude_md, "CLAUDE.md has start sentinel")
        expect(SENTINEL_END in claude_md, "CLAUDE.md has end sentinel")
        expect(operating_rules in claude_md, "CLAUDE.md inlines operating-rules.md content")
        expect("{{OPERATING_RULES_CONTENT}}" not in claude_md,
               "CLAUDE.md placeholder was substituted, not left as literal")


def test_simulation_idempotency():
    print("\n── Mechanical simulation: idempotency (second run is no-op) ──")
    operating_rules = (PLUGIN_ROOT / "operating-rules.md").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        # First run
        first = simulate_init_foundry(tmp, operating_rules)
        # Snapshot file state
        files_before = {
            p.relative_to(tmp).as_posix(): p.read_bytes()
            for p in tmp.rglob("*") if p.is_file()
        }
        # Second run
        second = simulate_init_foundry(tmp, operating_rules)
        files_after = {
            p.relative_to(tmp).as_posix(): p.read_bytes()
            for p in tmp.rglob("*") if p.is_file()
        }

        expect_equal(second["step_2"], "SKIPPED", "Step 2 idempotent (Workbench/ already exists)")
        expect_equal(second["step_3"], "SKIPPED", "Step 3 idempotent (LOG already exists)")
        expect_equal(second["step_4"], "SKIPPED", "Step 4 idempotent (Retired/ already exists)")
        expect_equal(second["step_5"], "SKIPPED", "Step 5 idempotent (.gitignore entries already present)")
        expect_equal(second["step_6"], "SKIPPED", "Step 6 idempotent (CLAUDE.md content matches)")
        expect_equal(files_before, files_after, "File state byte-identical after second run")


def test_simulation_existing_claude_md_with_no_sentinels():
    print("\n── Mechanical simulation: existing CLAUDE.md without sentinels gets block appended ──")
    operating_rules = (PLUGIN_ROOT / "operating-rules.md").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        # Seed with existing CLAUDE.md that has no sentinels
        original = "# My Project\n\nSome existing content.\n"
        (tmp / "CLAUDE.md").write_text(original, encoding="utf-8")

        results = simulate_init_foundry(tmp, operating_rules)
        expect_equal(results["step_6"], "PASS", "Step 6: sentinel block appended to existing CLAUDE.md")

        result = (tmp / "CLAUDE.md").read_text(encoding="utf-8")
        expect(result.startswith(original.rstrip("\n")),
               "Original CLAUDE.md content preserved at top")
        expect(SENTINEL_START in result, "Start sentinel appended")
        expect(SENTINEL_END in result, "End sentinel appended")
        expect(operating_rules in result, "Operating rules content inlined")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"test_init_foundry.py — running smoke tests against {REPO_ROOT}")

    test_static_artifacts()
    test_simulation_fresh_dir()
    test_simulation_idempotency()
    test_simulation_existing_claude_md_with_no_sentinels()

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {len(_passes)} PASS, {len(_failures)} FAIL")
    if _failures:
        print("\nFailures:")
        for f in _failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
