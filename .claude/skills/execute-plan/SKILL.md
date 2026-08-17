---
name: execute-plan
description: 'Plan execution skill. Runs a PLAN from Workbench/ end-to-end - executes steps in order, populates Executor Notes, writes last_executor_outcome to PLAN frontmatter. Caller (plan-pipeline orchestrator or Human) commits and pushes. Trigger phrases: "execute this plan", "implement the plan", "run PLAN_x", "ok implement".'
---

<essential_principles>
Execute the plan as written - do not redesign, re-scope, or improve mid-flight.
Execute steps in order. Verify each before moving on.
If a step is ambiguous, unsafe, or marked [Human]: halt and flag. Do not improvise.
Always populate Executor Notes before returning to the caller (caller commits + pushes per parent PLAN 202605011400 decisions 13, 22).
On closure (outcome=done), if frontmatter sets parent_plan_of_plans, apply the plan-of-plans sync (workflows/execute-steps.md Step 4.5).
Git commit and push are the caller's responsibility (e.g. plan-pipeline orchestrator, or the Human during bootstrap) - execute-plan no longer commits or pushes. The caller commits at every milestone and pushes per `push_policy` (read via `_shared/push_policy.get_push_policy(plan_path)`). When push_policy=`manual`, commit only and surface `<push_status>commit landed locally; push manual per push_policy. Run \`git push\` when ready.</push_status>`.
Retirement of the PLAN file is the caller's responsibility - execute-plan no longer auto-retires.
On any halt (success or failure), write `last_executor_outcome` to PLAN frontmatter so callers can route deterministically (parent PLAN 202605011400 decision 24).
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23. No XML payload, no HTML escaping.
**Executor uses filesystem tools, never Bash, for mechanical Steps.** See the **Invariant: Subagent Permission Inheritance** section below for the underlying constraint. Create/copy/move/read/grep/edit operations go through Read, Write, Edit, Glob, Grep - not `mkdir`/`cp`/`mv`/`cat`/`grep`/`sed` shell calls. The plan-executor agents enforce this structurally via `disallowedTools: [Bash, ...]`. Bash is not needed for self-verification of `verify:`/`acceptance:` items - the orchestrator's outcome-verifying phase (decision 25) re-runs those in parent context, where the allowlist works correctly. The executor self-ticks Verification boxes based on filesystem-tool observations only.
**Write heartbeat on entry to each Step.** Before executing the body of each PLAN step, write `Workbench/.heartbeat/<plan-id>.json` with `phase: running`, `current_step: N`, and `step_summary` from the PLAN body. See `references/heartbeat-spec.md` for the full schema. Heartbeat writes are best-effort - if the Write fails, log a one-line warning and continue.
**Write heartbeat on every filesystem tool call (coalesce to <= 1 per 30 s within the same step).** After each Read, Write, Edit, Glob, or Grep call, increment `tool_calls_since_last_tick`. If >= 30 s has elapsed since the last heartbeat write, write the heartbeat and reset the counter. This keeps the signal fresh without flooding writes.
</essential_principles>

## Invariant: Subagent Permission Inheritance

