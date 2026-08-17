---
title: Skill Standard
description: The definition of a legitimate skill in this bundle. Read by write-skill when scaffolding one and by audit-skills when reporting on the corpus. Carries no procedure and no scripts.
created: 2026-08-03
schema_version: 1
---
# Skill Standard

This file defines what a skill in this bundle has to be, and carries no procedure,
no scripts and no workflow. `write-skill` reads this standard and builds against it.
`audit-skills` reads the same standard and reports the corpus against it. Neither
skill owns the standard, because a constraint graded by the party it binds is not a
constraint. The same separation holds for `plan-safe.md`, which `write-plan` and
`audit-haiku-safe` both read and neither owns.

## What a SKILL.md must say

A skill that omits any of the following is not finished.

1. **The objective.** What the skill is for, in the terms of the person invoking it,
   rather than the mechanism. A reader who knows only the objective must be able to
   tell whether this is the skill they want.
2. **The constraints.** What the skill must not do, and what it must route elsewhere.
   The descriptive scaffolding described in the next section belongs here. A skill
   with no constraints section is either trivial or has not been thought about.
3. **What done looks like.** The condition under which the work is finished, stated so
   that a reader can check it rather than judge it. "The file exists and its frontmatter
   parses" is checkable. "The output is high quality" is not.

Everything else in a SKILL.md is optional and earns its place case by case.

## Compensating versus descriptive

This is the centre of the standard, and the judgement it asks for is the reason
`audit-skills` is model-driven rather than a linter.

Anthropic's Opus 5 guidance says to remove explicit verification instructions,
naming "include a final verification step for any non-trivial task" and "use a
subagent to verify" as examples, because they cause over-verification. The
best-practices page frames this as a migration instruction: remove them rather
than rewrite them. Read naively, that guidance says to dismantle a bundle largely
made of scaffolding.

Two different things look alike here.

**Compensating scaffolding** works around a model weakness. It should go as the
weakness disappears, and keeping it costs tokens and induces the behaviour it was
written to prevent.

**Descriptive scaffolding** encodes policy the model cannot infer. It must stay,
and it does not decay with capability, because no amount of capability tells a
model what this project decided.

**The counterfactual test.** An instruction is **compensating** if a competent model
would follow it unprompted. An instruction is **descriptive** if removing it would
let a correctly-reasoning model still produce an unacceptable outcome.

Apply the test to the instruction, not to how the instruction is worded. A rule that
sounds procedural can be descriptive, and a rule that sounds like policy can be
compensating.

### Descriptive, and staying

`execute-plan` says that a step which is ambiguous, unsafe, or marked `[Human]`
halts and is surfaced rather than improvised. A correctly-reasoning model with that
line removed would pick the most sensible reading and proceed, which is the wrong
outcome here. Who owns an ambiguity is a decision this project made, and nothing in
the request carries it.

`execute-plan` also allows the executor to write `last_executor_outcome` to a PLAN's
frontmatter and forbids it writing `status` or `pipeline_phase`, which the
orchestrator owns. Remove that and a capable executor writes the terminal status
itself, helpfully and wrongly, because the division of ownership between executor
and orchestrator exists nowhere in the task.

### Compensating, and going

`execute-plan` says to verify each step before moving on. As a standing instruction
that is the shape Anthropic names: a competent model checks its work as it goes, and
the instruction converts that into a separate announced pass. Where a specific step
has a real dependency on the previous one landing, say so at that step. The general
form earns nothing.

`writing-style.md` says to apply the mechanical word, verb and sentence rules by hand
while drafting and to check for them again when reviewing. A model that has those
rules in front of it applies them while writing. The second check is a re-read of
rules already applied, which is the over-verification the guidance is about. The tells
that file groups under "Review These After Drafting" are the opposite case: it says
they can only be assessed once a draft exists, so that pass earns its place.

### What to do with a finding

Naming an instruction as compensating is a report, not a removal order. Enforcement of
this standard is forward-only: the existing corpus is measured against it, and new
skills are built to it. A compensating finding against a shipped skill is recorded with
its counterfactual reasoning shown, and the decision to act on it is separate work.

## No references to ephemeral objects

A skill carries no reference to anything that is going to move or be deleted.

Named specifically: PLAN files, inputs, handoffs, audit records, requests,
testreports, anything under `Workbench/`, and anything already in `Retired/`. Those
are working artefacts with a lifecycle that ends. A skill outlives all of them.

This covers the identifier as well as the path. Citing a decision as "per D4 of
PLAN-XX0" is the same defect as linking the file, because the reader cannot resolve
it once the plan retires, and the sentence stops meaning anything.

Two things go wrong. The visible failure is the broken pointer. The worse failure is
that the skill stops being readable on its own terms, because a rule justified by a
decision the reader cannot look up is a rule they cannot evaluate, so they either
follow the rule blindly or ignore it.

