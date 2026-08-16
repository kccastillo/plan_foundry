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

These rules were later mechanised into a formal orchestrator design, with a
matching decision for each: the bounded reply, shared state on disk, the
orchestrator holding git, the declared writable set, and the surrounding loop
conditions. This file is the practice those decisions rest on.

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

The cap is on the reply, and the reply can still go missing. A skill invoked at
the end of a dispatch can replace the agent's reply with its own structured
output, so the agent's account of its work is lost and the orchestrator has to
reconstruct what happened from the diff. The remedy that worked was a durable
per-run record on disk, overwritten as the run progresses, so the outcome
survives a lost reply. A bounded reply that never arrives is still a gap - the
rule above is necessary and not sufficient on its own.

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

Several agents that run at the same time each get their own scratchpad path.
A dispatch names a unique subdirectory or output filename per agent, which
stops two of them colliding on one file. In the case this came from, two agents
that shared a scratchpad both chose the obvious name for the extraction task,
`extract_pptx.py`; the second write clobbered the first mid-run, and the first
agent's file changed underneath with no warning.

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

The check belongs at the moment of acting, not only once at intake. A triage
verdict goes stale fast. On the board this came from, an item judged live at
triage was already fixed by the time an executor reached it, hours later - the
fix had landed in between, and re-checking the premise at execution is what
caught the drift.

A subagent's report that a file was tampered with is still a claim.
The orchestrator reads the file and the directory before it acts on that report.
One subagent reported tampering after its scratchpad script changed mid-run.
The orchestrator then inspected the directory and discovered a second agent's
write to the same path where the report expected an attack.

An agent records what it observed and stops at that.
In this case the report went past the observed change to the file.
The report added a detail that nobody had verified: a note on disk had told the
agent to keep quiet, and that note never existed.
Whoever reads the artefact next diagnoses the cause from what the record holds.

### A self-scoped dispatch needs a named failure mode

An agent asked to choose its own scope can choose one that is honest and
useless. A check on this board was wired first to nothing and then to a single
ephemeral scratch file, reported truthfully both times, and passed CI both
times - the honesty was real and the scope was worthless. A brief that asks an
agent to scope its own work has to name what would make the scope worthless, not
only ask for honesty, because honesty about a bad scope still produces a bad
scope.

### Pick the cheapest capable tier and effort per piece of work

The model ladder and dispatch thresholds live in
[dispatch-authorisation.md](dispatch-authorisation.md); this discipline is that
ladder applied to fan-out-shaped work. Concurrent cheap agents for mechanical
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

This assumes one agent at a time per step touches the same repository files.
The writable-set rule above covers parallel writes to a shared scratchpad.
The isolation question for repository files was weighed once and set aside:
worktree isolation was considered and rejected, because the orchestrator's
lock keys off a gitignored file inside the caller's own working tree and the
identifier allocator scans only its own tree, so a worktree would trade one
loud collision for two quiet ones rather than remove the contention. That
evidence holds whether the concurrent session is another agent's or the
human's own, which is why re-opening the question needs both the lock and the
allocator fixed first, not only worktrees added.
