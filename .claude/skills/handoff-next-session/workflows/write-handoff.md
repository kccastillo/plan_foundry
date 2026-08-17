# handoff-next-session workflow

This procedure is idempotent. Each step PASSes, SKIPPEDs, or FAILs.

## Step 0: Compose the live filename (mandatory datetime+slug grammar)

All handoffs - scoped and unscoped alike - use the mandatory datetime+slug grammar per PLAN-AH0 D1. Compose the live target filename as `Workbench/HANDOFF-<YYYYMMDD>-<hhmm>-<gist-slug>.md`, where:
- `YYYYMMDD-hhmm` is the current session datetime supplied by the write-time agent from its own clock/context (not a shell call, and carrying no colon, which keeps the name Windows-path-safe). Example: `HANDOFF-20260712-1430-restructure-mandate.md`.
- `<gist-slug>` is a few-word lowercase-kebab summary of the handoff's headline content, authored at write time. The gist slug is a **discovery aid** (a reader listing `Workbench/` can triage without opening the file) and is **never a substitute** for the exploded handoff body (per ADVICE-018).
- **The slug must not be the reserved token `NEXT-SESSION`.**
- The legacy fixed default `HANDOFF-NEXT-SESSION.md` is **never written** as a new handoff. If a legacy `HANDOFF-NEXT-SESSION.md` is present on disk, it is discovered and retired in Step 1 using `NEXT-SESSION` as the scope, but no new file is written with that fixed name.

Optional `scope` (string) - when given (via trigger phrase "handoff <thread> thread" or as a skill argument), the scope is preserved in the body banner (Step 4) and used for per-scope retire targeting. The scope is not part of the filename.

All later steps operate on this single resolved target filename and its scope only. See [../references/handoff-naming.md](../references/handoff-naming.md) for the full grammar, coexistence rules, and the per-scope-retire invariant.

## Step 1: Assess forward work and retire any existing handoff *for this scope*

**Terminal-state assessment (D5):** Before retiring and writing, assess whether there is any forward work for this scope: actionable `## Session roadmap` items, in-flight PLANs (any `Workbench/PLAN-*.md` at a non-terminal status), or explicitly queued/paused work.

- **If forward work exists** (or the operator has not requested retire-outright): follow the normal retire-then-write path below. Terminal state: `updated` (successor written).
- **If no forward work exists** (roadmap fully discharged, no in-flight PLANs, nothing queued/paused) **OR the operator explicitly requests retire-outright**: retire the existing handoff for this scope (if present) and write **no successor**. Report `terminal_state: retired-outright`. PASS. Skip Steps 2-4.

Check whether any existing handoff for this scope is on disk. For the new-grammar path, look for `Workbench/HANDOFF-*.md` files whose body scope banner matches the current scope (or whose gist slug matches when no banner is present). For an unscoped invocation where a legacy `HANDOFF-NEXT-SESSION.md` is present, that legacy file is the retire target.
- **If present:** Move that handoff to `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md` (where `<scope>` is `NEXT-SESSION` for the unscoped default, and the timestamp suffix avoids collisions with prior retirements). Use the Bash-disallowed-friendly approach: read the source content, write the content to the destination, then delete the source (or use the `retire` skill when the orchestrator is dispatching). PASS.
- **If absent:** SKIPPED. This is the first invocation for this scope, or a retire-outright with no prior handoff to retire.

**Never** read, move, or overwrite any other `HANDOFF-*.md` file - retire is strictly per-scope. This is what allows multiple thread handoffs to coexist.

## Step 2: Gather current-session observations

Read context for the handoff body:
- **Recent commits:** Use Bash (`git log --oneline -10 main`) where the parent context allows, and otherwise summarise from conversation memory.
- **Open PRs touching this repo:** Mention numbers and one-line titles. If no PR-list tool is available in the executor context, leave that subsection sparse and note "see GitHub UI". **Ordering note (handoff-before-PR rule):** this handoff is prepared and pushed as part of the durability pass that always precedes any pull request create/update - the pushed, current durable state is the PR's precondition (see `## Handoff-before-PR ordering` in operating-rules.md).
- **Workbench/ contents:** List PLAN files currently in `Workbench/` with their `status:` frontmatter values (extract via Read + grep on each PLAN file).
- **Active branch:** When the current git branch is not main, note the branch and flag any unmerged work-in-flight.
- **Carryover items:** Anything explicitly paused mid-pipeline, any blocked PLANs, and any deferred work the human flagged during the session.

The human invokes this skill at end-of-session ("write session handoff"), so the executor uses conversation context as the primary input. If invoked early or in an empty session, populate from observable repo state alone.

