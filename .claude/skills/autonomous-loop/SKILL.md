---
name: autonomous-loop
disable-model-invocation: true
description: "Requires a session exposing the create_trigger Routines tool - verified absent from desktop Claude Code on this bundle version (2026-07-27), where only session-scoped, non-durable CronCreate exists, so the skill halts at its precondition rather than running. Drive a PLAN autonomously from drafted through complete without human intervention. Creates a create_trigger Routine (hourly, create_new_session_on_fire: true) that fires plan-pipeline on each session. Self-terminates via delete_trigger on completion, genuine human block, or exception. Covers pipeline_phase: drafted, checked, executing, outcome-verifying only - ideation (drafting) remains conversational. Trigger phrases: 'run autonomously', 'loop until done', 'autonomous loop on PLAN-XXX', 'drive this to complete'."
---

# autonomous-loop

Creates a Routine - a server-side hourly cron trigger, configured here with `create_new_session_on_fire: true` - that drives a PLAN through the plan-pipeline without human intervention across session boundaries. The session each Routine firing starts reads fresh PLAN state from disk, advances the pipeline one or more phases, and deletes the Routine when the PLAN reaches a terminal or human-required state.

The design commits to six things, and the rest of this file states each one where it applies: a server-side trigger primitive rather than a session-scoped job, no coverage of ideation, deference to any interactive session holding the orchestrator lock, a cross-session ceiling on total attempts that guards against the IAL - the infinite agentic loop, the non-termination failure mode where each firing looks individually reasonable and the run never ends - a cost warning raised before that ceiling is reached, and a re-grounding read of the PLAN at every firing so the loop cannot advance against a stale picture of it.

## Skill workflow

See [workflows/run-loop.md](workflows/run-loop.md) for the step-by-step procedure.

## Inputs

- `plan_path` - absolute path to the PLAN file. Derived from current active PLAN if not supplied.

## Environment precondition - read before invoking

**Verified 2026-07-27 by a model-drift check run against a live desktop Claude Code session: this skill does not run there on this bundle version.** The skill is not deprecated and the procedure below is sound. The skill halts because the primitive the design requires is absent from a desktop session.

The design requires `create_trigger` with `create_new_session_on_fire: true`, so that each hourly firing starts a **clean session** and re-reads PLAN state from disk. The primitive was selected for exactly those properties. The scheduling tools a desktop session exposes are `CronCreate`, `CronList` and `CronDelete`, which differ from `create_trigger` in ways that each independently break the design:

1. Jobs are **session-scoped**, not server-side, and are gone when the session exits.
2. Durable persistence is **explicitly unavailable** - the `durable` parameter is documented as having no effect.
3. There is **no new-session-on-fire parameter**, so a firing cannot start the clean session the re-grounding check depends on.
4. Jobs fire **only while the REPL is idle**, and recurring jobs auto-expire after seven days.

**What to expect.** Step 3 below calls `create_trigger`. Where that tool is absent the precondition fails and the skill halts without creating anything, which is the intended behaviour and is why the absence surfaced as an unmet precondition rather than as a runaway loop.

**Scope of this warning.** The warning establishes that the primitive is absent from a desktop Claude Code session, and it makes no claim that Routines are absent everywhere - a `schedule` skill describing scheduled cloud agents is present, so another session type plausibly exposes the required surface. If you are in such a session, the procedure below stands unchanged.

**Do not schedule work that depends on this skill** until the skill is re-based on the available primitive, re-scoped to the session types that expose Routines, or withdrawn. Those three are the whole option set. For self-paced iteration **within** a single session, `ScheduleWakeup` and the `/loop` skill cover part of what this skill is designed to do, though not the cross-session part.

## Preconditions

- PLAN exists on disk and is readable.
- PLAN `pipeline_phase` is one of: `drafted`, `checked`, `executing`, `outcome-verifying`.
- Not `drafting`, because ideation is conversational and the loop does not drive ideation.
- Not `complete`, because a complete PLAN leaves the loop nothing to advance.
- `create_trigger` tool is available in this session. **This precondition is frequently false - see the environment precondition above.** `CronCreate` is not a substitute, because `CronCreate` is session-scoped and cannot start a new session on fire.

## Terminal conditions (loop self-terminates)

The session started by a Routine firing resolves `trigger_id` via `list_triggers(name='autonomous-loop-<plan-id>')` and calls `delete_trigger` when any of the following is reached:

1. `pipeline_phase: complete`
2. `pipeline_phase: outcome-verifying` with non-empty `human_pending`
3. `pipeline_phase: drafted` with `last_outcome: revision_needed` and `real_judgement_call` blockers remaining
4. Any `pipeline_phase: exception` / kanban halt
5. `total_loop_attempts >= 10` (IAL ceiling)

## Notifications

The `create_trigger` call sets `notifications: {push: true, email: true}` so all terminal escalations reach the human.

## Model policy

The session started by a Routine firing dispatches only the tiers `plan-pipeline` already routes to - haiku, sonnet, opus per the PLAN's `assigned_to:`. A PLAN carrying `assigned_to: human` is never dispatched by the loop either, because `plan-pipeline` halts at `checked` for that value, and an unattended loop is the worst place to route around a halt whose whole point is that a human drives the steps. **Fable is never dispatched from inside an autonomous loop, under any circumstances.** An unsupervised loop is the exact shape rule 3 of [../_shared/fable-escalation-policy.md](../_shared/fable-escalation-policy.md) forbids: a single escalation is permitted, an iterate-until-satisfied loop is not, and each firing here would look individually defensible while the aggregate cost is unbounded. If a firing genuinely cannot proceed on Opus, that is a terminal condition - escalate to the human via the notification path rather than raising the tier.

## Trigger naming

Routine name: `autonomous-loop-<plan-id>`, which is deterministic and is resolved at runtime via `list_triggers` for `delete_trigger`, because `trigger_id` is not known until `create_trigger` returns and so cannot be injected into the Routine's own prompt at creation time.
