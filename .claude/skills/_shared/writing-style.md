---
title: Writing Style
description: Defines the writing rules for artefact writing. States which writing mode applies, what to do before drafting, the prose tells that mark artificial writing, and the mechanical rules for words, verbs, sentences, and structure. Read whenever writing style is in question.
created: 2026-07-27
---
# Writing Style

This file defines the detailed writing rules for artefact writing.

The rules for conversation, communication, and working with the human live in the root `CLAUDE.md` and in `.claude/skills/init-plan-foundry/operating-rules.md`.

## Which Writing Mode Applies

The reader determines which writing mode applies. Ask one question:

> Will the reader have seen the conversation that produced this text?

- **Yes: conversation mode.** The reader already shares the context. Signposting is encouraged because it helps the reader follow the discussion. Contractions are allowed. The length limits in this document do not apply. The word rules, verb rules, drafting rules, and one-name-per-thing rule still apply.
- **No, or not sure: artefact mode.** Apply all rules in this document.

A draft written in chat for later inclusion in a file uses artefact mode, even though it appears in a conversation. The surrounding explanation remains in conversation mode. When both appear in the same message, the draft itself marks the boundary.

Subagent reports also use artefact mode, because their eventual reader did not participate in the run that produced them.

Keep the distinction clear. Conversation mode should not become telegraphic, and artefact mode should not become conversational or ornamental.

Build-up is different from signposting. Signposting helps the reader follow the discussion, while build-up withholds the point for effect. Do not withhold the point for effect in either mode.

## Before You Draft

Apply these rules before drafting begins. They define the material the document needs before any prose is written.

1. **Ask clarifying questions before producing long outputs.**
2. **Do not write artefacts, code, or long-form sections without authorisation.**
3. **Write one line per subject first.** For every subject the document names, record:

   - its canonical name
   - what a new reader must know at first mention
   - the verb the domain uses for that subject

   Draft from those notes. If you cannot complete a line, treat it as a research gap and consult the source material before writing.
4. **Write the load-bearing sentence first.** Decide what the document exists to say, then write that sentence before drafting the rest. Everything else should help the reader understand that sentence on first reading. Decide where the emphasis belongs rather than leaving it to sentence rhythm or structure.

## Prose Tells: Read Before Writing Longform

Read this section before writing anything longer than a few paragraphs.

Aim for prose that sounds like someone who understands the material and is explaining it directly to the reader. Read the draft aloud. The draft should sound like a knowledgeable colleague explaining something clearly. If a passage sounds performed, stylised, or overly polished, rewrite it, and use the tells below to identify why.

The tells are not mechanical rules and they are not a checklist. They exist to make common writing faults easier to recognise. Except where a tell notes otherwise, the tells apply in both writing modes.

### Remember While Drafting

These tells affect drafting decisions as you write.

- **Sentences about the document.** Do not describe the document when you could state the point directly.

  Common examples:

  - "It is worth noting that..."
  - "It is important to understand..."
  - "In today's environment..."
  - "There are three things to know..."
  - "Here is what you need to know..."

  Avoid signposting a short list the reader can already see, such as "first, second, finally".

  Ask one question: does the sentence provide information, or does it describe the document that contains the information? Delete the second kind and start with the point instead.

  This tell does not apply in conversation mode, where signposting is often useful.
- **Manufactured contrast.** Avoid constructions such as:

  - "It is not just X, it is Y."
  - "Not only X, but also Y."
  - "This is not about A, it is about B."

  These constructions often create the appearance of depth by rejecting a position that nobody has argued for.

  State the point directly instead.
- **Parataxis, asyndeton, staccato prose and clipped fragments.** These are different forms of the same problem: presenting related facts without stating how they relate.

  Examples:

  - Parataxis: "The file was there. The check ran. Nothing failed."
  - Asyndeton: "He read the log, he found the gap, he wrote the fix."
  - Clipped fragment: "Committed and clean."

  Technical writing should state relationships explicitly. If two facts are connected, say how they are connected. Use words such as "because", "so", "after", "although", and "which" when they describe the relationship accurately. Do not rely on neighbouring sentences to imply meaning.

  If several short sentences appear together, identify the claim and its supporting facts, then write the relationship explicitly rather than leaving the reader to infer it.
- **Hedging.** Do not soften claims with words such as "may", "could", "often", or "generally" unless necessary.

  Commit to a conclusion. A reader should not have to infer your position. State the conclusion you actually support and explain why you reached it. If you are unsure, say that you are unsure and explain the cause of the uncertainty.

  This is a confidence problem, not a writing problem. The fix is to decide what level of certainty the evidence supports, not to rewrite the sentence.
- **Elegant variation.** Do not replace a word with synonyms simply to avoid repeating it.

  Repeat the same word when it refers to the same thing. Consistent terminology helps the reader track the subject and keeps attention on the meaning rather than the wording.
