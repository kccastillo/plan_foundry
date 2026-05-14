---
name: foundry-log
description: Manage the foundry operation log — note hiccups, summarise patterns, export for cross-project analysis. Three modes: "note-hiccup" (manual entry), "summarise" (on-demand or monthly-rollover summary), "export" (date-range bundle). Trigger phrases: "note a hiccup", "log a hiccup", "summarise the foundry log", "foundry summary", "export foundry log".
---

## What this skill does

Manages the unified foundry operation log (`.claude/_foundry_log.jsonl`). Mechanical events (tool use, skill calls, subagent lifecycle, session boundaries) are captured automatically by the hook script — this skill handles the human-facing operations.

## Modes

### `note-hiccup`
Record a human-observed event. The user describes what happened; the skill appends a `kind: hiccup` entry to the log with the current timestamp.

### `summarise`
Analyse the log for the current month (or a specified date range). Dispatches the `foundry-log-summariser` Haiku subagent to parse the JSONL, compute per-kind/per-skill statistics, and surface patterns:
- Recurring hiccups → `lessons-learned` jots (if plan-foundry-core installed)
- Architectural findings (zero-call skills, persistent misfires) → Workbench PLAN (if plan-foundry-core installed)
- Without core: findings printed to conversation

### `export`
Bundle a date range of log entries into a single file for cross-project analysis. Output: `foundry-log-export-YYYYMMDD-YYYYMMDD.jsonl` in the project root.

## Output mode (soft dependency on plan-foundry-core)

- **With core:** Summarise mode routes findings to `Skill("lessons-learned")` jots and `Skill("write-plan")` for architectural findings.
- **Without core:** Findings are printed to conversation. The hook still captures events regardless.

<essential_principles>
The hook captures mechanical events deterministically — this skill handles human-judged events and analysis.
Append-only log — never rewrite history. Entries are immutable once written.
Schema-versioned per line for forward compatibility.
The summariser subagent runs in isolated context to handle large logs without blowing the parent's context window.
</essential_principles>

<constraints>
- Never delete or modify existing log entries
- Never write hiccups without a user-provided summary — do not infer or fabricate events
- Summariser subagent handles log parsing — do not read large log files directly in the parent session
- Export mode writes to project root, not inside `.claude/`
</constraints>

<success_criteria>
- `note-hiccup`: a valid JSONL entry with `kind: hiccup` appended to the log
- `summarise`: findings surfaced with actionable patterns; lessons-learned jots created (with core) or printed (without)
- `export`: a valid JSONL file written to project root covering the specified date range
</success_criteria>

**Log schema:** See [references/log-schema.md](references/log-schema.md).
