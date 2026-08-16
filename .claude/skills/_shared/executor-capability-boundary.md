---
title: Executor Capability Boundary
description: What a dispatched plan-executor may touch, and why specific skills are orchestrator-only; derived from the executor agent file's own `skills:`/`disallowedTools:`.
created: 2026-08-17
---

# Executor capability boundaries (per PLAN-009)

Steps must not ask `plan-executor` (or its tier variants `plan-executor-sonnet`, `plan-executor-opus`) to perform any of the following. Each has a different mechanism but the rule is uniform: **route through orchestrator (parent session) instead.**

**These four are the recorded instances, not the rule (D8, PLAN-AK1).** The rule is derived from the dispatched agent file's own `skills:` and `disallowedTools:` declarations; a skill absent from the preload list is excluded whether or not it appears below. The derived check is `audit-haiku-safe` Step 4e, and it catches crossings that none of the four sub-clauses covers. Its regression fixtures live with the check itself, so coverage never depends on a particular PLAN continuing to contain the shape.

- **(a) Raw `Bash`.** Denied at the tool-permission layer via `disallowedTools` (F1 Option C, PLAN 202605011900). Use Read/Edit/Write/Glob/Grep filesystem tools, or `python -c` for shell-equivalent operations within the executor's `python` allowance, instead. Audit-haiku-safe blocker if a Step's prose or `verify:`/`acceptance:` shell name `bash`/`sh` directly inside Step bodies (not the Verification section, which runs in parent context).
- **(b) Skills excluded by orchestrator-ownership decisions.** Currently: `retire` (parent PLAN 202605011400 decision 3 - orchestrator owns retire via 4F or, for closeout-style PLANs, via direct parent-session retire). Audit-haiku-safe blocker if a Step says "invoke `retire`" / "use `Skill('retire')`" / "call retire skill" / equivalent.
- **(c) Skills that are parent-session-only by structural convention.** Currently: `ideate` (decision 10 - no agent file exists; cannot be dispatched). Audit-haiku-safe blocker if a Step asks the executor to run ideate; route ideation to parent session.
- **(d) Skills that orchestrate other skills.** Currently: `plan-pipeline` (the orchestrator itself), `write-input` (runs in parent during ideation per decision 12). These run in parent context by design. Audit-haiku-safe blocker if a Step asks the executor to invoke them.

  Skill names in this section are canonical for audit purposes and the mechanical gate matches them literally. A name that has drifted from the live skill makes the gate check for something that does not exist, which passes every Step it was meant to stop. Keep each one exact against `.claude/skills/`, and treat a rename there as a required edit here.

Source of truth for **what the executor can reach**: the dispatched agent file's `skills:` and `disallowedTools:` declarations (`.claude/agents/plan-executor*.md`) - a skill absent from the preload list is excluded whether or not it appears in the four sub-clauses above. This section is the source of truth for **why** each of those four is excluded, and stays the place to record a new orchestrator-ownership decision.

The runtime defence is the executor agents' `Exception conditions` clause - a Step that slips past audit still produces `outcome: exception` rather than silent no-op (PLAN-009 Step 2).

**Audit enforcement:** `audit-haiku-safe` Step 4e resolves the PLAN's `assigned_to` to an executor agent file, reads its `skills:` and `disallowedTools:` declarations, scans each top-level Step in the `## Steps` section, and emits error-severity `EBV001` when a Step in executor scope names an operation those declarations do not permit. See `audit-haiku-safe/workflows/audit-haiku-safe-steps.md` Step 4e for the procedure and `audit-haiku-safe/lib/capability_boundary.py` for the lint module. Add `EBV001` to a PLAN's `audit_acknowledgements` to suppress it; `EBV002` (warn) reports that the agent file could not be read.

## Boundary with dispatch-authorisation.md

This file governs what a *pipeline-dispatched* executor may touch. Discretionary-subagent
tier and concurrency selection - the cheapest-capable-tier ladder, the model-selection
thresholds, the dispatch-count reasoning requirements - is governed separately by
[dispatch-authorisation.md](dispatch-authorisation.md), whose own scope paragraph already
carves pipeline dispatch out of itself.
