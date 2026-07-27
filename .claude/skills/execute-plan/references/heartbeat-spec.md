# Heartbeat Spec - Executor Live Progress Observability

The executor writes a sibling `.heartbeat/<plan-id>.json` file as it runs. This file provides a live signal of execution progress to the `/status` command and INDEX projection alerts.

---

## JSON Schema

```json
{
  "schema_version": 1,
  "plan_id": "<plan-id>",
  "phase": "starting | running | halting | exited",
  "current_step": 3,
  "step_summary": "<first ~80 chars of the PLAN step text>",
  "last_tick_at": "2026-05-13T10:00:00Z",
  "notes": "<optional free-text, e.g. 'halt reason'",
  "tool_calls_since_last_tick": 0
}
```

### Field definitions

| Field | Type | Description |
|---|---|---|
| `schema_version` | integer | Always `1` in v1. |
| `plan_id` | string | The PLAN filename stem (e.g. `PLAN-023_executor-heartbeat`). |
| `phase` | enum | `starting` (before step 1 executes), `running` (mid-execution), `halting` (halt path taken), `exited` (executor finished, result recorded). |
| `current_step` | integer | 1-based index of the step currently executing (or most recently entered). |
| `step_summary` | string | First ~80 chars of the PLAN step body, for human-readable display in `/status`. |
| `last_tick_at` | ISO 8601 UTC string | Timestamp of the most recent heartbeat write. |
| `notes` | string | Optional. Populated on `halting`/`exited` with e.g. the halt reason or the outcome enum. |
| `tool_calls_since_last_tick` | integer | Count of Read/Write/Edit/Glob/Grep calls since the last heartbeat write; reset to 0 on each write. |

---

## Tick Cadence

The executor writes the heartbeat file at three event types:

1. **Step entry** - at the top of each step in the per-step loop. `phase: running`, `current_step: N`, `step_summary` from PLAN body. This is a mandatory write (no coalescing).

2. **Per-tool-call (coalesced <= 1 per 30 seconds within the same step)** - after each Read, Write, Edit, Glob, or Grep call, increment `tool_calls_since_last_tick`. If >= 30s has elapsed since `last_tick_at`, write the heartbeat and reset the counter. This prevents flooding writes during tight loops while keeping the signal fresh.

3. **Halt / exit** - on halt path detection (`phase: halting`) and on final executor exit (`phase: exited`). Both are mandatory writes (no coalescing). The `notes` field is populated with the halt reason or outcome enum.

The initial write at Step 1 (before any steps execute) uses `phase: starting`, `current_step: 0`.

---

## Idempotency Preservation

Heartbeat writes are strictly out-of-band. They do NOT:
- Mutate the PLAN body or any PLAN frontmatter fields (except `last_executor_outcome`, which is written via the normal Executor Notes path).
- Affect state machine transitions (the orchestrator never routes on heartbeat data - heartbeat is diagnostics-only).
- Block or condition execution flow (a failed heartbeat write is logged and skipped; the executor continues).

The heartbeat file may be absent, stale, or malformed at any time without breaking idempotency. Consumers (the `/status` command, INDEX alerts, orchestrator diagnostics) must handle all three cases gracefully.

---

## Lifecycle

| Event | Action |
|---|---|
| Executor reaches Step 1 | Write initial heartbeat (`phase: starting`); create `.heartbeat/` directory on first write. |
| Each PLAN step entry | Write heartbeat (`phase: running`, `current_step: N`). |
| Halt path detected | Write heartbeat (`phase: halting`, `notes: <reason>`). |
| Executor exits (any outcome) | Write final heartbeat (`phase: exited`, `notes: <outcome enum>`). |
| Orchestrator: `outcome: success` (-> `outcome-verifying`) | Orchestrator deletes the heartbeat file immediately after the success commit. |
| Orchestrator: `outcome: revision_needed` (-> reverts to `drafted`) | Orchestrator deletes the heartbeat file immediately after the revert commit. |
| Orchestrator: `outcome: exception` (kanban halt) | Heartbeat PRESERVED as forensic data. Deleted when the human resumes via override/extract/dispute/different-auditor action (the halt-recovery routine in `dispatch.md` deletes it). |

---

## File path convention

```
Workbench/.heartbeat/<plan-id>.json
```

Where `<plan-id>` is the PLAN filename stem (without `.md`). Example:

```
Workbench/.heartbeat/PLAN-023_executor-heartbeat.json
```

The `.heartbeat/` directory is gitignored (`Workbench/.heartbeat/` in `.gitignore`). It is created on first write by the executor; its absence is normal on a fresh clone.

---

## Resumption checkpoint (deferred)

**Decision:** D2 - Defer heartbeat resumption checkpoint (PLAN-AC7, 2026-05-22).

### Proposal (what was considered)

A resumption checkpoint would extend the heartbeat file with two additional fields:

```json
{
  "last_completed_step": 4,
  "checkpoint_written_at": "2026-05-22T10:00:00Z"
}
```

Written to `Workbench/.heartbeat/<plan-id>.json` alongside the existing fields, this would let
the orchestrator re-enter a long-running PLAN at the last verified Step boundary rather than
restarting from Step 1 after a session disruption or context-rot failure.

### Why deferred

Implementing resumption checkpoints requires three changes that are out of scope for PLAN-AC7:

1. **Idempotency invariant rewrite.** The current spec's idempotency section states: "Heartbeat
   writes are strictly out-of-band. They do NOT affect state machine transitions (the orchestrator
   never routes on heartbeat data - heartbeat is diagnostics-only)." A resumption checkpoint
   consumed by the orchestrator for re-entry violates this invariant directly. Rewriting it
   requires a principled invariant-impact statement and a new "checkpoint-consumed" mode
   distinguishable from the existing diagnostics-only mode.

2. **Checkpoint schema and consumer wiring.** The orchestrator's `dispatch.md` and
   `phase-state-machine.md` would need a new re-entry path: detect a valid checkpoint, skip
   completed steps, and re-enter at `last_completed_step + 1`. This is non-trivial wiring with
   its own edge cases (checkpoint stale, step already idempotent, partial writes).

3. **Shape-defining architectural choice.** Choosing between "re-enter at last step" vs.
   "re-run from last verified step" vs. "re-run entire PLAN idempotently" is a design decision
   that warrants its own ideate cadence and PLAN - not a paragraph in a bounding PLAN.

Folding this implementation into PLAN-AC7 would itself be a long-horizon-execution risk (the
very failure mode the Plan-AC7 ceiling is designed to mitigate).

### Empirical trigger for re-opening

This decision should be re-opened when context-rot is empirically observed in production runs:
specifically, when two or more long-PLAN executions (> 8 Steps) fail late (Step 6+) with
degraded outputs attributable to accumulated context drift rather than logic errors in the Steps
themselves. At that point, the cost of implementing the resumption-checkpoint mechanism is
justified by observed failure data rather than theoretical risk.

Until that trigger fires, the heartbeat remains diagnostics-only per the idempotency invariant.

---

## Error handling

If a heartbeat write fails (e.g. filesystem permission, disk full):
1. Log a one-line warning in the executor's progress trace (visible in the session transcript but not written to PLAN frontmatter).
2. Continue execution. The heartbeat is best-effort.
3. Do NOT set `outcome: exception` for a heartbeat write failure alone.

If a heartbeat file is malformed JSON when read:
- `/status` command: skip and log a one-line warning.
- `build_index.py`: skip and log a one-line warning.
- `dispatch.md` idempotency check: skip with a one-line log and proceed.
