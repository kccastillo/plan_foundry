---
name: rehydrate-handoff
description: 'Discover handoff files at session start and surface the chosen one as structured orientation, so a cold session can resume without conversation history. Lists them for selection when more than one exists, surfaces a single handoff directly, and no-ops when none exist. Leaves the handoff on disk - the retire decision belongs to session end, in handoff-next-session. Trigger phrases: "rehydrate handoff", "catch me up", "what''s pending", "what''s the state", "resume session", "list handoffs".'
---

<objective>
This skill is the consume-side companion to handoff-next-session. The write side (handoff-next-session) ends a session by retiring any prior handoff *for a scope* and writing a fresh one using the mandatory datetime grammar `HANDOFF-YYYYMMDD-hhmm-<slug>.md` (per PLAN-AF6 D1 + PLAN-AH0 D1 - the legacy fixed default `HANDOFF-NEXT-SESSION.md` is no longer a write target, though the file remains discoverable and retirable as a legacy form). The read side (this skill) starts a session by discovering all handoff files (`Workbench/HANDOFF-*.md` - legacy `HANDOFF-NEXT-SESSION.md`, old-grammar, and new-grammar files), and surfacing the chosen one as structured orientation, then leaving the handoff on disk, because the retire decision belongs to session end and is resolved there by `handoff-next-session` (see the deferred-retire principle below and [workflows/read-handoff.md](workflows/read-handoff.md) Step 3). Together they form a producer/consumer lifecycle across multiple concurrent threads: discover+select+read per-scope at start-of-session, retire-and-write per-scope at end-of-session. Filename grammar and coexistence rules: see [../handoff-next-session/references/handoff-naming.md](../handoff-next-session/references/handoff-naming.md).
</objective>

<essential_principles>
Resumption drift preflight first (Step 0): before any handoff is discovered or surfaced (Step 1), Step 0 runs a read-only resumption drift preflight by reading the handoff's `## Plan-state baseline` block as `expected_plan_states`, its `## Carried-claims baseline` block as `expected_claim_checks`, and calling `.claude/skills/_shared/resume_preflight.py::check_resume_drift`. If drift is detected (branch behind/diverged, PR merged into default, PLAN on-disk phase differs from the persisted baseline, or a carried claim no longer reproduces), the skill halts and surfaces a re-orientation summary requiring reconciliation before proceeding. The check is fail-open: a `checked: false` axis (git offline, gh unavailable) never blocks. Desktop-session only - project-local skills do not run in Claude Code mobile/web.
Deferred retire - the retire decision belongs at session end, not session start. Rehydration surfaces the handoff and leaves the handoff on disk. The skill does not prompt the operator to retire at rehydration time. `handoff-next-session` performs the retire at session end, resolving to a terminal state: updated-into-successor (forward work remains, so a fresh handoff is written) or retired-outright (roadmap fully discharged, no successor written). An explicit unprompted operator "retire now" request is honoured as an override, with the same AA2 post-condition verification and commit path.
Surface structurally: parse the handoff's H2 sections - including the content contract (`## Session roadmap`, `## Lessons & decision rationale`, `## Audit & execution-readiness gate`, `## Agentic & model plan`, `## Next-handoff trigger`, `## Blocking decisions`) - and present them as named blocks, not as one prose dump, because the consumer (the orchestrator + Human) needs to skim rather than read linearly.
Discover all, surface one: glob `Workbench/HANDOFF-*.md`. Zero handoffs -> graceful no-op. Exactly one -> surface that handoff directly. More than one -> list them (scope, last-modified, title line) and ask which to surface/resume rather than dumping every body. Explicit-override retire is per-file, so retiring one handoff never affects the others.
No-op gracefully: if no handoff is present (first-time invocation in a fresh project, or all already retired), return a structured "nothing to rehydrate" surface, not an error.
Idempotent: invoking twice in one session is fine - both invocations surface the same handoff and note the deferred retire. No per-session "consumed" tracking is required.
No wire format block: this skill runs in the parent session only - there is no consuming orchestrator to parse a `<pipeline-result>` block. Do not emit one. The operator receives all information via the structured surface in Steps 2-3.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a project with `Workbench/` directory present (plan_foundry already bootstrapped via init-plan-foundry).
</preconditions>

<inputs>
None. The skill operates on the current working directory.
</inputs>

**Read procedure:** See [workflows/read-handoff.md](workflows/read-handoff.md) for the step-by-step.

<constraints>
- Never modify any handoff file's content - surface verbatim, retire (move) only.
- Never prompt the operator to retire at session start. Rehydration leaves the handoff on disk, and the retire decision is deferred to session end and resolved by `handoff-next-session`. Honour an explicit unprompted "retire now" request as an override, but never auto-prompt or auto-retire.
- Explicit-override retire is per-file - retiring one handoff never touches the others.
- Destination path on retire: `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md` (`<scope>` is `NEXT-SESSION` for the reserved default, and the timestamp suffix mirrors handoff-next-session's retire convention to avoid collisions).
- Never block on missing handoff - first-session projects and fully-retired projects both produce "nothing to rehydrate" + PASS, not an error.
</constraints>

<success_criteria>
- All `Workbench/HANDOFF-*.md` files were discovered, and when more than one was found, the operator was shown a selectable list before any body was surfaced.
- The selected handoff's content (if any present) was surfaced as structured per-section blocks to the operator, with `## Session roadmap` surfaced first.
- Retire decision deferred to session end (default path): handoff left on disk, operator informed of the deferred retire, and Step 3 reported SKIPPED.
- If operator explicitly overrode to retire-now: selected file moved to `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md` (non-zero size, readable at destination, absent at source), no other handoff was touched, and Step 3 reported PASS.
- No `<pipeline-result>` block emitted - the skill runs in the parent session, so all output is the structured surface delivered to the operator in Steps 2-3.
</success_criteria>
