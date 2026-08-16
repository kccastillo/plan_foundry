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

The resolver checks the PLAN's frontmatter `push_policy:` field; if absent or invalid, falls back to the hard-coded default `"manual"`. (Per PLAN-AC4 D6/D6a, the earlier `.claude-plugin/marketplace.json` project-default layer was removed - the value had never been set to anything other than `"manual"` in tree.)

- `policy == "auto"` -> push as today (run `git push` after every commit).
- `policy == "manual"` -> skip push; emit `<push_status>commit landed locally; push manual per push_policy. Run \`git push\` when ready.</push_status>`.

All references to "commit + push" in this document are subject to this conditional. The commit always happens; the push is gated on `policy == "auto"`.

**Phase-boundary chaining (F9 from PLAN 202605011900, 2026-05-01):** the orchestrator MAY chain phase transitions within a single invocation (e.g. `drafted -> checked -> executing`) when running in a continuous parent session, provided each transition produces a milestone commit + push. Audit-loop iterations stay within `drafted`. Re-entry idempotency is preserved by reading disk on every invocation - the chaining relaxation does not weaken the on-disk-state contract. The Human or parent-Claude triggers the next invocation if the chain pauses (e.g. background executor dispatched, Human-pending verification surfaced).

Per-phase routing tables, commit-message templates, and frontmatter mutation cheat sheet live in [../references/phase-state-machine.md](../references/phase-state-machine.md). This file is the procedural narrative; the reference is the lookup.

---

## Orchestrator-owned state: snapshot, restore, never trust

**Principle (D1 - "No-Trust-Subagent-State").** The orchestrator never trusts orchestrator-owned frontmatter fields as written by a subagent. After dispatching `plan-writer`, `sufficiency-auditor`, or `plan-safety-auditor`, the orchestrator MUST restore the owned fields to the values it snapshotted before dispatch, then mutate them itself (`audit_state` exclusively via `audit_loop.py`). Only after the restore may the orchestrator derive `audit_state` or mutate other owned fields directly.

The owned-field set is defined by the constant `OWNED_FIELDS` in `.claude/skills/_shared/orchestrator_state_guard.py`:

```
pipeline_phase, audit_state, last_executor_outcome, verification_state, total_loop_attempts
```

Note: `total_loop_attempts` is included in `OWNED_FIELDS` so the snapshot/restore guard protects it from subagent writes. It is Routine-managed (not pipeline-owned) and is NOT zeroed on `drafted`-revert - unlike `audit_state`, its purpose spans resets to maintain the cross-session IAL guard (PLAN-AH1 FM2). The orchestrator reads it but must not reset it during audit-state resets.

Note: `status` is intentionally excluded from the guard. It is legitimately executor-written and outside the BUG-3 forgery surface. Guarding it would risk reverting a legitimate executor-set status.

**Required call sequence around every subagent dispatch:**

```python
import sys
sys.path.insert(0, ".claude/skills/_shared")
from orchestrator_state_guard import snapshot_owned_fields, restore_owned_fields

# Before dispatch:
snapshot = snapshot_owned_fields(plan_path)

# D1a carve-out: if this dispatch DIRECTS an owned-field value (e.g. plan-writer
# target_phase), set the intended value in the snapshot before restore so it survives:
#     snapshot["pipeline_phase"] = target_phase   # only on the directed path

# ... dispatch subagent ...

# Immediately after subagent returns, before reading any state:
restore_owned_fields(plan_path, snapshot)
# Now safe to run audit_loop.py and mutate owned fields.
```

**D1a carve-out ("Orchestrator-Directed-Writes").** When the orchestrator itself *directs* a subagent to write an owned field - specifically `plan-writer`'s `target_phase` parameter, which has plan-writer atomically write a new `pipeline_phase` alongside body content - the orchestrator MUST set that field in the snapshot dict to its *intended post-dispatch value* before calling `restore_owned_fields`. This preserves the orchestrator-directed change while still wiping any OTHER owned-field write the subagent made. The guard wipes undirected subagent owned-field writes; it never reverts a value the orchestrator deliberately requested.

### Verify, don't trust the narrator

**Principle (D4 - "Verify-Dont-Trust-Narrator").** The orchestrator independently verifies any subagent-CLAIMED state change against disk/git before acting. A subagent's return text is an assertion, not evidence. The orchestrator confirms claims against the filesystem or git log before treating them as true.

The canonical prior instance of this principle is `## Step 4F` (retire post-condition check, PLAN-AA2): when `plan-retirer` reports `outcome: success`, the orchestrator independently stats the source and destination paths before committing. The step 4F pattern is the template; all other subagent dispatches should apply the same verification discipline.

**Observed instance (2026-06-18 - BUG 3 / BUG 4 incident).** During this incident, two concrete failures of the "trust the narrator" pattern occurred:

1. A `plan-writer` dispatched only to revise a PLAN body returned claiming it had also flipped `pipeline_phase: drafted -> checked`, fabricated an `audit_state` with `last_outcome: success`, and written a forged `last_audit_commit` - all with no real audit. The snapshot/restore pattern (D1) closes this class of forgery.

2. A `plan-retirer` subagent reported it had "pushed to main" - git showed nothing was pushed. Verification against disk/git caught it; trusting the narrator would not have.

Subagents are unreliable narrators of their own side effects. Never treat a subagent's claimed outcome as authoritative without confirming it against the filesystem or git log.

The owned-field set guarded by the snapshot/restore mechanism: `pipeline_phase`, `audit_state`, `last_executor_outcome`, `verification_state`, `total_loop_attempts` (status excluded - see D1 above).

---

## Step 0: Acquire orchestrator lock

Before any state-mutating work, acquire the per-repo advisory lock using the helper at `.claude/skills/_shared/orchestrator_lock.py`:

```python
import sys
sys.path.insert(0, ".claude/skills/_shared")
from orchestrator_lock import acquire, release

lock_result = acquire(repo_root, phase=current_phase_or_empty, plan=plan_id_or_empty)
```

**If `lock_result["acquired"] is False`:** the lock is held by another active orchestrator walk. Surface the following refusal to the Human and return WITHOUT mutating any state, committing, or dispatching any subagent:

> "Another orchestrator walk is active (lock held since `<holder.acquired_at>`, phase `<holder.phase>`, plan `<holder.plan>`). Refusing to act to avoid forked history. If you believe this lock is stale, delete `Workbench/.orchestrator.lock` and re-invoke."

