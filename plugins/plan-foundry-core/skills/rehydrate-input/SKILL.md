---
name: rehydrate-input
description: Read a Workbench ADVICE or RESEARCH input file, surface its content as orientation context, and flip its `integration_status: pending → integrated` after operator confirms the findings have been absorbed (folded into a PLAN's Steps, Context, or shipped behaviour). Does NOT auto-retire — retire is plan-pipeline §4F's job at PLAN-retire time (gated on integration_status + lifecycle_mode + all-feeds_plan-retired). Idempotent: invoking on an already-integrated input is a no-op + structured surface. Trigger phrases: "rehydrate input <path>", "consume input <path>", "absorb input <path> into <plan>", "mark input integrated".
---

<objective>
Consume-side companion to write-input. The write side creates ADVICE/RESEARCH files with `integration_status: pending`. The read side (this skill) reads the file, surfaces its content, and (on operator confirmation) flips the status to `integrated` — signalling that the findings are now load-bearing in a downstream PLAN. Retire of the file itself is plan-pipeline's job (auto-fires at PLAN-retire when all gates pass).
</objective>

<essential_principles>
Read-then-confirm: the skill surfaces the input verbatim, then asks the operator "absorbed into <PLAN>? mark integrated?" — flipping integration_status only on explicit confirmation. Auto-flipping on read would create false positives.
Do NOT auto-retire: the skill mutates frontmatter (integration_status) but does NOT move the file. Retire is plan-pipeline §4F's job (gated on integration_status + lifecycle_mode + all-feeds_plan-retired).
Idempotent: invoking on an already-integrated input is a no-op (surface "input X already integrated; no action").
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
- Never move, rename, or delete the input file. Retire is plan-pipeline §4F's responsibility.
- Never flip `integration_status` without operator confirmation. The skill SURFACES the input and PROMPTS for the flip; the operator's response triggers the mutation.
- Never modify the input's content body — frontmatter mutation only (integration_status field).
- Reference-mode inputs (`lifecycle_mode: reference`) still get integration_status flipped on consumption; auto-retire is the exemption, not the integration tracking.
</constraints>

<success_criteria>
- Input content surfaced as named per-section blocks to the operator.
- On operator confirmation: `integration_status: integrated` written to the input's frontmatter (single-field edit).
- Input file body unchanged.
- Skill returned a `<pipeline-result>` block with structured payload (path, prior_status, new_status, lifecycle_mode).
</success_criteria>
