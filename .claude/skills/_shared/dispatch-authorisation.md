---
title: Dispatch Authorisation
description: The concurrency-and-tier ladder governing discretionary subagent dispatch. Names what runs without asking, what needs an exception, and what an exception obliges the dispatcher to record. Referenced by plan-pipeline, ideate and handoff-next-session rather than restated in each.
created: 2026-07-31
---
# Dispatch authorisation

**Scope.** This file governs **discretionary** subagent dispatch: agents the
orchestrator or a conversational session chooses to spawn. It does not govern
pipeline dispatch, where the phase state machine names the agent and the agent
file names the tier. A `sufficiency-auditor` run at the `drafted` phase is
pipeline dispatch and needs no authorisation under this file.

Claude Fable 5 sits outside this ladder entirely. See
[fable-escalation-policy.md](fable-escalation-policy.md).

This file sets the tier and concurrency a dispatch may reach, and says nothing
about how to run several agents once authorised - for that, see
[thin-orchestration.md](thin-orchestration.md): agents read from and write to
disk, the reply is capped and routing-only, and a dispatch states what it may
write.

## The ladder

Two dials set the rung: the model tier, and how many run at once.

| Rung | Shape | Authorisation |
|---|---|---|
| 1 | Any number of Haiku, concurrent | Standing. Dispatch and report. |
| 2 | One Sonnet at a time | Standing. Dispatch and report. |
| 3 | One Opus, **or** more than one Sonnet concurrently | Exception. See below. |
| 4 | More than one Opus concurrently | Extreme exception. See below. |

Concurrency counts agents alive at the same moment, not agents dispatched over
a session. Ten Haiku agents one after another is rung 1. Two Sonnet agents
launched in the same message is rung 3.

A rung covers everything below it. A session authorised to rung 3 may run
Haiku concurrently without further justification.

## What an exception obliges

Difficulty is the trigger. Importance is not. A task being consequential,
consumer-facing or irreversible does not raise its rung. The qualifying
condition is that the work does not fit the rung below, and the reason is
stated **before** dispatch, not reconstructed afterwards.

**Rung 3.** Name, in one sentence written before the dispatch, what the rung
below cannot do. Two shapes qualify:

- The task needs judgement a Sonnet agent has been observed to get wrong on
  this class of work.
- The work splits into independent parts whose results are needed together,
  and running them in sequence would exceed the session's remaining context.

**Rung 4.** A rung 3 attempt must have been made and fallen short, with the
shortfall named. Absent that attempt, escalate to the human instead.

Record the exception where the work is recorded: the PLAN's Executor Notes for
pipeline-adjacent work, the handoff for session-level work. An exception that
was not written down did not happen, because the retired handoff chain is this
repo's durable history.

## Default when no grant is in force

Rungs 1 and 2 are always available. Rungs 3 and 4 need a grant.

A grant lasts for the session that received it. It does not survive into the
next session unless the handoff carries it forward.

## The grant token: `send it`

A grant is set by the human typing a reserved token. Prose is not a grant. The
token exists so that neither party has to judge whether a sentence counted, and
so that a grant can be written into a handoff and read back verbatim by a
session that was not there when it was given.

| What the human types | Decision autonomy | Dispatch ceiling |
|---|---|---|
| `send it 1` | Revoked | Rung 1 |
| `send it 2`, or bare `send it` | Granted | Rung 2 |
| `send it 3` | Granted | Rung 3 |
| `send it 4` | Granted | Rung 4 |
| `stand down` | Revoked | Rung 1 (synonym for `send it 1`) |

Bare `send it` means `send it 2`. It is a convenience, not a separate mode, and
it never means the agent chooses its own level - see "The number is a ceiling"
below.

`stand down` is retained as a synonym for `send it 1` rather than replaced by
it. It reads as a brake, and it is a spoken word rather than a slash command,
so it still works in a session where project-local commands do not load.

The rung argument raises the dispatch ceiling. It does not change the decision
autonomy, which is the same at every level: reaching rung 3 still obliges the
pre-dispatch reason under "What an exception obliges" above. The token
authorises the rung; it does not excuse the record.

## The number is a ceiling, not a setpoint

A grant names the highest rung available. It does not instruct the agent to
dispatch at that rung. Within a granted ceiling the agent still picks the
cheapest rung that fits each piece of work, under the obligations already
stated: rung 3 needs a reason written before the dispatch, rung 4 needs a
failed attempt at rung 3. A session granted `send it 3` that runs most of its
work at rung 1 is using the grant correctly.

**Cheapest capable, rightsized.** A ceiling is permission, not a budget to
spend. Under any grant the standing expectation is the cheapest model and
effort that will do the job, chosen per piece of work rather than per session.
Two dials move independently: the model tier, and the effort level on models
that carry one.

