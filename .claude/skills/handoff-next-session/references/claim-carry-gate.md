# Carried-claims gate - persistent identity for a handoff-carried claim

Single source of truth for the `CLAIM-<id>` grammar, the checkable-vs-freeform
split, the drop guard, and the repeat-escalation rule. Referenced by
[../workflows/write-handoff.md](../workflows/write-handoff.md) Step 2.6 and
rendered into the mandatory `## Carried-claims baseline` template section, and
by [../../rehydrate-handoff/workflows/read-handoff.md](../../rehydrate-handoff/workflows/read-handoff.md)
Step 0. Sibling mechanism to [readiness-gate.md](readiness-gate.md). That gate
distrusts a PLAN's self-assessment until an audit confirms the assessment.
This gate distrusts a handoff-carried claim until either a command
re-confirms the claim or a human has explicitly seen the repeat.

## Why this exists

A handoff carries standing facts, open defects and constraints forward to a
session with no conversation history. Unlike a PLAN's frontmatter, a claim in
`## Constraints & do-nots` is prose with no identity: nothing connects this
session's sentence to last session's sentence about the same fact. Without
identity, three failures are invisible - a stale claim reads exactly like a
current one, a dropped claim vanishes with nothing noticing, and a claim
restated unresolved across several handoffs never forces a decision. Giving
the claim a persistent id makes all three computable: re-run the checkable
ones, diff the id set to catch a silent drop, and count repeats to force an
escalation.

## The `CLAIM-<id>` grammar

`CLAIM-<kebab-nickname>`, assigned once by whichever agent first writes the
claim into `## Constraints & do-nots` or `## Blocking decisions`, and reused
verbatim by any later handoff restating the same claim. No sequential counter
and no content hash - a nickname carried by hand needs no allocator (avoiding
the concurrent-id-race problem already logged against `next_id.py`) and is not
defeated by the claim's own prose being reworded between restatements (a
hash would be). A deliberately renamed nickname is treated as a new claim -
the same trade-off the PLAN decision-id convention (CLAUDE.md) already
accepts.

## Checkable vs freeform - the split, and why freeform is not re-run

A claim whose truth reduces to a command's exit code carries a trailing
`check: <shell command>` line (exit 0 = the claim's stated fact holds). A
claim that is a judgement call - a reconciliation finding, an open design
question - does not, and is **never re-run**. This is a deliberate scope
limit, not a gap the mechanism silently misses: running an agent's opinion of
whether a judgement call still holds is attestation, not tree evidence, and a
constraint graded by the party it binds is worthless. A freeform claim still
gets an id, and is still covered by the drop guard and repeat escalation
below - both are text-presence checks, not attestation - but a freeform claim
that has genuinely gone stale is caught only when a human or a later session
re-reads it, same as before this gate existed.

## The drop guard

Before a successor handoff is written, every `CLAIM-*` id present in the
retiring handoff's `## Constraints & do-nots` and `## Blocking decisions`
sections must also be present in the successor - either restated, or named
in an explicit one-line removal note: `CLAIM-<id> removed - <reason>`. An id
missing from the successor with no such note is a structural FAIL at write
time (`write-handoff.md` Step 2.6c), the same shape as the existing
filename-validation post-condition at Step 4. This is what stops a claim
being compressed out of the handoff chain with nothing noticing.

## The `## Carried-claims baseline` and the escalation rule

A computed, never-hand-edited fenced-yaml block, sibling to `## Plan-state
baseline`: `{claim_id: {nickname, check, carried_count}}`. `carried_count`
increments by one each time the same id is carried forward unresolved, and
the id drops out of the baseline entirely the moment it is resolved or
removed. When a claim's `carried_count` reaches **3**, `write-handoff.md`
Step 2.6e structurally requires that claim to appear under `## Blocking
decisions` in the successor rather than stay in `## Constraints & do-nots` -
forcing the repeat into human-decision territory instead of letting it recur
informationally forever. The threshold is a small fixed constant named once
in `claim_carry.py`, reasoned from the report's own evidence: a scope-collision
finding restated across four consecutive handoffs, closed only by accident
when the underlying PLAN was retired, never by the reconciliation the finding
kept asking for. Three restatements is already past the point the report's
own evidence shows the human consequence being visible.

A `carried_count` is a per-item state field, not a project tally - the same
shape as `audit_state.sufficiency_iterations`, already on every PLAN. The
field describes one named claim's own history and is never summed across
claims.

## Staleness re-check

For a checkable claim, `write-handoff.md` Step 2.6a runs its `check:`
command via `claim_carry.run_claim_checks` (fail-open: an unrunnable or
timed-out command is `checked: False` and never counts as stale - only a
confirmed non-zero exit does). A claim found stale is carried into the
successor prefixed "stale - claim no longer reproduces, verify before
trusting" rather than restated silently. `resume_preflight.py`'s
`check_resume_drift` gains the identical check as an `expected_claim_checks`
axis so `rehydrate-handoff` Step 0 surfaces the same signal at session start,
mirroring how the PLAN-phase drift axis already works.

## Rendered shape (goes in the handoff)

```yaml
CLAIM-audit-exit-code:
  nickname: audit-exit-code
  check: "python -c \"exit(0)\""  # illustrative - the real command names a script in the target project
  carried_count: 1
CLAIM-scope-collision-aa2-aa3:
  nickname: scope-collision-aa2-aa3
  check: ""
  carried_count: 3
```

`CLAIM-audit-exit-code` is checkable and current - `carried_count` stays low
while the command keeps passing. If the command's exit code changed, the
successor would carry it prefixed "stale - claim no longer reproduces,
verify before trusting" instead of restating it as fact.
`CLAIM-scope-collision-aa2-aa3` is freeform (no `check:`) and has now reached
the escalation threshold - `write-handoff.md` requires it to appear under
`## Blocking decisions` in this handoff, not `## Constraints & do-nots`.

When nothing is carried, the section reads exactly `{}`.