Do NOT attempt to wait, retry, or override the lock automatically.

**If `lock_result["acquired"] is True`:** proceed to Step 1. The lock MUST be released (via `release(repo_root)`) on EVERY return path from this invocation - including exception/halt paths, idempotent no-ops, and all kanban-halt branches in Step 4G. The release is a finally-style guarantee: every code path that passes Step 0 acquisition calls `release(repo_root)` before returning control to the parent session. Exception and halt branches in Step 7 and Step 4G MUST also call `release(repo_root)` before returning.

---

## Step 1: Resolve target PLAN

**If `plan_path` was supplied:**
- Read the file. If unreadable -> emit `exception` (orchestrator-side; commit not required since nothing changed).
- Parse frontmatter. If malformed -> `exception`.

**If only `request` was supplied (fresh entry):**
- Detect intent. If the request contains an existing PLAN reference (e.g. "resume the pipeline on PLAN_xyz"), resolve to its path and proceed as above.
- Otherwise, treat as a fresh planning request -> enter Step 4 (`drafting` phase) with no PLAN file yet.

**If both supplied:** prefer `plan_path`; treat `request` as additional context only.

**If neither:** emit `exception`. The orchestrator does not invent a target.

---

## Step 2: Read durable state

Extract from PLAN frontmatter (when a PLAN exists):

```
pipeline_phase             # absent or empty -> treat as drafted (plan-conventions ad-hoc default)
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
assigned_to                  # haiku (default) | sonnet | opus | human (never dispatched) | other
```

Treat any absent field as the documented default.

---

## Step 3: Idempotency and parent/children gates

