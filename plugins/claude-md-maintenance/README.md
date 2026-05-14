# claude-md-maintenance

Audit, propose additions to, and prune CLAUDE.md and CONTEXT_CONSTITUTION.md — keeping your Claude Code project configuration current and lean.

## Install

```
/plugin marketplace add plan-foundry
/plugin install claude-md-maintenance
```

## Skills

| Skill | What it does |
|---|---|
| `maintain-claude-md` | Three modes — **audit** (scan against checklist, produce punch-list), **add** (propose additions with exact diff), **prune** (propose removals). Output lands as a file for human approval before any edit happens. |

## Optional dependency: plan-foundry-core

This plugin works **with or without** `plan-foundry-core`:

- **With core installed:** Audit findings are written as a Workbench PLAN via `Skill("write-plan")`, integrating with the full plan-foundry pipeline.
- **Without core:** Findings are written as plain markdown (`claude-md-audit-findings.md` in project root). Same content, standalone.
- **Override:** Use `--output workbench` or `--output plain` to force either mode.

## Source

Part of [plan-foundry](../../README.md) — the plan-foundry harness mono-repo.