- **False agency.** Do not give human actions or intentions to files, checks, logs, audits, or other outputs.

  Avoid:

  - "the fixture found two defects"
  - "the audit decided"
  - "the log chose not to flag it"

  Instead, describe what happened or who acted:

  - "the fixture's output lists two defects"
  - "the auditor classified the finding as..."
  - "the log contains no matching entry"

  Name the person, tool, process, or output that actually produced the result. If no actor exists, describe the outcome rather than inventing one.

  In any document used for review, approval, or audit, responsibility and causation are often significant. Do not obscure them.
- **Unnecessary comparisons.** Do not strengthen a claim by comparing it to something the reader was not already considering.

  Avoid:

  - "...that reading the code twice had not"
  - "...faster than three engineers working it by hand"

  These comparisons often create the appearance of significance without adding useful information.

  State the claim directly. Add a comparison only when the comparison is necessary to understand the point.
- **Unnamed decisions.** When raising a decision, name the decision itself.

  Avoid:

  - "gated on a decision only you can make"
  - "gates roadmap item 3"

  The reader should not have to infer the decision from its consequences.

  Name the decision in the same sentence that raises it. If a choice is needed, state what the choice is.

  Example:

  - "Choose between schema A and schema B. This blocks roadmap item 3."

### Review These After Drafting

These patterns can only be assessed once a draft exists. Review them as an editing pass.

- **Unnecessary groups of three.** Three parallel clauses, three-item lists, or three examples where two would do. Writing often produces uneven counts. When something arrives in threes, check whether the third item adds information or only supplies rhythm.
- **Empty summaries.** A closing paragraph that restates the document in more abstract language. If the final paragraph can be removed without losing information, remove it.
- **Symmetrical endings.** Returning to the opening phrase, image, or framing simply to create a neat ending. This often feels constructed rather than helpful.
- **Uniform sentence length.** A long run of sentences with similar length and rhythm. A run of short sentences becomes staccato, the style described above. A run of long sentences becomes heavy. Vary sentence length deliberately where it improves readability: use longer sentences where explanation is needed and shorter ones where a consequence, conclusion, or important point should stand out. Contrast creates emphasis, and contrast is what makes a short sentence noticeable.
- **Uniform emphasis.** When every paragraph ends on a notable closing line, none of them stands out. Read the paragraph endings together. Most should end plainly. Use emphasis sparingly and deliberately.
- **Plainer restatements.** A dense sentence immediately followed by a simpler version of the same point. Keep the clearer sentence and remove the other one.

Writing that feels artificial is often fluent, evenly weighted, and polished in the same way throughout. When the read-aloud test fails, start with the sentences that feel the most polished or performative, because those are often where these patterns hide.

## Mechanical Rules

Spotting the tells above takes judgement. The rules below are mechanical, so apply them by hand while drafting and check for them when reviewing.

Length limits apply differently depending on the document type. Determine the document type first, then apply the relevant limits.

**Instructions**

Documents used while performing a task, including facilitator guides, speaker notes, checklists, and step-by-step procedures.

Apply all rules below, including the length limits.

The purpose of the limits is to keep instructions short enough to act on directly. They are not a licence for sentence fragments, aphorisms, or clipped prose. Make instructions concise by removing unnecessary language, not by removing words required for meaning.

**Everything else**

Analysis documents, briefs, summaries, reports, and participant-facing prose.

Apply the word, verb, and structure rules below. Length limits do not apply.

### Words

Use plain language. Name the thing, the action, and the result. Prefer ordinary words, complete syntax, and direct statements. The goal is clear technical writing, not a literary style.

- **One name per thing.** Use the same name for the same thing throughout the document. Do not call it the pre-fill sheet in one paragraph and the written questions in the next.
- **Prefer short, familiar words.** Start, not commence or initiate. Use, not utilise or leverage. Help, not facilitate. Before, not prior to. After, not subsequent to. About, not regarding or in relation to. Get, not obtain. Show, not demonstrate. Also, not additionally or furthermore. Enough, not sufficient.
- **Gloss identifiers and coined terms at first use.** Write "PLAN-AK3, the rolling board orchestrator", not just "PLAN-AK3". Do the same for project shorthand, internal labels, and event names the reader has not encountered before. Include the gloss by default. Omit it only when there is a clear reason to assume the reader already knows the term.
- **One meaning per word.** If "cover" means log-source coverage in one section, do not use it to mean "handle" in another.
- **Avoid promotional language.** Do not rely on adjectives such as "seamless", "robust", "holistic", "comprehensive", "world-class", "best-in-class", "cutting-edge", or "powerful". Avoid filler uses of "key" and "critical".
- **Use Australian spelling and date formats.**

### Verbs

- **Make cause and responsibility clear.** Name the responsible person, tool, process, or cause when doing so improves understanding. Use the active voice where it helps. For example: "Kaisar maintains the log-source list", not "the log-source list is maintained".
- **Do not invent actors.** When responsibility is unknown, irrelevant, or intentionally withheld, do not force the active voice. Use the passive voice or rewrite the sentence to describe what happened. Do not attribute decisions, intentions, or actions to things that cannot make them.
- **Use the domain's verb.** Use the verb that accurately describes how the subject behaves. A document, requirement, control, file, or rule applies, covers, states, requires, defines, or excludes something. Prefer precise domain verbs over vague physical ones such as "sits", "rests on", "lives in", "binds", or "shapes". "The requirement applies to the sensor" is clearer than "the requirement lives at the sensor". If no suitable domain verb comes to mind, find out how the subject behaves before writing about it.

  `carries` is accepted house usage throughout this bundle.
