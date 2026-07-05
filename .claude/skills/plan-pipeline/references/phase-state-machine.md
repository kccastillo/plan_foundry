# Plan-Pipeline Phase State Machine

Lookup tables and templates for the orchestrator. The procedural narrative is in [../workflows/dispatch.md](../workflows/dispatch.md); this file is the reference.

---

## Phase enum

```
drafting → drafted → checked → executing → outcome-verifying → complete
```

`outcome-verifying` is a transient phase that always sits between `executing` and `complete` (per parent PLAN 202605011400 decision 25). Never skipped.

**Ad-hoc PLAN default** (per `plan-conventions.md`): `pipeline_phase` absent or empty → treat as `drafted`. Do NOT treat as `drafting` — that would re-ideate an already-authored PLAN.

---

## (Phase, Outcome) → Action routing table

The load-bearing contract (decisions 19, 20). `outcome` always comes from a `<pipeline-result>` block (subagent return) or from the orchestrator itself (MAX_ITERATIONS, git failure, malformed return).

| Phase                | Outcome           | Next action                                                                                                  |
|----------------------|-------------------|--------------------------------------------------------------------------------------------------------------|
| drafting             | (n/a — interactive) | Continue arc; `plan-writer` checkpoint commits.                                                            |
| drafted              | success           | Audit-loop dispatch table below.                                                                             |
| drafted              | revision_needed   | Update `audit_state`; commit; surface review; await Human revision; return.                                  |
| drafted              | exception         | Kanban halt: commit + push WIP; surface diagnostics; return.                                                 |
| checked              | (n/a)             | Flip → `executing`; commit; dispatch executor (background); return.                                          |
| executing            | success           | Flip → `outcome-verifying`; commit; continue into outcome-verification.                                      |
| executing            | revision_needed   | Revert → `drafted`; reset `audit_state`; set `status: needs-revision`; commit; surface; return.              |
| executing            | exception         | Kanban halt: commit + push WIP; surface; return.                                                             |
| outcome-verifying    | all-pass, no human_pending | Flip → `complete`; commit; dispatch `plan-retirer`.                                                |
| outcome-verifying    | shell-fail        | Override executor success → revision_needed; revert → `drafted`; reset `audit_state`; commit; surface; return. |
| outcome-verifying    | human_pending     | Surface structured prompt; commit `verification_state` write; return; await Human reply.                     |
| outcome-verifying    | human_verdict: all_pass | Flip → `complete`; commit; dispatch `plan-retirer`.                                                    |
| outcome-verifying    | human_verdict: rejected | Override → revision_needed; revert → `drafted`; reset `audit_state`; commit; surface; return.          |
| complete             | success           | `plan-retirer` returned success → commit retire; run drift-check sub-step; surface "pipeline complete"; return. |
| complete             | exception         | Retire failed → kanban halt; commit WIP; surface; return.                                                    |
| complete (drift-check) | n/a (auxiliary) | If `files_touched` intersects skill/command paths or `CLAUDE.md`, dispatch `maintain-claude-md` foreground. Failure is logged, not halting. No separate phase transition. |
| any                  | malformed return  | Orchestrator emits `exception`; commit + push WIP; surface "subagent return malformed"; return.              |
| any                  | git failure       | Orchestrator emits `exception`; commit (local) WIP if possible; surface "git operation failed: <op>"; return. |

---

## Audit-loop dispatch table (within `drafted`)

Driven by the durable `audit_state` frontmatter. Per parent decision 21.

| `audit_state.last_stage` | `audit_state.last_outcome` | Next dispatch                                | Iteration counter incremented |
|--------------------------|----------------------------|----------------------------------------------|-------------------------------|
| none                     | none                       | `sufficiency-auditor`                        | `sufficiency_iterations`      |
| sufficiency              | revision_needed            | `sufficiency-auditor` (after Human revision) | `sufficiency_iterations`      |
| sufficiency              | success                    | `plan-safety-auditor`                        | `plan_safety_iterations`      |
| plan_safety              | revision_needed            | `plan-safety-auditor` (after Human revision; sufficiency NOT re-run) | `plan_safety_iterations` |
| plan_safety              | success                    | (none) — flip `pipeline_phase: checked`; exit loop. | (n/a)                  |
| any                      | exception                  | (none) — kanban halt already in effect.      | (n/a)                         |

**MAX_ITERATIONS = 5** per stage. If incrementing would exceed 5, do NOT dispatch — orchestrator emits `outcome: exception` itself with diagnostics_summary `"audit loop did not converge after 5 iterations on <stage>"`. Commit + push WIP. Return.

