---
title: Plan-Pipeline Phase State Machine
description: Lookup tables and templates for the orchestrator - phase/outcome routing, the audit-loop dispatch table, agent dispatch table, frontmatter mutation cheat sheet, staging scope and commit-message templates.
created: 2026-08-17
---

# Plan-Pipeline Phase State Machine

Lookup tables and templates for the orchestrator. [../workflows/dispatch.md](../workflows/dispatch.md) carries the procedural narrative, while this file carries the lookups.

---

## Phase enum

```
drafting -> drafted -> checked -> executing -> outcome-verifying -> complete
```

`outcome-verifying` is a transient phase that the orchestrator always enters between `executing` and `complete` (per parent PLAN 202605011400 decision 25), and the orchestrator never skips that phase.

**Ad-hoc PLAN default:** `pipeline_phase` absent or empty -> treat as `drafted`. Do not treat as `drafting`, because that would re-ideate an already-authored PLAN.

---

## (Phase, Outcome) -> Action routing table

This routing table is the load-bearing contract (decisions 19, 20). `outcome` always comes from a `<pipeline-result>` block (subagent return) or from the orchestrator itself (MAX_ITERATIONS, git failure, malformed return).

| Phase                | Outcome           | Next action                                                                                                  |
|----------------------|-------------------|--------------------------------------------------------------------------------------------------------------|
| drafting             | (n/a - interactive) | Continue the arc, with `plan-writer` checkpoint commits.                                                            |
| drafted              | success           | Audit-loop dispatch table below.                                                                             |
| drafted              | revision_needed   | Update `audit_state`, commit, surface the review, await Human revision, and return.                                  |
| drafted              | exception         | Kanban halt: commit + push WIP, surface diagnostics, and return.                                                 |
| checked              | (n/a)             | Flip -> `executing`, commit, dispatch the executor (background), and return.                                          |
| executing            | success           | Flip -> `outcome-verifying`, commit, and continue into outcome-verification.                                      |
| executing            | success (subtype: gate-halt) | Flip -> `outcome-verifying`, commit, and continue into outcome-verification. The PLAN's paired `verify: human` items surface as `human_pending`. |
| executing            | revision_needed   | Revert -> `drafted`, reset `audit_state`, set `status: needs-revision`, commit, surface, and return.              |
| executing            | exception         | Kanban halt: commit + push WIP, surface, and return.                                                             |
| outcome-verifying    | all-pass, no human_pending | Flip -> `complete`, commit, and dispatch `plan-retirer`.                                                |
| outcome-verifying    | shell-fail        | Override executor success -> revision_needed, revert -> `drafted`, reset `audit_state`, commit, surface, and return. |
| outcome-verifying    | human_pending     | Surface the structured prompt (attestation-then-assent where checkable - see dispatch.md `### Present-with-content rule`), commit the `verification_state` write, return, and await the Human reply. |
| outcome-verifying    | human_verdict: all_pass | Flip -> `complete`, commit, and dispatch `plan-retirer`.                                                    |
| outcome-verifying    | human_verdict: rejected | Override -> revision_needed, revert -> `drafted`, reset `audit_state`, commit, surface, and return.          |
| outcome-verifying    | attestation-then-assent: accept-attestation | The Human accepted the orchestrator attestation for a `verify: human` item, so tally the item as passed. When all items are resolved -> flip -> `complete`, commit, and dispatch `plan-retirer`. |
| outcome-verifying    | attestation-then-assent: veto | The Human vetoed the orchestrator attestation for a `verify: human` item, so treat the veto as `human_verdict: rejected`, revert -> `drafted`, reset `audit_state`, commit, surface, and return. |
| outcome-verifying    | attestation-then-assent: dig-into | The Human requested full evidence for a specific item, so the orchestrator surfaces the full evidence set for that item, returns, and awaits a Human reply of `accept-attestation` or `veto`. |
| complete             | success           | `plan-retirer` returned success -> commit the retire, run the drift-check sub-step, surface "pipeline complete", and return. |
| complete             | exception         | Retire failed -> kanban halt, commit WIP, surface, and return.                                                    |
| complete (drift-check) | n/a (auxiliary) | If `files_touched` intersects skill/command paths or `CLAUDE.md`, dispatch `maintain-project-docs` foreground. The orchestrator logs a failure without halting, and this sub-step has no separate phase transition. |
| any                  | malformed return  | The orchestrator emits `exception`, commits and pushes WIP, surfaces "subagent return malformed", and returns.              |
| any                  | git failure       | The orchestrator emits `exception`, commits WIP locally where possible, surfaces "git operation failed: <op>", and returns. |

**Gate-halt note:** a `gate-halt` return (`outcome: success`, `outcome_subtype: gate-halt`) routes forward to `outcome-verifying` and does not revert to `drafted`. The orchestrator surfaces the remaining human work at `outcome-verifying` as `human_pending` **via the PLAN's paired `verify: human` Verification items** (the gate-halt authoring convention in `execute-steps.md` Step 4) rather than dropping the work. A gate-halt does not trigger the `executing | revision_needed` destructive-revert row.

---

## Audit-loop dispatch table (within `drafted`)

The durable `audit_state` frontmatter drives this loop, per parent decision 21.

