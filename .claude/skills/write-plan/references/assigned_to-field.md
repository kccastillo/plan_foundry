---
title: assigned_to Field - Valid Values
type: reference
description: Frontmatter field specifying who or what executes a PLAN file
---

# assigned_to Field

Free-text optional field naming the executor of the plan. Default empty (the active session executes).

## Valid Values

| Value | Meaning |
|---|---|
| `""` (empty) | **Default.** The active session executes the plan steps directly. Under plan-pipeline, dispatched to the Sonnet default executor (`plan-executor`), size **S**. |
| `haiku` | **Legacy alias** - routes to the Sonnet default executor (`plan-executor`); Haiku is retired as an execution tier (recalibrated 2026-07-04). Denotes a fully haiku-safe / mechanical PLAN, size **S**. |
| `sonnet` | Needs light judgement / larger context - executed by `plan-executor-sonnet`. Size **M**. |
| `opus` | Design-heavy at execution time - executed by `plan-executor-opus` (Opus 4.8). Size **L**. Escape hatch; prefer decomposition. |
| `human` | Plan requires human action/decision before execution can begin. Plan status should be `blocked` with `blocked_by` explaining what the human needs to do. Size **XL** work that cannot be executor-run as one PLAN routes here or is decomposed. |
| (free-text other) | Optional: a specific tool, sub-agent, or external system that should execute. Document the value's meaning where it's used. |

**Execution floor is Sonnet (recalibrated 2026-07-04).** The default executor runs Sonnet 5; only `opus` escalates. Empty/`haiku` -> Sonnet `plan-executor` (size **S**), `sonnet` -> the identical `plan-executor-sonnet` (size **M**), `opus` -> `plan-executor-opus` (size **L**). See the phase-state-machine executor-tier table and [../../_shared/plan-safe.md](../../_shared/plan-safe.md) section Executor t-shirt sizing. When a PLAN carries a `size:` field it must agree with `assigned_to:` per that mapping.

## Examples

```yaml
# Default - active session executes
assigned_to: ""
status: ready

# Plan blocked on human action
assigned_to: ""
status: blocked
blocked_by: "Awaiting confirmation of which two commands to keep inline in CLAUDE.md"
```
