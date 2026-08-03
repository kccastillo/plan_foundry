---
name: autonomous-loop
description: "REQUIRES A SESSION THAT EXPOSES THE create_trigger ROUTINES TOOL - verified absent from desktop Claude Code on this bundle version (2026-07-27), where only session-scoped, non-durable CronCreate exists; the skill halts at its precondition rather than running. Drive a PLAN autonomously from drafted through complete without human intervention. Creates a create_trigger Routine (hourly, create_new_session_on_fire: true) that fires plan-pipeline on each session. Self-terminates via delete_trigger on completion, genuine human block, or exception. Covers pipeline_phase: drafted, checked, executing, outcome-verifying only - ideation (drafting) remains conversational. Trigger phrases: 'run autonomously', 'loop until done', 'autonomous loop on PLAN-XXX', 'drive this to complete'."
---

# autonomous-loop

Creates a server-side Routine (hourly cron, `create_new_session_on_fire: true`) that drives a PLAN through the plan-pipeline without human intervention across session boundaries. Each Routine firing reads fresh PLAN state from disk, advances the pipeline one or more phases, and self-terminates when the PLAN reaches a terminal or human-required state.

Per PLAN-AH1 D3 (Trigger Primitive), D5 (Ideation Scope), D7 (Concurrency posture), FM2 (cross-session IAL guard), FM4 (cost runaway mitigation), FM7 (artefact degradation mitigation).

## Skill workflow

See [workflows/run-loop.md](workflows/run-loop.md) for the step-by-step procedure.

## Inputs

- `plan_path` - absolute path to the PLAN file. Derived from current active PLAN if not supplied.

## Environment precondition - read before invoking

**Verified 2026-07-27 by the W2.2 model-drift check (RESEARCH-012): this skill does not run in a desktop Claude Code session on this bundle version.** It is not deprecated and it is not broken in its logic. Its stated primitive is unavailable here.

The design requires `create_trigger` with `create_new_session_on_fire: true`, so that each hourly firing starts a **clean session** and re-reads PLAN state from disk. `RESEARCH-010` selected that primitive for exactly those properties. The scheduling tools a desktop session exposes are `CronCreate`, `CronList` and `CronDelete`, which differ on four points that each independently break the design:

1. Jobs are **session-scoped**, not server-side, and are gone when the session exits.
2. Durable persistence is **explicitly unavailable** - the `durable` parameter is documented as having no effect.
3. There is **no new-session-on-fire parameter**, so a firing cannot start the clean session the re-grounding check depends on.
4. Jobs fire **only while the REPL is idle**, and recurring jobs auto-expire after seven days.

**What to expect.** Step 3 below calls `create_trigger`. Where that tool is absent the precondition fails and the skill halts without creating anything, which is the intended behaviour and is why this surfaced as an unmet precondition rather than a runaway loop.

**Scope of this warning.** It establishes that the primitive is absent from a desktop Claude Code session. It does **not** claim Routines exist nowhere - a `schedule` skill describing scheduled cloud agents is present, so another session type plausibly offers the required surface. If you are in such a session, the procedure below stands unchanged.

**Do not schedule work that depends on this skill** until it is re-based on the available primitive, re-scoped to the session types that expose Routines, or withdrawn. See `FOUNDRYREQ-plan_foundry_dev-20260727-1815-autonomous-loop-scheduling-primitive-absent` for the three options and `PLAN-AD2` standing constraints. For self-paced iteration **within** a single session, `ScheduleWakeup` and the `/loop` skill cover part of what this skill reaches for, though not the cross-session part.

## Preconditions

- PLAN exists on disk and is readable.
- PLAN `pipeline_phase` is one of: `drafted`, `checked`, `executing`, `outcome-verifying`.
- Not `drafting` (ideation is conversational - loop does not touch it).
- Not `complete` (already done - nothing for the loop to do).
- `create_trigger` tool is available in this session. **Frequently false - see the environment precondition above.** `CronCreate` is not a substitute: it is session-scoped and cannot start a new session on fire.

## Terminal conditions (loop self-terminates)

The Routine resolves `trigger_id` via `list_triggers(name='autonomous-loop-<plan-id>')` and calls `delete_trigger` when any of the following are reached:

1. `pipeline_phase: complete`
2. `pipeline_phase: outcome-verifying` with non-empty `human_pending`
3. `pipeline_phase: drafted` with `last_outcome: revision_needed` and `real_judgement_call` blockers remaining
4. Any `pipeline_phase: exception` / kanban halt
5. `total_loop_attempts >= 10` (IAL ceiling)

## Notifications

The `create_trigger` call sets `notifications: {push: true, email: true}` so all terminal escalations reach the human.

## Model policy

The loop dispatches only the tiers `plan-pipeline` already routes to - haiku, sonnet, opus per the PLAN's `assigned_to:`. **Fable is never dispatched from inside an autonomous loop, under any circumstances.** An unsupervised loop is the exact shape rule 3 of [../_shared/fable-escalation-policy.md](../_shared/fable-escalation-policy.md) forbids: a single escalation is permitted, an iterate-until-satisfied loop is not, and each firing here would look individually defensible while the aggregate cost is unbounded. If a firing genuinely cannot proceed on Opus, that is a terminal condition - escalate to the human via the notification path rather than raising the tier.

## Trigger naming

Routine name: `autonomous-loop-<plan-id>` (deterministic; resolved at runtime via `list_triggers` for `delete_trigger` - trigger_id is NOT injected at creation time, per PLAN-AH1 mechanically-forced decision).
