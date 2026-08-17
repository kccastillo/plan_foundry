---
title: Decision-Briefing Contract
description: How to ask the Human to choose - the leading/bamboozle pre-checks and the four things every choice-question must carry.
created: 2026-07-24
---

# Decision-briefing contract

This contract governs how to ask the Human to choose. It applies to **every** question that offers a choice, both in free-form conversation and inside skill surfaces (plan-pipeline decision-15, ideate Survey/Converge).

## Two checks - run BEFORE serving any question

1. **Leading check.** Do the options smuggle in the answer? Is the real alternative - usually **"do nothing / not yet / just the assessment"** - missing? If so, put that alternative back in. Omitting the no-change option settles the question before the Human answers.
2. **Bamboozle check.** Is the question overwhelming or jargon-dense, so that the Human cannot see what they are agreeing to? If so, break the choice down before asking.

## Four things every choice-question must carry

- **Context** - why the choice exists, what prompted it, and what is at stake.
- **Per-option consequence and risk** - what each path leads to and its downside, in plain language (name the thing, the operation, the result - no compression).
- **My lean and why** - which option I would pick, and the reason.
- **An eject button** - always offered: *"none of these / break it down / you decide / stop and let me think."* Offer the eject button every time, so the Human can decline a frame instead of choosing inside it.

## An assessment is not a mandate

When the request is diagnostic (assess, check, or review whether), stop at the findings and a genuinely open "what do you want to do". Do not convert a diagnosis into an executed change without an explicit, non-leading go-ahead. The contract above states *how* to ask for that go-ahead, and this section states *when* it has to be asked at all.

## Surface/tooling note

`AskUserQuestion` is denied wherever plan_foundry is installed: `.claude/skills/_shared/bundle-settings.json` carries it in `permissions.deny`, and `init-plan-foundry` merges that into the target's `.claude/settings.json`. Every question under this contract is therefore asked in plain text, on every surface, rather than only where the tool renders badly. See `harness-contract.md` ("AskUserQuestion rendering on Claude Code Mobile") for the Claude Code Mobile behaviour behind the deny and for the suppression mechanism itself.
