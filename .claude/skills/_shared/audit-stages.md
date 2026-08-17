---
title: Audit Stages
description: Three-tier audit stage distinction (Self-Critique, audit-sufficiency,
  plan-safety) defining the bounded focus of each stage so reviewers do not duplicate
  work.
created: 2026-05-26
schema_version: 1
---
# Audit Stages - Three-Tier Focus Distinction

plan-foundry uses three distinct audit stages in sequence. Each stage has a clearly bounded focus, so a reviewer who knows the distinction neither duplicates another stage's work nor expects one stage to catch what another is designed to catch.

## Stage 1 - Self-Critique (ideate Phase 5)

**Focus: structural omissions.**

Self-Critique is the spec-author performing a critical re-read of their own draft. Self-Critique catches:
- Missing sections (e.g. no Verification section, Steps with no acceptance criteria)
- Incomplete coverage (e.g. an edge case the Steps do not address)
- Internal inconsistency (e.g. a Step that contradicts a decision in Context)
- Under-specified acceptance criteria (e.g. a `verify: human` with no framing question)

Self-Critique does NOT check invariant compliance, cross-document correctness, or mechanical step safety - those belong to the stages below. A PLAN can pass Self-Critique and still fail sufficiency-audit. That is the system working correctly, not a regression.

## Stage 2 - audit-sufficiency (conceptual review)

**Focus: invariant violations.**

audit-sufficiency is an outside-reviewer pass (Opus-pinned) that applies nine lenses to the PLAN: 1 Assumptions, 2 Validation path, 3 Test fidelity, 4 Edge cases at the orchestration layer, 5 Freshness, 6 Meta, 7 Spec-acceptance fidelity, 8 Rigour heuristics applied, 9 Audit-trail durability.

audit-sufficiency does NOT check per-step concreteness, atomicity, or command syntax - that is audit-haiku-safe's job. Its lens is "is this the right thing to build and can it be verified?" not "are the individual steps executable?"

For the full lens-by-lens procedure, see [../audit-sufficiency/workflows/audit-sufficiency-steps.md](../audit-sufficiency/workflows/audit-sufficiency-steps.md).

## Stage 3 - audit-haiku-safe / plan-safety (mechanical review)

**Focus: mechanical safety violations.**

audit-haiku-safe is a lint-style pass (Opus-pinned, recalibrated 2026-08-03) that checks each Step against the plan-safe criteria: Concrete, Atomic, Unambiguous, Safe, Testable.

audit-haiku-safe runs AFTER sufficiency passes. There is no benefit to checking step concreteness on an insufficient plan.

For the full mechanical criteria, see [plan-safe.md](plan-safe.md).

## Why the distinction matters

Each stage catches what the others miss by design:

| Stage | Catches | Does not catch |
|---|---|---|
| Self-Critique | Structural omissions, internal inconsistency | Invariant violations, mechanical step errors |
| audit-sufficiency | Invariant violations, cross-doc correctness, conceptual gaps | Per-step atomicity, command syntax |
| audit-haiku-safe | Per-step concreteness, command safety, format | Conceptual sufficiency, missing sections |

**Productive audit failure is normal.** A PLAN that passes Self-Critique and then fails audit-sufficiency is the multi-stage system doing its job rather than evidence of a broken process. Each stage has a distinct failure surface, so passing one does not guarantee passing the next. See the "Productive audit failure" paragraph under ARCHITECTURE.md section "(b) Audit Gates" for the strategic framing.

**Origin:** Canonised in PLAN-AB0 per retrospective finding F5 (Reeve retrospective, 2026-05-16).