**What to do instead.** State the rule and the reason in the skill, in full. If the
reasoning is too long for the skill, it belongs in a helper under `_shared/`, which is
durable, and the skill links to that. If the reasoning only explains where the rule
came from, it belongs in the commit message and nowhere else.

This applies to reference and workflow files under a skill directory, not only to
SKILL.md.

## Assertions before results

This principle comes from Anthropic's skill grader and applies to every check this
bundle writes about a skill.

A passing grade on a weak assertion is worse than useless, because it converts an
unexamined question into recorded evidence that the question was answered. An
assertion is therefore critiqued before its result. Ask what a wrong implementation
would have to do to fail this check, and if the answer is "almost nothing", the check
is the defect.

This is why a skill's stated success condition has to be checkable. An uncheckable
one cannot be critiqued, so it always passes.

## Frontmatter contract

Two validators disagree about what a SKILL.md may carry. Anthropic's platform
validator accepts `name`, `description`, `license`, `allowed-tools`, `metadata` and
`compatibility`, and rejects everything else. Claude Code documents a wider set that
includes `when_to_use`, `paths`, `disable-model-invocation` and others.

**This bundle writes against the Claude Code field set.** The bundle runs in Claude
Code, and the fields that control triggering and cost live only in that set. The
field set registered in [harness-contract.md](harness-contract.md) is the list a skill
here may use. That register does not carry `license`, `metadata` or `compatibility`,
so treat those three as platform-validator fields and check one against the live
documentation before putting it in a SKILL.md here. Anything written against the
narrower platform validator will report a false failure on this corpus, and that is
expected rather than a defect to fix.

`name` and `description` are required on every skill. `name` is lowercase letters,
digits and hyphens.

The recognised field list, and the fact that unknown keys are ignored silently with no
diagnostic, live in [harness-contract.md](harness-contract.md) "Skill frontmatter field
set". Circulating third-party guidance recommends `triggers`, `exclude`, `user_intent`
and `required_inputs`, none of which are fields. Check a field against the live
documentation before using it.

The current cap on description length, and every other value the harness enforces,
lives in [harness-contract.md](harness-contract.md) with the version it was observed
against. Do not restate a harness value here.

## Triggering

A description is the only thing about a skill that is always in context. The harness
loads the description into every turn in every project that has the skill installed,
whether or not the skill is ever used, so the description is both a standing cost and
the whole match surface.

**What a description has to do.** Say what the skill does, when to use it, and what it
produces. Write it for a reader deciding between this skill and the nearest other one,
because that is the decision it exists to settle. Name the concrete artefact or effect,
not the category of work.

**What makes a description fire wrongly.** Two failures need opposite fixes.

*Under-firing* comes from a description written in the author's vocabulary rather than
the invoker's. The skill matches the words the author would use and misses the words a
user types. The fix is trigger phrasing in the invoker's terms.

*Over-firing* comes from a description broad enough to plausibly match work that
belongs elsewhere. The fix is a stated exclusion in the description itself, naming the
neighbouring skill the request should go to instead.

**Overlap is a corpus property.** Two descriptions can each be good and still collide.
Nothing in the harness resolves two unrelated skills whose descriptions both plausibly
match, so the resolution is left to model judgement on description quality, and the
only place a collision is visible is a view of the whole corpus.

**Measure trigger behaviour rather than arguing about it.** The measurement needs
both a set of prompts that must fire the skill and a set of near-miss prompts that
must not, run more than once each, because a single run of a single prompt tells you
nothing about a stochastic decision. A description that fires on everything passes
the positive set and is worse than the description it replaced.

## Markup

Markup is free. This standard rules on what a SKILL.md says and not on how it is
tagged.

Plain markdown headings are preferred for new skills. The corpus is currently split
between XML-ish section tags and plain headings, with the tag vocabulary itself
inconsistent, and no earlier document ruled on the split. Mandating the tags would
entrench a pattern Anthropic now cautions against, and mandating nothing would
preserve the split. There is no required tag vocabulary, and a skill using headings
is conforming.

## Size and disclosure

Keep SKILL.md short enough to read. The body loads on trigger, so its length is paid
every time the skill fires.

Disclosure is three levels: frontmatter is always loaded, the body loads on trigger,
and referenced files load on demand. Push detail down a level rather than out of the
skill, and keep reference links one level deep so a reader is never chasing a chain.

## Retirement

A skill that is never invoked still costs its description on every turn in every
project that has the skill installed. A corpus therefore has a disposal question, and
no property of an individual skill answers that question.

The evidence for retiring a skill is collected externally and re-derived on demand,
never held as a self-reported field on the skill. A lifecycle field on the artefact
is a cache of a fact computable from the corpus, and the cache diverges the first
time somebody edits the skill without updating the field. This bundle removed a
registry that failed in exactly that way. The only writer of the `last_consulted`
field was `rehydrate-input` in asset mode, and the one invocation on record ran
during the PLAN that built the stamping mechanism, so the registry reported almost
every asset as never consulted.
