---
asset_id: help-research-prompt-template
kind: helper
title: Research Prompt Template
topic_tags: [research, prompts, ideate, survey, sub-questions]
description: Mandatory sub-questions that research-bot prompts must include when dispatched during the Survey phase of the ideate cadence.
discoverable_via: [ideate-clarify, manual]
created: 2026-05-26
last_consulted: ""
consulted_by: []
schema_version: 1
---

# Research Prompt Template - Sub-Questions

This file enumerates mandatory sub-questions that research-bot prompts MUST include when dispatched during the Survey phase of the ideate cadence. Each section is a topic area with the required sub-question text.

PLAN-AA9 (Reeve F1 research-anchor) consumes this file when constructing Survey-phase research dispatches. When AA9 ships, its research-dispatch logic should read this file and include every listed sub-question in the prompt sent to the research bot.

**Maintenance rule:** add sub-questions here when a new class of hallucination-from-missing-ground-truth is discovered and confirmed in the hiccup log. Do not add speculative or low-signal sub-questions - each entry should be backed by a concrete hiccup or recurring failure pattern.

---

## Sub-Questions

### 1. Public API Surface (H5 - FastMCP private-attribute hallucination, 2026-05-16)

**Originating hiccup:** H5 - Plan B Spec-Draft used `s._tools` (FastMCP private attribute) in two verify/acceptance gates. Research covered FastMCP conceptually; Spec-Draft jumped to "use FastMCP's tool registry" without checking the public introspection API.

**Required sub-question text (include verbatim in each tool/framework research prompt at Survey):**

> For each chosen tool/framework, enumerate the public API surface: which attributes/methods are documented public vs private (e.g. `_`-prefixed) vs dunder. For introspection/registry use-cases specifically, list which methods/attributes the documentation recommends for that purpose. The spec MUST author against documented public surface only - private attributes (`_`-prefixed) and dunder methods are off-limits unless the framework's own documentation explicitly calls them out as stable extension points.

**Expected output shape from research bot:**
- Table or list: `attribute/method name | public/private/dunder | documented use-case`
- Flag any commonly-misused private attributes the framework's issues tracker mentions
- Cite the specific documentation page or source code docstring backing each "public" classification

---

### 2. Prior-Art Citations (F1 - Research-anchor, PLAN-AA9, 2026-05-17)

**Originating finding:** F1 from the 2026-05-16 plan-foundry retrospective. Survey phase relied on first-principles reasoning for Real-judgement-call decisions instead of checking prior art in adjacent communities. Research outputs that cite no sources are untraceable and unverifiable.

**Required sub-question text (include verbatim in each research-bot prompt at Survey):**

> For each finding or recommendation in this research output, cite at least one source - a URL to documentation, a paper, a canonical reference in adjacent communities (e.g. RFC, library docs, community post), or a tracked issue thread. Do not assert a fact without a citation. If no external citation exists, state that explicitly rather than omitting the citation slot.

**Expected output shape from research bot:**
- Each finding is followed by a `Source:` line with the URL or reference
- If citing multiple sources for a single finding, list them as a numbered sub-list
- Flag findings where no external citation could be located (these become candidates for further research or for demotion to "orchestrator's prior reasoning only")

---

### 3. Lean-Reversibility (F1 - Research-anchor, PLAN-AA9, 2026-05-17)

**Originating finding:** F1 from the 2026-05-16 plan-foundry retrospective. A research finding reversed the orchestrator's Survey lean (N5 stacking decision), but the cadence had no mechanism for surfacing this reversal explicitly. The reversal was discovered post-hoc rather than during the Survey phase where it would have changed the decision.

**Required sub-question text (include verbatim in each research-bot prompt at Survey):**

> The orchestrator's current lean on this decision is: [ORCHESTRATOR FILLS IN LEAN BEFORE DISPATCHING]. If any finding in this research output contradicts or qualifies that lean, state this explicitly at the top of the output with: "REVERSAL: this research reverses [or refines] the stated lean because [reason]." If the lean is confirmed by the research, state: "CONFIRMED: research supports the stated lean." Do not bury a lean-reversal in the body of the output.

