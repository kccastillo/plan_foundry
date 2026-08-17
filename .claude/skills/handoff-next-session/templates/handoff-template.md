<!--
HANDOFF DISCIPLINE - read before writing.
A handoff is a forward-only action brief, NOT a compression. A compression answers "what happened?";
a handoff answers "what should the next session DO?". Apply one test to every line:
  does the next session need this to act correctly? If not, cut it.
KEEP: session roadmap; agentic & model plan; next-handoff trigger; human-only decisions that gate them; constraints whose violation causes harm; where artifacts live.
CUT: anything decided-against; the deliberation trail; restatements of git / Workbench/INDEX.md / CLAUDE.md; "what happened" narrative.
RATIONALE: only when load-bearing (its absence would let the next session re-open a settled call or repeat a wrong move),
  and then as a one-clause forward constraint ("do NOT X - it Y"), never as a record of the debate.
Absorb what is useful, discard what is useless. Delete any section below that has no actionable content, except
  Session roadmap, Lessons & decision rationale, Audit & execution-readiness gate, Plan-state baseline and
  Carried-claims baseline - those five are never deleted (write-handoff.md Step 3).
-->
# Handoff - {SCOPE OR "next session"}

*{ONE LINE: the single most important thing about the current state - only if it changes what the next session does. Else delete this line.}*

## Audit & execution-readiness gate

<!-- MANDATORY - never deleted, even when empty. One of the five sections exempt from the
"delete empty sections" rule above. See ../references/readiness-gate.md. A NOT-READY plan must never read as ready.
A PLAN is execution-ready ONLY at pipeline_phase: checked (both audits success). Populate the
table for every Workbench/ PLAN, or write exactly "No in-flight PLANs." -->

| PLAN | Phase | Readiness | Size | Ideation | Flags |
|------|-------|-----------|------|----------|-------|
| {ID} | {pipeline_phase} | {READY / NOT-READY - what it awaits} | {S/M/L/XL (tier)} | {live ideation / stale-in-drafting / ideate-complete / -} | {self-assessed-not-audited * scope-collision * unsized * -} |

## Plan-state baseline

<!-- MACHINE-READABLE - consumed by rehydrate-handoff Step 0 -> resume_preflight expected_plan_states; do not hand-edit -->

```yaml
# Mapping of each in-flight Workbench/PLAN-*.md relpath to its last-known state.
# Written by handoff-next-session (write-handoff.md Step 2.5).
# Empty mapping when no in-flight PLANs.
{}
```

## Carried-claims baseline

<!-- MANDATORY - never deleted, even when empty. Sibling to the Plan-state baseline
above: a computed, never-hand-edited yaml mapping consumed by rehydrate-handoff Step 0
via resume_preflight.py::check_resume_drift (expected_claim_checks). See
../references/claim-carry-gate.md. A claim carried in Constraints & do-nots or Blocking
decisions gets a stable `CLAIM-<kebab-nickname>` id (assigned once, reused verbatim on
restatement - see the guidance in the Constraints & do-nots comment below); this block
tracks how many consecutive handoffs have carried each one forward unresolved. -->

```yaml
# Mapping of each carried CLAIM-<id> to {nickname, check, carried_count}.
# Written by handoff-next-session (write-handoff.md Step 2.6).
# Empty mapping when no carried claims.
{}
```

## Session roadmap

**Start here:** {ONE SENTENCE naming the single action the next session takes first, concrete enough to begin without deciding anything else - the command to run, the file to open, the dispatch to make, or the question to put to the human. Mandatory. If the first action is blocked on a human decision, say so here and name the decision rather than naming a substitute action. Never a theme or an area of work.}

1. {THE FIRST CONCRETE ACTION - the same one named above, with the detail needed to carry it out. Ordered. This section is the spine of the session: phases, gates, and checkpoints, not merely an action list. It is never empty.}
2. {WHAT FOLLOWS IT, and what it depends on. Each item states its own next action, not the topic it belongs to. Where the order is a genuine choice rather than a dependency, say which way you lean and why.}

## Agentic & model plan

{For each step in the Session roadmap, state whether it runs foreground or is delegated to a subagent. For each delegated step, name the model and add a one-clause rationale (e.g. "haiku - mechanical file-find only; no judgement required"). Delete this section only if every roadmap step is foreground with no delegation.}

**Dispatch grant carried forward:** {Write the grant token itself, verbatim, so the next session reads the grant rather than an account of it - `send it`, `send it 3`, `send it 4`, or "none (rungs 1-2 only, no autonomy grant)" when the human granted nothing beyond the standing position. Add one clause naming what it was granted for. A grant does not survive a session unless the token is written here. Grammar and carve-outs: `.claude/skills/_shared/dispatch-authorisation.md`.}

## Next-handoff trigger

{The *expected / anticipated* seam where the next session should stop, write a fresh handoff, and clear. Advisory and overridable by live judgment - never mandatory. Example: "After PLAN-XY0 moves to outcome-verifying and CI is green." Delete this section if there is no meaningful anticipated stop point.}

## Lessons & decision rationale

{MANDATORY - never deleted. Two things, and they are the *why* behind everything above.

**Lessons learned this session.** What was discovered by doing the work that is not recoverable from the diff: what broke and what that revealed, what a premise turned out to be wrong about, what a measurement said that contradicted the reasoning, what a method cost versus what it returned. Write the lesson AND what it changes about how future work should be done - a lesson with no consequence is trivia.

**Motivation for each decision made.** For every decision locked this session, record the reasoning that produced it, the alternative that was rejected, and why. Reference decisions by their ID and nickname where the project uses them (e.g. "D3 - Substrate First"). A decision recorded without its motivation cannot be revisited: a future session can only obey it or overturn it blindly, and both are wrong.

Never compress this into a list of conclusions. A conclusion without its reasoning is exactly the abbreviation ADVICE-018 exists to prevent, and under the retired-handoff-chain-as-history model this file is the only durable record - a "why" lost at write time is lost permanently.}

## Blocking decisions

{HUMAN-ONLY calls that gate the next steps. One line each: the decision + what it unblocks. Delete this section if nothing is blocked.

A carried claim (CLAIM-<id>) that has now been restated unresolved three handoffs running lands here, not in Constraints & do-nots - write-handoff enforces this per references/claim-carry-gate.md, so a repeat forces a decision instead of recurring informationally forever.}

## Constraints & do-nots

{BOUNDARIES whose violation would cause harm or rework. One line each; append a one-clause "- because Y" only when the reason is load-bearing. Delete if none.

A claim that names a command or file state the next session might re-trust gets a stable id: "CLAIM-<kebab-nickname>: <the claim>." Reuse the same id verbatim when a later handoff restates the same claim - renaming it starts a new claim. If the claim's truth reduces to a command's exit code, add a trailing `check: <shell command>` line (exit 0 = the claim holds) so write-handoff can re-run it before trusting it forward. A claim with no such command (a judgement call, a reconciliation finding) still gets an id but is never re-run - see references/claim-carry-gate.md for why.}

## Where things live

{PATHS to the artifacts the next steps reference - PLAN files, sources, scripts. Delete if the next steps already name them inline.}
