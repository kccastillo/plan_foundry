---
name: foundry-research
description: plan_foundry's model-tiered, budget-sized deep-research harness — fan-out web searches, fetch sources, adversarially verify claims, and synthesize a cited report, with each fan-out role pinned to the cheapest capable model (scope/fetch on Sonnet, search/verify on Haiku, synthesis on Opus; never Fable) and the fan-out sized to the token budget. Prefer this over the native `deep-research` skill, which omits per-role model pins and runs every agent on the inherited (possibly frontier) session model. Trigger phrases — "foundry research <question>", "tiered research", "planned research report", "deep dive on <topic>", "research <question> with model tiering", "deep research the cheap way".
---

## What this skill does

It runs the same research shape as the native `deep-research` harness — **Scope → Search → Fetch+Extract → adversarial Verify → Synthesize** — but fixes the two defects documented in `Workbench/EXTERNAL_RESEARCH-009` and `Workbench/EXTERNAL_ADVICE-002`:

1. **Per-role model tiering.** The native harness omits `model:` on every `agent()` call, so all ~100 fan-out agents inherit the session model (one observed run: ~104 agents on Fable 5, ~1.48M tokens, degraded result). This skill pins the cheapest capable model per role.
2. **Budget-aware fan-out sizing.** The native harness fans out to fixed caps regardless of remaining budget. This skill scales its caps from the Workflow `budget` global and trims the verify pool to fit.

The model assignment lives in **version-controlled bundle code** (the workflow script + `references/model-tiering.md`), not in an un-honoured operator memory.

## Model tier policy

| Role | Model | Why |
|---|---|---|
| Scope (decompose) | **Sonnet** | Bounded decomposition; judgement but light — Opus not needed |
| Search (WebSearch) | **Haiku** | Mechanical search + relevance ranking; high-volume-cheap |
| Fetch + extract | **Sonnet** | Fetch + falsifiable-claim extraction; reading comprehension |
| Verify (3-vote) | **Haiku** | Boolean adversarial votes; schema-bounded, highest volume — biggest cost win |
| Synthesize | **Opus** | Merge / judge / cite — the one place real judgement concentrates |

**Fable is used nowhere. Opus appears only at synthesis.** See [references/model-tiering.md](references/model-tiering.md) for the full rationale and the cross-cutting principle (the same tier-by-role discipline applies to any role-homogeneous fan-out — judge panels, review/bughunter swarms).

> **Caveat — no effort knob.** The Workflow `agent()` opts expose `model:` but not an effort level. The operator's recorded "sonnet/medium retrieval + opus/high synthesis" split is honoured by model tier only.

## How to run it

1. **Narrow the question first.** If the question is underspecified (e.g. "what car to buy" with no budget/use-case/region), ask 2-3 clarifying questions and weave the answers in. A sharp question is what makes the fan-out worth its tokens.

2. **Flag budget posture before a wide dispatch (per ADVICE-013).** Multi-agent fan-out drains a **shared** token pool fast. If a budget cap is in force, size the run deliberately and confirm before launching. Be honest that **the assistant cannot read the live plan-usage %** — that figure lives only in the human's client UI; this skill can only size to an explicit token target (`budget.total`) and throttle at checkpoints, not auto-pause at "N% of plan used".

3. **Invoke the shipped workflow** (it carries the model pins and budget sizing):

   ```
   Workflow({
     scriptPath: ".claude/skills/foundry-research/workflows/foundry-research.workflow.js",
     args: "<the refined research question>"
   })
   ```

   The workflow returns a structured report (`summary`, `findings[]` with confidence + sources, `caveats`, `openQuestions`, `refuted[]`, and a `stats`/`tiering` block). Surface the report to the human; persist it to `Workbench/` via `write-input` (as a RESEARCH file) when it feeds a PLAN.

## Boundary

A literal `/deep-research` invocation still routes to the **native** harness — this skill cannot intercept it. Reach for `foundry-research` whenever you would otherwise reach for deep-research. To change defaults (tier table, cap sizes), edit `workflows/foundry-research.workflow.js` (`MODEL_BY_ROLE`, the budget-sizing block) and keep `references/model-tiering.md` in step.
