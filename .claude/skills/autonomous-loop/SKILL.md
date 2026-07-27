---
name: autonomous-loop
description: "Drive a PLAN autonomously from drafted through complete without human intervention. Creates a create_trigger Routine (hourly, create_new_session_on_fire: true) that fires plan-pipeline on each session. Self-terminates via delete_trigger on completion, genuine human block, or exception. Covers pipeline_phase: drafted, checked, executing, outcome-verifying only — ideation (drafting) remains conversational. Trigger phrases: 'run autonomously', 'loop until done', 'autonomous loop on PLAN-XXX', 'drive this to complete'."
---

# autonomous-loop

Creates a server-side Routine (hourly cron, `create_new_session_on_fire: true`) that drives a PLAN through the plan-pipeline without human intervention across session boundaries. Each Routine firing reads fresh PLAN state from disk, advances the pipeline one or more phases, and self-terminates when the PLAN reaches a terminal or human-required state.

Per PLAN-AH1 D3 (Trigger Primitive), D5 (Ideation Scope), D7 (Concurrency posture), FM2 (cross-session IAL guard), FM4 (cost runaway mitigation), FM7 (artefact degradation mitigation).

## Skill workflow

See [workflows/run-loop.md](workflows/run-loop.md) for the step-by-step procedure.

## Inputs

- `plan_path` — absolute path to the PLAN file. Derived from current active PLAN if not supplied.

## Preconditions

- PLAN exists on disk and is readable.
- PLAN `pipeline_phase` is one of: `drafted`, `checked`, `executing`, `outcome-verifying`.
- Not `drafting` (ideation is conversational — loop does not touch it).
- Not `complete` (already done — nothing for the loop to do).
- `create_trigger` tool is available in this session.

## Terminal conditions (loop self-terminates)

The Routine resolves `trigger_id` via `list_triggers(name='autonomous-loop-<plan-id>')` and calls `delete_trigger` when any of the following are reached:

1. `pipeline_phase: complete`
2. `pipeline_phase: outcome-verifying` with non-empty `human_pending`
3. `pipeline_phase: drafted` with `audit_state.last_outcome: revision_needed` after `auto_fix_iterations >= 2` AND `real_judgement_call` blockers remain
4. Any `pipeline_phase: exception` / kanban halt
5. `total_loop_attempts >= 10` (IAL ceiling)

## Notifications

The `create_trigger` call sets `notifications: {push: true, email: true}` so all terminal escalations reach the human.

## Trigger naming

Routine name: `autonomous-loop-<plan-id>` (deterministic; resolved at runtime via `list_triggers` for `delete_trigger` — trigger_id is NOT injected at creation time, per PLAN-AH1 mechanically-forced decision).