## Step 2.5: Compute the Audit & Execution-Readiness Gate (mandatory)

Run the standing handover checks so a NOT-READY plan can never be mistaken for
a ready one. Full definition and rendered shape: [../references/readiness-gate.md](../references/readiness-gate.md).

For **every** PLAN file in `Workbench/`, read its `pipeline_phase`, `audit_state`,
`status`, `ideate_phase` (if present), and `assigned_to` / `size`, then record:

1. **Execution-readiness verdict** - READY only at `pipeline_phase: checked` (both
   audits `success`), and NOT-READY otherwise, naming the phase and what the PLAN awaits.
2. **Audit-verdict provenance** - flag any "blockers addressed by design / expected to
   pass" claim in the PLAN body or a prior handoff that `audit_state` does not confirm
   with a passing re-audit. A self-assessment is never folded into a READY verdict.
3. **Ideation status** - classify each `drafting`/`drafted` PLAN as live ideation /
   stale-in-drafting / ideate-complete-awaiting-audit.
4. **Scope-collision / supersession** - flag overlapping in-flight PLANs whose
   reconciliation is not recorded in any PLAN's Context section, as a blocking decision.
5. **Size** - the gate table's Size column rather than a fifth check (readiness-gate.md
   section Sizing column). Render S / M / L / XL from `size:` / `assigned_to:` (per
   `_shared/plan-safe.md` section Executor t-shirt sizing) so the next session sees the
   executor tier each job needs - flag any non-haiku-safe PLAN with no recorded size.

During this same per-PLAN pass, also read each PLAN's `last_executor_outcome` frontmatter field (in addition to `pipeline_phase` and `status` already read above) and record `pipeline_phase`, `status` and `last_executor_outcome` into the template's `## Plan-state baseline` fenced-yaml block - the machine-readable resumption baseline consumed by `rehydrate-handoff` Step 0 via `.claude/skills/_shared/resume_preflight.py::check_resume_drift` (`expected_plan_states`). Recording the baseline needs no extra file reads, because `last_executor_outcome` is read in the same pass that already reads `pipeline_phase` and `status`. Write the mapping as `{ relpath: {pipeline_phase, status, last_executor_outcome} }` for each in-flight PLAN, or the literal `{}` if there are no in-flight PLANs.

This step always produces output - a per-PLAN table or the literal `No in-flight PLANs.`
The gate section is never deleted, because Step 3's cut rule does not apply to the gate.
Likewise, `## Plan-state baseline` is never deleted - when there are no in-flight PLANs the section is written as the literal `{}` empty mapping rather than omitted.
PASS when the gate has been computed for every `Workbench/` PLAN.

## Step 2.6: Compute the Carried-claims gate (mandatory)

[../references/claim-carry-gate.md](../references/claim-carry-gate.md) gives the full definition.
This step uses `.claude/skills/_shared/claim_carry.py`.

(a) If a retiring handoff for this scope was found at Step 1, read its body and call
`claim_carry.parse_claims(text)` to get its claim set, then
`claim_carry.run_claim_checks(claims, repo_root)` against the current repo
root. If no retiring handoff was found (first invocation for this scope),
the claim set is empty and the rest of this step is a no-op producing `{}`.

(b) For any claim `run_claim_checks` flags `stale: True`, do not restate the
claim verbatim in the successor's `## Constraints & do-nots`. Carry the claim
forward prefixed "stale - claim no longer reproduces, verify before trusting"
so a stale claim is visibly flagged rather than silently trusted.

(c) Once the successor body is drafted (Step 3), call
`claim_carry.diff_dropped(prior_claims, successor_text)`. If `diff_dropped`
returns any id, hard-FAIL this step - mirroring the Step 4 filename-validation
post-condition's fail shape - with `diagnostics.reason` naming the missing
claim id(s). The drafter must either restate the claim or add an explicit
"CLAIM-`<id>` removed - `<reason>`" note before this step can PASS.

(d) Call `claim_carry.next_baseline(prior_baseline, current_claims)`, where
`prior_baseline` is the retiring handoff's parsed `## Carried-claims
baseline` (or `{}` if absent/first invocation) and `current_claims` is the
successor's own parsed claim set. Write the returned mapping into the
successor's `## Carried-claims baseline` block (or `{}` when there are no
carried claims).

(e) For every id in the escalation list `next_baseline` returned
(`carried_count` reached the threshold in `claim_carry.ESCALATION_THRESHOLD`),
hard-FAIL this step unless that id's claim text appears under the
successor's `## Blocking decisions` heading - this is what forces an
unresolved repeat into human-decision territory instead of letting it recur
informationally.

PASS when (c) and (e) both hold. SKIPPED under `terminal_state:
retired-outright` (no successor is written, so there is nothing to gate).

