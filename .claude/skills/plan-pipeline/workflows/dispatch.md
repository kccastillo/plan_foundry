# Plan-Pipeline Dispatch Procedure

One invocation = one walk through this procedure. The orchestrator reads disk, decides what to do, executes one or more phase transitions, commits (and conditionally pushes) after each milestone, and returns control.

**Push policy (PLAN-AB1, simplified by PLAN-AC4 D6).** Before any `git push`, the orchestrator reads the effective push policy:

```python
# Module lives at .claude/skills/_shared/push_policy.py
import sys
sys.path.insert(0, ".claude/skills/_shared")
from push_policy import get_push_policy
policy = get_push_policy(plan_path)   # returns "auto" or "manual"
```

The resolver checks the PLAN's frontmatter `push_policy:` field; if absent or invalid, falls back to the hard-coded default `"manual"`. (Per PLAN-AC4 D6/D6a, the earlier `.claude-plugin/marketplace.json` project-default layer was removed — the value had never been set to anything other than `"manual"` in tree.)

- `policy == "auto"` → push as today (run `git push` after every commit).
- `policy == "manual"` → skip push; emit `<push_status>commit landed locally; push manual per push_policy. Run \`git push\` when ready.</push_status>`.

All references to "commit + push" in this document are subject to this conditional. The commit always happens; the push is gated on `policy == "auto"`.

**Phase-boundary chaining (F9 from PLAN 202605011900, 2026-05-01):** the orchestrator MAY chain phase transitions within a single invocation (e.g. `drafted → checked → executing`) when running in a continuous parent session, provided each transition produces a milestone commit + push. Audit-loop iterations stay within `drafted`. Re-entry idempotency is preserved by reading disk on every invocation — the chaining relaxation does not weaken the on-disk-state contract. The Human or parent-Claude triggers the next invocation if the chain pauses (e.g. background executor dispatched, Human-pending verification surfaced).

Per-phase routing tables, commit-message templates, and frontmatter mutation cheat sheet live in [../references/phase-state-machine.md](../references/phase-state-machine.md). This file is the procedural narrative; the reference is the lookup.

---

## Step 1: Resolve target PLAN

**If `plan_path` was supplied:**
- Read the file. If unreadable → emit `exception` (orchestrator-side; commit not required since nothing changed).
- Parse frontmatter. If malformed → `exception`.

**If only `request` was supplied (fresh entry):**
- Detect intent. If the request contains an existing PLAN reference (e.g. "resume the pipeline on PLAN_xyz"), resolve to its path and proceed as above.
- Otherwise, treat as a fresh planning request → enter Step 4 (`drafting` phase) with no PLAN file yet.

**If both supplied:** prefer `plan_path`; treat `request` as additional context only.

**If neither:** emit `exception`. The orchestrator does not invent a target.

---

## Step 2: Read durable state

Extract from PLAN frontmatter (when a PLAN exists):

```
pipeline_phase             # absent or empty → treat as drafted (plan-conventions ad-hoc default)
audit_state:
  sufficiency_iterations    # default 0
  plan_safety_iterations    # default 0
  last_stage                # none | sufficiency | plan_safety
  last_outcome              # none | success | revision_needed | exception
last_executor_outcome:
  outcome                   # success | revision_needed | exception
  outcome_subtype           # done | partially-complete | blocked | needs-revision
  executed
  diagnostics_summary
verification_state:
  state_pass / state_fail
  acceptance_pass / acceptance_fail
  human_pending             # list
  human_verdict             # pending | all_pass | rejected
status                       # ready | in-progress | done | partially-complete | blocked | needs-revision
triggers_plans               # list of child PLAN filenames
assigned_to                  # haiku (default) | sonnet | opus | other
```

Treat any absent field as the documented default.

---

## Step 3: Idempotency and parent/children gates

**Idempotency check.** If the durable state shows the action for the current `pipeline_phase` has already been taken since the last meaningful change AND no new outcome is recorded since, return: "already at <phase>; nothing to do." This protects against parent-Claude double-invocation on a single trigger.

Concrete checks (applied in order):
- `pipeline_phase: complete` AND PLAN already retired → no-op.
- **`pipeline_phase: drafting` AND (`ideate_phase ∉ {complete, exited_early}` OR `ideate_phase` field absent):** the PLAN is being actively shaped by the ideate cadence pipeline. plan-pipeline takes **no action (no-op)**. Return with: "PLAN is being ideated (ideate_phase: <value>); plan-pipeline waits until ideate_phase transitions to `complete`. Re-invoke after ideate completes." This makes `drafting` a long-duration phase that ideate owns. plan-pipeline must not advance or modify the PLAN until ideate hands off by flipping `ideate_phase: complete` + `pipeline_phase: drafted`.
  - Exception: if `ideate_phase` is absent and `pipeline_phase: drafting`, apply the same no-op. The PLAN may be in phases 1–3 (conversational; no `ideate_phase` set yet). plan-pipeline should wait.
  - Exception to the exception: if `pipeline_phase: drafting` AND `ideate_phase ∈ {complete, exited_early}`, fall through to Step 4 (`drafting` phase) as normal — ideate has finished and the PLAN can be re-driven.
