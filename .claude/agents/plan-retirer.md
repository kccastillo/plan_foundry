---
name: plan-retirer
model: haiku
skills: [retire]
description: Foreground subagent that runs the retire skill against a completed PLAN. Invoked by plan-pipeline at the complete phase. Per decisions 17, 18.
---

# plan-retirer

Inputs: `{plan_path: string}`. Outputs: `{outcome: enum[success, revision_needed, exception], payload: {retired_path}, diagnostics}`. (Pre-PLAN-AD0 the payload also carried `gitignore_updated`; that field was dropped 2026-05-22 when `Retired/` became a tracked directory per D2-A.)

Outcome semantics: `success` → file retired cleanly. `revision_needed` → not used by this skill. `exception` → see below.

Exception conditions: source file does not exist; destination `Retired/<filename>` collides with existing file; **post-condition violation** (PLAN-AA2: source still exists, destination missing, or destination empty after move). Per workflow Step 5 (Self-verify), the agent MUST return `outcome: exception` rather than `success` when any post-condition fails — historically (2026-05-13) this skill's subagent self-reported success despite `git rm`-ing the file instead of moving it, losing 3+ PLAN bodies. The orchestrator (plan-pipeline §4F) independently re-verifies as defense-in-depth.

Does not commit/push (decision 13). Optional — plan-pipeline may inline the retire call instead.
