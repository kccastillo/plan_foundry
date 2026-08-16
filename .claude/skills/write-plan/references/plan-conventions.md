---
title: Plan File Conventions
description: PLAN/INPUT file conventions - naming, identity, status, lifecycle phase, frontmatter-field schema, and the holding-PLAN authoring convention.
created: 2026-05-18
---

# Plan File Conventions

This file is the canonical source for PLAN/INPUT file conventions: naming, identity, status, lifecycle phase, frontmatter-field schema, and the holding-PLAN authoring convention. AGENT_RULES.md and CLAUDE.md should point here rather than duplicate.

## File Naming

`{YYYYMMDDHHMI}_{TYPE}_{slug}.md` - see `references/naming-convention.md` for full pattern, type tokens, and examples.

## PLAN Identity Policy (2026-05-16, per PLAN-AA0 plan-of-plans)

**D1 Active-Unique-LOG-History.** PLAN IDs are unique within the *currently active set only*. The LOG carries history. Slug is the durable cross-generation discriminator across ID re-uses.

**D2 AA0-ZZ9 active scheme.** New PLAN IDs are allocated in `PLAN-[A-Z][A-Z][0-9]` (6,760 lexicographic slots: AA0 -> AA9 -> AB0 -> ... -> ZZ9). Strict-sequential issuance per the AA1 allocator. Burned IDs leave permanent gaps; reissue is forbidden. At ZZ9 the scheme will need extension - that is the next generation's problem (>6,760 PLANs at the foundry's rate is decades away).

**D2a Burn-By-Tombstone.** An ID can be retired without ever owning a PLAN file - the work it named was reverted, or the ID was drawn and abandoned. Record the burn as a file, never as prose: `Retired/PLAN-<ID>_BURNED_<slug>.md`, carrying the reason and pointing at wherever the decision was made. The allocator derives its used set from filenames, so the tombstone is what enforces D2; a burn recorded only in prose is invisible to it and the ID gets handed out again. That happened on 2026-07-31, when `AI6` was offered after being burned the previous day, and was caught only because the operator recognised the number. `next_id.py --explain` labels a tombstoned ID `Burned` rather than `Retired`, so the table says why the ID is skipped.

**D3 Numeric-Historical-Frozen.** Old `PLAN-NNN` IDs in `Retired/` are historical-only and frozen. They are not migrated. Reference them exactly as historically recorded. When a `PLAN-NNN` collides with an AA-form ID's predecessor (e.g. PLAN-031 renamed to PLAN-AA9), reference the active PLAN by its AA-form ID and disambiguate by appending "(formerly PLAN-NNN)" in narrative prose.

**Inputs carry no allocated ID.** A new input is `INPUT-YYYYMMDD-hhmm-<slug>.md`, so there is nothing to allocate and nothing to collide. The grandfathered `ADVICE-NNN` and `RESEARCH-NNN` spaces stay numeric and stay readable; `next_id.py` keeps both tokens for that space alone (PLAN-AJ3 D5).

**Allocator.** `.claude/skills/write-plan/scripts/next_id.py` is the canonical allocator. Source of truth: the filesystem, and only the filesystem - Workbench/ + Retired/ (recursive) are authoritative for "used IDs". No cache. Read-only contract - not idempotent across calls. See PLAN-AA1's design lineage (research-validated leans across event-sourcing canonical pattern, Postgres `nextval` template, Jira/Linear/GitHub ID conventions).

**Anti-pattern (per AA4 TESTREPORT-002 finding).** "PLAN shipped inline in a PR but never walked through plan-pipeline" leaves the PLAN's `status: ready` while the deliverables are in tree. Future `audit-foundry.py` extensions may flag this by cross-checking `status: ready` PLANs' `files_touched` against recent commit changesets. The cure is to walk plan-pipeline against the PLAN retroactively (mark status: done, populate Executor Notes), then retire.

## Recurring PLAN Prefix

Slugs start with `RECUR-`. One persistent file per recurring task; each cycle appends to `## History`.

## File Types

`PLAN` | `INPUT`. `RESEARCH` and `ADVICE` are grandfathered read-only tokens.

## PLAN Status Lifecycle

Frontmatter `status` field:
```
ready -> in-progress -> done | partially-complete | blocked | needs-revision
```