The canonical statement of this invariant is recorded in [`/ARCHITECTURE.md`](../../../ARCHITECTURE.md#invariants-register). In summary: subagents dispatched via the Agent tool do not inherit the parent's `permissions.allow` allowlist (Anthropic GH #37730, closed not-planned). Consequence for this skill: the executor cannot rely on shell tooling, so plan-executor agent variants carry `disallowedTools: [Bash, WebFetch, WebSearch]` structurally, and the orchestrator re-runs `verify:`/`acceptance:` shell lines in parent context (decision 25).

## Heartbeat Observability

The executor writes a live progress signal to `Workbench/.heartbeat/<plan-id>.json` as the executor runs. This allows the `/status` command and INDEX projection alerts to show which step is executing and whether the executor has stalled.

Full schema, tick cadence, lifecycle, and error-handling rules: see [references/heartbeat-spec.md](references/heartbeat-spec.md).

**Key points:**
- `.heartbeat/` is gitignored, and the first write creates the directory.
- Heartbeat writes are best-effort: failure does not halt execution.
- The orchestrator deletes the heartbeat on `outcome: success` / `revision_needed`, and preserves the file on `outcome: exception` for forensics.
- The orchestrator never routes on heartbeat data - heartbeat data is diagnostics-only.

<preconditions>
Before starting, confirm:
- PLAN file exists in Workbench/ with `status: ready`
- PLAN is not in `status: blocked` and `blocked_by` is empty - blocks are cleared by `write-input` when the requisite input lands, or by the Human explicitly saying "proceed without" (Human clears `blocked_by` manually in that case)
- The human has authorised execution (trigger phrase in this skill's description)
</preconditions>

**Plan-safe definition:** See [../_shared/plan-safe.md](../_shared/plan-safe.md) - single source of truth shared with check-plan.

<skill_invocation_semantics>
**Invoking a skill from a PLAN step:**

When a PLAN step says "Invoke `Skill("skill-name", "args")`", the executor's role is:
1. Call `Skill("skill-name", "args")`
2. Read the returned SKILL.md documentation (skill call returns the skill's SKILL.md)
3. Execute the documented workflow steps using available tools (Read, Write, Edit, Bash, Glob, Grep, etc.)
4. The Skill() call *loads the instructions*, and the executor runs them

The skill framework does not self-execute. The executor reads the skill's workflow files and implements the steps using the available tools.

**Example:** A PLAN step says "Run atomise on break_glass_requirement.md". The executor:
- Calls `Skill("atomise", "mode:production file:Production/Staging/break_glass_requirement.md")`
- Reads the returned SKILL.md, which references `workflows/atomise-steps.md`
- Reads atomise-steps.md to see the detailed workflow (Steps 1-7)
- Executes each step manually using Read, Write, Bash, etc., creating atom files as directed
</skill_invocation_semantics>

<constraints>
- **Frontmatter write allowlist (T14, 2026-05-13).** The executor may write only these PLAN frontmatter fields:
  - `last_executor_outcome` - the structured executor verdict (outcome / outcome_subtype / executed / diagnostics_summary).
  - The Executor Notes section body (not frontmatter - body markdown only).
- **Frontmatter write forbidlist (T14, 2026-05-13).** The executor MUST NOT write any of the following - they are orchestrator-owned and the orchestrator flips them after outcome-verifying:
  - `status` (terminal status: done / partially-complete / blocked / needs-revision)
  - `pipeline_phase` (drafting / drafted / checked / executing / outcome-verifying / complete)
  - `audit_state` and any of its subfields
  - `verification_state` and any of its subfields
  - `audit_acknowledgements`, `audit_disputes`, `audit_overrides`, `audit_extracted`, `pipeline_overrides`, `halt_log`
- Never modify the PLAN's Objective, Context, Steps, or Verification sections.
- Never tick a Verification checkbox without confirming the condition.
- Caller must commit and push after execute-plan returns, and never use `--no-verify`, `--force`, `--force-with-lease`, or bypass signing.
- If a PLAN step requires tools or permissions the executor lacks: halt, flag, escalate to the human.
- If outcome is not `done`: still populate Executor Notes. The caller decides commit cadence and content per parent PLAN 202605011400 decision 22.
- **Halt-on-failure protocol:** If any step fails or produces output that does not match the step's verification criteria, halt the PLAN immediately. Do not attempt subsequent steps. Write `last_executor_outcome` with `outcome: exception` + `diagnostics_summary` + the structured executor verdict. Populate Executor Notes with: which step failed, actual output, suspected cause. Do not flip frontmatter `status` - the orchestrator does that after reading `last_executor_outcome`. Return to caller. The orchestrator handles status routing + commit/push of partial work with `WIP:` prefix per decision 22. Report to the Human.
</constraints>

<success_criteria>
- PLAN's Executor Notes populated with execution details and today's date
- PLAN frontmatter `last_executor_outcome` written with structured outcome / outcome_subtype / executed / diagnostics_summary (single executor frontmatter write per T14, 2026-05-13)
- Every State/ file modified has its frontmatter `last_updated` bumped to today
- PLAN frontmatter `status` and `pipeline_phase` were not modified by the executor (T14: orchestrator-owned fields)
- The human has been given the final report: filename, outcome
- Halt-on-failure protocol applied: any failed step results in `last_executor_outcome.outcome: exception` with a `diagnostics_summary`, and the orchestrator reads `last_executor_outcome` and flips PLAN frontmatter `status` itself (to `needs-revision` or the appropriate terminal state) - the executor does not flip `status`
- Plan-of-plans sync applied if applicable: parent plan-of-plans tracking entry updated (parent_plan_of_plans) and its frontmatter `last_updated` bumped to today.
</success_criteria>