Three things this exists to keep in view, because they are what gets forgotten
under a high ceiling:

- **A swarm of cheap agents is a real option and an encouraged one.** Mechanical
  fan-out - file-finding, grepping, reading, boolean checks, schema-bounded
  votes - belongs on Haiku, in parallel, in quantity. Reaching for one expensive
  agent because the ceiling allows it is the failure this line exists to prevent.
- **Effort is a separate dial from tier.** A cheaper model at higher effort often
  beats a dearer one at default, and the reverse is true for retrieval-shaped
  work. Do not move both at once without saying why.
- **The shape of the work matters as much as the tier.** Adversarial verification,
  independent-panel judging, running until a sweep comes back empty, searching
  the same question several unrelated ways, and a final pass asking what is still
  unchecked are all available, and each fits some stages and not others. Pick the
  shape for the stage rather than defaulting to one agent doing everything.

This file states the stance and deliberately carries no task-to-model table.
The stance is the mechanism: a human-set ceiling, and the cheapest capable rung
chosen per piece of work beneath it. A table would freeze into policy what has
to be judged per stage.

Two facts about the dial itself, which hold whatever rung is in force. Haiku 4.5
accepts no `effort` parameter at all, so passing one is meaningless rather than
merely redundant. And the effort floor for a judgement-concentrated call is a
starting point to sweep upward from, not a ceiling to sit at.

**The agent never sets its own ceiling.** Choosing a rung at or below a
human-set ceiling is ordinary dispatch judgement. Choosing the ceiling is the
party bound by a constraint setting that constraint, which is the invariant
"No Party Grades Its Own Constraint" in ARCHITECTURE.md, and the failure mode
is recorded there: in PLAN-AI7 every individual judgement in the bypass was
defensible, which is why the boundary cannot sit in the agent's judgement.

The agent may **ask** for a higher ceiling, naming the work that wants it and
why the rung below will not do. Asking is the interested party requesting a
bound. Taking one is not available at any grant level.

## Announcing a change of grant

Every change to the ceiling is confirmed to the human in one line, in both
directions - set, raised, lowered, revoked. The line states the level now in
force and what it permits, so the human can check that what landed is what they
meant. On a revocation it also names anything that was in flight when the grant
was pulled, so they can see what stopped and what did not.

Dispatch choices *within* an unchanged ceiling are not announced. They are
already recorded where they belong - the pre-dispatch reason for rung 3, the
failed attempt for rung 4 - and announcing each one buries the confirmations
that matter under a line per subagent.

**Decision autonomy** means the whole run belongs to the agent until the work
is finished. Every fork is taken on the agent's own lean, including forks the
tooling has explicitly routed to the human: an audit blocker classified
`real_judgement_call`, a `[Human]` step, an ideate `judgement`-tier row. Those
classifications are defaults for the unattended case, not instructions that
outrank the grant. Record the reasoning where it will be found later, disclose
in the durable record who decided, and report once at the end rather than per
decision.

**What a grant never covers.** These stay with the human whatever token is in
force, because the cost of a wrong call is not recoverable by re-running:

- Promotion to prod, or any push to a repository the session does not own.
- Deleting data, or any outward-facing act - a PR, a published artefact, a
  message to a third party.
- Raising or routing around a bound. The disk-derived pre-human bound
  (`pre_human_bound_reached` in `.claude/skills/plan-pipeline/lib/patch_gate.py`),
  the audit `MAX_ITERATIONS` ceiling and their kin are limits on the agent's own
  behaviour, and a grant of autonomy is not a grant to lift them. If a bound is
  wrong, raise it in a PLAN. See the invariant "No Party Grades Its Own
  Constraint" in ARCHITECTURE.md.

**Scope and expiry.** A grant covers the session that received it and ends when
that session ends. To carry one forward, write the token itself into the
handoff's `## Agentic & model plan` section, so the next session reads the
grant rather than an account of it.

## Verifying compliance

The dispatcher must not certify its own compliance. Check it from disk.

Each Claude Code session writes a subagent record per dispatch under
`~/.claude/projects/<project-slug>/<session-id>/subagents/`. The
`agent-<id>.meta.json` file carries `agentType` and `toolUseId`. The sibling
`agent-<id>.jsonl` carries the model that actually ran, on the `model` field of
every assistant message. Joining the two yields the tier per dispatch, and the
parent transcript's tool-call ordering yields concurrency.

That join is the audit. Read it rather than asking the dispatcher what it did.

## Not the same as session_dispatch_budget

A 2026-07-27 proposal used the name `session_dispatch_budget` for a **count**
of executor dispatches, bounding context growth within a pipeline session. That
is a different quantity from the rungs here, which bound tier and concurrency.
A session can sit at rung 1 and still exhaust a dispatch count.
