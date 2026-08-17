---
title: assigned_to Field - Valid Values
type: reference
description: Frontmatter field specifying who or what executes a PLAN file
---

# assigned_to Field

A free-text optional field naming the executor of the plan. The default is empty, and an empty value means the active session executes the plan.

## Valid Values

| Value | Meaning |
|---|---|
| `""` (empty) | **Default.** The active session executes the plan steps directly. Under plan-pipeline, the orchestrator dispatches the PLAN to the Sonnet default executor (`plan-executor`), size **S**. |
| `haiku` | **Legacy alias** - routes to the Sonnet default executor (`plan-executor`), because Haiku is retired as an execution tier (recalibrated 2026-07-04). Denotes a fully haiku-safe or mechanical PLAN, size **S**. |
| `sonnet` | Needs light judgement or a larger context - executed by `plan-executor-sonnet`. Size **M**. |
| `opus` | Design-heavy at execution time - executed by `plan-executor-opus` (Opus). Size **L**. An escape hatch, so prefer decomposition. |
| `human` | A human-led parent session drives the steps and no executor is dispatched. Under plan-pipeline the orchestrator halts at `checked` instead of dispatching - see the executor-tier table in [../../plan-pipeline/references/phase-state-machine.md](../../plan-pipeline/references/phase-state-machine.md), guarded by `scripts/ci/check-human-not-dispatched.py`. Size **XL** work that cannot be executor-run as one PLAN routes here or is decomposed. |
| (free-text other) | Optional: a note naming a specific tool, sub-agent, or external system. **It does not route.** Under plan-pipeline an unrecognised value is mapped to the default `plan-executor` exactly as an empty value is - see the executor-tier table in [../../plan-pipeline/references/phase-state-machine.md](../../plan-pipeline/references/phase-state-machine.md) and dispatch.md section 4C - so the orchestrator dispatches the Sonnet executor against the PLAN and the named system is never consulted. Use `human` when the intent is that no executor is dispatched. Document the value's meaning wherever the value is used. |

**Execution floor is Sonnet (recalibrated 2026-07-04).** The default executor runs Sonnet 5, and only `opus` escalates above that floor. Empty and `haiku` -> Sonnet `plan-executor` (size **S**), `sonnet` -> the identical `plan-executor-sonnet` (size **M**), `opus` -> `plan-executor-opus` (size **L**). See the phase-state-machine executor-tier table and [../../_shared/plan-safe.md](../../_shared/plan-safe.md) section Executor t-shirt sizing. When a PLAN carries a `size:` field it must agree with `assigned_to:` per that mapping.

## Examples

```yaml
# Default - active session executes
assigned_to: ""
status: ready

# Plan blocked on human action
assigned_to: ""
status: blocked
blocked_by: "Awaiting confirmation of which two commands to keep inline in CLAUDE.md"

# Human-driven steps, nothing waiting on a decision
assigned_to: human
size: XL
status: ready
```

**`assigned_to: human` and `status: blocked` are independent.** `assigned_to` states who performs the steps, while `status` states whether anything is waiting. A PLAN whose steps must be run from a parent session - because those steps invoke `plan-pipeline`, `ideate` or `write-input`, all outside the executor capability boundary in [../../_shared/executor-capability-boundary.md](../../_shared/executor-capability-boundary.md) - carries `assigned_to: human` and stays `ready` while the human is free to drive the PLAN. Set `status: blocked` only when something the human has not yet supplied is holding the work up, and name that thing in `blocked_by`.
