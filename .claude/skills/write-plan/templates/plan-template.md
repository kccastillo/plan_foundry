---
schema_version: 2        # Required. Orchestrator rejects PLANs without this field. Clean break from v1.
title: "[Plan title]"
type: plan
status: ready
assigned_to: ""
priority: medium
created: YYYY-MM-DD
created_by: ""
created_month: YYYYMM
log_month: YYYYMM
due: ""
repeatable: false
repeat_cadence: ""
linked_decisions: []
linked_inputs: []
blocked_by: ""
rollover_count: 0
triggers_plans: []      # Child PLAN filenames for plan-of-plans; may use "[placeholder] <slug>" entries until children draft (see plan-conventions.md)
closes_thread: ""        # ROADMAP.md thread ID this PLAN fully closes (e.g. "T01"); empty if none
advances_thread: ""      # ROADMAP.md thread ID this PLAN partially progresses; empty if none
parent_plan_of_plans: "" # Path to parent plan-of-plans file if part of a coordinated effort; empty if standalone
pipeline_phase: ""       # plan-pipeline orchestration state; empty for ad-hoc PLANs (see plan-conventions.md)

# Ideate cadence fields (orchestrator-managed — set by ideate skill; never human-edited directly)
ideate_phase: ""             # enum; empty for ad-hoc PLANs not produced via ideate cadence
                             # values: clarify|survey|converge|risk_assess_idea|risk_assess_idea_blocked|spec_draft|risk_assess_spec|risk_assess_spec_blocked|self_critique|spec_refine|cross_spec_reconcile|consolidate|complete|exited_early
ideate_critique_addressed: [] # cumulative list of finding fingerprints (8-char SHA) addressed across self-critique iterations
                               # appended on each spec_refine phase; never replaced
ideate_iteration_count:      # bounded loop counters (orchestrator-incremented; hard limit on self_critique = 5; Gate B limit = 1)
  self_critique: 0           # number of self-critique iterations completed for this PLAN
  spec_refine: 0             # number of spec-refine iterations completed (informational; no hard limit in v1)
  risk_assess_idea: 0        # number of human-initiated Gate A re-runs (after risk_assess_idea_blocked → risk_assess_idea back-edge)
  risk_assess_spec: 0        # number of autonomous Gate B revision attempts (bound: MAX_RISK_ASSESS_SPEC_REVISIONS = 1)
ideate_reconcile_outcome: "" # enum: "passed" | "conflicts-resolved" | "conflicts-pending" | "" (skipped or not yet reached)

# Orthogonal classification (author-populated)
tags: []                 # e.g. [refactor, risky-migration, infra, tooling]
files_touched: []        # List of file paths this PLAN will modify. Populated by author. Used by INDEX dependency graph.
substrate_files: []      # Optional. File paths plan-writer must Read as ground truth before authoring substrate-grammar Steps (SQL DDL, Python imports, enum literals, API attrs). See plan-conventions.md "Substrate Files Declaration".

# Human-authority fields (HUMAN-EDITED ONLY — orchestrator never auto-modifies these)
audit_acknowledgements: []
# Each entry: {fingerprint: "<8-char hex>", rationale: "<why this finding is accepted as-is>", ack_date: "YYYY-MM-DD", ack_iteration: <int>}

audit_disputes: []
# Each entry: {fingerprint: "<8-char hex>", rationale: "<why this finding is contested>", dispute_date: "YYYY-MM-DD", dispute_iteration: <int>}

audit_overrides: []
# Each entry: {fingerprint: "<8-char hex>", rationale: "<why this finding is overridden>", override_date: "YYYY-MM-DD", override_iteration: <int>, scope: "single" | "phase"}

audit_extracted: null
# If non-null: {from_plan_id: "<plan-id>", step_n: <int>, extracted_at: "YYYY-MM-DD"}
# Indicates this PLAN was extracted from a parent PLAN's step. Human-edited.

