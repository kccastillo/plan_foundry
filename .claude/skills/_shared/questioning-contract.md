# Decision-briefing contract

How to ask the Human to choose. Applies to **every** question that offers a choice - in free-form conversation and inside skill surfaces (plan-pipeline decision-15, ideate Survey/Converge). One source of truth; skills reference this file rather than restating it.

Origin: the AH1 episode (2026-07-24) - a leading question whose options were all change-paths (no "do nothing" option), with no per-option consequence and no eject, walked a diagnosis into an executed change. See `raise-foundry-request`-filed FOUNDRYREQ (question-surfaces-need-decision-briefing) for the systemic backlog item.

## Two checks - run BEFORE serving any question

1. **Leading check.** Do the options smuggle in the answer? Is the real alternative - usually **"do nothing / not yet / just the assessment"** - missing? If so, put it back in. A menu that omits the no-change option is a decision wearing a question's clothes.
2. **Bamboozle check.** Is this overwhelming or jargon-dense, such that the Human can't see what they're agreeing to? If so, break the choice down before asking.

## Four things every choice-question must carry

- **Context** - why the choice exists and what's at stake / what prompted it.
- **Per-option consequence + risk** - what each path leads to and its downside, in plain language (name the thing, the operation, the result - no compression).
- **My lean + why** - which I'd pick and the reason.
- **An eject button** - always offered: *"none of these / break it down / you decide / stop and let me think."* The Human is never trapped inside a frame they didn't accept.

## Pairs with

- **Assessment != mandate.** When the request is diagnostic (assess / check / review whether), stop at findings + a genuinely-open "what do you want to do." Do not convert a diagnosis into an executed change without an explicit, non-leading go-ahead. The contract above is *how* to ask that go-ahead question.

## Surface/tooling note

On Claude Code Mobile the `AskUserQuestion` tool has open rendering bugs (question/options don't render; selections don't propagate). Prefer plain-text questions carrying this contract; the tool is a desktop-only convenience, never the sole channel. Hard suppression, where configured, is `permissions.deny: ["AskUserQuestion"]` in settings.json (a harness config, not skill logic).