| `audit_state.last_stage` | `audit_state.last_outcome` | Next dispatch                                | Iteration counter incremented |
|--------------------------|----------------------------|----------------------------------------------|-------------------------------|
| none                     | none                       | `sufficiency-auditor`                        | `sufficiency_iterations`      |
| sufficiency              | revision_needed            | Apply auditor-supplied patches for findings whose `triaged_human_items` class is `mechanically_forced`, then re-dispatch `sufficiency-auditor` (mtime-gate bypassed on the patch path). Otherwise dispatch `sufficiency-auditor` (after Human revision) | `sufficiency_iterations` |
| sufficiency              | success                    | `plan-safety-auditor`                        | `plan_safety_iterations`      |
| plan_safety              | revision_needed            | `plan-safety-auditor` (after Human revision, with sufficiency not re-run) | `plan_safety_iterations` |
| plan_safety              | success                    | (none) - flip `pipeline_phase: checked` and exit the loop. | (n/a)                  |
| any                      | exception                  | (none) - kanban halt already in effect.      | (n/a)                         |

**Patch-application path (PLAN-AJ0):** applies to `last_stage: sufficiency` only, per D10 - the `plan_safety` stage does not emit `triaged_human_items` and its `revision_needed` outcomes follow the existing human-surface path unchanged. On a `sufficiency | revision_needed` return, join each `mechanically_forced` entry in `triaged_human_items` to its finding in `diagnostics.findings` on `code` plus `location`, then call `pre_human_bound_reached` (in `.claude/skills/plan-pipeline/lib/patch_gate.py`) with the PLAN path and the iteration number of the round just written. The human-surface path applies instead of the patch path when any `real_judgement_call` item is present, when no `mechanically_forced` finding carries an applicable patch, when `pre_human_bound_reached` returns `True`, or when `pre_human_bound_reached` raises `DefectiveAuditRecord`.

In a mixed round - some patches apply, some demote - the orchestrator applies what applies, records the demotions against the existing human-surface path, commits, and re-dispatches `sufficiency-auditor`. The orchestrator does not surface and wait, because a demoted finding recurs in the next round with its fingerprint intact, so nothing is lost by letting the round finish.

**mtime gate carve-out:** the orchestrator bypasses the re-revision mtime no-op gate ("if mtime is not advanced and `last_outcome: revision_needed`, orchestrator no-ops waiting on human") on the patch path, for the same reason the predecessor auto-fix path bypassed the gate - the PLAN file itself does not change when the orchestrator applies a patch, so a mtime-advance requirement would starve the loop.

**Pre-human bound:** `pre_human_bound_reached` in `lib/patch_gate.py` derives the pre-human repair bound of 2 from the audit JSONs already on disk in `Workbench/.audit/`. The orchestrator neither increments nor stores this bound, and no frontmatter counter records the bound. The bound applies inside the unchanged stage ceiling of `MAX_ITERATIONS = 5` on `sufficiency_iterations`.

**Commit message template for patch application:** `plan-pipeline: applied <N> auditor-supplied patches for <plan-filename>`.

**Renumber-and-remap (PLAN-AJ1):** the orchestrator follows patch application (item 4 in dispatch.md section 4B), in the same commit, with a deterministic renumber of the patched `## Steps` block (`step_renumber.py`) and a remap of the resulting ordinal changes into the PLAN's fingerprint-keyed frontmatter (`step_remap.py`), so an insertion does not silently invalidate an acknowledgement, dispute, or override pointing at a shifted Step. On a renumber failure - `RefusedRenumber` on a restarting sub-run, or `ValueError` on a missing `## Steps` heading - the orchestrator routes the whole round to the human surface rather than repairing the round.

**MAX_ITERATIONS = 5** applies per stage, defined in `lib/audit_loop.py` and enforced in `lib/build_brief.py`. The orchestrator does not count iterations and must not attempt a count. `build_brief.py` derives the iteration from the audit JSONs in `Workbench/.audit/` and raises `OrchestratorException` rather than returning a brief once five audits exist for that stage. Because the orchestrator cannot dispatch an auditor without a brief, the ceiling stops the loop before anyone pays for the dispatch.

On that exception the orchestrator dispatches `audit-ceiling-diagnostician` (Opus, foreground, read-only) before surfacing anything, writes its diagnosis and recommended next step into the PLAN's `## Kanban halt` section, then emits `outcome: exception` with diagnostics_summary `"audit loop did not converge after 5 iterations on <stage>"`, commits and pushes WIP, and returns. Procedure: `workflows/dispatch.md` -> "Ceiling diagnosis". The diagnosis never lifts the cap or authorises another lap. The diagnostician exists so the human decides against a diagnosis rather than against a bare failure, and because reconstructing five rounds of audit history by hand is a cost the loop should absorb rather than pass to the human.

The iteration number is derived, never supplied. `apply_audit_outcome` accepts an `iteration` argument for cross-checking only, reports a disagreement as `iteration_mismatch`, and uses the value derived from disk. Before 2026-07-29 the counter was whatever the caller passed, so a caller passing `1` every round held the counter at `1` and overwrote each prior audit JSON in place.

**Re-revision detection.** "After Human revision" means PLAN file mtime is later than the last `audit_state` commit timestamp. If mtime is not advanced and `last_outcome: revision_needed`, the orchestrator no-ops (waiting on Human).