pipeline_overrides: []
# Each entry: {phase: "<phase>", action: "<override action taken>", rationale: "<why>", override_date: "YYYY-MM-DD"}
# Audit trail of orchestrator-level overrides. Human-edited.

halt_log: []
# Each entry: {timestamp: "YYYY-MM-DDTHH:MM:SSZ", reason: "<why the pipeline halted>", recovery_action_taken: "<what was done>"}
# History of all kanban halts and resolutions. Orchestrator-managed (appended on each halt).

# Orchestrator-managed fields (do not hand-edit; orchestrator writes these)
audit_state:
  sufficiency_iterations: 0
  plan_safety_iterations: 0
  last_stage: none           # none | sufficiency | plan_safety
  last_outcome: none         # none | success | revision_needed | exception
  last_audit_commit: ""      # short SHA of the commit that wrote the most recent audit file; diff anchor for re-audit
  preferred_model_override: ""  # auditor model override (e.g. "sonnet"); empty = default

verification_state:
  state_pass: 0
  state_fail: 0
  acceptance_pass: 0
  acceptance_fail: 0
  human_pending: []                  # subjective verification items awaiting human verdict
  human_verdict: pending             # pending | all_pass | rejected
  human_diagnostics: ""              # free text from human reply when human_verdict: rejected
  human_acknowledged_failures: []    # entries: {check, rationale, ack_date}; shell-fails the human accepted
  failure_logs: {}                   # dict: failure check name → truncated stderr/stdout (≤200 chars)
  human_passed: false                # true if human affirmed pass; short-circuits re-checks
---

## Objective
[One paragraph: what this plan accomplishes and why it matters now.]

## Context
[What prompted this plan. Link to relevant Wiki pages via [[wikilinks]]. Note any constraints or dependencies.]

## Design Decisions Classification
*Populated by `ideate` at Converge close (decision 15 from the plan-pipeline ideation session) when the PLAN is born from an ideation arc. For ad-hoc PLANs not from `ideate`, leave as "n/a — ad-hoc PLAN, not produced via ideate" or list any decisions you'd want a future Human reviewer to know about.*

**Already locked** (Human proposed/affirmed during ideation; require no answer at design-review checkpoint):
- 

**Mechanically forced** (no meaningful alternative; downstream consequence of locked decisions):
- 

**Real judgement calls** (genuinely have alternatives the Human might prefer; surfaced for design-review):
- 

## Steps
[Numbered steps to execute via the `execute-plan` skill. Each step must be independently verifiable.
Mark [Human] for steps that require human action before execution can proceed.
Mark [blocked-on-input] for steps waiting on a RESEARCH or ADVICE file (note which file — will be created via `write-input`).]

1. 
2. 
3. 

## Verification
- [ ] [State check — e.g. "file X exists"]
      `verify: test -f path/to/file`
- [ ] [State check — e.g. "frontmatter status field is 'active'"]
      `verify: grep -q "^status: active" path/to/file`
- [ ] [Acceptance check — exercises the deliverable's behaviour. AT LEAST ONE per PLAN.]
      `acceptance: <shell command that runs the deliverable on a representative input and checks its output>`
- [ ] [Subjective item — surfaced for Human eyeball; no auto-fail]
      `verify: human`

## Recurring Task
*(Remove this section if repeatable: false)*

- **Cadence:** monthly | quarterly | after-event: [description]
- **Next due:** YYYY-MM-DD
- **Trigger condition:** [For event-driven tasks: what event fires the next cycle]

## Executor Notes
*Populated after execution via `execute-plan`. Leave blank.*

**Executed:**
**Outcome:** done | partially-complete | blocked | needs-revision
**What was done:**
**Blockers (if any):**
**Files modified:**

## History
*(For recurring tasks only — RECUR- slugs. Append one row per completed cycle.)*

| Cycle | Completed | Outcome | Notes |
|---|---|---|---|
