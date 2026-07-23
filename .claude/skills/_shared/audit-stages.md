---
asset_id: help-audit-stages
kind: helper
title: Audit Stages
topic_tags:
- audit
- stages
- ideate
- sufficiency
- plan-safety
description: Three-tier audit stage distinction (Self-Critique, Spec-Refine sufficiency,
  plan-safety) defining the bounded focus of each stage so reviewers do not duplicate
  work.
discoverable_via:
- ideate-clarify
- audit-sufficiency
- audit-haiku-safe
- manual
created: 2026-05-26
last_consulted: '2026-05-26'
consulted_by:
- PLAN-AE1
schema_version: 1
---

# Audit Stages — Three-Tier Focus Distinction

plan-foundry uses three distinct audit stages in sequence. Each stage has a clearly bounded focus; understanding the distinction prevents reviewers from duplicating each other's work or expecting one stage to catch what another is designed to catch.

## Stage 1 — Self-Critique (ideate Phase 5)

**Focus: structural omissions.**

Self-Critique is the spec-author performing a critical re-read of their own draft. It catches:
- Missing sections (e.g. no Verification section, Steps with no acceptance criteria)
- Incomplete coverage (e.g. an edge case the Steps don't address)
- Internal inconsistency (e.g. a Step that contradicts a decision in Context)
- Under-specified acceptance criteria (e.g. a `verify: human` with no framing question)

Self-Critique does NOT check invariant compliance, cross-document correctness, or mechanical step safety — those belong to the stages below. A PLAN can pass Self-Critique and still fail sufficiency-audit. That is the system working correctly, not a regression.

## Stage 2 — audit-sufficiency (conceptual review)

**Focus: invariant violations.**

audit-sufficiency is an outside-reviewer pass (Opus-pinned) that applies seven lenses to the PLAN:
- Assumptions: are they documented and valid?
- Validation path: can the plan actually be verified?
- Test fidelity: do the tests catch the real failure modes?
- Orchestration edge cases: what happens when things go wrong?
- Freshness: are cited sources and decisions still current?
- Meta-design: does the PLAN over-engineer or under-scope?
- Spec-acceptance fidelity: does the PLAN satisfy its stated Objective?

audit-sufficiency does NOT check per-step concreteness, atomicity, or command syntax — that is audit-haiku-safe's job. Its lens is "is this the right thing to build and can it be verified?" not "are the individual steps executable?"

For the full seven-lens procedure, see [../audit-sufficiency/workflows/audit-sufficiency-steps.md](../audit-sufficiency/workflows/audit-sufficiency-steps.md).

## Stage 3 — audit-haiku-safe / plan-safety (mechanical review)

**Focus: mechanical safety violations.**

audit-haiku-safe is a lint-style pass (Sonnet-pinned) that checks each Step against the five plan-safe criteria:
- Concrete: the step specifies exactly what to do, with no ambiguity.
- Atomic: the step does one thing; it is not a compound instruction.
- Unambiguous: the step cannot be misread.
- Safe: the step does not use Bash-only tooling in executor context, does not use destructive flags, and respects the executor capability boundary.
- Testable: the Verification item for this step can actually be checked.

audit-haiku-safe runs AFTER sufficiency passes. There is no benefit to checking step concreteness on an insufficient plan.

For the full mechanical criteria, see [../audit-haiku-safe/../_shared/plan-safe.md](plan-safe.md).

## Why the distinction matters

Each stage catches what the others miss by design:

| Stage | Catches | Does not catch |
|---|---|---|
| Self-Critique | Structural omissions, internal inconsistency | Invariant violations, mechanical step errors |
| audit-sufficiency | Invariant violations, cross-doc correctness, conceptual gaps | Per-step atomicity, command syntax |
| audit-haiku-safe | Per-step concreteness, command safety, format | Conceptual sufficiency, missing sections |

**Productive audit failure is normal.** A PLAN that passes Self-Critique and then fails audit-sufficiency is not evidence of a broken process — it is the multi-stage system doing its job. Each stage has a distinct failure surface; passing one does not guarantee passing the next. See ARCHITECTURE.md §Productive audit failure for the strategic framing.

**Origin:** Canonised in PLAN-AB0 per retrospective finding F5 (Reeve retrospective, 2026-05-16, `Workbench/202605160001_RESEARCH_plan-foundry-retrospective.md`).
