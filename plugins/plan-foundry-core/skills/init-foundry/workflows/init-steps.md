# init-foundry workflow

Idempotent six-step bootstrap. Each step PASSes (the operation landed), SKIPPEDs (already present, no action needed), or FAILs (operation could not complete; report and continue).

## Step 1: Resolve plugin install path

Use Glob to locate the plan-foundry-core install: `~/.claude/plugins/cache/*/plan-foundry-core/operating-rules.md`. Record matches as a list.

- **Zero matches** → FAIL Step 1 with diagnostic "plan-foundry-core install not found under ~/.claude/plugins/cache/*/. Confirm the plugin is installed: `/plugin install plan-foundry-core@plan-foundry`." Abort.
- **Exactly one match** → record its absolute path as `PLUGIN_OPERATING_RULES_PATH`. PASS.
- **Multiple matches** → FAIL Step 1 with diagnostic: "Multiple plan-foundry-core installs found at: {paths}. Please disambiguate by running `/plugin marketplace remove <name>` for the marketplace you no longer want, then re-run init-foundry." Abort. (Silent-pick risks bootstrapping against a stale or fork copy whose operating-rules.md diverges from the intended one.)

## Step 2: Ensure Workbench/ directory

Check if `Workbench/` exists in the project root. If absent, create it (use Write tool with a placeholder file like `Workbench/.gitkeep` to materialise the directory) — PASS. If present, SKIPPED.

## Step 3: Ensure current-month LOG file

Read `Workbench/` and look for any file matching `*_LOG_YYYYMM.md` where `YYYYMM` is the current year-month (use the session's date, e.g. 202605 for May 2026). If present, SKIPPED. If absent, create `Workbench/YYYYMMDDHHMI_LOG_YYYYMM.md` (using current timestamp YYYYMMDDHHMI) with this exact body:

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

## Step 4: Ensure Retired/ directory

Check if `Retired/` exists. If absent, create it with a `Retired/.gitkeep` placeholder — PASS. If present, SKIPPED.

## Step 5: Ensure .gitignore entries

Read `.gitignore` (create if absent). Scan for the literal strings `Retired/` and `Workbench/.heartbeat/` on their own lines. For each absent entry, append it. If both present, SKIPPED. Otherwise PASS with diagnostic listing which entries were added.

## Step 6: Ensure consumer CLAUDE.md awareness (inline content between sentinel markers)

First, read `PLUGIN_OPERATING_RULES_PATH` (from Step 1) and record its full content as `OPERATING_RULES_CONTENT`.

Then check if `CLAUDE.md` exists in the project root.

**If absent:** Create `CLAUDE.md` using the template at `../templates/claude-md-stub.md` (read the template, substitute `{{OPERATING_RULES_CONTENT}}` with `OPERATING_RULES_CONTENT`, write the result to `CLAUDE.md`). PASS.

**If present:** Read the file. Count occurrences of `<!-- plan-foundry:init-foundry:start -->` (call it `START_COUNT`) and `<!-- plan-foundry:init-foundry:end -->` (call it `END_COUNT`).

- **If `START_COUNT == 0` AND `END_COUNT == 0`** (sentinels absent): Append the following block to the end of the file (preserve a leading blank line if the file does not already end with one):

  ```

  <!-- plan-foundry:init-foundry:start -->
  <!-- WARNING: content between these markers is managed by the plan-foundry init-foundry skill. Re-running the skill replaces everything between the markers with the current operating-rules.md from the plugin. Do not hand-edit between markers — edits will be lost on re-run. To customise, edit the plugin's operating-rules.md or move the content outside the markers. -->

  {{OPERATING_RULES_CONTENT}}
  <!-- plan-foundry:init-foundry:end -->
  ```

  Substitute `{{OPERATING_RULES_CONTENT}}` with the content read above. PASS.

- **If `START_COUNT == 1` AND `END_COUNT == 1` AND end appears AFTER start** (sentinels well-formed): Extract the current content between the start and end markers (exclusive of the marker lines themselves). Strip one leading newline and one trailing newline introduced by the wrapping. Compare byte-for-byte to `OPERATING_RULES_CONTENT`. If equal, SKIPPED (no change needed). Otherwise replace the between-markers content (preserve the warning comment immediately after the start marker) with `OPERATING_RULES_CONTENT`. PASS.

- **Any other case** (`START_COUNT != 1` OR `END_COUNT != 1` OR end appears BEFORE start): FAIL Step 6 with diagnostic "CLAUDE.md sentinel markers are malformed (START_COUNT=N, END_COUNT=M, order=...); manual repair required. Expected exactly one start marker followed by exactly one end marker." Do not attempt automatic recovery.

## Reporting

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` if no FAILs; `exception` if Step 1 FAILed (skill cannot proceed without the plugin path).
- `payload.step_results`: object with keys `step_1` through `step_6`, each value one of `PASS` / `SKIPPED` / `FAIL`.
- `payload.summary`: one-line human-readable summary.
- `diagnostics`: any per-step diagnostic notes.
