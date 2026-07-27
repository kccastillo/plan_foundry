---
asset_id: help-writing-style
kind: helper
title: Writing Style
topic_tags: [writing-style, prose, technical-writing, output-quality, ste]
description: How written outputs should be written. Spelling, dates, authorisation to write, plain language, file stamping, the prose tells to watch for, and the sentence-level rules. Adapted from an ASD-STE100 distillation.
discoverable_via: [ideate, write-plan, write-input, handoff-next-session, manual]
created: 2026-07-27
last_consulted: ""
consulted_by: []
---

# Writing Style

Provided by the human on 2026-07-27, adapted from the working-style document maintained in another project. Two adaptations were needed to bring it into this repo, both marked inline under "Adapted for plan_foundry" and neither silent. Everything else is the human's text as supplied.

- Australian spelling and date formats.
- Ask clarifying questions before producing long outputs.
- Do not write artefacts, code, or longform sections without authorisation.
- Plain language. Do not compress, abbreviate, or elide. Name the thing, the operation, the result.
- When creating dated md files for project memory, the header and the filename both carry a datetime stamp.

## Adapted for plan_foundry

Two rules in the source document point at things that do not exist in this repo. Both are recorded here rather than dropped, because the divergence is a decision the human may want to revisit.

**1. The character-set rule diverges, and this is the live conflict.** The source document says "Plain ASCII only, including no em dashes or curly quotes", and defers the rule, its replacements and its one verbatim-reproduction exemption to a character-set section of `CLAUDE.md`. This repo has no such section, and its actual position is the opposite one: under PLAN-AD2 D9, ASCII is enforced only at the git boundary, covering commit messages and tag annotations and never file contents. 968 non-ASCII lines across 55 files are deliberate, and "do not ASCII-ify documentation prose" is a standing constraint.

So the source document's plain-ASCII rule is **not** in force here, and the "No dashes" line under Sentences is scoped accordingly: it applies to commit subjects and tag annotations, which the `commit-msg` hook already sanitises, and not to prose. Adopting the stricter rule would mean either rewriting those 968 lines or holding a rule the repo visibly breaks on every page. That is a decision for the human, not one to take by transcription. See the open question at the end of this file.

**2. The grounding reference has no local equivalent.** The Limitations section defers truth and grounding to a `working-principles.md` that exists in the source project and not here. The nearest local surface is the audit loop: `audit-sufficiency` for conceptual grounding and `audit-haiku-safe` for mechanical checkability. The reference is left as prose rather than a link, so it does not dangle.

## Prose tells: read before writing longform

Character rules are checkable, so they can be enforced as a hard default. The tells below are not checkable. They are judgement, and the most a written list can do is make them noticeable. Read this before writing anything longer than a few paragraphs. Do not treat it as a checklist to pass, because writing that has been made to pass a checklist has its own smell.

- **The rule of three.** Three parallel clauses, three-item lists, three examples where two would have done. Real thinking produces uneven counts. When something arrives in threes, check whether the third earns its place or is there for the cadence.
- **"It is not just X, it is Y."** Also "not only, but also", and "this is not about A, it is about B". The construction manufactures depth by denying something nobody claimed.
- **The summary that adds nothing.** A closing paragraph restating what was just said in more abstract words. If the final paragraph could be deleted without loss, delete it.
- **The symmetrical close.** Ending by returning to the opening image or phrase. It reads as composed rather than thought.
- **Even sentence length.** Consistently medium sentences with the same shape and rhythm. Vary them. Short sentences carry weight.
- **Elegant variation.** Cycling through synonyms to avoid repeating a word. Repeat the word. The reader tracks it better and the writing stops drawing attention to itself.
- **Throat-clearing openers.** "It is worth noting that", "It is important to understand", "In today's environment". Cut them and start at the point.
- **Uniform hedging.** Every claim softened with "may", "could", "often", "generally". Say what you mean, or say you are unsure and say why.
- **Signposting the obvious.** "First, second, finally" on a short list the reader can already see.

The test that works better than any of the above: read it aloud. Machine prose is fluent, evenly weighted, and sounds like nobody in particular. If no sentence sounds like something you would actually say out loud, start rewriting with the ones that sound most polished.

## Sentence-level rules

The tells above are judgement. These are mechanical, and they can be checked.

**Why this exists.** Almost everything written here is read once, quickly, by someone about to act on it. A facilitator glancing at a speaker note has seconds. A participant reads a client reference the night before and never again. A sentence the reader has to decode twice has failed. Writing that reads as generated does worse than fail. These documents go in front of people asked to trust, validate and sign them.

**Objectives.**

- The reader can act on a sentence at first reading.
- Two readers take the same meaning from it.
- The writing sounds like a person who knows the material.

Two tiers.

**Instructions.** Read while doing something else: facilitator references, speaker notes, step lists, checklists. Apply everything below, length caps included.

**Everything else.** Analysis documents, briefs, summaries, participant-facing prose, replies in session. Apply the word, verb and structure rules. The length caps do not apply.

### Words