**On commit after Human revision** (before re-dispatching the audit): stage the `PLAN` class by name and commit with `plan-pipeline: human-revised <plan-filename> (audit_state.<stage>_iterations=<N>)`. Push follows only per `push_policy`. See the `## Staging scope` section for the staging rule.

---

## Agent dispatch table

| Phase / sub-phase                                | Agent name                                                                | Mode       | Input fields                                              | Output payload (relevant fields used by orchestrator) |
|--------------------------------------------------|---------------------------------------------------------------------------|------------|-----------------------------------------------------------|------------------------------------------------------|
| drafting (checkpoints)                           | `plan-writer`                                                             | foreground | `{plan_content, target_filename, mode: create|update}`    | `{filename_written, action, log_updated}`            |
| drafting (input)                                 | (skill `write-input`, parent-session direct, not a subagent)              | n/a        | `{type: INPUT, topic, body}`                               | written filename                                     |
| drafted (audit, sufficiency)                     | `sufficiency-auditor`                                                     | foreground | `{plan_path}`                                              | `{blockers_count, review_text, triaged_human_items}` |
| drafted (audit, patch application - PLAN-AJ0)   | (orchestrator applies auditor-supplied patches directly - no subagent dispatched) | n/a | n/a                                                        | n/a                                                   |
| drafted (audit, plan-safety)                     | `plan-safety-auditor`                                                     | foreground | `{plan_path}`                                              | `{blockers_count, review_text}`                      |
| executing (executor dispatch by `assigned_to`)   | `plan-executor` (Sonnet, default) / `plan-executor-sonnet` / `plan-executor-opus` | **background** | `{plan_path}`                                              | `{outcome_subtype, executor_notes, files_modified}`  |
| outcome-verifying (shell + human)                | (orchestrator runs Bash directly - no subagent)                            | n/a        | n/a                                                        | n/a                                                  |
| complete (retire)                                | `plan-retirer`                                                            | foreground | `{plan_path}`                                              | `{retired_path, gitignore_updated}`                  |

**Executor tier selection** (PLAN-driven, decision 8):

| PLAN frontmatter `assigned_to:`        | Agent dispatched               |
|----------------------------------------|--------------------------------|
| `haiku`, empty, absent, or unrecognised | `plan-executor` (**Sonnet** - default) |
| `sonnet`                               | `plan-executor-sonnet` (identical to default) |
| `opus`                                 | `plan-executor-opus`           |
| `human`                                | **none - do not dispatch.** Halt at `checked` and hand the walk to the Human. |

**`assigned_to: human` is a routing value, not a label.** A PLAN whose steps only a human-driven parent session can perform - invoking `plan-pipeline`, `ideate`, `write-input`, or otherwise acting outside the executor capability boundary in [../../_shared/executor-capability-boundary.md](../../_shared/executor-capability-boundary.md) - declares `assigned_to: human`, and the orchestrator MUST NOT dispatch any executor for that PLAN. Without this row the value falls to `unrecognised` and routes to `plan-executor`, which is the failure this row exists to prevent: the PLAN declares that no executor is dispatched, and the dispatch path dispatches one anyway. `scripts/ci/check-human-not-dispatched.py` names every surface that states this mapping and fails CI if any of them loses the branch. Add a new statement of the mapping to that guard's `REQUIRED` on the day the statement is written. That guard lists the surfaces it covers and this paragraph deliberately does not, so this paragraph cannot go stale as those surfaces change.

**Execution floor is Sonnet (recalibrated 2026-07-04).** Haiku is retired as a plan-execution tier - `plan-executor` now runs Sonnet 5. The legacy `assigned_to: haiku` value and the empty default both route to the Sonnet `plan-executor`, and `sonnet` routes to the identical `plan-executor-sonnet`. Only `opus` differs (design-heavy execution). `assigned_to` is a guideline - Human may override per PLAN. Per decision 16's anti-monolithic principle, prefer decomposition over `opus` execution, because `plan-executor-opus` is an escape hatch rather than a default.

---

## Gitignored paths

The following paths are gitignored and managed by the orchestrator/executor out-of-band. They must not be committed.

| Path | Owner | Purpose |
|---|---|---|
| `Workbench/.heartbeat/` | Executor (writes), Orchestrator (deletes) | Live execution progress signals, one JSON file per active executor run. The orchestrator deletes the file at `outcome-verifying` or at a `drafted` revert, and preserves the file on `exception`. |
| `Workbench/.orchestrator.lock` | Orchestrator | Single-orchestrator lock. |
| `Workbench/.audit-tmp/` | Orchestrator | Audit scratch space. |

Audit JSON under `Workbench/.audit/` is tracked and is staged by name per the `## Staging scope` section below. `.gitignore` is the authority, and this table must agree with `.gitignore`.

---

## Frontmatter mutation cheat sheet

The orchestrator may write these fields directly (without going through `plan-writer`) because they are orchestration-owned, not body content. Use the Edit tool on the PLAN file's YAML frontmatter block. One field below, `total_loop_attempts`, is orchestration-owned but written by the Routine rather than by the orchestrator - its own entry states what the orchestrator may do with it.

### `pipeline_phase`
The orchestrator mutates this string enum at every phase transition. Values: `drafting | drafted | checked | executing | outcome-verifying | complete`.

