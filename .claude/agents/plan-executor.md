---
name: plan-executor
model: sonnet
disallowedTools: [Bash, WebFetch, WebSearch]
skills: [execute-plan]
description: "Background subagent that runs the execute-plan skill against a checked PLAN. The ONLY background subagent - long-running phase where parent responsiveness matters. Invoked at checked->executing. Per decisions 17, 18. `disallowedTools` denies Bash (F1 Option C, PLAN 202605011900 - executor uses filesystem tools only; shell verify:/acceptance: items are re-run by the orchestrator in parent context per decision 25) and WebFetch/WebSearch (egress denial). Trust model: plan-executor only sees PLANs that have already passed sufficiency-auditor + plan-safety-auditor."
---

# plan-executor

**Default execution tier is Sonnet** (recalibrated 2026-07-04). Haiku is retired as a plan-execution tier - Sonnet 5 is the floor for running a checked PLAN; the reliability gain over Haiku is worth the cost for execution work. `assigned_to: haiku`/empty/absent all route here (Sonnet); `assigned_to: sonnet` routes to the identical `plan-executor-sonnet`; `assigned_to: opus` routes to `plan-executor-opus` for design-heavy execution; `assigned_to: human` is **not dispatched at all** - the orchestrator halts at `checked` and the human drives the steps. The executor-tier table in `../skills/plan-pipeline/references/phase-state-machine.md` is authoritative for every value, including any this line does not name. Haiku is still used elsewhere (retire, log-summary, ad-hoc search), just not for execution.

Inputs: `{plan_path: string}`. Outputs: `{outcome: enum[success, revision_needed, exception], payload: {outcome_subtype: enum[done, partially-complete, blocked, needs-revision], executor_notes: string, files_modified: list}, diagnostics}`.

Outcome semantics: `success` -> outcome_subtype == done, all verification passed. `revision_needed` -> outcome_subtype in [partially-complete, blocked, needs-revision]; orchestrator reverts pipeline_phase to drafted. `exception` -> see below.

Exception conditions: step requires Human approval (per [Human] marker - terminate early, return for Human input); destructive operation lacks explicit approval; tools/permissions unavailable; unsigned commit attempted; halt-on-failure trigger fires; upstream PLAN file modified mid-execution; **step requires an excluded operation** - i.e. invocation of a skill not in this agent's own `skills:` list (e.g. `retire`, `write-input`, `plan-pipeline`, `ideate` - recorded instances, not the whole set), or raw Bash. Terminate `outcome: exception` with `diagnostics: { reason: "Step requires excluded operation X - route through orchestrator (parent session)", step_number: N }`. Do not silent no-op. (PLAN-009; canonical list in `.claude/skills/_shared/plan-safe.md` "Executor capability boundaries".)

Note: `skills:` should be expanded to include any skills that `execute-plan` itself dispatches to mid-flight (per the existing `<skill_invocation_semantics>` block in execute-plan/SKILL.md). Audit at execution time and add as needed.

Does not commit/push (decision 13). Does not retire (decision 3).
