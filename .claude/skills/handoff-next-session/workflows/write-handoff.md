# handoff-next-session workflow

Idempotent procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Step 0: Compose the live filename (mandatory datetime+slug grammar)

All handoffs - scoped and unscoped alike - use the mandatory datetime+slug grammar per PLAN-AH0 D1. Compose the LIVE target filename as `Workbench/HANDOFF-<YYYYMMDD>-<hhmm>-<gist-slug>.md`, where:
- `YYYYMMDD-hhmm` is the current session datetime supplied by the write-time agent from its own clock/context (NOT a shell call; no colon - Windows-path-safe). Example: `HANDOFF-20260712-1430-restructure-mandate.md`.
- `<gist-slug>` is a few-word lowercase-kebab summary of the handoff's headline content, authored at write time. The gist slug is a **discovery aid** (a reader listing `Workbench/` can triage without opening the file) and is **never a substitute** for the exploded handoff body (per ADVICE-018).
- **The slug must not be the reserved token `NEXT-SESSION`.**
- The legacy fixed default `HANDOFF-NEXT-SESSION.md` is **never written** as a new handoff. If a legacy `HANDOFF-NEXT-SESSION.md` is present on disk, it is discovered and retired in Step 1 using `NEXT-SESSION` as the scope, but no new file is written with that fixed name.

Optional `scope` (string) - when given (via trigger phrase "handoff <thread> thread" or as a skill argument), the scope is preserved in the body banner (Step 4) and used for per-scope retire targeting. The scope is NOT part of the filename.

All later steps operate on this single resolved target filename and its scope only. See [../references/handoff-naming.md](../references/handoff-naming.md) for the full grammar, coexistence rules, and the per-scope-retire invariant.

## Step 1: Assess forward work and retire any existing handoff *for this scope*

**Two-terminal-state assessment (D5):** Before retiring and writing, assess whether there is any forward work for this scope: actionable `## Session roadmap` items, in-flight PLANs (any `Workbench/PLAN-*.md` at a non-terminal status), or explicitly queued/paused work.

- **If forward work exists** (or the operator has not requested retire-outright): follow the normal retire-then-write path below. Terminal state: `updated` (successor written).
- **If no forward work exists** (roadmap fully discharged, no in-flight PLANs, nothing queued/paused) **OR the operator explicitly requests retire-outright**: retire the existing handoff for this scope (if present) and write **no successor**. Report `terminal_state: retired-outright`. PASS. Skip Steps 2-4.

Check if any existing handoff for this scope exists on disk. For the new-grammar path, look for `Workbench/HANDOFF-*.md` files whose body scope banner matches the current scope (or whose gist slug matches when no banner is present). For an unscoped invocation where a legacy `HANDOFF-NEXT-SESSION.md` is present, it is the retire target.
- **If present:** Move it to `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md` (where `<scope>` is `NEXT-SESSION` for the unscoped default; timestamp-suffixed to avoid collisions with prior retirements). Use the Bash-disallowed-friendly approach: read the source content, write it to the destination, then delete the source (or use the `retire` skill if the orchestrator is dispatching). PASS.
- **If absent:** SKIPPED. First-time invocation for this scope (or retire-outright with no prior handoff to retire).

**Never** read, move, or overwrite any other `HANDOFF-*.md` file - retire is strictly per-scope. This is what allows multiple thread handoffs to coexist.

## Step 2: Gather current-session observations

Read context for the handoff body:
- **Recent commits:** Use Bash (`git log --oneline -10 main`) if available in parent context; otherwise summarise from conversation memory.
- **Open PRs touching this repo:** Mention numbers and one-line titles. If no PR-list tool is available in the executor context, leave that subsection sparse and note "see GitHub UI". **Ordering note (handoff-before-PR rule):** this handoff is prepared and pushed as part of the durability pass that always precedes any pull request create/update - the PR treats the pushed, current durable state as its precondition (see `## Handoff-before-PR ordering` in operating-rules.md).
- **Workbench/ contents:** List PLAN files currently in `Workbench/` with their `status:` frontmatter values (extract via Read + grep on each PLAN file).
- **Active branch:** Note the current git branch if not main; flag any unmerged work-in-flight.
- **Carryover items:** Anything explicitly paused mid-pipeline; any blocked PLANs; any deferred work the human flagged during the session.

The skill is expected to be invoked at end-of-session by the human ("write session handoff"); the executor uses conversation context as the primary input. If invoked early or in an empty session, populate from observable repo state alone.

## Step 2.5: Compute the Audit & Execution-Readiness Gate (mandatory)

Run the four standing handover checks so a NOT-READY plan can never be mistaken for
a ready one. Full definition and rendered shape: [../references/readiness-gate.md](../references/readiness-gate.md).

For **every** PLAN file in `Workbench/`, read its `pipeline_phase`, `audit_state`,
`status`, `ideate_phase` (if present), and `assigned_to` / `size`, then record:

1. **Execution-readiness verdict** - ✅ READY only at `pipeline_phase: checked` (both
   audits `success`); 🚫 NOT-READY otherwise, naming the phase and what it awaits.
2. **Audit-verdict provenance** - flag any "blockers addressed by design / expected to
   pass" claim in the PLAN body or a prior handoff that `audit_state` does not confirm
   with a passing re-audit. A self-assessment is never folded into a READY verdict.
3. **Ideation status** - classify each `drafting`/`drafted` PLAN as live ideation /
   stale-in-drafting / ideate-complete-awaiting-audit.
4. **Scope-collision / supersession** - flag overlapping in-flight PLANs whose
   reconciliation is not recorded in any PLAN's Context section, as a blocking decision.