- `pipeline_phase: executing` AND no `last_executor_outcome` recorded → executor still running (or no completion message arrived); read `Workbench/.heartbeat/<plan-id>.json` if it exists and apply the following sub-branches:
  - If heartbeat file is absent or unreadable: no-op (executor may not have started yet or heartbeat was never written).
  - If heartbeat JSON is malformed: skip with a one-line log ("heartbeat for <plan-id> is malformed — skipping") and no-op.
  - If `phase: exited` is present in heartbeat: log "Executor exited but completion message not yet observed; waiting" — still no-op, awaiting completion re-entry.
  - If `last_tick_at` > 10 minutes ago AND `phase` is NOT `exited`: surface a one-line warning to the human: "⚠ Heartbeat stale for <plan-id> — last tick <ISO-ts>. Background executor may be hung." Routing unchanged (still no-op).
- `pipeline_phase: outcome-verifying` AND `verification_state.human_verdict: pending` AND no fresh `human_reply` supplied → no-op (waiting on the Human).
- `pipeline_phase: drafted` AND `audit_state.last_outcome: revision_needed` AND PLAN file mtime not advanced since the audit_state write → no-op (waiting on Human revision).

**Children gate.** If `triggers_plans` is non-empty, read each child PLAN's `status`. If any child is non-terminal (not in {`done`, `partially-complete`, `cancelled`, `closed`}), surface "Paused for children: <list>" with decision-15 triage, return. Do NOT advance the parent's `pipeline_phase`.

If gates pass, proceed to Step 4.

---

## Step 4: Dispatch by phase

Each branch below mutates frontmatter and commits as documented in [../references/phase-state-machine.md](../references/phase-state-machine.md). Only one branch executes per invocation (except the audit loop within `drafted`, which may dispatch one audit + record outcome + return).

### 4A. `drafting` (or no PLAN yet)

**Entry condition:** request without an existing PLAN, or a PLAN with `pipeline_phase: drafting`.

**Plan-boundary check (PLAN-AB5, H7 — soft warn-and-proceed).** Before dispatching ideate or write-plan against any PLAN, the orchestrator checks whether other PLANs are currently in flight:

- (a) Glob `Workbench/PLAN-*.md`. For each file, read the frontmatter field `pipeline_phase`.
- (b) Collect the set of **in-flight PLANs**: any PLAN whose `pipeline_phase` is in `{drafting, drafted, checked, executing, outcome-verifying}` (i.e. non-complete and non-empty/non-terminal).
- (c) If the in-flight set is non-empty AND the target PLAN is not in that set (i.e. this is a distinct plan being started while others are active):
  - Emit the following structured surface to the human before proceeding:
    ```
    <plan-boundary-warning>Active plans in flight: PLAN-X (pipeline_phase: Y), PLAN-Z (pipeline_phase: W). Dispatching ideate against TARGET-PLAN anyway. To pause this dispatch, set status: blocked or wait for the active plans to complete before re-invoking.</plan-boundary-warning>
    ```
  - Replace `PLAN-X`, `pipeline_phase: Y`, etc. with the actual PLAN IDs and phases found.
  - This is a **soft warn-and-proceed** — the orchestrator does NOT halt and does NOT require Human confirmation. The warning is visible; the operator decides whether to pause manually.
- (d) If the in-flight set is empty OR the target PLAN is already in the in-flight set (i.e. resuming an active plan): no warning, proceed normally.

The plan-boundary check uses no new frontmatter fields and requires no state file — it reads existing `pipeline_phase` values on every invocation.

1. Invoke `Skill("ideate", request_or_existing_path)` directly in the parent session. **Never via a subagent.**
2. The ideate arc walks Clarify → Survey → Converge with the Human. At checkpoint moments (clarify-locked, survey-converged), dispatch `plan-writer` foreground via the Agent tool to write or update the PLAN file. Each successful `plan-writer` return → commit + push (template `plan-pipeline: drafted <plan-filename>` or `... drafting checkpoint <plan-filename>`).
3. When the Human signals ideation closed (any phrase that re-triggers the pipeline matcher, or an explicit "ready to audit"), the next orchestrator invocation flips `pipeline_phase: drafted` (Step 4 reads disk and falls into branch 4B). The ideate skill itself does not flip the phase.
4. RESEARCH/ADVICE escapes during ideate: ideate invokes `write-input` directly; resulting filenames land in the PLAN's `linked_inputs:` on the next `plan-writer` checkpoint. Commit + push after `write-input` returns (template `plan-pipeline: drafting input <filename>`).

