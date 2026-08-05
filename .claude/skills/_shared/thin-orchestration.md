---
title: Thin orchestration
description: How to run a session where agents do the reading and the orchestrator holds only routing state. Derived from practice, not design, and the source of several decisions in the rolling-board restructure.
created: 2026-08-05
---
# Thin orchestration

A way of working a long session so the parent's context stays small while the
work stays large. Agents read from disk, write their output to disk, and the next
agent collects it. The parent holds paths and verdicts, never content.

This is written from a session that ran it by hand across the whole Workbench.
Every rule below exists because something went wrong without it, and the failure
is named so the rule can be argued with rather than obeyed.

This is a standing discipline for fan-out-shaped work, not a mode switched on by
a spoken token. The reason it is not a token: an autonomy grant has to originate
with the human because the hazard is bypassing them, and this has no equivalent
hazard. Its own failure is drift rather than overreach, and a declaration does
not catch drift - a session that was instructed to run thin drifted out of it
anyway. What catches it is the disk-derived compliance check in
[dispatch-authorisation.md](dispatch-authorisation.md) under `Verifying
compliance`, read rather than asked for.

`PLAN-AK3` mechanises this, and its decisions already carry these rules: D22 is
the bounded reply, D23 shared state on disk, D24 the orchestrator holding git,
D25 the declared writable set, and D26 to D28 the surrounding loop conditions.
Read those for the argued form. This file is the practice.

## The rules

### The reply is routing, the file is the deliverable

Every dispatch states a cap on what the agent returns: a few lines, in a named
shape. The real output goes to a file the dispatch names.

Without this, the parent's context fills from agent replies rather than from
reading files, and every rule about what the orchestrator may read is satisfied
while the failure those rules exist to prevent happens in full. This is the rule
that actually keeps the parent thin. It is also the one that looks least
necessary until it is missing.

The cap should be measured rather than requested once the mechanism exists. An
instruction to be brief is graded by the party it binds.

### Shared findings go to a seed file

When several agents need the same premises, write those premises to a file and
name its path in each dispatch. Do not restate them in each prompt and do not
hold them in the parent to paste forward.

Concurrent agents that each derive the same background reach different versions
of it and then contradict each other downstream. A seed file also survives a
restart and is auditable afterwards, which a parent's memory is not.

Mark clearly which of its contents are verified and which are inherited claims.
An agent given a seed treats all of it as settled.

### The orchestrator owns git

Agents write files and may move them. They never commit.

Concurrent agents race the index. This is the one serialisation point that
cannot be handed off, and it is a real exception to the parent holding nothing
rather than an implementation detail.

After every commit, check what actually landed. A multi-path staging command
that fails stages nothing, and the commit on the next line still succeeds, so a
milestone can report clean and carry none of its files.

### A dispatch names what may be written; everything else is read-only

State the writable set explicitly. Do not leave it to be inferred from the task.

An agent asked to judge a set of files rewrote several of them, normalising
punctuation and cutting prose, losing a few hundred words. The brief named which
files could be moved and said nothing about editing, because editing was not
contemplated. The damage read as a punctuation diff until the words were counted.

Where the files belong to someone else - reports raised from another repository,
inherited records, anything with a named author - say so as well as saying
read-only.

### Verify a premise before acting on it

A claim in a PLAN, a handoff, a backlog item or an advice file is a claim about
the tree, not a fact about it. Check it. Usually one or two greps.

In the session this came from, two blockers carried forward across successive
handoffs were both already false, and one of them had been fixed by a commit that
also silently discharged a plan nobody had closed. Confidently-worded claims need
this most, not least.

Give agents the same instruction. An agent that reports a defect it did not
check has produced a claim, and a bucket table full of unchecked claims is worse
than no table, because it reads as verified.

### Pick the cheapest capable tier and effort per piece of work

Effort is a dial separate from model. Concurrent cheap agents for mechanical
fan-out are the normal case, not an indulgence.

Extraction, listing, grepping and mechanical checks go to the cheapest tier.
Judgement against a decision register does not: a bucket assignment or a
relevance call needs a middle tier at least. One top-tier dispatch wants a stated
reason recorded before it goes.

Dispatch the shape the work wants rather than one agent doing everything: several
independent lenses over the same subject, an adversarial pass whose job is to
refute, a final pass asking what is still unchecked.

### Commit at milestones, not at the end

A session that commits only at the end loses everything when it is interrupted,
and a long autonomous run will be interrupted. Commit when a stage lands, push,
and say in the message what changed and why rather than what was done.

## What this does not cover

The pattern exercises dispatch, disk handoff and routing. It says nothing about
pausing a run, parking work that cannot proceed, bounding what an item may spend,
or a periodic reassessment, because none of those existed while it was practised.
Do not read it as evidence about those.

It also assumes one agent at a time per step. Parallel agents writing to the same
paths is a different problem with different failure modes, and the isolation
question is settled separately in `PLAN-AK3` under considered and not adopted.