5. **Size** - render S / M / L / XL from `size:` / `assigned_to:` (per
   `_shared/plan-safe.md` section Executor t-shirt sizing) so the next session sees the
   executor tier each job needs - flag any non-haiku-safe PLAN with no recorded size.

During this same per-PLAN pass, also read each PLAN's `last_executor_outcome` frontmatter field (in addition to `pipeline_phase` and `status` already read above) and record all three into the template's `## Plan-state baseline` fenced-yaml block - the machine-readable resumption baseline consumed by `rehydrate-handoff` Step 0 via `.claude/skills/_shared/resume_preflight.py::check_resume_drift` (`expected_plan_states`). The baseline is a near-free by-product of this existing per-PLAN loop. Write the mapping as `{ relpath: {pipeline_phase, status, last_executor_outcome} }` for each in-flight PLAN, or the literal `{}` if there are no in-flight PLANs.

This step always produces output - a per-PLAN table or the literal `No in-flight PLANs.`
It is the one gate section that is never deleted (Step 3's cut rule does not apply to it).
Likewise, `## Plan-state baseline` is never deleted - when there are no in-flight PLANs it is written as the literal `{}` empty mapping, not omitted.
PASS when the gate has been computed for every `Workbench/` PLAN.

## Step 3: Render handoff body from template - ruthlessly forward-only

Read `../templates/handoff-template.md` and populate it. **A handoff is a forward-only action brief, NOT a compression.** Apply one test to every line you consider writing: *does the next session need this to act correctly?* If not, cut it.

- **Keep:** the session roadmap (the spine - `## Session roadmap` is never empty; it opens with a mandatory **Start here** line naming the single first action, then an ordered list of phases, gates, and checkpoints, each item stating its own next action rather than its topic); the agentic & model plan (`## Agentic & model plan` - for each delegated step: model and one-clause rationale); the next-handoff trigger (`## Next-handoff trigger` - the expected/anticipated seam, advisory and overridable); human-only decisions that gate those steps (`## Blocking decisions`); constraints whose violation causes harm (`## Constraints & do-nots`); where the artifacts live (`## Where things live`).
- **Cut:** anything the team **decided against**; the deliberation trail; restatements of what `git` / `Workbench/INDEX.md` / `CLAUDE.md` already say; any proportional "what happened" narrative.
- **Rationale:** include only when load-bearing - its absence would let the next session re-open a settled call or repeat a known wrong move - and write it as a one-clause forward constraint ("do not X - it Y"), never as a record of the debate.
- **Keep (mandatory):** `## Lessons & decision rationale` - the lessons learned this session, each paired with what it changes about future work, AND the motivation behind every decision locked this session (the reasoning, the rejected alternative, and why). This section is never deleted and never compressed to a list of conclusions. Rationale: the retired-handoff chain is the project's durable history, so reasoning not written here is lost permanently rather than merely omitted.
- **Delete empty sections** (except `## Session roadmap`, `## Lessons & decision rationale`, `## Audit & execution-readiness gate`, and `## Plan-state baseline`). The gate and baseline sections are mandatory and are never deleted - the gate is a per-PLAN table or "No in-flight PLANs.", and the baseline is a yaml mapping or `{}` (empty). `## Agentic & model plan` and `## Next-handoff trigger` may be deleted when they have no content (all foreground / no meaningful stop point). Section presence is not the contract for all other sections; actionability is. Absorb what is useful, discard what is useless.

## Step 4: Write the handoff file

Write the rendered body to the resolved target - `Workbench/HANDOFF-<YYYYMMDD>-<hhmm>-<gist-slug>.md` (using the datetime + gist slug composed in Step 0). The legacy fixed default `HANDOFF-NEXT-SESSION.md` is **never the write target** - the datetime+slug grammar is mandatory for all new handoffs (per PLAN-AH0 D1). Lead the body with a one-line scope banner naming the thread (or "unscoped" when no scope was given) and stating that it deliberately does not touch other handoffs - this banner is also the source from which `rehydrate-handoff` recovers the scope when constructing the retire destination (see [../references/handoff-naming.md](../references/handoff-naming.md) Retire scope derivation). No colon may appear in the datetime portion of the filename.

**Post-condition - filename validation (D5):** After composing the target filename, call `.claude/skills/_shared/validate_artefact_filename.py::classify_artefact_filename(basename)`. If the result is not `"conforming"`, hard-fail: return `outcome: FAIL` with `diagnostics.reason: "composed filename classified as <class>: <reason>"`. This guard catches any agent that accidentally composes a colon-containing or slug-absent name before the file is written. PASS.

## Reporting

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` if no FAILs.
- `payload.scope`: the resolved scope slug (`NEXT-SESSION` when unscoped).
- `payload.terminal_state`: `updated` when a successor handoff was written; `retired-outright` when the prior handoff was retired and no successor was written (roadmap fully discharged or explicit operator request).
- `payload.step_results`: object with keys `step_0`, `step_1`, `step_2`, `step_2_5`, `step_3`, `step_4`, each value `PASS` / `SKIPPED` / `FAIL`. `step_2_5` (the readiness gate) must be `PASS` - it is mandatory and never `SKIPPED`. Under `terminal_state: retired-outright`, steps `step_2`, `step_3`, and `step_4` are `SKIPPED`.
- `payload.handoff_path`: the resolved target path (`Workbench/HANDOFF-YYYYMMDD-hhmm-<gist-slug>.md`), or `null` when `terminal_state: retired-outright` (no successor written).
- `payload.retired_path` (if Step 1 retired a prior handoff): the retired path.
- `diagnostics`: any per-step notes.
