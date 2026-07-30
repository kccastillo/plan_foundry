# Autonomous Loop - Run Procedure

## Step 1: Validate and accept input

Accept `plan_path` as input (absolute path to the target PLAN file). If not supplied, derive from the current active PLAN (the most recently referenced PLAN in this conversation).

Read the PLAN file. If unreadable -> surface error and exit.

Parse `pipeline_phase` from frontmatter. Validate:
- Accepted phases: `drafted`, `checked`, `executing`, `outcome-verifying`.
- If `drafting` -> exit: "autonomous-loop does not drive ideation. Re-invoke after ideate completes and pipeline_phase is drafted."
- If `complete` -> exit: "PLAN is already complete. No Routine needed."
- If absent or unknown -> exit with diagnostic.

Extract `plan_id` from frontmatter (e.g. `PLAN-AH1`).

## Step 2: Construct absolute PLAN path

Confirm `plan_path` is absolute. If relative, prepend the repo root path so the Routine fires into the correct file regardless of session working directory.

## Step 3: Create the Routine

Call `create_trigger` with the following parameters:

```
name: "autonomous-loop-<plan-id>"
cron_expression: "0 * * * *"
create_new_session_on_fire: true
notifications: {push: true, email: true}
prompt: <see Routine prompt template below>
```

**Routine prompt template** - substitute `<absolute PLAN path>` and `<plan-id>` at Routine creation time:

```
Re-grounding check (run first, before any other action):
  Re-read <absolute PLAN path> from disk. Verify pipeline_phase, audit_state, and
  verification_state match what this Routine expects for PLAN <plan-id>. If the PLAN
  is already complete or pipeline_phase differs from the expected handoff state,
  surface a diagnostic and exit without advancing.

Concurrency deference check (run after re-grounding, before incrementing):
  Read the orchestrator lock at Workbench/.orchestrator.lock (if it exists).
  If the lock is held AND acquired_at is within the last LOCK_TTL_SECONDS (3600 s):
    Compute lock_age = now - acquired_at (seconds).
    If lock_age > 3 * LOCK_TTL_SECONDS (i.e. > 10800 s / 3 hours):
      Surface "autonomous loop for <plan-id> - lock held for more than 3 hours.
        Check for a stalled interactive run." and exit.
    Otherwise: exit cleanly without incrementing total_loop_attempts and without
      writing anything to frontmatter.
  If the lock is absent or acquired_at is older than LOCK_TTL_SECONDS: treat as free,
  proceed.
  Interactive sessions always win; this Routine is supplementary.

Cross-session IAL guard:
  Read total_loop_attempts from frontmatter (default 0 if absent).
  If total_loop_attempts >= 10: resolve trigger_id via list_triggers
    (match name == 'autonomous-loop-<plan-id>'), call delete_trigger with that
    trigger_id, surface "autonomous loop ceiling reached for <plan-id>.
    Human review required." and exit.
  If total_loop_attempts >= 8: surface a warning "autonomous loop for <plan-id> is at
    {total_loop_attempts}/10 attempts - review spend before it self-terminates."
    (then continue - this is a warning, not a halt).
  Increment total_loop_attempts by 1. Write updated total_loop_attempts to frontmatter
  before dispatching any subagent or advancing any phase.

Run the plan-pipeline skill on <absolute PLAN path>.
Invoke Skill("plan-pipeline") with plan_path set to <absolute PLAN path>.
Read pipeline_phase from frontmatter after each phase advance.

Terminal conditions - if any of the following are reached, first resolve trigger_id via
list_triggers (match name == 'autonomous-loop-<plan-id>'), call delete_trigger with
that trigger_id, THEN surface the message:
  - pipeline_phase is complete:
      "PLAN-<plan-id> complete. Autonomous loop Routine terminated."
  - pipeline_phase is outcome-verifying AND verification_state.human_pending is
    non-empty:
      "PLAN-<plan-id> requires human attestation: [items]. Awaiting input.
       Autonomous loop Routine terminated."
  - pipeline_phase is drafted AND audit_state.last_outcome is revision_needed AND
    audit_state.auto_fix_iterations >= 2 AND triaged_human_items contains
    real_judgement_call entries:
      "PLAN-<plan-id> blocked on real_judgement_call items after 2 auto-fix attempts:
       [items]. Awaiting human input. Autonomous loop Routine terminated."
  - Any exception / kanban halt:
      Surface the diagnostics. "PLAN-<plan-id> halted at [phase]. Autonomous loop
       Routine terminated. See diagnostics."
  - total_loop_attempts >= 10 (handled above in IAL guard - Routine already terminated).

Otherwise exit normally. The Routine fires again next hour and advances further phases.
```

## Step 4: Report to the operator

Surface the following after successful `create_trigger`:

```
Autonomous loop Routine created.
  Routine name:  autonomous-loop-<plan-id>
  PLAN:          <absolute PLAN path>
  Firing:        hourly (0 * * * *)
  Notifications: push + email

The Routine will advance PLAN-<plan-id> through the pipeline each hour. It self-terminates
on completion, human-required attestation, real_judgement_call escalation, exception, or
after 10 total loop attempts.

trigger_id is resolved at runtime via list_triggers - it is not stored here (bootstrapping
constraint: trigger_id is unknown until after create_trigger returns and cannot be injected
into the Routine's own prompt).

To cancel the loop manually:
  list_triggers -> find the entry named 'autonomous-loop-<plan-id>' -> note its id
  delete_trigger(trigger_id=<id>)
```

## Operating notes

- The Routine defers to any active interactive session holding the orchestrator lock (D7). If the lock is held by another session, the Routine exits without advancing or writing anything to frontmatter. Interactive sessions win.
- `total_loop_attempts` is incremented on every non-deferred firing. A deferred firing (lock held) does NOT increment the counter.
- The `total_loop_attempts` counter is in `OWNED_FIELDS` (orchestrator_state_guard.py) so the snapshot/restore guard protects it. It is NOT zeroed on `drafted`-revert (it spans resets to maintain the IAL guard across auto-fix cycles).
- The IAL ceiling of 10 attempts ensures the composition of hourly cron + per-session MAX_ITERATIONS is bounded end-to-end (FM2).
- The within-2-of-ceiling warning at `>= 8` attempts is FM4's cost-runaway mitigation.
- The re-grounding check at Routine startup re-reads the PLAN from disk to verify state before proceeding - this is FM7's artefact-degradation mitigation.
