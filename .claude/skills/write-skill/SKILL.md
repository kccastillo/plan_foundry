---
name: write-skill
description: Scaffold one new skill against the skill standard, then prove it triggers by measuring it against must-fire and must-not-fire prompts. Say "write a skill", "new skill", "scaffold a skill".
---

# write-skill

## Objective

Produce one new skill that conforms to the standard and demonstrably fires when it
should. The measurement is the deliverable as much as the files are. A skill that has
not been measured has not been finished, because a description's trigger behaviour
cannot be reasoned about from the text.

One skill per run. If the request describes several, build the first and say so.

## Read the standard first

[`../_shared/skill-standard.md`](../_shared/skill-standard.md) defines what a skill
must be: what a SKILL.md has to say, the compensating-versus-descriptive test, the
frontmatter contract, the triggering rules, and the markup ruling. Read it before
writing anything.

This skill does not restate it. Where they appear to disagree, the standard wins and
this file is the defect.

[`../_shared/harness-contract.md`](../_shared/harness-contract.md) holds the current
description cap and the listing budget. Read the value from there rather than from
memory, because both have moved.

## Constraints

- Do not write the skill before the objective, constraints and done-condition are
  settled. Ask for whichever is missing. A skill whose author cannot state its
  done-condition does not have one.
- Do not restate the standard inside the new skill. Link to it.
- Do not add a frontmatter key without checking it against the harness contract. An
  unrecognised key is ignored silently, so the skill fails by doing nothing.
- Do not ship the skill until the trigger proof has run and both sets have passed.
  Skipping this is the one shortcut that makes the whole exercise pointless.
- Do not write a reference to a PLAN, an input, a handoff, a request, or anything else
  under a working directory. The standard's rule on ephemeral objects applies to every
  file this skill writes.
- Never delete or overwrite an existing skill. If the name is taken, stop and say so.

## Scaffold

1. Settle the three things the standard requires a SKILL.md to say: the objective, the
   constraints, and what done looks like. Write them down before creating a directory.
2. Pick the name. Lowercase letters, digits and hyphens. Check it against the existing
   corpus for a near-collision, not only an exact one, because two plausibly-matching
   descriptions are resolved by model judgement and nothing else.
3. Create `.claude/skills/<name>/` and write `SKILL.md` from
   [templates/SKILL.md.template](templates/SKILL.md.template).
4. Write the description last, once the body exists. A description written first
   describes what the author intended rather than what the skill does.
5. Write the eval fixture at `.claude/skills/<name>/evals.json` from
   [templates/evals.json.template](templates/evals.json.template).

## Prove it triggers

Full procedure: [workflows/prove-triggering.md](workflows/prove-triggering.md).

In short: a set of prompts that must fire the skill, a set of near-miss prompts that
must not, each run more than once, and the negative set passes by not firing. Report
both rates. A description that fires on everything passes the positive set and is
worse than what it replaced.

## What done looks like

- `.claude/skills/<name>/SKILL.md` exists, its frontmatter parses, and `name` matches
  the directory.
- The body states the objective, the constraints, and the done-condition.
- `evals.json` exists with a non-empty `should_trigger` set and a non-empty
  `should_not_trigger` set.
- The trigger proof has been run and its two rates reported to the person who asked.
- The combined description length is within the cap in the harness contract, and the
  addition to the listing total has been named out loud rather than absorbed silently.

## When the proof is not enough

Anthropic's `skill-creator`, at `github.com/anthropics/skills`, runs a heavier
evaluation than the one above: paired subagents with and without the skill, eval sets
split into train and held-out, test scores blinded from the model doing the improving,
and the best iteration picked by held-out score. Reach for it when a description
resists tuning.

Use it in place, and do not copy its code into this bundle. Its frontmatter validator
encodes the narrower platform field set that the standard rejects, so running it
against a conforming skill here reports a false failure.