### `audit_state`
```yaml
audit_state:
  sufficiency_iterations: 0
  plan_safety_iterations: 0
  last_stage: none           # none | sufficiency | plan_safety
  last_outcome: none         # none | success | revision_needed | exception
  last_audit_commit: ""      # short SHA (8 chars, git rev-parse --short=8 HEAD) of the commit that wrote
                             # the most recent audit file; used as the diff anchor for the next re-audit brief.
                             # Written by a SECOND commit after the audit_state update commit - never amended.
  preferred_model_override: ""  # auditor model override (e.g. "sonnet"); empty = default
```
Reset to fresh (all zeros / `none` / empty strings) when reverting from `executing` or `outcome-verifying` back to `drafted` (PLAN content has changed, so prior audits are stale).

### `last_executor_outcome`
The `execute-plan` workflow writes this field on completion (per decision 24). The field is read-only for the orchestrator:
```yaml
last_executor_outcome:
  outcome: success            # success | revision_needed | exception
  outcome_subtype: done       # done | partially-complete | blocked | needs-revision | gate-halt
  executed: 2026-05-01
  diagnostics_summary: ""
```

`gate-halt` pairs with `outcome: success`. See the `executing | success (subtype: gate-halt)` routing row.

### Heartbeat file (out-of-band, not PLAN frontmatter)

`Workbench/.heartbeat/<plan-id>.json` - gitignored, orchestrator-managed, deleted at `outcome-verifying`/`drafted` revert. Schema:

```json
{
  "schema_version": 1,
  "plan_id": "<plan-id>",
  "phase": "starting | running | halting | exited",
  "current_step": 3,
  "step_summary": "<first ~80 chars of step text>",
  "last_tick_at": "2026-05-13T10:00:00Z",
  "notes": "",
  "tool_calls_since_last_tick": 0
}
```

Stale threshold: `last_tick_at` > 10 minutes ago AND `phase != exited` -> surface warning. Full spec: `.claude/skills/execute-plan/references/heartbeat-spec.md`.

### `verification_state`
```yaml
verification_state:
  state_pass: 0
  state_fail: 0
  acceptance_pass: 0
  acceptance_fail: 0
  human_pending: []
  human_verdict: pending      # pending | all_pass | rejected
  human_diagnostics: ""       # populated when human_verdict: rejected
  human_acknowledged_failures: []  # one entry per shell failure the Human accepted with `ack-failure`:
                                   # { check: <failure id, e.g. F1>, rationale: <str>, ack_date: <YYYY-MM-DD> }
  failure_logs: {}            # failure check name -> truncated stderr/stdout (<= 200 chars)
  human_passed: []            # the human-item ids (H1, H2, ...) the Human passed, appended by an
                              # `ack-human` or `accept-attestation` reply and never duplicated
  orchestrator_attestations: []
  # Each entry in orchestrator_attestations is a record:
  #   { item: <str>,      # the verification prose being attested
  #     verdict: pass|fail,
  #     evidence: <str>,  # concrete evidence: command output, enumerated match set, line-by-line check
  #     verifier: <str>   # the agent identity that performed the check - NEVER the executor }
  #
  # verify: orchestrator items populate orchestrator_attestations and NEVER human_pending.
  # A verify: orchestrator pass contributes to the "all checks passed" branch condition.
  # A verify: orchestrator fail routes like a shell failure: auto-revert unless a human item co-occurs.
```

### `status`
Existing field. Orchestrator mutates on phase boundaries:
- Entering `executing` -> `status: in-progress`.
- Reverting from `executing`/`outcome-verifying` -> `drafted` -> `status: needs-revision`.
- After successful retire -> `status: done` (already set by `execute-plan`; just confirm).

PLAN frontmatter `status` is the sole canonical surface for PLAN state.

### `total_loop_attempts`

An integer, treated as 0 when the field is absent. The Routine that the `autonomous-loop` skill creates increments this counter by 1 on every firing it does not defer, and a firing deferred because another session holds the orchestrator lock leaves the counter alone. That Routine warns the operator at 8 and self-terminates at the ceiling of 10 (see [../../autonomous-loop/workflows/run-loop.md](../../autonomous-loop/workflows/run-loop.md)). The field is listed in `OWNED_FIELDS` in [../../_shared/orchestrator_state_guard.py](../../_shared/orchestrator_state_guard.py) so the snapshot/restore guard protects it from subagent writes, but the orchestrator only reads it. Unlike `audit_state`, this counter is NOT reset when reverting to `drafted`, because its purpose is to span those resets and bound the loop across sessions.

### `step_remaps`

A list, empty by default. Each entry is `{iteration: <int>, map: [{"old": <int>, "new": <int>}, ...]}`. The orchestrator appends one entry per renumber the patch-application procedure performs (see [../workflows/dispatch.md](../workflows/dispatch.md) branch 4B, item 5), inside the same commit as the patch application, so an acknowledgement, dispute, or override keyed to a Step ordinal can still be traced after an inserted patch shifted that ordinal. The orchestrator appends nothing when the remap is empty. The list is never hand-edited and never reset.

---

## Staging scope

Every pipeline commit stages an explicit list of paths. The orchestrator stages what the phase it is committing wrote, and nothing else. A file present in the tree that the orchestrator cannot attribute to the phase is not staged, and is left visible as a dirty tree for the next phase to surface.

The orchestrator MUST NOT run `git add -A`.