**Re-revision detection.** "After Human revision" means PLAN file mtime is later than the last `audit_state` commit timestamp. If mtime is NOT advanced and `last_outcome: revision_needed`, the orchestrator no-ops (waiting on Human).

**On commit after Human revision** (before re-dispatching the audit): `git add -A && git commit -m "plan-pipeline: human-revised <plan-filename> (audit_state.<stage>_iterations=<N>)" && git push`.

---

## Agent dispatch table

| Phase / sub-phase                                | Agent name                                                                | Mode       | Input fields                                              | Output payload (relevant fields used by orchestrator) |
|--------------------------------------------------|---------------------------------------------------------------------------|------------|-----------------------------------------------------------|------------------------------------------------------|
| drafting (checkpoints)                           | `plan-writer`                                                             | foreground | `{plan_content, target_filename, mode: create|update}`    | `{filename_written, action, log_updated}`            |
| drafting (RESEARCH/ADVICE)                       | (skill `write-input`, parent-session direct, NOT a subagent)              | n/a        | `{type: RESEARCH|ADVICE, topic, body}`                     | written filename                                     |
| drafted (audit, sufficiency)                     | `sufficiency-auditor`                                                     | foreground | `{plan_path}`                                              | `{blockers_count, review_text, triaged_human_items}` |
| drafted (audit, plan-safety)                     | `plan-safety-auditor`                                                     | foreground | `{plan_path}`                                              | `{blockers_count, review_text}`                      |
| executing (executor dispatch by `assigned_to`)   | `plan-executor` (Sonnet, default) / `plan-executor-sonnet` / `plan-executor-opus` | **background** | `{plan_path}`                                              | `{outcome_subtype, executor_notes, files_modified}`  |
| outcome-verifying (shell + human)                | (orchestrator runs Bash directly — no subagent)                            | n/a        | n/a                                                        | n/a                                                  |
| complete (retire)                                | `plan-retirer`                                                            | foreground | `{plan_path}`                                              | `{retired_path, gitignore_updated}`                  |

**Executor tier selection** (PLAN-driven, decision 8):

| PLAN frontmatter `assigned_to:`        | Agent dispatched               |
|----------------------------------------|--------------------------------|
| `haiku`, empty, absent, or unrecognised | `plan-executor` (**Sonnet** — default) |
| `sonnet`                               | `plan-executor-sonnet` (identical to default) |
| `opus`                                 | `plan-executor-opus`           |

**Execution floor is Sonnet (recalibrated 2026-07-04).** Haiku is retired as a plan-execution tier — `plan-executor` now runs Sonnet 5. The legacy `assigned_to: haiku` value and the empty default both route to the Sonnet `plan-executor`; `sonnet` routes to the identical `plan-executor-sonnet`. Only `opus` differs (design-heavy execution). `assigned_to` is a guideline — Human may override per PLAN. Per decision 16's anti-monolithic principle, prefer decomposition over `opus` execution; `plan-executor-opus` is an escape hatch, not a default.

---

## Gitignored paths

The following paths are gitignored and managed by the orchestrator/executor out-of-band. They must not be committed.

| Path | Owner | Purpose |
|---|---|---|
| `Workbench/.heartbeat/` | Executor (writes), Orchestrator (deletes) | Live execution progress signals. One JSON file per active executor run. Deleted by orchestrator at `outcome-verifying` or `drafted` revert; preserved on `exception`. |
| `Workbench/.audit/` | Orchestrator | Audit JSON artefacts. One file per audit iteration. |
| `Workbench/.index.json` | `update-workbench-index` skill | Machine-readable INDEX projection. |

---

## Frontmatter mutation cheat sheet

The orchestrator may write these fields directly (without going through `plan-writer`) because they are orchestration-owned, not body content. Use the Edit tool on the PLAN file's YAML frontmatter block.

### `pipeline_phase`
String enum. Mutated at every phase transition. Values: `drafting | drafted | checked | executing | outcome-verifying | complete`.

### `audit_state`
```yaml
audit_state:
  sufficiency_iterations: 0
  plan_safety_iterations: 0
  last_stage: none           # none | sufficiency | plan_safety
  last_outcome: none         # none | success | revision_needed | exception
  last_audit_commit: ""      # short SHA (8 chars, git rev-parse --short=8 HEAD) of the commit that wrote
                             # the most recent audit file; used as the diff anchor for the next re-audit brief.
                             # Written by a SECOND commit after the audit_state update commit — never amended.
  preferred_model_override: ""  # auditor model override (e.g. "sonnet"); empty = default
```
Reset to fresh (all zeros / `none` / empty strings) when reverting from `executing` or `outcome-verifying` back to `drafted` (PLAN content has changed; prior audits are stale).