- `ready` - transcribed, not yet started. Set on creation.
- `in-progress` - execute-plan skill has started. Set when execution begins.
- `done` - all verification criteria pass. Terminal.
- `partially-complete` - some steps done, others blocked or deferred. Terminal for this cycle.
- `blocked` - cannot proceed; `blocked_by` holds the reason. Cleared automatically by `write-input` when the resolving input lands, or manually by the Human. Non-terminal until unblocked.
- `needs-revision` - plan itself is faulty; return to Sonnet. Non-terminal.

PLAN frontmatter is the sole canonical surface for PLAN status.

## PLAN Pipeline Phase

Frontmatter `pipeline_phase` field, orthogonal to `status`. Tracks orchestration state for PLANs managed by the `plan-pipeline` skill. The phase enum and its ad-hoc default (absent/empty treated as `drafted`) are canonical in `.claude/skills/plan-pipeline/references/phase-state-machine.md` - see that file for the values and what each means.

**`target_phase` at PLAN creation.** `write-plan`'s `target_phase` input is the mechanism behind two of `proportionality-gate.md`'s rungs (see that file's `## Mechanism per rung` section). `ideate`'s `audit it` rung is the caller that sets `target_phase: drafted` explicitly, because it hands straight to `plan-pipeline` and wants the audit loop entered without a second read of the file. `plan it` deliberately calls `write-plan` with no `target_phase` at all, relying on phase-state-machine.md's ad-hoc default to resolve to `drafted` if the PLAN is ever later run through `plan-pipeline` - so both PLAN-producing rungs end up at the same effective phase, one by setting it and one by the default.

## PLAN Input Linkage

Frontmatter `linked_inputs: []` contains one array of input filenames, live and grandfathered alike. No separate `linked_research` / `linked_advice` / `requires_opus` / `requires_research` fields - `status: blocked` + `blocked_by` carries the "needs input before running" signal.

## Parent plan-of-plans linkage

PLANs may reference a coordinating parent via one optional frontmatter field:

- `parent_plan_of_plans: <path>` - this PLAN is part of a coordinated effort tracked by another file. On closure, `execute-plan` updates the parent plan-of-plans tracking section per that file's schema.

Set this on PLAN creation (in `write-plan`). Empty string means no linkage.

## Push Policy

**Optional frontmatter field: `push_policy: auto | manual`**

Controls whether the plan-pipeline orchestrator pushes to remote after each milestone commit, or commits locally and surfaces a `<push_status>` message for the operator to push manually.

```yaml
push_policy: manual   # or "auto"
```

**Resolution order (first match wins; simplified by PLAN-AC4 D6):**
1. PLAN frontmatter `push_policy` field - per-PLAN override.
2. Hard-coded default: `manual`.

**Values:**
- `auto` - push after every milestone commit (original behaviour).
- `manual` - commit only; emit `<push_status>commit landed locally; push manual per push_policy. Run \`git push\` when ready.</push_status>` to the operator.

**Project default:** `manual`. Set `push_policy: auto` per-PLAN for individual plans that need immediate remote propagation.

**Implementation:** `.claude/skills/_shared/push_policy.py` - function `get_push_policy(plan_path, repo_root=None) -> str`.

## Orchestrator-managed frontmatter fields

Frontmatter fields managed exclusively by the plan-pipeline orchestrator - executors and subagents MUST NOT write them directly (per T14, 2026-05-13). The full field list and shape (`pipeline_phase`, `audit_state`, `last_executor_outcome`, `verification_state`, `total_loop_attempts`, `step_remaps`, and others) is canonical in `.claude/skills/plan-pipeline/references/phase-state-machine.md`'s frontmatter mutation cheat sheet - see that file for what each field carries.

## Substrate Files Declaration

**Optional frontmatter field: `substrate_files: []`**

An opt-in declaration of file paths that plan-writer MUST `Read` as ground truth before authoring any Steps that emit SQL DDL/queries, ORM operations, Python imports from existing modules, or string-literal values of constrained-type (enum) fields.

```yaml
substrate_files:
  - path/to/schema.py
  - path/to/enums.py
```

**Purpose:** prevents hallucinated column names, enum values, and private API attributes - the H5/H9/H11 hiccup class (2026-05-16 retrospective). When `substrate_files` is non-empty, plan-writer reads each listed path before any Write/Edit that touches a substrate-grammar construct; the read must appear in the writer's reasoning trace. audit-haiku-safe lints substrate fidelity post-hoc (grep-based) and emits `error`-severity findings for any named entity in Steps that has zero matches across the declared substrate files.

**When to set:** any PLAN whose Steps reference SQL table/column names, Python symbols imported from existing modules, enum string-literal values, or third-party API attributes. Leave empty (`substrate_files: []`) for PLANs with no such references - the lint heuristic-detects them and emits a `warn`-severity advisory if it finds substrate-grammar constructs despite the empty declaration.

**Fidelity lint scope (four failure classes from H5/H9/H11):**
1. SQL column refs (`table.column` pattern)
2. Python imports (`from X import Y`)
3. Enum string-literal values (string literal adjacent to a `*.kind`, `*.status`, or `Enum` class reference)
4. Public-API surface attributes (`_`-prefixed attribute on a third-party module signals private access)

See `.claude/skills/audit-haiku-safe/workflows/audit-haiku-safe-steps.md` (Step 4a: Substrate fidelity check) and `.claude/skills/write-plan/workflows/write-plan.md` (Step 0: Substrate-verification preflight) for the enforcement sites.

## Platform portability (per PLAN-AB3)

Every `verify:` and `acceptance:` item in a PLAN's Verification section MUST be portable, with platform-specific commands annotated `# platform: posix` or `# platform: windows` on the same line. See `.claude/skills/_shared/platform-portability.md` for the CI baseline, the forbidden-pattern table with rationale and portable alternatives, and audit enforcement.

## Preliminary holding-PLAN pattern

A **preliminary holding-PLAN** (also called a holding-PLAN) is a PLAN file created before ideation has begun - used to park inputs and frame the open questions that ideation will eventually answer.

**Frontmatter signature:**
- `pipeline_phase: drafting` - ideation not yet started; plan-pipeline will not auto-advance past drafting until explicitly invoked.
- `ideate_phase: not-started` - distinguishes a holding-PLAN from a PLAN whose ideation is in-flight.
- `linked_inputs: [...]` - pre-populated with the input files that motivated the holding-PLAN. These are the primary inputs ideation will consume.

**Body structure (minimal):**
- **Objective** - one paragraph stating what decision or work the holding-PLAN is meant to produce.
- **Context** *(optional)* - background for the reader; include when the motivation is not self-evident from the linked inputs.
- **Key Questions** - the open questions that Phase 1 (Clarify) will treat as its agenda when plan-pipeline runs against this PLAN.
- **Re-prosecution Checklist** *(optional)* - a checklist of prior art, anti-patterns, or commitments the spec-author must check before locking any answer.

**Lifecycle:** When `plan-pipeline` is invoked against a holding-PLAN, it detects `pipeline_phase: drafting` and `ideate_phase: not-started` and enters Phase 1 (Clarify) of the ideate cadence, using the Key Questions section as the Clarify agenda. No dedicated entry point or separate skill is needed - existing `write-plan` and plan-pipeline handle holding-PLANs implicitly.

**Use case:** surfaces a durable, version-controlled destination for inputs that are not yet ready to walk the full ideate cadence. Allows a batch of inputs to be triaged into action-ready holding-PLANs before committing to spec work on any one of them.


**Note on schema enforcement:** holding-PLANs vary in shape. The pattern is documented here but audit-haiku-safe does not reject deviations - the pattern is a convention, not a schema rule.

> Spec-Draft rigour heuristics (H2/H4/H8) now live in `.claude/skills/_shared/spec-rigour-heuristics.md`.

## Ideate Cadence Requirements

The four retrospective findings (F1, F2, F7, F8) embedded in the ideate cadence, their source of truth, and their structural tests are documented in `.claude/skills/ideate/workflows/cadence-phases.md`.

## PLAN sizing

A single PLAN's top-level Step-count ceiling, the decomposition options when it is exceeded, and the `audit_acknowledgements: [PSZ001]` exception path are documented in `.claude/skills/_shared/plan-safe.md`, under executor t-shirt sizing and the PSZ001 advisory.

> The plan-of-plans sketch-first authoring convention now lives in `.claude/skills/write-plan/references/plan-of-plans-authoring.md`.