- **Prefer actions over nominalisations.** Use a verb where the sentence describes an action. Write "analyse the gap", not "perform an analysis of the gap".
- **Avoid stacked auxiliaries.** Do not bury a simple claim under layers of helper verbs. Instead of "it is important to note that this may help to improve coverage", write "this improves coverage", or explain the uncertainty if uncertainty is real.
- **Prefer simple tenses.** Do not use an `-ing` main verb where a simple tense expresses the same idea.
- **Prefer direct verbs.** Where a plain verb exists, use it. "Start", not "kick off". "Ensure", not "make sure". "Create", not "set up".

### Sentences

- **One instruction per sentence.**
- **Keep instructions short.** In instruction documents, instructional sentences should be no more than 20 words. Descriptive sentences should be no more than 25 words.

  Outside instruction documents, 25 words is a prompt to review the sentence, not a limit. Do not write to a fixed length.
- **No contractions in artefacts.**
- **Keep articles.** Do not drop words such as "a", "an", "the", "this", or "these" to save space.
- **Do not use semicolons.** If two clauses are related, name the relationship with a conjunction. If they are unrelated, write two sentences. Do not treat this rule as a licence to produce disconnected sentences.
- **No dashes in commit subjects or tag annotations.**
- **Name what you are referring to.** Prefer repeating the noun, or use "this" or "that" when repetition would be genuinely awkward.

  Avoid relying on "it" where the reader could reasonably interpret it in more than one way.

  Do not:

  - open a sentence with "it"
  - close a sentence with "it"
  - use "it" where multiple antecedents are possible

  Readers should not have to guess what a pronoun refers to.
- **Avoid weak sentence boundaries.**

  - Do not begin a sentence with "So".
  - Do not end a sentence with "from".

  The opening and closing positions in a sentence carry disproportionate weight. Do not spend them on filler words, ambiguous pronouns, or trailing prepositions.

### Structure

- **One topic per paragraph.** Keep paragraphs to six sentences or fewer.
- **Write steps as a numbered list.** One action per step. Use the imperative mood.
- **Put conditions before commands.** Write "If Kaisar brings the log-source list, go through each item", not "go through each item if Kaisar brings the log-source list".
- **Write the deliverable and stop.** Do not add preambles or closing summaries. Frontmatter, stamp lines, and version headers are still part of the deliverable. This rule applies to artefacts, not conversation.
- **Stamp dated files.** When creating dated Markdown files for project memory, include the datetime stamp in both the filename and the document header.
- **Do not persist derived counts.** Do not record counts of things that can be listed or re-derived.

  Avoid:

  - "the 24 skills" <!-- tally-ok: an example of the banned pattern, not a real count to enforce -->
  - "8 tests covering" <!-- tally-ok: an example of the banned pattern, not a real count to enforce -->
  - "the nine-step procedure"

  Instead, name the members or provide the command that produces the count.

  Counts become stale. They can also hide changes by persisting long after the underlying members have changed.

  Counts are acceptable when the number itself is the fact, such as a limit, threshold, bound, or slot count. Dated historical measurements are also allowed and must include a `tally-ok:` marker explaining why the count is being preserved.
- **Keep reference documents operative.** Reference documents tell the reader what to do. They do not contain commentary about themselves.

  Do not include:

  - provenance notes
  - adaptation notes
  - open questions
  - design commentary
  - unresolved disputes parked in the document

  Ask: does removing this sentence change what the reader does? If not, it probably does not belong in the document.

  Put supporting reasoning in the PLAN, commit message, or Workbench record instead.

  Operative scoping is not marginalia. For example, "this rule applies to commit subjects, not prose" changes reader behaviour and therefore belongs in the document.

## Project-local Supplement

Projects may add local writing rules in `.claude/writing-style-local.md`.

The supplement may add rules or tighten existing ones, but it must not relax or override anything in this file. A project may add banned words or phrases in the supplement's **Additional banned words or phrases** list.

If no supplement exists, this file applies unchanged.

Judgement-based rules still require a human reader. A supplement can add mechanical rules, but it does not replace editorial judgement.

The subset of these rules that governs writing agents is also inlined into seven agent bodies under `.claude/agents/`. See [harness-contract.md](harness-contract.md) "Output-style isolation from subagents" for why this file cannot reach them directly. That inlined copy is synced from a single source, `.claude/skills/_shared/artefact-register-agent-block.md`: change the rules there and run `scripts/ci/sync-artefact-register.py` to propagate the change, rather than editing an agent body directly.

## Limitations

These rules govern form, not substance.

They do not determine whether a claim is true, well-supported, complete, or worth making.