Return control to parent after each `plan-writer` checkpoint (the arc itself is conversational; the orchestrator re-enters when the Human's next turn re-triggers the pipeline).

### 4B. `drafted` (audit loop)

**Severity-surface wiring (audit-revision loop, branch 4B).** When the auditor returns `outcome: revision_needed`, the orchestrator invokes the severity-surface modules to present a structured prompt and parse the human's reply:

```python
# Modules are in .claude/skills/plan-pipeline/lib/
from render_prompts import render_audit_surface
from parse_replies import parse_audit_reply
from apply_actions import apply_audit_action

# 1. Render the human-facing audit-revision prompt
prompt_text = render_audit_surface(
    plan=plan_frontmatter,
    auditor="sufficiency" | "plan_safety",
    iteration=N,
    max_iterations=5,
    audit_result_json=audit_json,
    prior_audit_json=prior_audit_json_or_None,
    recurring_fingerprints=recurring_fingerprints,  # from recurrence detection
)
# Surface prompt_text to the human; await reply.

# 2. On re-entry with human_reply, parse the reply
parse_result = parse_audit_reply(
    reply_text=human_reply,
    plan_frontmatter=plan_frontmatter,
    audit_result_json=audit_json,
    prior_audit_json=prior_audit_json_or_None,
)

if parse_result["action"] == "ambiguous":
    # Send parse_result["reprompt_text"] to human; await reply (one clarification allowed).
    # On second ambiguous result from same human turn → emit exception (two-strike rule).
elif parse_result["action"] == "help":
    # Emit parse_result["action_args"]["usage_text"] and re-prompt (not counted as ambiguous strike).
else:
    # 3. Apply mutations to PLAN frontmatter
    updated_frontmatter = apply_audit_action(
        plan=plan_frontmatter,
        action=parse_result["action"],
        action_args=parse_result["action_args"],
        audit_result_json=audit_json,
    )
    # Write updated_frontmatter back to PLAN file.
    # Commit: "plan-pipeline: audit_human_reply — <K>ack/<L>dispute/<M>override on <plan-filename>"
    # Route per state-transition table in phase-state-machine.md "severity surface" rows.
```

State transitions after applying mutations (see references/phase-state-machine.md severity rows):
- Reply contains `fix`: commit mutations; await PLAN mtime advance; re-dispatch auditor on next re-entry.
- All errors covered by `override` actions (no `fix`): treat as audit success for this stage; advance.
- Only `ack`/`dispute` on warnings/notes; no errors: treat as success; advance.
- Errors remain unresolved: re-surface "errors remain — reply 'fix' or 'override <ID>: <reason>'."
- `extract` action: dispatch `Skill("write-bus-plan")` to seed child PLAN; link `triggers_plans` on parent.
- `different-auditor` action: `audit_state.preferred_model_override` written; reset stage iter; await re-invocation.

**Brief construction.** Before each auditor dispatch (sufficiency or plan-safety), the orchestrator constructs the audit brief using the Python helper:

```bash
python .claude/skills/plan-pipeline/lib/build_brief.py \
  <plan_path> <auditor> <iteration> > /tmp/audit_brief_<plan-id>.md
```

The orchestrator reads `/tmp/audit_brief_<plan-id>.md` and embeds the contents verbatim as the user-message content in the `Agent()` dispatch. The subprocess + temp file pattern keeps `dispatch.md` Python-free and allows the helper to evolve independently.

**Last-commit anchor capture.** After each `audit_state update` commit, the orchestrator runs `git rev-parse --short=8 HEAD`, captures the short SHA, and writes it to `audit_state.last_audit_commit` in the PLAN frontmatter via a **second commit** (commit message: `plan-pipeline: record last_audit_commit for <plan-id>`). Never amend the prior commit — project policy is "new commits, never amends". This SHA becomes the diff anchor for the next re-audit (passed to `build_brief.py` as part of `audit_state`).

**Recurrence detection logic.** After the auditor returns and the orchestrator writes the new audit JSON to `Workbench/.audit/<plan-id>-<iter>.json`, compare its findings' fingerprints against the prior iteration's audit JSON. If any fingerprint with `level: error` appears in both iterations (by fingerprint match), set a flag `recurring_findings: [<fingerprints>]` in the orchestrator's in-memory state. This flag is used by the severity-surface downstream to surface a `[STUCK ×N]` badge. (Recurrence detection: compare each finding's computed `sha256(code|level|category|location)[:8]` across iterations.)

