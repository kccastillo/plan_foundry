# foundry-keeper

Self-improvement plugin for the plan-foundry harness — captures foundry-operation events into a unified JSONL log and surfaces patterns through monthly summaries.

## Install

```
/plugin marketplace add plan-foundry
/plugin install foundry-keeper
```

## What it does

- **Hook-driven capture:** A PostToolUse hook deterministically logs every skill call, tool use, and subagent dispatch to `.claude/_foundry_log.jsonl`. No reliance on Claude remembering to log.
- **Manual hiccup recording:** `foundry-log note-hiccup` lets the user record human-observed events worth tracking.
- **Monthly summariser:** `foundry-log summarise` dispatches a Haiku subagent to analyse the log — surfaces per-skill frequency, recurring hiccups, skill-miss candidates, and architectural drift signals.
- **Cross-project export:** `foundry-log export` bundles a date range for analysis across multiple projects.

## Skills

| Skill | What it does |
|---|---|
| `foundry-log` | Three modes — **note-hiccup** (manual entry), **summarise** (pattern analysis), **export** (date-range bundle for cross-project use). |

## Subagents

| Agent | Role | Model |
|---|---|---|
| `foundry-log-summariser` | Parse log slice, return structured findings | haiku |

## Optional dependency: plan-foundry-core

- **With core:** Summarise mode routes lessons to `Skill("lessons-learned")` jots and architectural findings to Workbench PLANs via `Skill("write-plan")`.
- **Without core:** The hook still captures events. Summarise prints findings to conversation instead of persisting them.

## Log schema

See `references/log-schema.md` for the versioned JSONL schema. Key event kinds: `skill_call`, `tool_use`, `subagent_start`, `subagent_stop`, `session_start`, `session_stop`, `hiccup`.

## Source

Part of [plan-foundry](../../README.md) — the plan-foundry harness mono-repo.
