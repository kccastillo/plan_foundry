# handoff-next-session workflow

Idempotent procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Step 0: Resolve the target scope

Determine the handoff's scope from the optional `scope` input (or the trigger phrase "handoff <thread> thread"):
- **Scoped:** normalise the scope to a lowercase-kebab slug and set the target to `Workbench/HANDOFF-<scope>.md`. The slug must not be the reserved token `NEXT-SESSION`.
- **Unscoped:** the target is the reserved default `Workbench/HANDOFF-NEXT-SESSION.md`.

All later steps operate on this single resolved target file and its scope only. See [../references/handoff-naming.md](../references/handoff-naming.md) for the full grammar and the per-scope-retire invariant.

## Step 1: Retire any existing handoff *for this scope*

Check if the resolved target file (`Workbench/HANDOFF-<scope>.md`, or `HANDOFF-NEXT-SESSION.md` when unscoped) exists.
- **If present:** Move it to `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md` (where `<scope>` is `NEXT-SESSION` for the unscoped default; timestamp-suffixed to avoid collisions with prior retirements). Use the Bash-disallowed-friendly approach: read the source content, write it to the destination, then delete the source (or use the `retire` skill if the orchestrator is dispatching). PASS.
- **If absent:** SKIPPED. First-time invocation for this scope.

**Never** read, move, or overwrite any other `HANDOFF-*.md` file — retire is strictly per-scope. This is what allows multiple thread handoffs to coexist.

## Step 2: Gather current-session observations

Read context for the handoff body:
- **Recent commits:** Use Bash (`git log --oneline -10 main`) if available in parent context; otherwise summarise from conversation memory.
- **Open PRs touching this repo:** Mention numbers and one-line titles. If no PR-list tool is available in the executor context, leave that subsection sparse and note "see GitHub UI".
- **Workbench/ contents:** List PLAN files currently in `Workbench/` with their `status:` frontmatter values (extract via Read + grep on each PLAN file).
- **Active branch:** Note the current git branch if not main; flag any unmerged work-in-flight.
- **Carryover items:** Anything explicitly paused mid-pipeline; any blocked PLANs; any deferred work the human flagged during the session.

The skill is expected to be invoked at end-of-session by the human ("write session handoff"); the executor uses conversation context as the primary input. If invoked early or in an empty session, populate from observable repo state alone.

## Step 2.5: Compute the Audit & Execution-Readiness Gate (mandatory)

Run the four standing handover checks so a NOT-READY plan can never be mistaken for
a ready one. Full definition and rendered shape: [../references/readiness-gate.md](../references/readiness-gate.md).

For **every** PLAN file in `Workbench/`, read its `pipeline_phase`, `audit_state`,
`status`, `ideate_phase` (if present), and `assigned_to` / `size`, then record:

1. **Execution-readiness verdict** — ✅ READY only at `pipeline_phase: checked` (both
   audits `success`); 🚫 NOT-READY otherwise, naming the phase and what it awaits.
2. **Audit-verdict provenance** — flag any "blockers addressed by design / expected to
   pass" claim in the PLAN body or a prior handoff that `audit_state` does not confirm
   with a passing re-audit. A self-assessment is never folded into a READY verdict.
3. **Ideation status** — classify each `drafting`/`drafted` PLAN as live ideation /
   stale-in-drafting / ideate-complete-awaiting-audit.
4. **Scope-collision / supersession** — flag overlapping in-flight PLANs whose
   reconciliation is not recorded in any PLAN's Context section, as a blocking decision.
5. **Size** — render S / M / L / XL from `size:` / `assigned_to:` (per
   `_shared/plan-safe.md` § Executor t-shirt sizing) so the next session sees the
   executor tier each job needs — flag any non-haiku-safe PLAN with no recorded size.

This step always produces output — a per-PLAN table or the literal `No in-flight PLANs.`
It is the one gate section that is never deleted (Step 3's cut rule does not apply to it).
PASS when the gate has been computed for every `Workbench/` PLAN.

## Step 3: Render handoff body from template — ruthlessly forward-only

Read `../templates/handoff-template.md` and populate it. **A handoff is a forward-only action brief, NOT a compression.** Apply one test to every line you consider writing: *does the next session need this to act correctly?* If not, cut it.

- **Keep:** actionable next steps (the spine — `## Next steps` is never empty); human-only decisions that gate those steps (`## Blocking decisions`); constraints whose violation causes harm (`## Constraints & do-nots`); where the artifacts live (`## Where things live`).
- **Cut:** anything the team **decided against**; the deliberation trail; restatements of what `git` / `Workbench/INDEX.md` / `CLAUDE.md` already say; any proportional "what happened" narrative.
- **Rationale:** include only when load-bearing — its absence would let the next session re-open a settled call or repeat a known wrong move — and write it as a one-clause forward constraint ("do not X — it Y"), never as a record of the debate.
- **Delete empty sections** (except `## Next steps`). Section presence is not the contract; actionability is. Absorb what is useful, discard what is useless.

## Step 4: Write the handoff file

Write the rendered body to the resolved target — `Workbench/HANDOFF-<scope>.md`, or `Workbench/HANDOFF-NEXT-SESSION.md` when unscoped. For a scoped handoff, lead the body with a one-line scope banner naming the thread and stating that it deliberately does not touch other handoffs (mirrors the hand-written scoped-handoff convention). PASS.

## Reporting

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` if no FAILs.
- `payload.scope`: the resolved scope slug (`NEXT-SESSION` when unscoped).
- `payload.step_results`: object with keys `step_0`, `step_1`, `step_2`, `step_2_5`, `step_3`, `step_4`, each value `PASS` / `SKIPPED` / `FAIL`. `step_2_5` (the readiness gate) must be `PASS` — it is mandatory and never `SKIPPED`.
- `payload.handoff_path`: the resolved target path (`Workbench/HANDOFF-<scope>.md` or `Workbench/HANDOFF-NEXT-SESSION.md`).
- `payload.retired_path` (if Step 1 retired a prior handoff): the retired path.
- `diagnostics`: any per-step notes.