- One name for one thing. Not the pre-fill sheet in one paragraph and the written questions two paragraphs later.
- Reach for the short common word. Start, not commence or initiate. Use, not utilise or leverage. Help, not facilitate. Make sure, not ensure. Before, not prior to. After, not subsequent to. About, not regarding or in relation to. Get, not obtain. Show, not demonstrate. Also, not additionally or furthermore. Enough, not sufficient.
- One meaning per word. If "cover" means log-source coverage in one paragraph, do not use it for "handle" in the next.
- No selling adjectives: seamless, robust, holistic, comprehensive, world-class, best-in-class, cutting-edge, powerful. Also "key" and "critical" as filler.
- Australian spelling.

### Verbs

- Active voice, actor named. "Kaisar maintains the log-source list", not "the log-source list is maintained".
- Use the passive where the actor is unknown, or where naming them would attribute something in a room where attribution was assured against. Do not invent an actor to satisfy the rule.
- Use a verb for an action. "Analyse the gap", not "perform an analysis of the gap".
- No stacked auxiliaries. Not "it is important to note that this may help to improve coverage". Write "this improves coverage", or say you are unsure and why.
- No "-ing" main verb where a simple tense works.
- No phrasal verbs where a plain one exists. Set up, not spin up. Start, not kick off.

### Sentences

- One instruction per sentence.
- Instructions: 20 words. Descriptive sentences inside an instruction document: 25. Elsewhere, 25 is a prompt to look at the sentence, not a limit. Writing to a uniform cap produces the even rhythm listed above as a tell. Vary length on purpose.
- No contractions in artefacts. Replies in session may use them.
- Keep the articles: a, an, the, this, these.
- No semicolons. Write two sentences.
- No dashes. Scoped to commit subjects and tag annotations in this repo, per "Adapted for plan_foundry" above. Prose em dashes are deliberate here and are not in scope.

### Structure

- One topic per paragraph, six sentences at most.
- Steps as a numbered vertical list, one action per item, imperative.
- Condition before command. "If Kaisar brings the log-source list, walk it", not "walk the list if Kaisar brings it".
- Write the requested text and stop. No preamble, no closing summary. Frontmatter, stamp lines and version headers stay.

### What good looks like

Good is not a document that passes the lint. It is a document the reader acts on without stopping.

In an instruction, that means three things and nothing else: what to ask, what answer to expect, what to watch for.

Before:

> This question was merged from the original Q7 and Q12 during the leanness pass and is protected under D14, so it should not be shortened. It is important to note that the answer may vary depending on whether participants have visibility of the underlying tooling.

After:

> Ask Kaisar. Expect a named tool and a rough count. If he names a vendor only, ask what it covers. Do not rush this one.

The second is shorter, but length is not what changed. Every sentence in it tells the facilitator to do something. The first explains why the slide is the way it is, which is unusable while a room waits.

In prose rather than instructions, good reads as though someone who knows the material is telling you about it. Sentence lengths are uneven. Nothing clears its throat before starting. Claims sit at the strength the evidence supports, hedged where genuinely uncertain and stated flatly where not. The same thing carries the same name from the first page to the last.

### Lint before returning

1. Sentence over 25 words. Split it, or decide it earns the length.
2. Semicolon. Write two sentences.
3. Contraction in an artefact. Expand it.
4. Passive with an actor who can be named. Name them.
5. Nominalisation, phrasal verb, or "-ing" main verb. Replace with a plain verb.
6. The same thing named two ways. Pick one and go back through.
7. American spelling.
8. Every sentence the same length. Vary them.

The source document's second lint item checked for em dashes, en dashes, curly quotes, ellipses and other non-ASCII characters. That check is not run over prose in this repo, for the reason under "Adapted for plan_foundry". It is enforced on commit subjects and tag annotations by `.claude/hooks/commit-msg` and `_shared/ascii_git.py`.

### Limitations

Form only. The lint does not check whether a claim is true, grounded, or worth making. In this repo that grounding sits with the audit loop: `audit-sufficiency` for conceptual grounding, `audit-haiku-safe` for mechanical checkability.

## Open question for the human

Should the plain-ASCII rule from the source document replace this repo's D9 position, or should D9 stand and this file keep the narrower scope? The two cannot both hold. Adopting plain ASCII means rewriting 968 deliberate non-ASCII lines across 55 files and reversing a locked decision. Keeping D9 means this file diverges from the source document on one rule. It is currently scoped to D9, which is the no-change option and the reversible one.

## Provenance

Adapted 27 July 2026 from <https://github.com/woosal1337/blog/blob/main/videos/ep01-the-cure-for-ai-slop/ste-writing-skill.md>. The underlying standard is ASD-STE100, at <https://asd-ste100.org>, copyrighted and not reproduced here. This file is an independent restatement, which is what makes it safe to ship in a public bundle. See `Retired/FOUNDRYREQ-plan-foundry-dev-20260727-1452-adopt-asd-ste100-technical-writing-standard.md` for the licensing reasoning and for the resolution of the three conflicts that request identified.