The artefact classes the commit-template table refers to:

| Class | Paths | Notes |
|---|---|---|
| `PLAN` | `Workbench/<plan-filename>` | The active PLAN file, whenever the phase wrote its frontmatter or body. |
| `AUDIT` | `Workbench/.audit/<plan-id>-<n>.json` | Tracked. Stage the audit file this iteration wrote. |
| `WORK` | The paths the executor reported in its `files_modified` return payload | Stage the returned list. Cross-check the list against the PLAN's `files_touched` frontmatter and stage anything in `files_modified` that `files_touched` omits, because the return is authoritative. Note the discrepancy in the phase surface. |
| `INPUT` | `Workbench/<input-filename>` | The input file `write-input` just wrote. |
| `UNBLOCKED-PLAN` | `Workbench/<unblocked-plan-filename>`, one entry per PLAN `write-input` reports as unblocked | `write-input/SKILL.md` states the report contract as "Report back: filename written, PLAN(s) unblocked if any" and constrains "Never clear `blocked_by` without also flipping `status: blocked` -> `ready` in the same edit", recording the input filename in its `linked_inputs`. Not reachable today, because the workflow inspects one `feeds_plan`/`advises_plan` target, although the class is written plural so it does not repeat the singular-assumption shape it exists to fix. Stage this class only when `write-input` reports at least one unblocked PLAN. |
| `RETIRE-PAIR` | `Workbench/<plan-filename>` and `Retired/<plan-filename>` | Both named, because the move leaves a deletion at the source and an addition at the destination. |
| `CHILD-PLAN` | `Workbench/<child-plan-filename>` | The PLAN `write-plan` seeds when an `extract <ID>` reply is applied (Surface 1 and Surface 3). Stage the child PLAN alongside the parent PLAN whose `audit_extracted` or `triggers_plans` field records the link. |
| `HEARTBEAT` | never staged | `Workbench/.heartbeat/` is gitignored. |

### RETIRE-PAIR on a partial move

The retire skill performs a filesystem move without running any git command, so a halt part-way through leaves the PLAN body deleted-but-unstaged at the source and untracked at the destination. The retire skill's own workflow records the 2026-05-13 incident in which PLAN bodies were lost exactly this way, and without staging `RETIRE-PAIR` on the halt route that loss is unrecoverable.

Therefore, on any halt route, stage whichever of the two paths actually exists on disk and only those - never both by fixed name, because `git add` is fatal on a pathspec that matches no file, and a halt mid-move is by definition a partial move, so naming the destination when the halt preceded its creation would take down the very commit the rule exists to guarantee. Do not widen the `git add` to the parent directories to dodge that: `git add Workbench/ Retired/` stages every dirty and untracked file under both, which is blanket staging with a narrower argument, on the one route where the tree is least likely to be clean.

---

## Commit-message templates

Every commit is `git add <paths> && git commit -m "<template>"`. Resolve `<paths>` from the `Staged paths` column below via the `## Staging scope` section above. Push follows only per `push_policy` (see preamble). Never pass `--no-verify`, `--force`, or `--force-with-lease`. If push fails -> orchestrator emits `exception` (commit is already local).

| Trigger                                          | Template                                                                                            | Staged paths |
|--------------------------------------------------|-----------------------------------------------------------------------------------------------------|--------------|
| `plan-writer` returned success during drafting   | `plan-pipeline: drafting checkpoint <plan-filename>`                                                | `PLAN` |
| `plan-writer` returned success at draft-close    | `plan-pipeline: drafted <plan-filename>`                                                            | `PLAN` |
| `write-input` lands during drafting              | `plan-pipeline: drafting input <input-filename>`                                                    | `INPUT` + `UNBLOCKED-PLAN` (when `write-input` reports an unblocked PLAN) |
| Human-revised PLAN, before re-audit              | `plan-pipeline: human-revised <plan-filename> (audit_state.<stage>_iterations=<N>)`                 | `PLAN` |
| Auditor-supplied patches applied (PLAN-AJ0)      | `plan-pipeline: applied <N> auditor-supplied patches for <plan-filename>`                           | `PLAN` |
| Audit `audit_state` write (success or rev_needed) | `plan-pipeline: audit_state update - <stage>:<outcome>`                                            | `PLAN` + `AUDIT` (the `git add` inside `apply_audit_outcome` in `.claude/skills/plan-pipeline/lib/audit_loop.py` already stages exactly `plan_path` and `audit_json_path` by name, which is the correct existing behaviour rather than a defect to fix) |
| Both audits passed -> `checked`                   | `plan-pipeline: checked <plan-filename>`                                                            | `PLAN` |
| Dispatch executor (`checked -> executing`)        | `plan-pipeline: executing <plan-filename>`                                                          | `PLAN` |
| Executor success -> `outcome-verifying`           | `plan-pipeline: outcome-verifying <plan-filename>`                                                  | `PLAN` + `WORK` |
| Outcome-verification ran (state recorded)        | `plan-pipeline: outcome-verification ran for <plan-filename>`                                       | `PLAN` |
| Outcome-verification shell failed (revert)       | `plan-pipeline: outcome-verification failed - reverting to drafted for <plan-filename>`             | `PLAN` |
| Human verification passed                        | `plan-pipeline: human verification passed for <plan-filename>`                                      | `PLAN` |
| Flip -> `complete`                                | `plan-pipeline: complete <plan-filename>`                                                           | `PLAN` |
| Retire success                                   | `plan-pipeline: retired <plan-filename>`                                                            | `RETIRE-PAIR` |
| CLAUDE.md drift check fired (complete sub-step)  | `plan-pipeline: claude-md-drift-check ran for <plan-id>`                                            | `PLAN`, plus the files `maintain-project-docs` reported writing, named at commit time |
| Executor revision_needed (revert)                | `plan-pipeline: executor revision_needed <plan-filename>`                                           | `PLAN` + `WORK` |
| Any kanban halt                                  | `WIP: pipeline halted at <phase> for <plan-filename> - see diagnostics`                             | `PLAN` + `AUDIT` + `WORK` so far, whichever of those the halted phase had already written, plus `RETIRE-PAIR` when the halting dispatch was `plan-retirer` - test the dispatch, not the phase, because testing the phase for `complete` misses the `any`/malformed-return row that also routes a retire failure here. On this route stage `RETIRE-PAIR` per `### RETIRE-PAIR on a partial move` under `## Staging scope`, and read that section before implementing this row, because a partial move makes the naive two-path form fatal |
| last_audit_commit anchor write                   | `plan-pipeline: record last_audit_commit for <plan-id>`                                             | `PLAN` |