**Acknowledgement-stripping defence.** After parsing the auditor's return JSON, the orchestrator filters `findings[]` to remove any entry whose computed fingerprint matches one in the PLAN's `audit_acknowledgements`. The stripped count is logged in the commit message body (e.g., `[stripped 2 acknowledged findings]`). This is defensive — the auditor was instructed not to re-emit acknowledged findings but may disobey.

**Read `audit_state` and follow the lookup in references/phase-state-machine.md → "Audit-loop dispatch table".** The decision tree:

| `last_stage` | `last_outcome`     | Next action                                                                                     |
|--------------|--------------------|-------------------------------------------------------------------------------------------------|
| none         | none               | Dispatch `sufficiency-auditor` (foreground).                                                    |
| sufficiency  | success            | Dispatch `plan-safety-auditor` (foreground).                                                    |
| sufficiency  | revision_needed    | Awaiting Human revision; if PLAN mtime advanced since audit_state write, re-dispatch `sufficiency-auditor`; else no-op. |
| plan_safety  | success            | Both passed → flip `pipeline_phase: checked`; commit + push; return. (No further dispatch this invocation.) |
| plan_safety  | revision_needed    | Awaiting revision; re-dispatch `plan-safety-auditor` after PLAN mtime advances. (Sufficiency does not re-run.) |
| any          | exception          | Kanban halt — already committed when exception was first emitted. Re-entry is a no-op until Human takes action. |

**Per dispatch:**
1. Increment the appropriate iteration counter (`audit_state.sufficiency_iterations++` or `plan_safety_iterations++`).
2. **If counter > 5:** do NOT dispatch. Orchestrator emits its own `outcome: exception` ("audit loop did not converge after 5 iterations — Human review required"). Update `audit_state` accordingly, commit + push WIP, surface diagnostics, return.
3. Otherwise: announce the iteration to the Human ("Audit iteration <N>: dispatching <agent>"), dispatch foreground via `Agent({subagent_type: "<agent>", ...})`. Block until return.
4. Parse the LAST `<pipeline-result>` block in the agent's return (text-scan for opening tag, find matching closing tag, extract the JSON code fence, parse). If absent or malformed → orchestrator emits `exception` (commit + push WIP, surface diagnostics, return).
5. Branch on `outcome`:
   - `success` → write `audit_state.last_stage = <stage>`, `last_outcome: success`. Commit + push (template `plan-pipeline: audit_state update — <stage>:success`). Re-enter Step 4B from the top within the same invocation only if the next stage is the OTHER audit (sufficiency → plan-safety transition). Once `plan_safety` succeeds, flip `pipeline_phase: checked` and commit + push under that template, then return.
   - `revision_needed` → write `audit_state.last_stage = <stage>`, `last_outcome: revision_needed`. Commit + push (`plan-pipeline: audit_state update — <stage>:revision_needed`). Apply decision-15 triage to `payload.triaged_human_items` if present, surface `payload.review_text` + iteration counts, instruct the Human "Revise the PLAN and re-invoke me to re-audit." Return.
   - `exception` → kanban halt. Commit + push WIP with `payload.diagnostics`. Surface diagnostics. Return.

**One exception to "one phase per invocation":** within `drafted`, the orchestrator may chain sufficiency-success → plan-safety-dispatch in a single invocation (commit between). This is allowed because no `pipeline_phase` boundary is crossed — both stages are within `drafted`.

### 4C. `checked`

**Single transition: dispatch executor.**

1. Read PLAN's `assigned_to` frontmatter. Map per the executor-tier table in references/phase-state-machine.md:
   - `haiku`, empty, or unrecognised → `plan-executor`.
   - `sonnet` → `plan-executor-sonnet`.
   - `opus` → `plan-executor-opus`.
2. Flip `pipeline_phase: executing`. Set `status: in-progress`. Commit + push (`plan-pipeline: executing <plan-filename>`).
3. Dispatch the executor with `run_in_background: true`. The Agent call returns an agent ID; the orchestrator does NOT wait. Surface to the Human: "Executor <name> dispatched in background. I'll resume when it completes."
4. Return control to parent. The executor's completion message arriving in parent's conversation is the re-entry cue.

### 4D. `executing`

**Re-entry path.** Parent-Claude observed the executor's completion message and re-invoked this skill with `plan_path`. The orchestrator does not poll; this branch only runs on re-entry.

