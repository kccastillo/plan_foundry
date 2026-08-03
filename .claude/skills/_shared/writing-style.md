---
title: Writing Style
description: How written outputs should be written. Spelling, dates, authorisation to write, plain language, file stamping, the prose tells to watch for, and the sentence-level rules. Adapted from an ASD-STE100 distillation.
created: 2026-07-27
---
# Writing Style

This file carries the detailed word, verb, sentence and structure rules for anything that outlives the session. The stance governing everything Claude writes, including conversation, is the `How to work with the human` section of the root `CLAUDE.md` and of `.claude/skills/init-plan-foundry/operating-rules.md`.

- Australian spelling and date formats.
- Ask clarifying questions before producing long outputs.
- Do not write artefacts, code, or longform sections without authorisation.
- Plain language. Do not compress, abbreviate, or elide. Name the thing, the operation, the result.
- When creating dated md files for project memory, the header and the filename both carry a datetime stamp.

## Prose tells: read before writing longform

Aim for prose that sounds like it came from someone who knows the material and is talking to you directly. Read it aloud. If no sentence sounds like something you would actually say out loud, the tells below name what likely produced that. Character rules are checkable, so they can be enforced as a hard default. These are not - they are judgement, and the most a written list can do is make them noticeable. Read this before writing anything longer than a few paragraphs. Do not treat it as a checklist to pass, because writing that has been made to pass a checklist has its own smell.

- **The rule of three.** Three parallel clauses, three-item lists, three examples where two would have done. Real thinking produces uneven counts. When something arrives in threes, check whether the third earns its place or is there for the cadence.
- **"It is not just X, it is Y."** Also "not only, but also", and "this is not about A, it is about B". The construction manufactures depth by denying something nobody claimed.
- **The summary that adds nothing.** A closing paragraph restating what was just said in more abstract words. If the final paragraph could be deleted without loss, delete it.
- **The symmetrical close.** Ending by returning to the opening image or phrase. It reads as composed rather than thought.
- **Even sentence length.** Consistently medium sentences with the same shape and rhythm. Vary them. A short sentence carries weight because the ones around it do not. Read that as an observation about contrast. It is not an instruction to write short sentences throughout.
- **Uniform emphasis.** Every paragraph landing on a closing beat, so none of them stands out. Individual sentences can each be defensible while the aggregate is wrong, which is why the per-sentence tells above will not catch this one. Read your paragraph closes in sequence. In varied prose most of them are flat and one or two carry weight. Aim for one weighted close in a piece. Removing all of them is the over-correction.
- **Elegant variation.** Cycling through synonyms to avoid repeating a word. Repeat the word. The reader tracks it better and the writing stops drawing attention to itself.
- **Throat-clearing openers.** "It is worth noting that", "It is important to understand", "In today's environment". Cut them and start at the point.
- **Uniform hedging.** Every claim softened with "may", "could", "often", "generally". Say what you mean, or say you are unsure and say why.
- **Signposting the obvious.** "First, second, finally" on a short list the reader can already see.
- **The preview-count opener.** "Three things it carries that you will want to know", "There are two reasons for this", "Here is what you need to know". Announcing that content is coming, and how many items, instead of just giving the content. Delete the preview and state the things - see the pronoun rule under Sentences for how to name what "it" is doing the work of.
- **False agency.** A file, a check or a piece of output given a verb only a person or an agent can do - "the fixture found two defects", "the audit decided", "the log chose not to flag it". Name who acted. If nobody did and the sentence only describes what the output contains, say that instead - "the fixture's output lists two defects".
- **The comparison-tail flourish.** A clause tacked on at the end that measures the claim against something nobody asked to compare it to - "...that reading the code twice had not", "...faster than three engineers working it by hand". The comparison manufactures a scale for a claim that did not need one. State the claim and stop.
- **The amped-up decision teaser.** Naming a decision by what it blocks or costs instead of naming the decision - "gated on a decision only you can make", "gates roadmap item 3". Name the decision in the sentence that raises it. A reader who has to go elsewhere to find out what is actually being decided has been made to work for something the sentence should have given them.