**Bootstrap exception:** the parent PLAN `202605011400_PLAN_build-plan-pipeline-orchestrator.md` is git-managed by the Human, not the orchestrator. Detect by filename comparison and skip all of the above for that one file.

The same class vocabulary is the default for the commit templates in the Severity-surface sections below (`## Severity-surface state-machine additions`). The `## Staging scope` section (stage what the phase wrote, name nothing else) governs those templates directly rather than through a restated per-template list, because restating those rows is the kind of duplication the class vocabulary exists to remove. One of those templates needs a named class beyond the table above: `plan-pipeline: audit_extract <step> from <plan-filename>` (Surface 1) stages `PLAN` + `CHILD-PLAN`, because `extract <ID>` both appends to the parent PLAN's `audit_extracted` and dispatches `write-plan` to seed a child PLAN. That template alone is annotated.

`extract <spec>` in the Surface 3 reply table carries no `Staged paths` annotation. That entry is a reply row rather than a commit template, and the `**Commit templates (Surface 3):**` list carries no extract template for an annotation to attach to. `extract <spec>` seeds a child PLAN, the `CHILD-PLAN` class names that file, and the `## Staging scope` default (stage what the phase wrote, name nothing else) governs any commit made for that child PLAN.

`human-override complete/retire for <plan-filename>` (Surface 3) stages `PLAN` alone under the default rule, and that default is correct here only because the preceding kanban-halt commit (the `Any kanban halt` row above) already captured `RETIRE-PAIR` when the halting dispatch was `plan-retirer` - the override reply itself only ever edits the PLAN's frontmatter. Every other Severity-surface template writes only frontmatter or `halt_log` on the PLAN already in flight, so the `PLAN` class alone covers them.

---

## `<pipeline-result>` parsing

Every subagent's return ends with:

```
<pipeline-result>
```json
{
  "outcome": "success" | "revision_needed" | "exception",
  "payload": { /* skill-specific */ },
  "diagnostics": { /* populated when outcome != success */ }
}
```
</pipeline-result>
```

**Parse procedure:**
1. Text-scan the agent's return string. Find the last `<pipeline-result>` opening tag.
2. From that position, find the matching `</pipeline-result>` closing tag.
3. Within that span, extract the content of the JSON code fence (```json ... ```).
4. JSON-parse. Validate `outcome` is in the enum.
5. On any failure (no opening tag, no closing tag, no JSON fence, parse error, outcome not in enum) -> orchestrator emits its own `outcome: exception` with `diagnostics: { reason: "subagent return malformed", agent: "<name>", excerpt: "<last 500 chars of return>" }`.

The agent's prose body before the block is for Human reading, and the orchestrator does not mine that prose for state.

---

## Decision-15 triage helper

This helper applies at every Human-facing surface. For each item the orchestrator is about to surface:

1. **Already locked** - was this Human-proposed earlier in this conversation, or affirmed in a prior PLAN? List for transparency only ("noted: <item>"), and do not ask.
2. **Mechanically forced** - is there a single mechanically-correct answer (downstream of a locked decision, an infrastructure constraint, or established working style)? List for transparency only, and do not ask.
3. **Real judgement call** - does the Human plausibly have alternatives they would prefer? Surface as a question.

Format the surface as:

```
**Already locked** (no action needed):
- <item>

**Mechanically forced** (no action needed):
- <item>

**Real judgement calls** (please respond):
- <question>
```

If all items are non-judgement-call, surface only the transparency lists with a one-line "no questions for you" close.

---

## Concrete `Agent({...})` invocation snippets

The procedural file uses these snippets implicitly.

**Plan-writer (foreground, draft checkpoint):**
```
Agent({
  subagent_type: "plan-writer",
  description: "Write PLAN drafting checkpoint",
  effort: "high",   // plan-writer runs Opus at high reasoning effort (recalibrated 2026-07-04) - authoring is load-bearing
  prompt: "<plan_content>\n\nTarget filename: <target_filename>\nMode: <create|update>\n\nReturn structured <pipeline-result> per your SKILL.md."
})
```

