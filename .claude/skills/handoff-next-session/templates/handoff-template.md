<!--
HANDOFF DISCIPLINE - read before writing.
A handoff is a forward-only action brief, NOT a compression. A compression answers "what happened?";
a handoff answers "what should the next session DO?". Apply one test to every line:
  does the next session need this to act correctly? If not, cut it.
KEEP: session roadmap; agentic & model plan; next-handoff trigger; human-only decisions that gate them; constraints whose violation causes harm; where artifacts live.
CUT: anything decided-against; the deliberation trail; restatements of git / Workbench/INDEX.md / CLAUDE.md; "what happened" narrative.
RATIONALE: only when load-bearing (its absence would let the next session re-open a settled call or repeat a wrong move),
  and then as a one-clause forward constraint ("do NOT X - it Y"), never as a record of the debate.
Absorb what is useful, discard what is useless. Delete any section below that has no actionable content (except Session roadmap).
-->
# Handoff - {SCOPE OR "next session"}

*{ONE LINE: the single most important thing about the current state - only if it changes what the next session does. Else delete this line.}*

## Audit & execution-readiness gate

<!-- MANDATORY - never deleted, even when empty. The one exception to the "delete empty sections"
rule above. See ../references/readiness-gate.md. A NOT-READY plan must never read as ready.
A PLAN is execution-ready ONLY at pipeline_phase: checked (both audits success). Populate the
table for every Workbench/ PLAN, or write exactly "No in-flight PLANs." -->

| PLAN | Phase | Readiness | Size | Ideation | Flags |
|------|-------|-----------|------|----------|-------|
| {ID} | {pipeline_phase} | {✅ READY / 🚫 NOT-READY - what it awaits} | {S/M/L/XL (tier)} | {live ideation / stale-in-drafting / ideate-complete / -} | {self-assessed-not-audited * scope-collision * unsized * -} |

## Plan-state baseline

<!-- MACHINE-READABLE - consumed by rehydrate-handoff Step 0 -> resume_preflight expected_plan_states; do not hand-edit -->

```yaml
# Mapping of each in-flight Workbench/PLAN-*.md relpath to its last-known state.
# Written by handoff-next-session (write-handoff.md Step 2.5).
# Empty mapping when no in-flight PLANs.
{}
```

## Session roadmap

1. {THE FIRST CONCRETE ACTION - a command, an edit, a decision to execute. Ordered. This section is the spine of the session: phases, gates, and checkpoints, not merely an action list. It is never empty.}
2. {NEXT PHASE OR ACTION...}

## Agentic & model plan

{For each step in the Session roadmap, state whether it runs foreground or is delegated to a subagent. For each delegated step, name the model and add a one-clause rationale (e.g. "haiku - mechanical file-find only; no judgement required"). Delete this section only if every roadmap step is foreground with no delegation.}

## Next-handoff trigger

{The *expected / anticipated* seam where the next session should stop, write a fresh handoff, and clear. Advisory and overridable by live judgment - never mandatory. Example: "After PLAN-XY0 moves to outcome-verifying and CI is green." Delete this section if there is no meaningful anticipated stop point.}

## Lessons & decision rationale

{MANDATORY - never deleted. Two things, and they are the *why* behind everything above.

**Lessons learned this session.** What was discovered by doing the work that is not recoverable from the diff: what broke and what that revealed, what a premise turned out to be wrong about, what a measurement said that contradicted the reasoning, what a method cost versus what it returned. Write the lesson AND what it changes about how future work should be done - a lesson with no consequence is trivia.

**Motivation for each decision made.** For every decision locked this session, record the reasoning that produced it, the alternative that was rejected, and why. Reference decisions by their ID and nickname where the project uses them (e.g. "D3 - Substrate First"). A decision recorded without its motivation cannot be revisited: a future session can only obey it or overturn it blindly, and both are wrong.

Never compress this into a list of conclusions. A conclusion without its reasoning is exactly the abbreviation ADVICE-018 exists to prevent, and under the retired-handoff-chain-as-history model this file is the only durable record - a "why" lost at write time is lost permanently.}

## Blocking decisions

{HUMAN-ONLY calls that gate the next steps. One line each: the decision + what it unblocks. Delete this section if nothing is blocked.}

## Constraints & do-nots

{BOUNDARIES whose violation would cause harm or rework. One line each; append a one-clause "- because Y" only when the reason is load-bearing. Delete if none.}

## Where things live

{PATHS to the artifacts the next steps reference - PLAN files, sources, scripts. Delete if the next steps already name them inline.}