Machine prose is fluent, evenly weighted, and sounds like nobody in particular. When the read-aloud test above fails, start rewriting with the sentences that sound most polished - those are usually where the tells are hiding.

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
- No dashes in commit subjects or tag annotations.
- Point at things by naming them. Name the noun again, or reach for "this"/"that" when repeating the noun would be genuinely clumsy - both make you say what you are pointing at, where "it" lets you skip that and drift to whatever the reader guesses. Never open a sentence on "it", never close one on it, and never leave two clauses in the same sentence each offering their own candidate for what one "it" means. "The file carries the date, the author and the retry count" beats "This carries..." beats "It carries...". "The file has not gone missing again. Every commit since is pushed to the remote" beats "The vanished file did not recur. Everything written after it is committed and on the remote," where "it" could mean the file or the recurrence and the reader has to guess mid-sentence.

### Structure

- One topic per paragraph, six sentences at most.
- Steps as a numbered vertical list, one action per item, imperative.
- Condition before command. "If Kaisar brings the log-source list, go through each item", not "walk the list if Kaisar brings it".
- Write the requested text and stop. No preamble, no closing summary. Frontmatter, stamp lines and version headers stay.
- **Never write down a count of things that exist elsewhere.** Not "the 24 skills", not "8 tests covering", not "the nine-step procedure". Name the members, or give the command that re-derives them. A tally is true on the day it is typed and silently false afterwards, and it does not even catch what it appears to guard: add one member and remove another and the number is unchanged while both facts are wrong. A number that *is* the fact rather than a count of facts stays - a cap, a threshold, a bound, a slot space. So does a dated measurement of a past event, because the date is part of the claim; mark those `tally-ok:` with the reason. Everything else: write the list.
- **No marginalia in reference documents.** A skill, helper or reference file carries what the reader must do. It does not carry commentary about itself. Specifically, do not write: provenance or attribution sections saying where the file came from; adaptation notes explaining how this copy differs from some original; open questions asking the reader to decide something; notes about why the document is shaped the way it is; or parked conflicts recorded in-line for someone to resolve later. The test: does removing this sentence change what a reader does? If not, it does not belong in the file. Put the reasoning in the PLAN, the commit message or a Workbench input, all of which are built to hold it. Operative scoping is not marginalia - "this rule applies to commit subjects, not prose" changes what the reader does and stays.

### What good looks like

Good means the reader acts on it without stopping.

In an instruction, that means three things and nothing else: what to ask, what answer to expect, what to watch for.

Before:

> This question was merged from the original Q7 and Q12 during the leanness pass and is protected under D14, so it should not be shortened. It is important to note that the answer may vary depending on whether participants have visibility of the underlying tooling.

After:

> Ask Kaisar to name a tool or a set, and to give a rough count. If a vendor is named, ask what the vendor covers. Afterwards, ask what is not covered.

The second is shorter, but length is not what changed. Every sentence in it tells the facilitator to do something. The first explains why the slide is the way it is, which is unusable while a room waits.

In prose rather than instructions, the same outcome anchor from Prose tells above applies: sentence lengths are uneven, nothing clears its throat before starting, claims sit at the strength the evidence supports, and the same thing carries the same name from the first page to the last.

### Lint before returning

1. Sentence over 25 words -> decide if the length is needed, otherwise split.
2. Semicolons -> Write two sentences.
3. Contraction in an artefact -> Expand it.
4. Passive with an actor who can be named -> Name them.
5. Nominalisation, phrasal verb, or "-ing" main verb -> Replace with a plain verb.
6. The same thing named two ways -> Pick one and go back through.
7. American spellings -> convert to Australian.
8. Every sentence the same length -> Vary them.

### Limitations

Form only. The lint does not check whether a claim is true, grounded, or worth making.
