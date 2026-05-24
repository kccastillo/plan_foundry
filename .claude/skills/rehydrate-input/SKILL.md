---
name: rehydrate-input
description: Read a Workbench ADVICE or RESEARCH input file, surface its content as orientation context, and flip its `integration_status: pending → integrated` after operator confirms the findings have been absorbed (folded into a PLAN's Steps, Context, or shipped behaviour). Late auto-retire: when an input is integrated AFTER all consuming PLANs (feeds_plan/advises_plan) are already retired AND lifecycle_mode != reference, the skill auto-retires the input immediately — covering the edge case where plan-pipeline §4F at PLAN-retire time already ran and won't re-fire. Tolerant of legacy `integration_status: open` (treated as `pending`). Idempotent: invoking on an already-integrated input is a no-op + structured surface. Trigger phrases: "rehydrate input <path>", "consume input <path>", "absorb input <path> into <plan>", "mark input integrated".
---

<objective>
Consume-side companion to write-input. The write side creates ADVICE/RESEARCH files with `integration_status: pending`. The read side (this skill) reads the file, surfaces its content, and (on operator confirmation) flips the status to `integrated` — signalling that the findings are now load-bearing in a downstream PLAN. Retire of the file itself is plan-pipeline's job (auto-fires at PLAN-retire when all gates pass).
</objective>

<essential_principles>
Read-then-confirm: the skill surfaces the input verbatim, then asks the operator "absorbed into <PLAN>? mark integrated?" — flipping integration_status only on explicit confirmation. Auto-flipping on read would create false positives.
Late auto-retire (the §4F edge case): after flipping `integration_status: integrated`, check the input's `feeds_plan`/`advises_plan` against the current `Retired/` tree. If `lifecycle_mode != reference` AND every consuming PLAN is already retired, auto-retire the input immediately (`git mv` to `Retired/<basename>` + commit). Without this, an input integrated AFTER all consuming PLANs were retired would never be cleaned up — §4F only fires at PLAN-retire time and won't re-walk past retirements.
Legacy normalisation: `integration_status: open` (predates the `pending`/`integrated` convention) is treated as equivalent to `pending` — read path normalises silently, write path emits `pending` or `integrated`.
Idempotent: invoking on an already-integrated input that was already retired is a no-op (the file is at `Retired/...`, so the skill returns "no Workbench/ input at <path>"). Invoking on an already-integrated input still in Workbench/ surfaces it + re-runs the late-auto-retire gate.
Surface structurally: parse the input's frontmatter + body sections; present them as named blocks so the operator can skim.
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a project with `Workbench/` directory present.
- Caller has identified a specific input file path (this skill does not search/discover inputs).
</preconditions>

<inputs>
- `input_path: string` — relative path to the ADVICE or RESEARCH file (e.g. `Workbench/RESEARCH-002_ab6-clarify-expand-research.md`).
- `consuming_plan: string (optional)` — the PLAN whose ideate / Steps is absorbing this input. Used in the confirmation prompt.
</inputs>

**Rehydrate procedure:** See [workflows/rehydrate-input.md](workflows/rehydrate-input.md) for the step-by-step.

<constraints>
- Never move, rename, or delete the input file EXCEPT via the Step-4 late-auto-retire path (gates: integrated + non-reference + all-feeds-retired).
- Never flip `integration_status` without operator confirmation. The skill SURFACES the input and PROMPTS for the flip; the operator's response triggers the mutation.
- Never modify the input's content body — frontmatter mutation only (integration_status field).
- Reference-mode inputs (`lifecycle_mode: reference`) still get integration_status flipped on consumption; auto-retire is the exemption, not the integration tracking.
- Step 4 mirrors plan-pipeline §4F step 7 (auto-retire absorbed inputs). Keep the two paths in sync — the difference is timing (this skill at integration; §4F at PLAN-retire).
</constraints>

<success_criteria>
- Input content surfaced as named per-section blocks to the operator.
- On operator confirmation: `integration_status: integrated` written to the input's frontmatter (single-field edit).
- Input file body unchanged.
- If Step 4 gates pass: input moved to `Retired/<basename>` with verified post-condition (source absent, destination non-zero).
- Skill returned a `<pipeline-result>` block with structured payload (path, prior_status, new_status, lifecycle_mode, late_auto_retired, will_auto_retire_at_4F).
</success_criteria>
