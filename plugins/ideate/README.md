# ideate

Three-phase ideation arc (Clarify → Survey → Converge) for shaping a problem into a plan-ready idea — imposes "requirement before mechanism" discipline and presents options with a recommendation.

## Install

```
/plugin marketplace add plan-foundry
/plugin install ideate
```

## Skills

| Skill | What it does |
|---|---|
| `ideate` | Interactive ideation assistant — walks three explicit phases (Clarify → Survey → Converge) to turn a fuzzy problem into a plan-ready idea. Runs in the parent session only (never as a subagent). |

## Optional dependency: plan-foundry-core

This plugin works **with or without** `plan-foundry-core`:

- **With core installed:** At Converge close, the plan-ready idea is transcribed as a Workbench PLAN via `Skill("write-plan")`. Mid-arc RESEARCH/ADVICE inputs are persisted via `Skill("write-input")`.
- **Without core:** At Converge close, the idea is written as plain markdown. Mid-arc inputs stay inline in the conversation.
- **Override:** Use `--output workbench` or `--output plain` to force either mode.

## Source

Part of [plan-foundry](../../README.md) — the plan-foundry harness mono-repo.
