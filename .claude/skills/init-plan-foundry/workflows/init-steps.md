# init-plan-foundry workflow

Idempotent eight-step bootstrap. Each step PASSes (the operation landed), SKIPPEDs (already present, no action needed), or FAILs (operation could not complete; report and continue).

## Step 1: Resolve bundle install path

Read `PLAN_FOUNDRY_BUNDLE_PATH` from the environment; default to `~/.claude/plan_foundry/` (expanduser). Verify the path exists and contains `.claude/skills/init-plan-foundry/operating-rules.md`.

- **Bundle missing or operating-rules.md absent** → FAIL Step 1 with diagnostic "plan_foundry bundle not found at {path} — clone https://github.com/kccastillo/plan_foundry into ~/.claude/plan_foundry first." Abort.
- **OK** → record the absolute path as `BUNDLE_PATH` and the operating-rules.md path as `BUNDLE_OPERATING_RULES_PATH`. PASS.

## Step 2: Compute target repo root

The current working directory IS the target repo root. Record as `TARGET_ROOT`.

## Step 3: Create the coarse `.claude` symlink

Compute `LINK = TARGET_ROOT/.claude`; `BUNDLE_CLAUDE = BUNDLE_PATH/.claude`.

- If `LINK` is already a symlink whose resolved target equals `BUNDLE_CLAUDE` → SKIPPED (idempotent re-run).
- If `LINK` is a symlink pointing somewhere else → FAIL with diagnostic "<target>/.claude is a symlink to {other}; expected {BUNDLE_CLAUDE}. Resolve manually." Abort.
- If `LINK` is a real directory with content → FAIL with diagnostic "<target>/.claude exists as a real directory; refusing to destroy. Move/remove it manually, then re-run init-plan-foundry." Abort.
- If `LINK` is absent → create the symlink with Python: `os.symlink(BUNDLE_CLAUDE, LINK, target_is_directory=True)`. On Windows this requires Developer Mode (already enabled per session memory). PASS.

## Step 4: Ensure Workbench/ directory

Check if `Workbench/` exists in the target root. If absent, create it (use Write tool with a `Workbench/.gitkeep` placeholder to materialise the directory) — PASS. If present, SKIPPED.

## Step 5: Ensure current-month LOG file

Read `Workbench/` and look for any file matching `*_LOG_YYYYMM.md` where `YYYYMM` is the current year-month. If present, SKIPPED. If absent, create `Workbench/YYYYMMDDHHMI_LOG_YYYYMM.md` (using current timestamp) with this exact body:

```
---
title: "[Project Name] Work Log — [Month Year]"
type: log
month: YYYY-MM
status: open
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
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
```

Replace `YYYY-MM`, `YYYY-MM-DD` placeholders with the current date. PASS.

## Step 6: Ensure Retired/ directory

Check if `Retired/` exists. If absent, create it with a `Retired/.gitkeep` placeholder — PASS. If present, SKIPPED.

## Step 7: Ensure .gitignore entries

Read `.gitignore` (create if absent). Scan for the literal strings `Retired/`, `Workbench/.heartbeat/`, and `.claude` on their own lines. For each absent entry, append it. If all present, SKIPPED. Otherwise PASS with diagnostic listing which entries were added.

**Rationale (D10):** the target's `.claude` is a symlink to `~/.claude/plan_foundry/.claude`, which is not part of the target's tracked content. Gitignoring `.claude` keeps the symlink local-only. Targets that want shareable foundry skills can selectively un-gitignore, but that is opt-in.

## Step 8: Ensure target CLAUDE.md awareness (inline content between sentinel markers)

First, read `BUNDLE_OPERATING_RULES_PATH` (from Step 1) and record its full content as `OPERATING_RULES_CONTENT`.

Then check if `CLAUDE.md` exists in the target root.

**If absent:** Create `CLAUDE.md` using the template at `../templates/claude-md-stub.md` (read the template, substitute `{{OPERATING_RULES_CONTENT}}` with `OPERATING_RULES_CONTENT`, write the result to `CLAUDE.md`). PASS.

**If present:** Read the file. Count occurrences of `<!-- plan-foundry:init-plan-foundry:start -->` (call it `START_COUNT`) and `<!-- plan-foundry:init-plan-foundry:end -->` (call it `END_COUNT`).

- **If `START_COUNT == 0` AND `END_COUNT == 0`** (sentinels absent): Append the following block to the end of the file (preserve a leading blank line if the file does not already end with one):

  ```

  <!-- plan-foundry:init-plan-foundry:start -->
  <!-- WARNING: content between these markers is managed by the plan_foundry init-plan-foundry skill. Re-running the skill replaces everything between the markers with the current operating-rules.md from the bundle. Do not hand-edit between markers — edits will be lost on re-run. -->

  {{OPERATING_RULES_CONTENT}}
  <!-- plan-foundry:init-plan-foundry:end -->
  ```

  Substitute `{{OPERATING_RULES_CONTENT}}` with the content read above. PASS.

- **If `START_COUNT == 1` AND `END_COUNT == 1` AND end appears AFTER start** (sentinels well-formed): Extract the current content between the start and end markers (exclusive of the marker lines themselves). Strip one leading newline and one trailing newline. Compare byte-for-byte to `OPERATING_RULES_CONTENT`. If equal, SKIPPED. Otherwise replace the between-markers content with `OPERATING_RULES_CONTENT`. PASS.

- **Any other case** (`START_COUNT != 1` OR `END_COUNT != 1` OR end appears BEFORE start): FAIL with diagnostic "CLAUDE.md sentinel markers are malformed (START_COUNT=N, END_COUNT=M); manual repair required."

## Step 9: Surface restart notice

Print to the human: "RESTART Claude Code for project-local skills to register. After restart, slash commands like `/init-plan-foundry`, `/plan-foundry-check-current`, `/test-foundry` will be available; `Skill(\"plan-pipeline\")` etc. will resolve."

## Reporting

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` if no FAILs; `exception` if Step 1, 2, or 3 FAILed (skill cannot proceed without the bundle path / writable target / non-conflicting `.claude`).
- `payload.step_results`: object with keys `step_1` through `step_9`, each value one of `PASS` / `SKIPPED` / `FAIL`.
- `payload.summary`: one-line human-readable summary.
- `diagnostics`: any per-step diagnostic notes.
