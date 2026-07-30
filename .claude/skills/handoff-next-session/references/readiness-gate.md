# Audit & execution-readiness gate - the standing handover checks

Single source of truth for the readiness checks every handoff MUST run, so the
state of in-flight work is unambiguous across a handover between tasks/sessions.
Referenced by [../workflows/write-handoff.md](../workflows/write-handoff.md) Step 2.5
and rendered into the mandatory `## Audit & execution-readiness gate` template
section. This gate is the **one exception** to the handoff's "delete empty sections"
rule: it is always populated - either a per-PLAN table, or the literal line
"No in-flight PLANs." Its whole point is that a NOT-READY plan can never be
mistaken for a ready one at handover.

## Why the gate exists

A drafting pass that writes "all audit blockers addressed by design" is stating a
**self-assessment**, not an audit **verdict**. Only the audit loop
(`sufficiency-auditor` then `plan-safety-auditor`, both returning `success`) can
declare blockers resolved, and it records that on disk in the PLAN's
`audit_state` frontmatter and by advancing `pipeline_phase` to `checked`. The gate
forces the handoff to report the on-disk verdict, never the drafter's claim.

## The four checks (run for every PLAN in `Workbench/`)

For each PLAN file, read its `pipeline_phase`, `audit_state`, `status`,
`ideate_phase` (if present), `assigned_to` / `size`, and body, then record:

### Check 1 - Execution-readiness verdict (READY / NOT-READY)

A PLAN is **execution-ready ONLY at `pipeline_phase: checked`** - both audits
returned `success` (`audit_state.last_stage: plan_safety`, `last_outcome: success`).
Emit exactly one verdict per PLAN:

- ✅ **READY** - `pipeline_phase: checked`. Safe to hand to a plan-executor.
- 🚫 **NOT-READY** - any other phase (`drafting`, `drafted`, `executing`,
  `outcome-verifying`, `complete`). State the phase and what it is waiting on.

This is enforced structurally - plan-pipeline dispatches an executor only on the
`checked -> executing` transition - but the handoff must make it **visible
per-PLAN** so no one hand-dispatches a NOT-READY plan.

### Check 2 - Audit-verdict provenance (verdict vs self-assessment)

If the PLAN body, Executor Notes, or a prior handoff claims blockers are
"resolved / addressed by design / expected to pass" but `audit_state` does NOT
show a passing re-audit for that stage, flag it:

> ⚠️ self-assessed, not audit-confirmed - needs sufficiency-N + plan-safety pass before `checked`.

"I expect it to pass" != `checked`. Never fold a self-assessment into a READY verdict.

### Check 3 - Ideation status (live vs stale vs superseded)

Distinguish a PLAN genuinely mid-ideation from a stale drafting file so a dead
draft cannot masquerade as live ideation. Classify each `drafting`/`drafted` PLAN:

- **live ideation** - an open `ideate` arc (`ideate_phase` present and not
  `complete`), conversational, possibly awaiting RESEARCH/ADVICE inputs. Name the
  phase and any pending inputs.
- **stale-in-drafting** - sits in `drafting` but never completed an ideate arc and
  its content shipped ad-hoc. A supersession/retire candidate, not live work.
- **ideate-complete, awaiting audit** - `ideate_phase: complete`, `drafted`,
  waiting on its first audit.

### Check 4 - Unrecorded scope-collision / supersession reconciliation

When one PLAN's scope has been split or carved into other PLANs (e.g. a
plan-of-plans decomposed into children), the supersession decision MUST be
recorded in the affected PLANs' Context sections (per the decision-naming
convention). If two in-flight PLANs cover overlapping work and no PLAN records the
reconciliation, flag it as a **blocking decision** for the next session:

> ⚠️ scope collision: PLAN-X Track N overlaps PLAN-Y/PLAN-Z; reduce PLAN-X to its unique parts and delegate the overlap, or record the supersession. Running both as-is collides.

An unrecorded reconciliation is exactly the kind of settled-but-unwritten call the
handoff exists to surface.

## Sizing column (ties in the executor t-shirt sizing)

Every NOT-READY-because-not-yet-audited or READY PLAN also carries its **size** so
the next session knows the executor tier a job needs - especially jobs that
**cannot be made haiku-safe**. Read `size:` / `assigned_to:` and render S / M / L /
XL per [../../_shared/plan-safe.md](../../_shared/plan-safe.md) section Executor t-shirt
sizing. A non-haiku-safe PLAN with no recorded size is itself a gate finding
(incompletely sized -> the next session must size it, not block it).

## Rendered shape (goes in the handoff)

A compact table, most-blocking first:

```
| PLAN | Phase | Readiness | Size | Ideation | Flags |
|------|-------|-----------|------|----------|-------|
| AA3  | drafted | 🚫 NOT-READY (awaiting sufficiency-2 + plan-safety) | L (opus) | ideate-complete | self-assessed split not yet re-audited |
| AA0  | drafting | 🚫 NOT-READY | M (sonnet) | live ideation - Survey; 4 pending RESEARCH | - |
| AA2  | drafting | 🚫 NOT-READY | - | stale-in-drafting | scope collision w/ AA3+AA4; supersession unrecorded |
```

When nothing is in flight, the section reads exactly: `No in-flight PLANs.`