### `last_executor_outcome`
Written by `execute-plan` workflow on completion (per decision 24). Read-only for the orchestrator:
```yaml
last_executor_outcome:
  outcome: success            # success | revision_needed | exception
  outcome_subtype: done       # done | partially-complete | blocked | needs-revision
  executed: 2026-05-01
  diagnostics_summary: ""
```

### Heartbeat file (out-of-band, not PLAN frontmatter)

`Workbench/.heartbeat/<plan-id>.json` — gitignored, orchestrator-managed, deleted at `outcome-verifying`/`drafted` revert. Schema:

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

Stale threshold: `last_tick_at` > 10 minutes ago AND `phase != exited` → surface warning. Full spec: `.claude/skills/execute-plan/references/heartbeat-spec.md`.

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
```

### `status`
Existing field. Orchestrator mutates on phase boundaries:
- Entering `executing` → `status: in-progress`.
- Reverting from `executing`/`outcome-verifying` → `drafted` → `status: needs-revision`.
- After successful retire → `status: done` (already set by `execute-plan`; just confirm).

**LOG-mirroring conditionalisation (per PLAN-AB9 D6, effective 2026-06-01):** the orchestrator mirrors `status` mutations into the monthly LOG's Status Table **only when the PLAN's `log_month` ≤ `202605`** (fat-LOG era). For PLANs whose `log_month` ≥ `202606`, the LOG is slim — it has no Status Table — and PLAN frontmatter `status` (projected by INDEX.md, regenerated on every commit-worthy phase transition) is the sole canonical surface. Phase-transition commits for `log_month ≥ 202606` PLANs touch the PLAN file and INDEX, but never the new-month LOG. (The YYYYMM gate is a lexicographic string-compare; `"202612" < "202701"` so the cutover is year-end-safe without calendar arithmetic.)

`workflows/dispatch.md` contains no LOG-Status-Table references and is unchanged by this conditionalisation — grep-verified during PLAN-AB9 sufficiency audit. The single LOG-Status-Table touchpoint in the orchestrator surface is this section's prose; the retire skill's Step 6 carries the analogous gate for retirement commits.

---

## Commit-message templates

Every commit is `git add -A && git commit -m "<template>" && git push`. Never `--no-verify`, `--force`, or `--force-with-lease`. If push fails → orchestrator emits `exception` (commit is already local).

| Trigger                                          | Template                                                                                            |
|--------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| `plan-writer` returned success during drafting   | `plan-pipeline: drafting checkpoint <plan-filename>`                                                |
| `plan-writer` returned success at draft-close    | `plan-pipeline: drafted <plan-filename>`                                                            |
| `write-input` lands during drafting              | `plan-pipeline: drafting input <input-filename>`                                                    |
| Human-revised PLAN, before re-audit              | `plan-pipeline: human-revised <plan-filename> (audit_state.<stage>_iterations=<N>)`                 |
| Audit `audit_state` write (success or rev_needed) | `plan-pipeline: audit_state update — <stage>:<outcome>`                                            |
| Both audits passed → `checked`                   | `plan-pipeline: checked <plan-filename>`                                                            |
| Dispatch executor (`checked → executing`)        | `plan-pipeline: executing <plan-filename>`                                                          |
| Executor success → `outcome-verifying`           | `plan-pipeline: outcome-verifying <plan-filename>`                                                  |
| Outcome-verification ran (state recorded)        | `plan-pipeline: outcome-verification ran for <plan-filename>`                                       |
| Outcome-verification shell failed (revert)       | `plan-pipeline: outcome-verification failed — reverting to drafted for <plan-filename>`             |
| Human verification passed                        | `plan-pipeline: human verification passed for <plan-filename>`                                      |
| Flip → `complete`                                | `plan-pipeline: complete <plan-filename>`                                                           |
| Retire success                                   | `plan-pipeline: retired <plan-filename>`                                                            |
| CLAUDE.md drift check fired (complete sub-step)  | `plan-pipeline: claude-md-drift-check ran for <plan-id>`                                            |
| Executor revision_needed (revert)                | `plan-pipeline: executor revision_needed <plan-filename>`                                           |
| Any kanban halt                                  | `WIP: pipeline halted at <phase> for <plan-filename> — see diagnostics`                             |
| INDEX regen (after any phase-transition commit)  | `plan-pipeline: update-workbench-index`                                                             |
| last_audit_commit anchor write                   | `plan-pipeline: record last_audit_commit for <plan-id>`                                             |

**Bootstrap exception:** the parent PLAN `202605011400_PLAN_build-plan-pipeline-orchestrator.md` is git-managed by the Human, not the orchestrator. Detect by filename comparison; skip all of the above for that one file.

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
1. Text-scan the agent's return string. Find the LAST `<pipeline-result>` opening tag.
2. From that position, find the matching `</pipeline-result>` closing tag.
3. Within that span, extract the content of the JSON code fence (```json ... ```).
4. JSON-parse. Validate `outcome` is in the enum.
5. On any failure (no opening tag, no closing tag, no JSON fence, parse error, outcome not in enum) → orchestrator emits its own `outcome: exception` with `diagnostics: { reason: "subagent return malformed", agent: "<name>", excerpt: "<last 500 chars of return>" }`.

The agent's prose body before the block is for Human reading; the orchestrator does NOT mine it for state.

---

## Decision-15 triage helper

Applied at every Human-facing surface. For each item the orchestrator is about to surface:

1. **Already locked** — was this Human-proposed earlier in this conversation, or affirmed in a prior PLAN? List for transparency only ("noted: <item>"); do NOT ask.
2. **Mechanically forced** — is there a single mechanically-correct answer (downstream of a locked decision, an infrastructure constraint, or established working style)? List for transparency only; do NOT ask.
3. **Real judgement call** — does the Human plausibly have alternatives they'd prefer? Surface as a question.

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

For reference (the procedural file uses these implicitly).

**Plan-writer (foreground, draft checkpoint):**
```
Agent({
  subagent_type: "plan-writer",
  description: "Write PLAN drafting checkpoint",
  effort: "high",   // plan-writer runs Opus 4.8 at high reasoning effort (recalibrated 2026-07-04) — authoring is load-bearing
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
  prompt: "Retire the PLAN at: <plan_path>\n\nMove to Retired/. Do NOT commit or push (orchestrator owns git). Return structured <pipeline-result>."
})
```

---

## Severity-surface state-machine additions

This section documents the three prompt surfaces introduced by PLAN `202605131030` and their state transitions. Implementation modules: `lib/render_prompts.py`, `lib/parse_replies.py`, `lib/apply_actions.py`.

### Surface 1 — Audit-revision loop (`drafted` phase, branch 4B)

**Trigger:** auditor returned `revision_needed`. Orchestrator calls `render_audit_surface()` and surfaces the structured prompt.

| Human reply pattern | Parsed action | Frontmatter mutation | Next orchestrator step |
|---|---|---|---|
| `fix` | `fix` | None (co-present acks/overrides are applied) | Commit mutations; await PLAN mtime advance; re-dispatch auditor. |
| `ack W1,W3` | `ack` | Append to `audit_acknowledgements` | If no errors remain: treat as success, advance. Else: remain in revision_needed. |
| `dispute E2: <reason>` | `dispute` | Append to `audit_disputes` | Commit; remain in revision_needed; surfaced to auditor next iteration. |
| `override E1: <reason>` | `override` | Append to `audit_overrides` | If all errors now overridden: treat as success, advance. |
| `fix` + `override E1: <reason>` | `fix` (primary) | Both mutations written | Commit; await PLAN revision. |
| `details <ID>` | `details` | None | Emit full message + suggested_fix; re-prompt. |
| `stuck` | `help` (show_stuck=True) | None | Emit stuck-triage sub-prompt. |
| `extract <ID>` | `extract` | Append to `audit_extracted` | Dispatch `Skill("write-bus-plan")` to seed child PLAN; link `triggers_plans`. |
| `different-auditor <m>` | `different-auditor` | Set `audit_state.preferred_model_override`; reset `<stage>_iterations: 0` | Await re-invocation; re-dispatch with model override. |
| `?` / `help` | `help` | None | Emit usage; re-prompt (not counted as ambiguous strike). |
| Unrecognised | `ambiguous` | None | Send `reprompt_text`; one re-prompt. Second ambiguous → emit exception → Surface 3. |

**Commit templates (Surface 1):**
- `plan-pipeline: audit_human_reply — <K>ack/<L>dispute/<M>override on <plan-filename>`
- `plan-pipeline: audit_extract <step> from <plan-filename>`
- `plan-pipeline: human model-override <m> on <plan-filename>`

---

### Surface 2 — Outcome verification (`outcome-verifying` phase, branch 4E)

**Trigger:** shell verification ran with `human_pending` non-empty, or mixed shell failures + human items. Orchestrator calls `render_outcome_surface()`.

| Human reply pattern | Parsed action | Frontmatter mutation | Next orchestrator step |
|---|---|---|---|
| `pass` | `pass` | `verification_state.human_verdict: all_pass` | Flip to `complete`; commit; dispatch retirer. |
| `fail: <reason>` | `fail` | `human_verdict: rejected`; `human_diagnostics: <reason>` | Revert to `drafted`; reset `audit_state`; commit. |
| `ack-failure F1: <reason>` | `ack-failure` | Append to `verification_state.human_acknowledged_failures` | Decrement effective fail count; re-evaluate transitions. |
| `ack-human H1` | `ack-human` | Append to `verification_state.human_passed` | If all items acked and no unacked fails: allow `pass`. |
| `reject-human H1: <reason>` | `reject-human` | `human_verdict: rejected`; `human_diagnostics` updated | Revert to `drafted`; reset `audit_state`; commit. |
| `details F1` or `details H1` | `details` | None | Emit `verification_state.failure_logs` entry or item prose; re-prompt. |
| `?` / `help` | `help` | None | Emit usage; re-prompt. |
| Unrecognised | `ambiguous` | None | Send `reprompt_text`; one re-prompt. Second ambiguous → emit exception → Surface 3. |

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
- `plan-pipeline: outcome-verification — human acked <K> shell fail(s) for <plan-filename>`
- `plan-pipeline: human verification passed for <plan-filename>` (existing)
- `plan-pipeline: outcome-verification rejected by human — reverting to drafted for <plan-filename>`

---

### Surface 3 — Kanban halt (any phase, branch 5)

**Trigger:** orchestrator emits `outcome: exception` for any cause. After committing WIP, orchestrator calls `render_halt_surface()`.

| Human reply | Parsed action | Frontmatter mutation | Next orchestrator step |
|---|---|---|---|
| `1` / `inspect <path>` | `inspect` | None | Emit full diagnostics; re-prompt. |
| `2` / `retry` | `retry` | None | Re-dispatch failing operation; counter NOT reset. |
| `3` / `override: <reason>` | `override` | Append to `pipeline_overrides` | Advance phase as if failed step succeeded; commit. |
| `4` / `reset-stage` | `reset-stage` | `audit_state.<stage>_iterations: 0` | Re-dispatch with reset counter. |
| `5` / `different-auditor <m>` | `different-auditor` | `audit_state.preferred_model_override: <m>`; reset counter | Await re-invocation; re-dispatch with model override. |
| `6` / `dispute: <reason>` | `dispute` | Append to `halt_log` (kind: dispute) | Halt remains; no phase change. |
| `7` / `abandon: <reason>` | `abandon` | Append to `halt_log` (kind: abandon); `status: cancelled`; `pipeline_phase: complete` | Commit; dispatch retirer. |
| `extract <spec>` | `extract` | Append to / set `audit_extracted` | Dispatch `Skill("write-bus-plan")` to seed child PLAN. |
| `?` / `help` | `help` | None | Emit usage; re-prompt. |
| Unrecognised | `ambiguous` | None | Send `reprompt_text`; one re-prompt. Second → nested exception logged. |

**Commit templates (Surface 3):**
- `plan-pipeline: human-override drafted <stage> for <plan-filename>`
- `plan-pipeline: human-override executing for <plan-filename>`
- `plan-pipeline: human-override complete/retire for <plan-filename>`
- `plan-pipeline: human reset-stage <stage> on <plan-filename>`
- `plan-pipeline: human model-override <m> on <plan-filename>`
- `plan-pipeline: abandoned <plan-filename> — see halt_log`

---

## Idempotent-no-op summary

Re-entry into the orchestrator on the same disk-state with no new outcome should return immediately. Quick checks (in order):

1. `pipeline_phase: complete` AND PLAN already moved to `Retired/` → "already retired".
2. `pipeline_phase: executing` AND no `last_executor_outcome` since dispatch → "executor still running".
3. `pipeline_phase: outcome-verifying` AND `verification_state.human_verdict: pending` AND no fresh `human_reply` → "awaiting Human verification reply".
4. `pipeline_phase: drafted` AND `audit_state.last_outcome: revision_needed` AND PLAN mtime ≤ `audit_state` commit time → "awaiting Human revision".
5. Children gate: `triggers_plans` non-empty with any non-terminal child → "paused for children: <list>".

If none of those apply, proceed into Step 4 of the dispatch procedure.