1. **Executor-return validation** (Reeve hiccup H10 / 2026-05-16). Before reading `last_executor_outcome` or treating any completion message as authoritative, validate the executor's return contains a well-formed `<pipeline-result>` block. Specifically:
   - If parent-Claude received a completion notification for this PLAN's executor dispatch, inspect the notification's result text.
   - The result MUST contain a literal `<pipeline-result>` block with a parseable JSON code fence per decision 23.
   - If the result is empty, contains a rate-limit string (e.g. `"You've hit your limit"`, `"resets at"`, `"rate-limited"`), or otherwise lacks the expected block: do NOT trust `last_executor_outcome` (it may not have been written, or may be stale from a prior run). Treat as `outcome: exception` with `diagnostics.reason = "executor return malformed: <empty | rate-limit | missing pipeline-result block>"`. Preserve heartbeat. Kanban halt. Commit + push WIP. Surface to Human with the raw completion text for inspection. Return.
   - This is structurally identical to the retire-skill post-condition pattern (§4F step 3): the harness's "completed" status conflates "executor finished successfully" with "executor's invocation returned a result of any kind"; the orchestrator MUST verify the structured block exists before progressing.
2. Read `last_executor_outcome.outcome` from PLAN frontmatter (the executor's `execute-plan` workflow writes this — decision 24).
3. If absent or stale (executed date older than the dispatch) → no-op. The completion message likely fired before the executor finished; wait for the next message.
4. Parse the most recent `<pipeline-result>` block from the executor's return (parent-Claude supplies it implicitly via the conversation; if not directly available, treat the frontmatter `last_executor_outcome` as canonical — that is the durable record per decision 24).
5. Branch:
   - `outcome: success` → **Delete `Workbench/.heartbeat/<plan-id>.json`** immediately (heartbeat is no longer load-bearing; would otherwise mislead `/status` and INDEX alerts). Flip `pipeline_phase: outcome-verifying`. Commit + push (`plan-pipeline: outcome-verifying <plan-filename>`). Continue into branch 4E within the same invocation.
   - `outcome: revision_needed` → **Delete `Workbench/.heartbeat/<plan-id>.json`** immediately (executor is done; heartbeat is stale). Revert `pipeline_phase: drafted`. Reset `audit_state` to fresh (`last_stage: none`, `last_outcome: none`, counters to 0) — content has changed materially, so prior audits are stale. Set `status: needs-revision`. Commit + push (`plan-pipeline: executor revision_needed <plan-filename>`). Surface executor's `diagnostics_summary` + Executor Notes pointer with decision-15 triage. Return.
   - `outcome: exception` → **Preserve `Workbench/.heartbeat/<plan-id>.json`** (forensic data attached to the halt; deleted on the next phase transition out of halted state — see heartbeat lifecycle table below). Kanban halt. Commit + push WIP (`WIP: pipeline halted at executing for <plan-filename> — see diagnostics`). Surface diagnostics. Return.

**Heartbeat lifecycle table** (quick reference — full spec in `execute-plan/references/heartbeat-spec.md`):

| Phase transition | Heartbeat action |
|---|---|
| `executing` → `outcome-verifying` (success) | Delete immediately after success commit |
| `executing` → `drafted` (revision_needed) | Delete immediately after revert commit |
| `executing` → halted (exception) | Preserve as forensic data |
| Halted → any resumption (override / extract / dispute / different-auditor) | Delete as part of halt-recovery routine (before re-dispatching) |

**Halt-recovery heartbeat cleanup.** When the human resumes a halted PLAN via any action that triggers a new execution (override, extract, dispute, different-auditor), the orchestrator's halt-recovery routine MUST include: `if Workbench/.heartbeat/<plan-id>.json exists, delete it`. This is the explicit cleanup hook — not automatic, not deferred to a later phase.

### 4E. `outcome-verifying` (per decision 25)

**Severity-surface wiring (outcome-verifying, branch 4C).** After running shell checks, the orchestrator invokes the outcome-verifying surface modules:

```python
from render_prompts import render_outcome_surface
from parse_replies import parse_outcome_reply
from apply_actions import apply_outcome_action

# Load executor heartbeat if present (None-safe: renderer omits line if None)
import json
heartbeat_path = f"Workbench/.heartbeat/{plan_id}.json"
executor_heartbeat = None
try:
    with open(heartbeat_path) as f:
        executor_heartbeat = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    executor_heartbeat = None

# 1. Render the outcome-verifying prompt
prompt_text = render_outcome_surface(
    plan=plan_frontmatter,
    verification_state=verification_state,
    executor_notes=last_executor_outcome.get("executor_notes", ""),
    shell_passes=shell_passes,     # list of {"type", "command"} for passed checks
    shell_failures=shell_failures, # list of {"id": "F1", "type", "command", "exit_code"}
    human_items=human_items,       # list of {"id": "H1", "prose"} for verify: human items
    executor_heartbeat=executor_heartbeat,
)
# Surface prompt_text to the human.

# 2. On re-entry, parse the reply
parse_result = parse_outcome_reply(
    reply_text=human_reply,
    verification_state=verification_state,
    shell_failures=shell_failures,
)

# 3. Apply mutations
updated_plan = apply_outcome_action(
    plan=plan_frontmatter,
    action=parse_result["action"],
    action_args=parse_result["action_args"],
    verification_state=verification_state,
)
# Write updated_plan back; commit (see phase-state-machine.md for commit templates).
```

1. Read PLAN's `## Verification` section. Extract every line annotated with `verify:`, `acceptance:`, or `verify: human`.
2. For each `verify:` shell command: run via Bash. Tally pass (exit 0) / fail.
3. For each `acceptance:` shell command: run via Bash. Tally pass / fail.
4. For each `verify: human` item: capture the prose description into `verification_state.human_pending`.
5. Write `verification_state` frontmatter:
   ```
   verification_state:
     state_pass: <int>
     state_fail: <int>
     acceptance_pass: <int>
     acceptance_fail: <int>
     human_pending: [<list of prose descriptions>]
     human_verdict: pending
   ```
   Commit + push (`plan-pipeline: outcome-verification ran for <plan-filename>`).
6. Branch:
   - **Any `verify:`/`acceptance:` shell failed AND `human_pending` is empty** → pure shell failure; auto-revert (existing behaviour). Revert `pipeline_phase: drafted`, reset `audit_state` to fresh, set `status: needs-revision`. Commit + push (`plan-pipeline: outcome-verification failed — reverting to drafted for <plan-filename>`). Surface failed-assertion list with decision-15 triage. Return.
   - **Any `verify:`/`acceptance:` shell failed AND `human_pending` is non-empty** → mixed failure; invoke `render_outcome_surface()` with the shell failures AND human items. Human may `ack-failure` non-blocking shell failures before issuing `pass`. Route per severity-surface state-machine rows in phase-state-machine.md.
   - **All shell checks passed AND `human_pending` empty** → flip `pipeline_phase: complete`. Commit + push (`plan-pipeline: complete <plan-filename>`). Continue into branch 4F.
   - **All shell checks passed AND `human_pending` non-empty** → invoke `render_outcome_surface()`. Surface the structured severity-surface prompt. Return. The Human's reply re-triggers the orchestrator. On re-entry while `pipeline_phase: outcome-verifying` AND `human_verdict: pending`:
     - Parse reply via `parse_outcome_reply()`; apply via `apply_outcome_action()`.
     - `pass` (all failures acked, all human items acked) → flip `pipeline_phase: complete`; commit + push.
     - `fail` or `reject-human` → revert `pipeline_phase: drafted`; reset `audit_state`; commit + push.
     - Ambiguous reply → re-prompt once. Second ambiguous → emit `exception`.

### 4F. `complete` (retire + drift check)

1. Dispatch `plan-retirer` foreground via the Agent tool with the PLAN path.
2. Parse the `<pipeline-result>` block.
3. **Post-condition verification** (PLAN-AA2 defense-in-depth pattern). When the subagent reports `outcome: success`, the orchestrator MUST independently verify the retire skill's success_criteria against the filesystem before committing. This catches the 2026-05-13 class of bug where the subagent self-reported success but `git rm`'d the file instead of moving it. Specifically, before treating `success` as success:
   - Compute expected destination: `Retired/<original-basename>` (basename derived from the PLAN path passed to the subagent).
   - Stat the source path — assert it does NOT exist on disk.
   - Stat the destination path — assert it exists, is a file, and has non-zero size.
   - If ANY assertion fails: override the subagent's reported outcome — treat it as `outcome: exception` with `diagnostics.reason = "post-condition violation: <specific failing check>"`. Halt; do NOT commit. Surface to Human via kanban-halt (branch 5) including the subagent's claimed-success message for contrast.
   - On all assertions passing: proceed to step 4.
4. Branch:
   - `success` (verified) → commit + push (`plan-pipeline: retired <plan-filename>`). Surface "Pipeline complete: <plan-filename> retired." Continue to sub-step 5 (drift check).
   - `exception` (subagent-reported OR orchestrator-overridden) → kanban halt. Commit + push WIP. Surface diagnostics using the kanban-halt surface (branch 5). Return.

5. **Compact suggestion (PLAN-AB5, H7).** After the retire commit (step 4 success), emit the following structured tag to the human:

   ```
   <compact_suggestion>Plan <plan-filename> retired. /compact suggested to reset working memory before the next plan-pipeline invocation.</compact_suggestion>
   ```

   Replace `<plan-filename>` with the actual filename of the PLAN that was just retired. The Claude Code harness picks up the `<compact_suggestion>` tag as a cue to run `/compact`; in a harness that does not support the tag, this is harmless prose. This surface exists to prevent the boundary-discipline failure pattern from H7 (PLAN-AB5): the orchestrator eagerly starting the next plan's ideate before compacting, losing working-memory continuity.

6. **Doc-drift check** (after successful retire, auxiliary). Read the just-completed PLAN's `files_touched` frontmatter. If any path matches any of the following patterns, foreground-dispatch `Skill("maintain-claude-md")` with no arguments — it audits the live state of CLAUDE.md and ARCHITECTURE.md against the current codebase (AGENT_RULES.md was dissolved 2026-05-14 per Option Y of ADVICE-003; its meta-policy lives in CLAUDE.md now):
   - `.claude/skills/*` (any skill change)
   - `.claude/commands/*` (any slash command change)
   - `.claude/skills/_shared/*` (invariants / plan-safe live here — ARCHITECTURE.md driver)
   - `.claude/agents/*` (executor capability boundaries — ARCHITECTURE.md driver)
   - `CLAUDE.md` itself
   - `ARCHITECTURE.md` itself

   Surface the skill's output to the human as a one-line summary: "Drift check: <outcome> — <brief description>". If the audit finds drift, the human invokes the produced PLAN at their discretion. If `files_touched` is absent or empty, skip silently. Failure of `maintain-claude-md` is logged (one line) but does NOT halt or revert the pipeline — this step is auxiliary.

7. **Auto-retire absorbed inputs (PLAN-AC0).** After the retire commit (step 4 success) and drift check (step 6 auxiliary), walk the just-completed PLAN's `linked_inputs` frontmatter array. For each input file path:
   - Read the input's frontmatter.
   - **Gate 1 — lifecycle_mode:** if `lifecycle_mode: reference` (default `input` if absent), SKIP. Surface one-line: "Input <path> retained: lifecycle_mode=reference."
   - **Gate 2 — integration_status:** if `integration_status != integrated` (default `pending`), SKIP. Surface one-line: "Input <path> retained: integration_status=<status> (operator must invoke rehydrate-input to confirm absorption)."
   - **Gate 3 — all-feeds-retired:** read every PLAN in the input's `feeds_plan` (RESEARCH) or `advises_plan` (ADVICE) field. For each, check whether the file exists at `Retired/202605/<plan-basename>` or `Retired/<plan-basename>` or any `Retired/**/<plan-basename>`. If ANY consuming PLAN is still in `Workbench/`, SKIP. Surface one-line: "Input <path> retained: PLAN <other-plan> still active."
   - **All gates pass → auto-retire:** `git mv Workbench/<input-basename> Retired/<input-basename>` (or `Retired/202605/<input-basename>` to match the PLAN-retire convention if the input is from the current LOG month). Commit + push (subject to push_policy): `plan-pipeline: auto-retired <input-basename> (consuming PLAN <plan-basename> retired; integration_status: integrated)`.
   - **Robustness:** if any input read fails (file missing, malformed frontmatter), log one line ("input <path> unreadable — skipping auto-retire") and continue with remaining inputs. Do NOT halt the pipeline; this sub-step is auxiliary.

   Reference-mode and integration-pending inputs are deliberately NOT auto-retired: reference-mode is durable knowledge; integration-pending means the operator hasn't confirmed absorption yet (a common case for inputs that feed multiple PLANs incrementally). This gate-set is intentionally conservative — false-positive auto-retires would destroy in-flight context.

8. **Thread-status surface** (after drift check, auxiliary). Read the just-completed PLAN's `closes_thread:` and `advances_thread:` frontmatter fields. If either is non-empty, surface a one-line notice to the human in this exact shape: "Thread reference: PLAN closes/advances thread <T-ID>. Consider updating ROADMAP.md thread status to reflect the closure." Use "closes" when `closes_thread` is non-empty; use "advances" when only `advances_thread` is non-empty; use "closes and advances" if both are non-empty. If both are empty, skip silently. This step never dispatches a subagent and never modifies ROADMAP.md — the human refreshes ROADMAP at their discretion. Return.

### 4G-halt. Exception / kanban halt (any phase, branch 5)

**Severity-surface wiring (kanban-halt, any phase).** Whenever the orchestrator emits `outcome: exception` (MAX_ITERATIONS, malformed return, git failure, uninterpretable human reply, executor exception), invoke the halt-surface modules:

```python
from render_prompts import render_halt_surface
from parse_replies import parse_halt_reply
from apply_actions import apply_halt_action

# Build diagnostics dict from exception context
diagnostics = {
    "phase": current_phase,
    "subagent": subagent_name_or_"orchestrator",
    "iteration": iteration_or_"n/a",
    "stage": stage_or_"n/a",
    "last_successful_commit": last_commit_sha_and_message,
    "wip_commit": wip_commit_sha_and_message,
    "diagnostics_path": audit_json_path_or_halt_file,
    "details": detail_lines_list,  # up to 15 lines; renderer truncates if more
}

# Load heartbeat for forensic context if executor was involved
executor_heartbeat = None
try:
    with open(f"Workbench/.heartbeat/{plan_id}.json") as f:
        executor_heartbeat = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    executor_heartbeat = None

# 1. Render the halt prompt
prompt_text = render_halt_surface(
    plan=plan_frontmatter,
    exception_reason=one_line_cause_summary,
    diagnostics=diagnostics,
    orchestrator_state={"pipeline_phase": current_phase},
    executor_heartbeat=executor_heartbeat,
)
# Surface prompt_text to the human; await reply.

# 2. On re-entry, parse the reply
parse_result = parse_halt_reply(
    reply_text=human_reply,
    halt_reason=one_line_cause_summary,
)

# 3. Apply mutations
updated_plan = apply_halt_action(
    plan=plan_frontmatter,
    action=parse_result["action"],
    action_args=parse_result["action_args"],
    exception_state={"phase": current_phase, "cause": one_line_cause_summary},
)
# Write updated_plan back; commit per phase-state-machine.md halt-recovery templates.
# Route on action: retry → re-dispatch; override → advance phase; reset-stage → reset counter + re-dispatch;
# different-auditor → write model override + reset + await; abandon → status: cancelled; pipeline_phase: complete.
```

State transitions on halt-recovery actions are documented in references/phase-state-machine.md "Severity-surface state-machine additions" table.

---

## Step 4G. INDEX regen (after every commit-worthy phase transition)

After every successful commit in steps 4A–4F, dispatch the `update-workbench-index` skill to regenerate `Workbench/INDEX.md` and `Workbench/.index.json`:

```
Skill("update-workbench-index")
```

INDEX regen is **auxiliary** — a skill failure (outcome: exception) is logged but does NOT halt the pipeline. The orchestrator continues to the next step regardless of INDEX regen outcome.

After successful regen, commit the two output files in a separate commit:
```
git add Workbench/INDEX.md Workbench/.index.json && git commit -m "plan-pipeline: update-workbench-index"
```

(This is a distinct commit from the phase-transition commit — per the design decision for separate commits per INDEX regen, giving cleaner git history.)

---

## Step 5: Children-aware advancement (when this PLAN spawns children)

If the active PLAN's `triggers_plans:` was populated during `drafting` (e.g. ideation produced a parent-of-plans), the children-gate in Step 3 prevents the parent from auto-advancing past `checked` until children reach terminal status. The Human typically:
1. Runs the orchestrator on the parent through `drafted → checked` (parent's own design is audited).
2. Manually flips children's `status: blocked → ready` (or runs the orchestrator on each child if they themselves use the pipeline).
3. Once all children terminal, re-invokes the orchestrator on the parent — Step 3's children gate now passes, and 4C dispatches the parent's executor.

The orchestrator does not poll children. Re-entry is the cue.

---

## Step 6: Bootstrap exception

While the parent PLAN `202605011400_PLAN_build-plan-pipeline-orchestrator.md` is itself executing (its own `pipeline_phase` is non-`complete`), the orchestrator does NOT manage git for it — the Human commits manually after each `execute-plan` call, per the bootstrap instructions in that PLAN's Constraints section. This branch is detected by inspecting whether the active PLAN is the parent bootstrap file.

For all other PLANs, full git milestone discipline applies.

---

## Step 7: Always commit (or fail loud) and return

After any phase work in Step 4, before returning control:
- If any frontmatter or filesystem change happened, the appropriate `git add -A && git commit -m "<template>"` was already run inline (per the templates). `git push` follows only when `push_policy == "auto"` (see preamble). When `push_policy == "manual"`, the commit lands locally and the `<push_status>` surface is emitted instead.
- If `git push` failed at any point, the orchestrator already emitted `exception` and committed WIP locally (push will be retried on Human action).
- If nothing changed (idempotent no-op), no commit needed.

Return control to parent-Claude with a one- or two-sentence summary of what just happened (which phase advanced, or which prompt is now in front of the Human, or that this was a no-op).