**Expected output shape from research bot:**
- First line of substantive output: either `CONFIRMED: ...` or `REVERSAL: ...`
- Lean-reversal states the new recommended direction and the primary evidence driving the reversal
- Lean-confirmation briefly states which evidence most strongly supports the current lean

---

### 4. Verdict Line (F1 - Research-anchor, PLAN-AA9, 2026-05-17)

**Originating finding:** F1 from the 2026-05-16 plan-foundry retrospective. Research outputs without a terminal verdict line require the orchestrator to synthesise a verdict from the body - introducing a second point of inference error after the research itself.

**Required sub-question text (include verbatim in each research-bot prompt at Survey):**

> End your response with a single "Verdict:" line that states one of: (a) "Confirmed - [lean] holds; [primary evidence]", (b) "Reversed - recommend [new lean] instead; [primary evidence]", or (c) "Refined - [lean] holds but qualified by [condition]; [evidence]". The Verdict line is the machine-readable terminal signal for the orchestrator; keep it to one sentence.

**Expected output shape from research bot:**
- Last line of the response: `Verdict: Confirmed - ...` or `Verdict: Reversed - ...` or `Verdict: Refined - ...`
- One sentence maximum
- Cites the single strongest piece of evidence driving the verdict

---

*(Add further sub-questions here as new hiccup classes accumulate. Each section: H-code reference, originating hiccup, required sub-question text, expected output shape.)*

---

## Prompt-Template Shape

Every research-bot dispatch constructed by the ideate Survey phase (Phase 2.B) MUST include these structural elements, in this order:

```markdown
## Research Brief

**Context:** [1-3 sentences: what ideation is about, which PLAN, which phase]

**Decision cluster under research:** [name the specific cluster, e.g. "N5 stacking mechanism", "write-input output format"]

**Orchestrator's current lean:** [state the lean explicitly - this is consumed by Sub-question 3 (Lean-reversibility)]

**Options being evaluated:**
- [Option A]: [one-liner + current disposition: lean/reject/defer]
- [Option B]: [one-liner + current disposition]
- ... (all >=3 options from Phase 2.A expand-explode pass)

## Mandatory Sub-Questions

Answer each of the following in your response:

1. **Public API Surface** (if this involves a tool/framework): [paste Sub-question 1 text verbatim]
2. **Prior-Art Citations**: [paste Sub-question 2 text verbatim]
3. **Lean-Reversibility**: [paste Sub-question 3 text verbatim, filling in the orchestrator's current lean]
4. **Verdict Line**: [paste Sub-question 4 text verbatim]

## Output Format

- 400 words maximum
- Cite every factual claim (Sub-question 2)
- Begin with CONFIRMED / REVERSAL lean signal (Sub-question 3)
- End with a single Verdict: line (Sub-question 4)
```

**Notes on the template:**
- The orchestrator fills in `[ORCHESTRATOR FILLS IN LEAN BEFORE DISPATCHING]` in Sub-question 3 with the actual lean from Phase 2.A before sending the prompt.
- All four sub-questions are mandatory regardless of cluster type. Sub-question 1 (Public API Surface) applies when the decision involves a tool or framework; for purely design decisions, the orchestrator notes "N/A - no tool/framework involved" in the dispatch and the research bot skips it.
- The 400-word cap applies to the research bot's response body, not the prompt itself.
- Research bot dispatch target: `survey-researcher` (`subagent_type: survey-researcher`), defined at `.claude/agents/survey-researcher.md` with `model: sonnet` pinned in its frontmatter (per PLAN-AE7). Dispatching by named agent enforces the Sonnet tier structurally - it is no longer advisory. Do not dispatch an unpinned general-purpose subagent for Survey Phase 2.B research; always use `survey-researcher`.