**Sufficiency / plan-safety auditor (foreground):**
```
Agent({
  subagent_type: "sufficiency-auditor",   // or "plan-safety-auditor"
  description: "Audit PLAN <filename>",
  prompt: "Audit the PLAN at: <plan_path>\n\nApply your skill's procedure end-to-end. Return structured <pipeline-result> per your SKILL.md."
})
```

**Plan-executor (background, tier-selected):**
```
Agent({
  subagent_type: "<plan-executor | plan-executor-sonnet | plan-executor-opus>",
  description: "Execute PLAN <filename>",
  prompt: "Execute the PLAN at: <plan_path>\n\nRun execute-plan skill end-to-end. Write last_executor_outcome to PLAN frontmatter on completion. Do NOT commit or push (orchestrator owns git). Return structured <pipeline-result>.",
  run_in_background: true
})
```

**Plan-retirer (foreground):**
```
Agent({
  subagent_type: "plan-retirer",
  description: "Retire PLAN <filename>",
  prompt: "Retire the PLAN at: <plan_path>\n\nMove to `$(git rev-parse --show-toplevel)/Retired/` (repo-root-anchored via `git rev-parse --show-toplevel`). Do NOT use a path relative to the source file's location or to cwd. Do NOT commit or push (orchestrator owns git). Return structured <pipeline-result>."
})
```

---

## Severity-surface state-machine additions

PLAN `202605131030` introduced the prompt surfaces below, together with their state transitions. Implementation modules: `lib/render_prompts.py`, `lib/parse_replies.py`, `lib/apply_actions.py`.

### Surface 1 - Audit-revision loop (`drafted` phase, branch 4B)

**Trigger:** auditor returned `revision_needed`. The orchestrator calls `render_audit_surface()` and surfaces the structured prompt.

| Human reply pattern | Parsed action | Frontmatter mutation | Next orchestrator step |
|---|---|---|---|
| `fix` | `fix` | None (co-present acks/overrides are applied) | Commit the mutations, await a PLAN mtime advance, then re-dispatch the auditor. |
| `ack W1,W3` | `ack` | Append to `audit_acknowledgements` | If no errors remain, treat as success and advance. Otherwise remain in revision_needed. |
| `dispute E2: <reason>` | `dispute` | Append to `audit_disputes` | Commit, remain in revision_needed, and surface the dispute to the auditor next iteration. |
| `override E1: <reason>` | `override` | Append to `audit_overrides` | If all errors are now overridden, treat as success and advance. |
| `fix` + `override E1: <reason>` | `fix` (primary) | Both mutations written | Commit, then await the PLAN revision. |
| `details <ID>` | `details` | None | Emit the full message and suggested_fix, then re-prompt. |
| `stuck` | `help` (show_stuck=True) | None | Emit stuck-triage sub-prompt. |
| `extract <ID>` | `extract` | Append to `audit_extracted` | Dispatch `Skill("write-plan")` to seed a child PLAN, then link `triggers_plans`. |
| `different-auditor <m>` | `different-auditor` | Set `audit_state.preferred_model_override` and reset `<stage>_iterations: 0` | Await re-invocation, then re-dispatch with the model override. |
| `?` / `help` | `help` | None | Emit usage, then re-prompt (not counted as an ambiguous strike). |
| Unrecognised | `ambiguous` | None | Send `reprompt_text` and re-prompt once. A second ambiguous reply -> emit exception -> Surface 3. |

**Commit templates (Surface 1):**
- `plan-pipeline: audit_human_reply - <K>ack/<L>dispute/<M>override on <plan-filename>`
- `plan-pipeline: audit_extract <step> from <plan-filename>`
- `plan-pipeline: human model-override <m> on <plan-filename>`

Staged paths for every template above follow the Staging scope section unless a class is named otherwise.

---

### Surface 2 - Outcome verification (`outcome-verifying` phase, branch 4E)

**Trigger:** shell verification ran with `human_pending` non-empty, or mixed shell failures + human items. The orchestrator calls `render_outcome_surface()`.

| Human reply pattern | Parsed action | Frontmatter mutation | Next orchestrator step |
|---|---|---|---|
| `pass` | `pass` | `verification_state.human_verdict: all_pass` | Flip to `complete`, commit, and dispatch the retirer. |
| `fail: <reason>` | `fail` | `human_verdict: rejected` and `human_diagnostics: <reason>` | Revert to `drafted`, reset `audit_state`, and commit. |
| `ack-failure F1: <reason>` | `ack-failure` | Append to `verification_state.human_acknowledged_failures` | Decrement the effective fail count, then re-evaluate transitions. |
| `ack-human H1` | `ack-human` | Append to `verification_state.human_passed` | If all items are acked and no unacked fails remain, allow `pass`. |
| `reject-human H1: <reason>` | `reject-human` | `human_verdict: rejected` and `human_diagnostics` updated | Revert to `drafted`, reset `audit_state`, and commit. |
| `details F1` or `details H1` | `details` | None | Emit the `verification_state.failure_logs` entry or the item prose, then re-prompt. |
| `?` / `help` | `help` | None | Emit usage, then re-prompt. |
| Unrecognised | `ambiguous` | None | Send `reprompt_text` and re-prompt once. A second ambiguous reply -> emit exception -> Surface 3. |