**Resumption drift preflight.** On a pipeline *resume* (re-invoking plan-pipeline against an in-flight PLAN in a new or resumed session), the orchestrator SHOULD run the resumption drift preflight (`.claude/skills/_shared/resume_preflight.py::check_resume_drift`) - or rely on `rehydrate-handoff` Step 0 having already run it - before taking any state-changing action. If `result["drift"]` is `True`, halt and surface `result["summary"]` as a re-orientation block, requiring reconciliation (fetch/rebase, restart from the default branch on a merged PR, or re-read the drifted PLAN's current state) before proceeding. The preflight is read-only and fail-open (a `checked: false` axis never blocks). The write-side sibling is `push_guard.py` (`.claude/skills/_shared/push_guard.py`), which guards the end of the session (pre-push divergence check); `resume_preflight.py` is the start-of-session counterpart. Full wiring in `.claude/skills/rehydrate-handoff/workflows/read-handoff.md` Step 0 (primary surface).

**Idempotency check.** If the durable state shows the action for the current `pipeline_phase` has already been taken since the last meaningful change AND no new outcome is recorded since, return: "already at <phase>; nothing to do." This protects against parent-Claude double-invocation on a single trigger.

Concrete checks (applied in order):
- `pipeline_phase: complete` AND PLAN already retired -> no-op.
- **`pipeline_phase: drafting` AND (`ideate_phase ∉ {complete, exited_early}` OR `ideate_phase` field absent):** the PLAN is being actively shaped by the ideate cadence pipeline. plan-pipeline takes **no action (no-op)**. Return with: "PLAN is being ideated (ideate_phase: <value>); plan-pipeline waits until ideate_phase transitions to `complete`. Re-invoke after ideate completes." This makes `drafting` a long-duration phase that ideate owns. plan-pipeline must not advance or modify the PLAN until ideate hands off by flipping `ideate_phase: complete` + `pipeline_phase: drafted`.
  - Exception: if `ideate_phase` is absent and `pipeline_phase: drafting`, apply the same no-op. The PLAN may be in phases 1-3 (conversational; no `ideate_phase` set yet). plan-pipeline should wait.
  - Exception to the exception: if `pipeline_phase: drafting` AND `ideate_phase ∈ {complete, exited_early}`, fall through to Step 4 (`drafting` phase) as normal - ideate has finished and the PLAN can be re-driven.
- `pipeline_phase: executing` AND no `last_executor_outcome` recorded -> executor still running (or no completion message arrived); read `Workbench/.heartbeat/<plan-id>.json` if it exists and apply the following sub-branches:
  - If heartbeat file is absent or unreadable: no-op (executor may not have started yet or heartbeat was never written).
  - If heartbeat JSON is malformed: skip with a one-line log ("heartbeat for <plan-id> is malformed - skipping") and no-op.
  - If `phase: exited` is present in heartbeat: log "Executor exited but completion message not yet observed; waiting" - still no-op, awaiting completion re-entry.
  - If `last_tick_at` > 10 minutes ago AND `phase` is NOT `exited`: surface a one-line warning to the human: "⚠ Heartbeat stale for <plan-id> - last tick <ISO-ts>. Background executor may be hung." Routing unchanged (still no-op).
- `pipeline_phase: outcome-verifying` AND `verification_state.human_verdict: pending` AND no fresh `human_reply` supplied -> no-op (waiting on the Human).
- `pipeline_phase: drafted` AND `audit_state.last_outcome: revision_needed` AND PLAN file mtime not advanced since the audit_state write -> no-op (waiting on Human revision).

**Children gate.** If `triggers_plans` is non-empty, read each child PLAN's `status`. If any child is non-terminal (not in {`done`, `partially-complete`, `cancelled`, `closed`}), surface "Paused for children: <list>" with decision-15 triage, return. Do NOT advance the parent's `pipeline_phase`.

If gates pass, proceed to Step 4.

---

## Step 4: Dispatch by phase

Each branch below mutates frontmatter and commits as documented in [../references/phase-state-machine.md](../references/phase-state-machine.md). Only one branch executes per invocation (except the audit loop within `drafted`, which may dispatch one audit + record outcome + return).

### 4A. `drafting` (or no PLAN yet)

**Entry condition:** request without an existing PLAN, or a PLAN with `pipeline_phase: drafting`.

**Plan-boundary check (PLAN-AB5, H7 - soft warn-and-proceed).** Before dispatching ideate or write-plan against any PLAN, the orchestrator checks whether other PLANs are currently in flight:

- (a) Glob `Workbench/PLAN-*.md`. For each file, read the frontmatter field `pipeline_phase`.
- (b) Collect the set of **in-flight PLANs**: any PLAN whose `pipeline_phase` is in `{drafting, drafted, checked, executing, outcome-verifying}` (i.e. non-complete and non-empty/non-terminal).
- (c) If the in-flight set is non-empty AND the target PLAN is not in that set (i.e. this is a distinct plan being started while others are active):
  - Emit the following structured surface to the human before proceeding:
    ```
    <plan-boundary-warning>Active plans in flight: PLAN-X (pipeline_phase: Y), PLAN-Z (pipeline_phase: W). Dispatching ideate against TARGET-PLAN anyway. To pause this dispatch, set status: blocked or wait for the active plans to complete before re-invoking.</plan-boundary-warning>
    ```
  - Replace `PLAN-X`, `pipeline_phase: Y`, etc. with the actual PLAN IDs and phases found.
  - This is a **soft warn-and-proceed** - the orchestrator does NOT halt and does NOT require Human confirmation. The warning is visible; the operator decides whether to pause manually.
- (d) If the in-flight set is empty OR the target PLAN is already in the in-flight set (i.e. resuming an active plan): no warning, proceed normally.

The plan-boundary check uses no new frontmatter fields and requires no state file - it reads existing `pipeline_phase` values on every invocation.

1. Invoke `Skill("ideate", request_or_existing_path)` directly in the parent session. **Never via a subagent.**
2. The ideate arc walks Clarify -> Survey -> Converge with the Human. At checkpoint moments (clarify-locked, survey-converged), dispatch `plan-writer` foreground via the Agent tool to write or update the PLAN file. Each successful `plan-writer` return -> commit + push (template `plan-pipeline: drafted <plan-filename>` or `... drafting checkpoint <plan-filename>`).
3. When the Human signals ideation closed (any phrase that re-triggers the pipeline matcher, or an explicit "ready to audit"), the next orchestrator invocation flips `pipeline_phase: drafted` (Step 4 reads disk and falls into branch 4B). The ideate skill itself does not flip the phase.
4. Input escapes during ideate: ideate invokes `write-input` directly; resulting filenames land in the PLAN's `linked_inputs:` on the next `plan-writer` checkpoint. Commit + push after `write-input` returns (template `plan-pipeline: drafting input <filename>`).

Return control to parent after each `plan-writer` checkpoint (the arc itself is conversational; the orchestrator re-enters when the Human's next turn re-triggers the pipeline).

### 4B. `drafted` (audit loop)

**Patch-application procedure (PLAN-AJ0, sufficiency stage only, per D10).** On a `sufficiency | revision_needed` return, attempt this before falling through to the severity-surface wiring below - a demotion out of this procedure is what lands on the severity surface.

1. Read `payload.triaged_human_items` and `diagnostics.findings` from the sufficiency return `apply_audit_outcome` has just recorded.
2. Join each `mechanically_forced` entry in `triaged_human_items` to its finding in `diagnostics.findings` on `code` plus `location`. Per D3, if the pair matches more than one finding in the round, send every finding it matches straight to the human surface and apply none of their patches.
3. Call `pre_human_bound_reached(plan_path, current_iteration, bound=2)` from `.claude/skills/plan-pipeline/lib/patch_gate.py`, passing the path of the PLAN under audit and, as `current_iteration`, the iteration number of the round `apply_audit_outcome` has just written. If it returns `True`, route the whole round to the human surface - do not attempt the patch path. If it raises `DefectiveAuditRecord`, route the whole round to the human surface as well, as a defective-record signal, with the exception's message attached to the surfaced diagnostics, because a present-but-broken audit record must not be read as a round that never happened and the round must not be retried silently. Catch `DefectiveAuditRecord` by its type, not by catching every exception: an unrelated failure such as an `ImportError` or a missing module also produces a traceback but is not a defective-record signal, so let it halt the pipeline as a kanban halt rather than routing it as a defective record.
4. Otherwise call `resolve_patches(text, findings)` from the same module and apply each returned applicable patch with one Edit call against the PLAN file under audit, in the order returned, using `replace_all: true` only when the patch's `occurrence > 1`.
5. Call `renumber_steps` (from `.claude/skills/plan-pipeline/lib/step_renumber.py`) on the patched PLAN text. When the returned remap is non-empty, write the renumbered text back, call `remap_plan_fingerprints` (from `.claude/skills/plan-pipeline/lib/step_remap.py`) with that remap and write the updated frontmatter back, append the `renumber_report` output and the remap report to the round's audit snapshot under `orchestrator_note`, and append `{iteration: <N>, map: <remap>}` to the PLAN's `step_remaps` frontmatter list. This happens inside the same commit as the patch application in item 4.

   Either exception `renumber_steps` can raise routes the whole round to the human surface rather than being repaired - name the exception class in the surfaced message rather than treating both the same way, because they mean different things: `RefusedRenumber` fires whenever D6's predicate rejects the patched block's ordinal sequence, which is the likelier of the two on a real PLAN under audit; `ValueError` fires only when the block has no `## Steps` heading, which cannot be true of a PLAN mid-audit-loop. On `RefusedRenumber`, surface the exception's ordinal sequence, leave the patched text in place unrenumbered, and do not call `remap_plan_fingerprints` at all - there is no remap to carry, and calling it with an empty remap would write a misleading empty entry to `step_remaps`.
6. Route every demoted finding to the existing human-surface path, with its reason string attached to the finding's message so the human can see what was attempted.
7. Commit (template `plan-pipeline: applied <N> auditor-supplied patches for <plan-filename>`); re-dispatch `sufficiency-auditor`.

A mixed round of applied and demoted patches re-dispatches rather than waiting on the human - it does not surface and wait for a partial round. The orchestrator does not retry a demoted patch and does not author a replacement for one; a demoted finding simply recurs in the next round with its fingerprint intact. The orchestrator never applies a patch to any file other than the PLAN under audit.

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
    # On second ambiguous result from same human turn -> emit exception (two-strike rule).
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
    # Commit: "plan-pipeline: audit_human_reply - <K>ack/<L>dispute/<M>override on <plan-filename>"
    # Route per state-transition table in phase-state-machine.md "severity surface" rows.
```

State transitions after applying mutations (see references/phase-state-machine.md severity rows):
- Reply contains `fix`: commit mutations; await PLAN mtime advance; re-dispatch auditor on next re-entry.
- All errors covered by `override` actions (no `fix`): treat as audit success for this stage; advance.
- Only `ack`/`dispute` on warnings/notes; no errors: treat as success; advance.
- Errors remain unresolved: re-surface "errors remain - reply 'fix' or 'override <ID>: <reason>'."
- `extract` action: dispatch `Skill("write-plan")` to seed child PLAN; link `triggers_plans` on parent.
- `different-auditor` action: `audit_state.preferred_model_override` written; reset stage iter; await re-invocation.

**Brief construction.** Before each auditor dispatch (sufficiency or plan-safety), the orchestrator constructs the audit brief using the Python helper:

```bash
python .claude/skills/plan-pipeline/lib/build_brief.py \
  <plan_path> <auditor> <iteration> --output /tmp/audit_brief_<plan-id>.md
```

`<iteration>` is a cross-check only. The helper derives the real iteration from the audit JSONs in `Workbench/.audit/`. Do not count iterations yourself and do not treat the number you pass as authoritative.

**The helper is the iteration ceiling.** It raises `OrchestratorException` instead of writing a brief once the stage already has `MAX_ITERATIONS = 5` audits on disk, with the message `"audit loop did not converge after 5 iterations on <auditor>"`. Treat that failure as the kanban halt at 4G - emit `outcome: exception`, commit and push WIP, surface to the Human. Do not retry the helper, and do not dispatch the auditor without a brief. This is the only enforcement of the cap. Nothing in this document counts anything.

**Before surfacing that halt, dispatch the ceiling diagnostician.** See "Ceiling diagnosis" below. The cap stops the loop; it does not excuse handing the Human a bare failure.

Use `--output` (not a shell redirect `>`). Shell redirect is unreliable in orchestrator Bash calls - if the redirect is silently dropped, the brief file is empty and the next auditor dispatch returns `outcome: exception` with no useful diagnostics. `--output` writes the file atomically inside the helper and exits non-zero on any write failure. After calling the helper, assert that `/tmp/audit_brief_<plan-id>.md` exists and has non-zero size before dispatching the auditor agent.

The orchestrator reads `/tmp/audit_brief_<plan-id>.md` and embeds the contents verbatim as the user-message content in the `Agent()` dispatch. The subprocess + temp file pattern keeps `dispatch.md` Python-free and allows the helper to evolve independently.

**Per dispatch (post-helper, PLAN-AE0):** After the auditor returns, the orchestrator:

1. Parse the LAST `<pipeline-result>` block (text-scan as today).
2. Write the auditor's return JSON to `Workbench/.audit-tmp/<plan-id>-<stage>-<iteration>.json` (transient temp). Run:
   ```python
   # CLI invocation mirrors audit_loop.apply_audit_outcome() signature:
   # apply_audit_outcome(plan_path, stage, audit_return_json, iteration) -> dict
   result = subprocess.run(
       ['python', '.claude/skills/plan-pipeline/lib/audit_loop.py',
        plan_path, stage, audit_json_tmp_path, str(iteration)],
       check=True, capture_output=True, text=True,
   )
   result_dict = json.loads(result.stdout)
   ```
   The helper writes `Workbench/.audit/<plan-id>-<stage>-<iteration>.json` (the canonical snapshot), strips acknowledged findings, computes recurrence fingerprints, mutates PLAN frontmatter (`audit_state.last_stage`, `last_outcome`, `<stage>_iterations`, `last_audit_commit`), produces **two git commits** (`audit_state update - <stage>:<outcome>` + `record last_audit_commit for <plan-id>`), and returns the JSON dict the orchestrator needs.
3. If `result_dict["recurring_fingerprints"]` is non-empty, pass that list to `render_audit_surface(..., recurring_fingerprints=...)` for `[STUCK xN]` badging.
4. Branch on `result_dict["outcome"]` per the routing table below (unchanged).
5. The next auditor dispatch (sufficiency -> plan-safety, or revision re-run) builds its brief via `build_brief.py`, which has a precondition fingerprint check (added by PLAN-AE0): it refuses to dispatch if the expected commit-pair housekeeping is not present in git history. This is the belt-and-braces backstop - if the helper from step 2 was not called (orchestrator skip), the next stage fails loudly at brief-build time.

Delete `Workbench/.audit-tmp/<plan-id>-<stage>-<iteration>.json` after parsing (transient; the canonical snapshot lives in `.audit/`).

**Read `audit_state` and follow the lookup in references/phase-state-machine.md -> "Audit-loop dispatch table".** The decision tree:

| `last_stage` | `last_outcome`     | Next action                                                                                     |
|--------------|--------------------|-------------------------------------------------------------------------------------------------|
| none         | none               | Dispatch `sufficiency-auditor` (foreground).                                                    |
| sufficiency  | success            | Dispatch `plan-safety-auditor` (foreground). **Pre-dispatch guard:** re-read `audit_state.last_outcome` from PLAN frontmatter on disk immediately before dispatching. If the on-disk value is not `success`, abort - do NOT dispatch plan-safety. Surface: "plan-safety dispatch aborted: on-disk last_outcome is `<value>`, not `success`. The prior sufficiency outcome has not been applied yet. Re-invoke after applying the revision." This prevents premature dispatch when a sufficiency `revision_needed` iteration is still pending. |
| sufficiency  | revision_needed    | Awaiting Human revision; if PLAN mtime advanced since audit_state write, re-dispatch `sufficiency-auditor`; else no-op. |
| plan_safety  | success            | Both passed -> flip `pipeline_phase: checked`; commit + push; return. (No further dispatch this invocation.) |
| plan_safety  | revision_needed    | Awaiting revision; re-dispatch `plan-safety-auditor` after PLAN mtime advances. (Sufficiency does not re-run.) |
| any          | exception          | Kanban halt - already committed when exception was first emitted. Re-entry is a no-op until Human takes action. |

**Pre-dispatch (per iteration):**
1. Increment the appropriate iteration counter (`audit_state.sufficiency_iterations++` or `plan_safety_iterations++`).
2. **If counter > 5:** do NOT dispatch the auditor. Run the ceiling diagnosis below, then emit `outcome: exception` ("audit loop did not converge after 5 iterations - Human review required"), attaching the diagnostician's recommendation. Update `audit_state` accordingly, commit + push WIP, surface diagnostics, return.
3. Otherwise: announce the iteration to the Human ("Audit iteration <N>: dispatching <agent>"), dispatch foreground via `Agent({subagent_type: "<agent>", ...})`. Block until return.
4. **Post-dispatch:** run the `audit_loop.py` helper as described in "Per dispatch (post-helper)" above. The helper handles parsing, snapshotting, stripping, recurrence, frontmatter mutation, and both git commits.
5. Branch on `result_dict["outcome"]`:
   - `success` -> frontmatter already mutated by helper (`last_stage`, `last_outcome`, `last_audit_commit`). Re-enter Step 4B from the top within the same invocation only if the next stage is the other audit (sufficiency to plan-safety transition). Once `plan_safety` succeeds, flip `pipeline_phase: checked` and commit + push under that template, then return.
   - `revision_needed` -> frontmatter already mutated by helper. Apply decision-15 triage to `result_dict["review_text"]` if present; surface iteration counts; instruct the Human "Revise the PLAN and re-invoke me to re-audit." If `result_dict["narrative_findings_mismatch"]` is true, surface it alongside the findings: the auditor's reported `blockers_count` disagrees with the number of error-level findings in `diagnostics.findings` for this same return, so a finding may have been named in the narrative and dropped from the structured array a revision only checks against. Return.
   - `exception` -> kanban halt. Commit + push WIP with diagnostics. Surface diagnostics. Return.

**Ceiling diagnosis (mandatory whenever the cap fires).** The cap can fire two ways - `build_brief.py` raising `OrchestratorException`, or the pre-dispatch counter check above - and both take this path before anything is surfaced to the Human.

1. Dispatch `audit-ceiling-diagnostician` foreground, with `{plan_path, stage, audit_dir: "Workbench/.audit"}`. It is pinned to Opus and is read-only: it never edits the PLAN, writes to `.audit/`, commits, or advances `pipeline_phase`.
2. Write its `payload` into a `## Kanban halt` section in the PLAN body - the diagnosis, the recommended next step, the alternatives with their costs, and the tier-fit judgement. The orchestrator writes this, not the diagnostician, so the No-Trust-Subagent-State principle holds.
3. Surface the recommendation with the halt. The Human decides against a diagnosis rather than against a bare "did not converge".
4. If the diagnostician itself returns `outcome: exception`, surface the ceiling halt anyway with a note that diagnosis was unavailable and why. A diagnostician failure must never swallow the halt it was dispatched to explain.

The diagnosis does not resolve the halt and does not lift the cap. `build_brief.py` still refuses a sixth brief, and the recommended step is carried out by the Human or, once they choose it, by the orchestrator in a fresh pass. Do not treat a recommendation as authorisation to continue the loop, and do not delete or move audit JSONs to reset the derived counter - the counter is derived from those files so that a caller cannot reset it.

**One exception to "one phase per invocation":** within `drafted`, the orchestrator may chain sufficiency-success -> plan-safety-dispatch in a single invocation (commit between). This is allowed because no `pipeline_phase` boundary is crossed - both stages are within `drafted`.

### 4C. `checked`

**Single transition: dispatch executor.**

1. Read PLAN's `assigned_to` frontmatter. Map per the executor-tier table in references/phase-state-machine.md:
   - `human` -> **do not dispatch.** See the halt below.
   - `haiku`, empty, or unrecognised -> `plan-executor`.
   - `sonnet` -> `plan-executor-sonnet`.
   - `opus` -> `plan-executor-opus`.

   **`assigned_to: human` halts here.** Leave `pipeline_phase: checked`, dispatch no executor, and surface: "PLAN <filename> declares `assigned_to: human`. Its steps are outside the executor capability boundary, so the orchestrator will not dispatch one. Drive the steps in this session, then re-invoke at `outcome-verifying` when they are done." This is not a kanban halt - nothing has gone wrong and no WIP commit is needed. It is the routing outcome for a PLAN the pipeline audits and verifies but does not execute. Without this branch the value falls through to `unrecognised` and an executor is dispatched against steps it is structurally unable to perform, which is the PLAN-009 regression shape. **Return - do not continue to step 2.**
2. Flip `pipeline_phase: executing`. Set `status: in-progress`. Commit + push (`plan-pipeline: executing <plan-filename>`).
3. Dispatch the executor with `run_in_background: true`. The Agent call returns an agent ID; the orchestrator does NOT wait. Surface to the Human: "Executor <name> dispatched in background. I'll resume when it completes."
4. Return control to parent. The executor's completion message arriving in parent's conversation is the re-entry cue.

### 4D. `executing`

**Re-entry path.** Parent-Claude observed the executor's completion message and re-invoked this skill with `plan_path`. The orchestrator does not poll; this branch only runs on re-entry.

1. **Executor-return validation** (Reeve hiccup H10 / 2026-05-16). Before reading `last_executor_outcome` or treating any completion message as authoritative, validate the executor's return contains a well-formed `<pipeline-result>` block. Specifically:
   - If parent-Claude received a completion notification for this PLAN's executor dispatch, inspect the notification's result text.
   - The result MUST contain a literal `<pipeline-result>` block with a parseable JSON code fence per decision 23.
   - If the result is empty, contains a rate-limit string (e.g. `"You've hit your limit"`, `"resets at"`, `"rate-limited"`), or otherwise lacks the expected block: do NOT trust `last_executor_outcome` (it may not have been written, or may be stale from a prior run). Treat as `outcome: exception` with `diagnostics.reason = "executor return malformed: <empty | rate-limit | missing pipeline-result block>"`. Preserve heartbeat. Kanban halt. Commit + push WIP. Surface to Human with the raw completion text for inspection. Return.
   - This is structurally identical to the retire-skill post-condition pattern (section 4F step 3): the harness's "completed" status conflates "executor finished successfully" with "executor's invocation returned a result of any kind"; the orchestrator MUST verify the structured block exists before progressing.
2. Read `last_executor_outcome.outcome` from PLAN frontmatter (the executor's `execute-plan` workflow writes this - decision 24).
3. If absent or stale (executed date older than the dispatch) -> no-op. The completion message likely fired before the executor finished; wait for the next message.
4. Parse the most recent `<pipeline-result>` block from the executor's return (parent-Claude supplies it implicitly via the conversation; if not directly available, treat the frontmatter `last_executor_outcome` as canonical - that is the durable record per decision 24).
5. Branch:
   - `outcome: success` -> **Delete `Workbench/.heartbeat/<plan-id>.json`** immediately (heartbeat is no longer load-bearing; would otherwise mislead `/status` and INDEX alerts). Flip `pipeline_phase: outcome-verifying`. Commit + push (`plan-pipeline: outcome-verifying <plan-filename>`). Continue into branch 4E within the same invocation.
   - `outcome: revision_needed` -> **Delete `Workbench/.heartbeat/<plan-id>.json`** immediately (executor is done; heartbeat is stale). Revert `pipeline_phase: drafted`. Reset `audit_state` to fresh (`last_stage: none`, `last_outcome: none`, counters to 0) - content has changed materially, so prior audits are stale. Set `status: needs-revision`. Commit + push (`plan-pipeline: executor revision_needed <plan-filename>`). Surface executor's `diagnostics_summary` + Executor Notes pointer with decision-15 triage. Return.
   - `outcome: exception` -> **Preserve `Workbench/.heartbeat/<plan-id>.json`** (forensic data attached to the halt; deleted on the next phase transition out of halted state - see heartbeat lifecycle table below). Kanban halt. Commit + push WIP (`WIP: pipeline halted at executing for <plan-filename> - see diagnostics`). Surface diagnostics. Return.

**Heartbeat lifecycle table** (quick reference - full spec in `execute-plan/references/heartbeat-spec.md`):

| Phase transition | Heartbeat action |
|---|---|
| `executing` -> `outcome-verifying` (success) | Delete immediately after success commit |
| `executing` -> `drafted` (revision_needed) | Delete immediately after revert commit |
| `executing` -> halted (exception) | Preserve as forensic data |
| Halted -> any resumption (override / extract / dispute / different-auditor) | Delete as part of halt-recovery routine (before re-dispatching) |

**Halt-recovery heartbeat cleanup.** When the human resumes a halted PLAN via any action that triggers a new execution (override, extract, dispute, different-auditor), the orchestrator's halt-recovery routine MUST include: `if Workbench/.heartbeat/<plan-id>.json exists, delete it`. This is the explicit cleanup hook - not automatic, not deferred to a later phase.

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

1. Read PLAN's `## Verification` section. Extract every line annotated with `verify:`, `acceptance:`, `verify: human`, or `verify: orchestrator`.
2. For each `verify:` shell command (excluding `verify: orchestrator` and `verify: human`): run via Bash. Tally pass (exit 0) / fail.
3. For each `acceptance:` shell command: run via Bash. Tally pass / fail.
4. For each `verify: orchestrator` item: the orchestrator performs the verification itself (or via a dispatched non-executor verifier). Record a line-by-line attestation into `verification_state.orchestrator_attestations`:
   ```
   { item: <prose description>,
     verdict: pass | fail,
     evidence: <concrete evidence: command output, enumerated check>,
     verifier: <agent identity - never the executor> }
   ```
   A `verify: orchestrator` item DOES NOT add to `human_pending`. A `verify: orchestrator` pass contributes to the "all checks passed" branch condition; a fail routes like a shell failure (auto-revert unless a human item co-occurs).
5. For each `verify: human` item: when the substance is checkable by the orchestrator (attestation-then-assent flow - see `### Present-with-content rule` below), the orchestrator performs the full verification, records the attestation into `orchestrator_attestations`, and surfaces ONE choice to the human (accept-attestation / veto / dig-into-row-X). When the substance requires genuine subjective judgement (authority, not independence), capture the prose description into `verification_state.human_pending` as before.
6. Write `verification_state` frontmatter:
   ```
   verification_state:
     state_pass: <int>
     state_fail: <int>
     acceptance_pass: <int>
     acceptance_fail: <int>
     human_pending: [<list of prose descriptions>]
     human_verdict: pending
     orchestrator_attestations: [<list of attestation records>]
   ```
   Commit + push (`plan-pipeline: outcome-verification ran for <plan-filename>`).
7. Branch:
   - **Any `verify:`/`acceptance:`/`verify: orchestrator` check failed AND `human_pending` is empty** -> pure shell failure; auto-revert (existing behaviour). Revert `pipeline_phase: drafted`, reset `audit_state` to fresh, set `status: needs-revision`. Commit + push (`plan-pipeline: outcome-verification failed - reverting to drafted for <plan-filename>`). Surface failed-assertion list with decision-15 triage. Return.
   - **Any `verify:`/`acceptance:`/`verify: orchestrator` check failed AND `human_pending` is non-empty** -> mixed failure; invoke `render_outcome_surface()` with the shell failures AND human items. Human may `ack-failure` non-blocking shell failures before issuing `pass`. Route per severity-surface state-machine rows in phase-state-machine.md.
   - **All shell checks passed AND `human_pending` empty** -> flip `pipeline_phase: complete`. Commit + push (`plan-pipeline: complete <plan-filename>`). Continue into branch 4F.
   - **All shell checks passed AND `human_pending` non-empty** -> invoke `render_outcome_surface()`. Surface the structured severity-surface prompt. Return. The Human's reply re-triggers the orchestrator. On re-entry while `pipeline_phase: outcome-verifying` AND `human_verdict: pending`:
     - Parse reply via `parse_outcome_reply()`; apply via `apply_outcome_action()`.
     - `pass` (all failures acked, all human items acked) -> flip `pipeline_phase: complete`; commit + push.
     - `fail` or `reject-human` -> revert `pipeline_phase: drafted`; reset `audit_state`; commit + push.
     - Ambiguous reply -> re-prompt once. Second ambiguous -> emit `exception`.

### Present-with-content rule

Any item surfaced to the human MUST explode the actual content inline - before/after text, complete evidence sets - because the operator often cannot access the repo mid-conversation. The surface presents the human with a CHOICE (accept / veto / dig-into-row-X), not a reading assignment.

When building each `human_items` entry passed to `render_outcome_surface()`, the orchestrator populates three OPTIONAL evidence fields in addition to the existing `id` and `prose`:
- `evidence`: the attestation evidence string (sourced from the matching `orchestrator_attestations` record)
- `before`: inline before-content (original text / command output before change)
- `after`: inline after-content (new text / result after change)

`render_outcome_surface()` explodes these optional fields inline beneath the item's prose when present, rendering exactly as today when absent (backwards-compatible - the existing `id` and `prose` keys are untouched). When reading file content for inline explosion, open files with `encoding="utf-8", errors="replace"` so a malformed byte in a diff never crashes the surface renderer.

For `verify: human` items with attestation-then-assent, the orchestrator sources the `evidence` field from `orchestrator_attestations` and inlines it. The human then replies `accept-attestation H1`, `veto H1: <reason>`, or `dig-into H1` rather than performing the check themselves:
- `accept-attestation H1` -> records that attestation was accepted; contributes to overall `all_pass`; flip -> `complete` once all items resolved.
- `veto H1: <reason>` -> treats item as `rejected`; revert -> `drafted`; reset `audit_state`.
- `dig-into H1` -> orchestrator surfaces full evidence set for that item only; human re-prompts with `accept-attestation` or `veto`.

### False-positive acknowledgement path

When an `acceptance:`/`verify:` failure is demonstrably a false positive, the orchestrator MUST enumerate the COMPLETE match set and show each match is benign BEFORE surfacing the `ack-failure` request. Specifically:

1. Run the failing command; capture the full output.
2. Enumerate every match entry inline (not just a count).
3. For each match, demonstrate why it is benign (e.g. "this occurrence is inside a comment / test fixture / documentation block - not load-bearing code").
4. Auto-attach the enumerated analysis to `verification_state.failure_logs` (existing field).
5. Surface a ONE-WORD acknowledgement request: `ack-failure FN: <reason>` - reusing the existing `ack-failure` reply path (no new machinery required).

The operator sees the full evidence set and types `ack-failure F1: false positive - all matches confirmed benign`. The orchestrator then applies the existing `ack-failure` action, decrementing the effective fail count and re-evaluating state-transition logic (see phase-state-machine.md Surface 2 state-transition logic).

### 4F. `complete` (retire + drift check)

1. Dispatch `plan-retirer` foreground via the Agent tool with the PLAN path.
2. Parse the `<pipeline-result>` block.
3. **Post-condition verification** (PLAN-AA2 defense-in-depth pattern). When the subagent reports `outcome: success`, the orchestrator MUST independently verify the retire skill's success_criteria against the filesystem before committing. This catches the 2026-05-13 class of bug where the subagent self-reported success but `git rm`'d the file instead of moving it. Specifically, before treating `success` as success:
   - Compute expected destination: `<repo-root>/Retired/<original-basename>` (computed via `git rev-parse --show-toplevel`; basename derived from the PLAN path passed to the subagent).
   - Stat the source path - assert it does NOT exist on disk.
   - Stat the destination path - assert it exists, is a file, and has non-zero size.
   - If ANY assertion fails: override the subagent's reported outcome - treat it as `outcome: exception` with `diagnostics.reason = "post-condition violation: <specific failing check>"`. Halt; do NOT commit. Surface to Human via kanban-halt (branch 5) including the subagent's claimed-success message for contrast.
   - On all assertions passing: proceed to step 4.
4. Branch:
   - `success` (verified) -> commit + push (`plan-pipeline: retired <plan-filename>`). Surface "Pipeline complete: <plan-filename> retired." Continue to sub-step 5 (drift check).
   - `exception` (subagent-reported OR orchestrator-overridden) -> kanban halt. Commit + push WIP. Surface diagnostics using the kanban-halt surface (branch 5). Return.

5. **Compact suggestion (PLAN-AB5, H7).** After the retire commit (step 4 success), emit the following structured tag to the human:

   ```
   <compact_suggestion>Plan <plan-filename> retired. /compact suggested to reset working memory before the next plan-pipeline invocation.</compact_suggestion>
   ```

   Replace `<plan-filename>` with the actual filename of the PLAN that was just retired. The Claude Code harness picks up the `<compact_suggestion>` tag as a cue to run `/compact`; in a harness that does not support the tag, this is harmless prose. This surface exists to prevent the boundary-discipline failure pattern from H7 (PLAN-AB5): the orchestrator eagerly starting the next plan's ideate before compacting, losing working-memory continuity.

6. **Doc-drift check** (after successful retire, auxiliary). Read the just-completed PLAN's `files_touched` frontmatter. If any path matches any of the following patterns, foreground-dispatch `Skill("maintain-project-docs")` with no arguments - it audits the live state of CLAUDE.md and ARCHITECTURE.md against the current codebase (AGENT_RULES.md was dissolved 2026-05-14 per Option Y of ADVICE-003; its meta-policy lives in CLAUDE.md now):
   - `.claude/skills/*` (any skill change)
   - `.claude/commands/*` (any slash command change)
   - `.claude/skills/_shared/*` (invariants / plan-safe live here - ARCHITECTURE.md driver)
   - `.claude/agents/*` (executor capability boundaries - ARCHITECTURE.md driver)
   - `CLAUDE.md` itself
   - `ARCHITECTURE.md` itself

   Surface the skill's output to the human as a one-line summary: "Drift check: <outcome> - <brief description>". If the audit finds drift, the human invokes the produced PLAN at their discretion. If `files_touched` is absent or empty, skip silently. Failure of `maintain-project-docs` is logged (one line) but does NOT halt or revert the pipeline - this step is auxiliary.

7. **Auto-retire absorbed inputs (PLAN-AC0) + disposition cascade (PLAN-AF8).** After the retire commit (step 4 success) and drift check (step 6 auxiliary), walk the just-completed PLAN's `linked_inputs` frontmatter array. For each input file path:

   **Phase A - existing auto-retire path (three-gate):**
   - Read the input's frontmatter.
   - **Gate 1 - lifecycle_mode:** if `lifecycle_mode: reference` (default `input` if absent), SKIP to Phase B. Surface one-line: "Input <path> retained by auto-retire: lifecycle_mode=reference."
   - **Gate 2 - integration_status:** if `integration_status` is not already `integrated`, set it to `integrated` on the input's frontmatter and continue to Gate 3. The retire is the confirmation: a PLAN that reached `complete` with this input in its `linked_inputs` consumed it. Surface one-line: "Input <path> marked integrated by PLAN <plan-basename> retire."
   - **Gate 3 - all-feeds-retired:** read every PLAN in the input's `feeds_plan` field, and in `advises_plan` on a grandfathered ADVICE file. For each, check whether the file exists at `Retired/202605/<plan-basename>` or `Retired/<plan-basename>` or any `Retired/**/<plan-basename>`. If ANY consuming PLAN is still in `Workbench/`, SKIP to Phase B. Surface one-line: "Input <path> retained by auto-retire: PLAN <other-plan> still active."
   - **All gates pass -> auto-retire:** `git mv Workbench/<input-basename> Retired/<input-basename>` (or `Retired/202605/<input-basename>` to match the PLAN-retire convention if the input is from the current LOG month). Commit + push (subject to push_policy): `plan-pipeline: auto-retired <input-basename> (consuming PLAN <plan-basename> retired; integration_status: integrated)`. Phase B does NOT run for this input (already disposed).
   - **Robustness:** if any input read fails (file missing, malformed frontmatter), log one line ("input <path> unreadable - skipping auto-retire") and continue with remaining inputs. Do NOT halt the pipeline; this sub-step is auxiliary.

   Reference-mode inputs are deliberately NOT auto-retired by Phase A - reference-mode is durable knowledge. Gate 3 is what protects an input that feeds several PLANs incrementally: it stays in `Workbench/` while any consuming PLAN is still active, whatever its integration status. False-positive auto-retires would destroy in-flight context, and Gate 3 is the gate that prevents them.

   **Phase B - disposition cascade [Human] (PLAN-AF8).** Runs for each input that was NOT disposed by Phase A (i.e. any input the auto-retire gates skipped). This phase is `[Human]`-surfaced - the executor MUST NOT auto-decide dispositions.

   For each undisposed input, surface the following prompt to the Human:

   ```
   Input disposition required: <input-basename>
     Status: integration_status=<status>, lifecycle_mode=<mode>
     Reason not auto-retired: <the Gate 1/2/3 skip reason from Phase A>

   Choose one disposition:
     1. fold-to-corpus - The input's substance belongs in a durable working doc
        (e.g. ARCHITECTURE.md, a reference file, or inline in a consuming PLAN).
        Action: you fold the content manually, then confirm. The orchestrator will
        then retire the input file via `git mv` to Retired/.
     2. move-to-transient - Point-in-time-useful background that may be referenced
        again but is not authoritative. Action: the orchestrator will `git mv` the
        file to Workbench/transient/<input-basename>.
     3. retire - No longer needed; substance already absorbed or superseded.
        Action: the orchestrator will `git mv` the file to Retired/<input-basename>.

   Reply with: disposition: <1|fold-to-corpus|2|move-to-transient|3|retire>
   ```

   On Human reply:
   - **fold-to-corpus:** wait for the Human to confirm they have folded the content, then `git mv Workbench/<input-basename> Retired/<input-basename>`. Commit: `plan-pipeline: fold-to-corpus disposition - retired <input-basename>`.
   - **move-to-transient:** `git mv Workbench/<input-basename> Workbench/transient/<input-basename>`. Commit: `plan-pipeline: move-to-transient disposition - <input-basename>`.
   - **retire:** `git mv Workbench/<input-basename> Retired/<input-basename>`. Commit: `plan-pipeline: disposition retire - <input-basename>`.
   - **Ambiguous / no reply:** log one line ("input <path> disposition deferred - Human did not reply; input left in Workbench/") and continue. Do NOT halt the pipeline.

   Phase B is auxiliary: if it fails for any input, log one line and continue to the next input. Never halt the complete-phase pipeline for a Phase B failure.

### 4G-halt. Exception / kanban halt (any phase, branch 5)

**Severity-surface wiring (kanban-halt, any phase).** Whenever the orchestrator emits `outcome: exception` (the iteration ceiling raised by `build_brief.py`, malformed return, git failure, uninterpretable human reply, executor exception), invoke the halt-surface modules:

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
# Route on action: retry -> re-dispatch; override -> advance phase; reset-stage -> reset counter + re-dispatch;
# different-auditor -> write model override + reset + await; abandon -> status: cancelled; pipeline_phase: complete.
```

State transitions on halt-recovery actions are documented in references/phase-state-machine.md "Severity-surface state-machine additions" table.

---

## Step 5: Children-aware advancement (when this PLAN spawns children)

If the active PLAN's `triggers_plans:` was populated during `drafting` (e.g. ideation produced a parent-of-plans), the children-gate in Step 3 prevents the parent from auto-advancing past `checked` until children reach terminal status. The Human typically:
1. Runs the orchestrator on the parent through `drafted -> checked` (parent's own design is audited).
2. Manually flips children's `status: blocked -> ready` (or runs the orchestrator on each child if they themselves use the pipeline).
3. Once all children terminal, re-invokes the orchestrator on the parent - Step 3's children gate now passes, and 4C dispatches the parent's executor.

The orchestrator does not poll children. Re-entry is the cue.

---

## Step 6: Bootstrap exception

While the parent PLAN `202605011400_PLAN_build-plan-pipeline-orchestrator.md` is itself executing (its own `pipeline_phase` is non-`complete`), the orchestrator does NOT manage git for it - the Human commits manually after each `execute-plan` call, per the bootstrap instructions in that PLAN's Constraints section. This branch is detected by inspecting whether the active PLAN is the parent bootstrap file.

For all other PLANs, full git milestone discipline applies.

---

## Step 7: Always commit (or fail loud) and return

After any phase work in Step 4, before returning control:
- If any frontmatter or filesystem change happened, the appropriate `git add <paths> && git commit -m "<template>"` was already run inline (per the templates), with `<paths>` resolved from the `Staged paths` column and the `Staging scope` section in `references/phase-state-machine.md`. `git push` follows only when `push_policy == "auto"` (see preamble). When `push_policy == "manual"`, the commit lands locally and the `<push_status>` surface is emitted instead.
- If `git push` failed at any point, the orchestrator already emitted `exception` and committed WIP locally (push will be retried on Human action).

### Step 7a: Pre-push divergence check

When `push_policy == "auto"` and the orchestrator is about to run `git push`, it MUST first call the divergence guard:

```python
import sys
sys.path.insert(0, ".claude/skills/_shared")
from push_guard import check_push_safe

result = check_push_safe(repo_root)
```

**If `result["safe"] is False`:** do NOT run `git push`. The milestone commit has already landed locally; local history is not lost. Raise the orchestrator's own `outcome: exception` (kanban halt per SKILL.md `exception_conditions`). Surface the following diagnostics to the Human:

> "Pre-push divergence detected: local branch is `<result['behind']>` commit(s) behind `origin/<branch>` and `<result['ahead']>` commit(s) ahead. Push refused to prevent forked history. You must reconcile manually - do NOT use `--force` or `--force-with-lease`. Run `git fetch && git log --oneline origin/<branch>..HEAD` to inspect local-only commits, then rebase or cherry-pick as appropriate. Re-invoke after reconciliation."

Return after emitting the kanban halt. `release(repo_root)` MUST be called before returning (per Step 0's finally-style release guarantee).

**If `result["safe"] is True`:** proceed with `git push` as normal. The reason string from `result["reason"]` is available for diagnostic logging if needed.

**If the check was skipped** (`result["safe"] is True` and `result["reason"]` contains "skipped"): proceed with `git push`. The native git non-fast-forward rejection remains the backstop.

- If nothing changed (idempotent no-op), no commit needed.

Return control to parent-Claude with a one- or two-sentence summary of what just happened (which phase advanced, or which prompt is now in front of the Human, or that this was a no-op).