## Step 3: Render handoff body from template - ruthlessly forward-only

Read `../templates/handoff-template.md` and populate it. **A handoff is a forward-only action brief, NOT a compression.** Apply one test to every line you consider writing: *does the next session need this to act correctly?* If not, cut it.

- **Keep:** the session roadmap (the spine - `## Session roadmap` is never empty, and opens with a mandatory **Start here** line naming the single first action, then an ordered list of phases, gates, and checkpoints, each item stating its own next action rather than its topic), the agentic & model plan (`## Agentic & model plan` - for each delegated step: model and one-clause rationale), the next-handoff trigger (`## Next-handoff trigger` - the expected/anticipated seam, advisory and overridable), human-only decisions that gate those steps (`## Blocking decisions`), constraints whose violation causes harm (`## Constraints & do-nots`), and where the artefacts are kept (`## Where things live`).
- **Cut:** anything the team **decided against**, the deliberation trail, restatements of what `git` / `Workbench/INDEX.md` / `CLAUDE.md` already say, and every "what happened" narrative of the session, however short - a handoff answers "what should the next session do?", so narrative earns its place only where the `## Lessons & decision rationale` rule below demands it.
- **Rationale:** include only when load-bearing - the absence of the rationale would let the next session re-open a settled call or repeat a known wrong move - and write the rationale as a one-clause forward constraint ("do not X - it Y"), never as a record of the debate.
- **Keep (mandatory):** `## Lessons & decision rationale` - the lessons learned this session, each paired with what the lesson changes about future work, and the motivation behind every decision locked this session (the reasoning, the rejected alternative, and why). This section is never deleted and never compressed to a list of conclusions. Rationale: the retired-handoff chain is the project's durable history, so reasoning not written here is lost permanently rather than merely omitted.
- **Delete empty sections** (except `## Session roadmap`, `## Lessons & decision rationale`, `## Audit & execution-readiness gate`, `## Plan-state baseline`, and `## Carried-claims baseline`). The gate and both baseline sections are mandatory and are never deleted - the gate is a per-PLAN table or "No in-flight PLANs.", and each baseline is a yaml mapping or `{}` (empty). `## Agentic & model plan` and `## Next-handoff trigger` may be deleted when they have no content (all foreground / no meaningful stop point). For all other sections, actionability rather than section presence is the contract. Absorb what is useful, discard what is useless.

## Step 4: Write the handoff file

Write the rendered body to the resolved target - `Workbench/HANDOFF-<YYYYMMDD>-<hhmm>-<gist-slug>.md` (using the datetime + gist slug composed in Step 0). The legacy fixed default `HANDOFF-NEXT-SESSION.md` is **never the write target** - the datetime+slug grammar is mandatory for all new handoffs (per PLAN-AH0 D1). Lead the body with a one-line scope banner naming the thread (or "unscoped" when no scope was given) and stating that writing this handoff deliberately leaves every other handoff untouched - this banner is also the source from which `rehydrate-handoff` recovers the scope when constructing the retire destination (see [../references/handoff-naming.md](../references/handoff-naming.md) Retire scope derivation). No colon may appear in the datetime portion of the filename.

**Post-condition - filename validation (D5):** After composing the target filename, call `.claude/skills/_shared/validate_artefact_filename.py::classify_artefact_filename(basename)`. If the result is not `"conforming"`, hard-fail: return `outcome: FAIL` with `diagnostics.reason: "composed filename classified as <class>: <reason>"`. This guard catches any agent that accidentally composes a colon-containing or slug-absent name before the file is written. PASS.

## Reporting

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` if no FAILs.
- `payload.scope`: the resolved scope slug (`NEXT-SESSION` when unscoped).
- `payload.terminal_state`: `updated` when a successor handoff was written, and `retired-outright` when the prior handoff was retired and no successor was written (roadmap fully discharged or explicit operator request).
- `payload.step_results`: object with keys `step_0`, `step_1`, `step_2`, `step_2_5`, `step_2_6`, `step_3`, `step_4`, each value `PASS` / `SKIPPED` / `FAIL`. `step_2_5` (the readiness gate) must be `PASS` - the gate is mandatory and never `SKIPPED`. Under `terminal_state: retired-outright`, steps `step_2`, `step_2_6`, `step_3`, and `step_4` are `SKIPPED`.
- `payload.handoff_path`: the resolved target path (`Workbench/HANDOFF-YYYYMMDD-hhmm-<gist-slug>.md`), or `null` when `terminal_state: retired-outright` (no successor written).
- `payload.retired_path` (if Step 1 retired a prior handoff): the retired path.
- `diagnostics`: any per-step notes.