The Surface 2 table also accepts the attestation-then-assent reply patterns:

| Human reply pattern | Parsed action | Frontmatter mutation | Next orchestrator step |
|---|---|---|---|
| `accept-attestation H1` | `accept-attestation` | Append H1 to `verification_state.human_passed` | Re-evaluate the state-transition logic, and if all items are resolved -> flip to `complete`. |
| `veto H1: <reason>` | `veto` | `human_verdict: rejected` and `human_diagnostics: <reason>` | Revert to `drafted`, reset `audit_state`, and commit. |
| `dig-into H1` | `dig-into` | None | Emit the full evidence from `orchestrator_attestations` for H1, then re-prompt. |

**False-positive acknowledgement path.** When an `acceptance:`/`verify:` failure is demonstrably a false positive - the orchestrator enumerates the complete match set and shows each match is benign - the orchestrator MUST:
1. Enumerate and show every match inline (not just a count).
2. Demonstrate each match is benign.
3. Auto-attach the enumerated analysis to `verification_state.failure_logs` (existing field).
4. Surface a one-word `ack-failure FN: <reason>` request rather than opening an investigation.

This path reuses the existing `ack-failure` reply path above without new machinery. A false-positive surface differs from a real failure by including the full match set and a benign-demonstration for each entry before asking for the ack, so the operator sees the evidence and types `ack-failure F1: false positive - all matches confirmed benign`.

**State-transition logic** (evaluated after applying reply actions):
```
effective_shell_fails = (state_fail + acceptance_fail) - len(human_acknowledged_failures)
effective_pending = len(human_pending) - len(human_passed)
if rejected or fail: revert drafted
elif effective_shell_fails > 0: revert drafted
elif effective_pending > 0: re-prompt residual items
elif pass or (effective_shell_fails == 0 and effective_pending == 0): flip complete
```

**Commit templates (Surface 2):**
- `plan-pipeline: outcome-verification - human acked <K> shell fail(s) for <plan-filename>`
- `plan-pipeline: outcome-verification - attestation accepted for <plan-filename>`
- `plan-pipeline: human verification passed for <plan-filename>` (existing)
- `plan-pipeline: outcome-verification rejected by human - reverting to drafted for <plan-filename>`

Staged paths for every template above follow the Staging scope section unless a class is named otherwise.

---

### Surface 3 - Kanban halt (any phase, branch 5)

**Trigger:** the orchestrator emits `outcome: exception` for any cause. After committing WIP, the orchestrator calls `render_halt_surface()`.

| Human reply | Parsed action | Frontmatter mutation | Next orchestrator step |
|---|---|---|---|
| `1` / `inspect <path>` | `inspect` | None | Emit the full diagnostics, then re-prompt. |
| `2` / `retry` | `retry` | None | Re-dispatch the failing operation, with the counter not reset. |
| `3` / `override: <reason>` | `override` | Append to `pipeline_overrides` | Advance the phase as if the failed step succeeded, then commit. |
| `4` / `reset-stage` | `reset-stage` | `audit_state.<stage>_iterations: 0` | Re-dispatch with reset counter. |
| `5` / `different-auditor <m>` | `different-auditor` | `audit_state.preferred_model_override: <m>` and reset the counter | Await re-invocation, then re-dispatch with the model override. |
| `6` / `dispute: <reason>` | `dispute` | Append to `halt_log` (kind: dispute) | The halt remains, with no phase change. |
| `7` / `abandon: <reason>` | `abandon` | Append to `halt_log` (kind: abandon), set `status: cancelled`, and set `pipeline_phase: complete` | Commit, then dispatch the retirer. |
| `extract <spec>` | `extract` | Append to / set `audit_extracted` | Dispatch `Skill("write-plan")` to seed child PLAN. |
| `?` / `help` | `help` | None | Emit usage, then re-prompt. |
| Unrecognised | `ambiguous` | None | Send `reprompt_text` and re-prompt once. A second ambiguous reply -> log a nested exception. |

**Commit templates (Surface 3):**
- `plan-pipeline: human-override drafted <stage> for <plan-filename>`
- `plan-pipeline: human-override executing for <plan-filename>`
- `plan-pipeline: human-override complete/retire for <plan-filename>`
- `plan-pipeline: human reset-stage <stage> on <plan-filename>`
- `plan-pipeline: human model-override <m> on <plan-filename>`
- `plan-pipeline: abandoned <plan-filename> - see halt_log`

Staged paths for every template above follow the Staging scope section unless a class is named otherwise.

---

## Idempotent-no-op summary

Re-entry into the orchestrator on the same disk-state with no new outcome should return immediately. Quick checks (in order):

1. `pipeline_phase: complete` AND PLAN already moved to `Retired/` -> "already retired".
2. `pipeline_phase: executing` AND no `last_executor_outcome` since dispatch -> "executor still running".
3. `pipeline_phase: outcome-verifying` AND `verification_state.human_verdict: pending` AND no fresh `human_reply` -> "awaiting Human verification reply".
4. `pipeline_phase: drafted` AND `audit_state.last_outcome: revision_needed` AND PLAN mtime <= `audit_state` commit time -> "awaiting Human revision".
5. Children gate: `triggers_plans` non-empty with any non-terminal child -> "paused for children: <list>".

If none of those apply, proceed into Step 4 of the dispatch procedure.
