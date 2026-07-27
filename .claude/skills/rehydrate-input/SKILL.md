---
name: rehydrate-input
description: "Surface a Workbench input (ADVICE/RESEARCH) or a reusable asset, and record that it was consumed. Two modes, detected automatically from frontmatter: input mode marks an input integrated once the operator confirms it was absorbed into a PLAN; asset mode stamps a helper or reference as consulted by a named PLAN. Idempotent. Trigger phrases: rehydrate input <path>, consume input <path>, absorb input <path> into <plan>, mark input integrated, consume asset <path>, rehydrate asset <path>, mark asset consulted."
---

<objective>
Consume-side companion to write-input. The write side creates ADVICE/RESEARCH files with `integration_status: pending`. The read side (this skill) reads the file, surfaces its content, and (on operator confirmation) flips the status to `integrated` - signalling that the findings are now load-bearing in a downstream PLAN. Retire of the file itself is plan-pipeline's job (auto-fires at PLAN-retire when all gates pass).
</objective>

<essential_principles>
Read-then-confirm: the skill surfaces the input verbatim, then asks the operator "absorbed into <PLAN>? mark integrated?" - flipping integration_status only on explicit confirmation. Auto-flipping on read would create false positives.
Late auto-retire (the section 4F edge case): after flipping `integration_status: integrated`, check the input's `feeds_plan`/`advises_plan` against the current `Retired/` tree. If `lifecycle_mode != reference` AND every consuming PLAN is already retired, auto-retire the input immediately (`git mv` to `Retired/<basename>` + commit). Without this, an input integrated AFTER all consuming PLANs were retired would never be cleaned up - section 4F only fires at PLAN-retire time and won't re-walk past retirements.
Legacy normalisation: `integration_status: open` (predates the `pending`/`integrated` convention) is treated as equivalent to `pending` - read path normalises silently, write path emits `pending` or `integrated`.
Idempotent: invoking on an already-integrated input that was already retired is a no-op (the file is at `Retired/...`, so the skill returns "no Workbench/ input at <path>"). Invoking on an already-integrated input still in Workbench/ surfaces it + re-runs the late-auto-retire gate.
Surface structurally: parse the input's frontmatter + body sections; present them as named blocks so the operator can skim.
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<asset_mode>
Asset mode (AC2c) is triggered when the target file has an `asset_id` field in its frontmatter (as defined by the AD6 schema for helpers and references), rather than an `integration_status` field (ADVICE/RESEARCH inputs). Mode detection is performed by `lib/mode_detect.py:detect_mode()` before any other validation.

**Asset-mode UX (surface-then-confirm-then-stamp-and-write-memory):**
1. Parse frontmatter; call `detect_mode()` to identify asset mode.
2. Validate required asset fields: `asset_id`, `kind` (reference|helper), `last_consulted`, `consulted_by`. Assert `consuming_plan` argument was supplied.
3. Surface the asset content (frontmatter + first body section) to the operator.
4. Prompt: "Mark consulted by <consuming_plan>? [y/N]"
5. On confirmation: write per-asset memory pointer file FIRST (S4 atomicity ordering), then stamp `last_consulted` and append `consuming_plan` to `consulted_by` on the asset frontmatter.
6. Emit pipeline-result with `outcome_subtype: consumed | deferred | warned-skip`.

**`consuming_plan` is required in asset mode.** If not supplied, the skill errors with a diagnostic and returns without stamping.

**Idempotency rule for `consulted_by`:** skip append only if `consuming_plan` is already the MOST RECENT (last) entry. Sequences like A->B->A produce [A, B, A] (legitimate re-consultation); two-in-a-row A->A produces [A] (no duplicate adjacent entries). Cap at 20 entries; FIFO eviction of oldest when cap is exceeded (per D6c).

See [workflows/rehydrate-input.md](workflows/rehydrate-input.md) for the full asset-mode sub-workflow (Step 1.a-asset through A6, and the Step 5-asset payload spec).
</asset_mode>

<preconditions>
- Running in a Claude Code session inside a project with `Workbench/` directory present.
- Caller has identified a specific input file path (this skill does not search/discover inputs).
</preconditions>

<inputs>
- `input_path: string` - relative path to the ADVICE or RESEARCH file (e.g. `Workbench/RESEARCH-002_ab6-clarify-expand-research.md` or `Workbench/ADVICE-20260712-1430-restructure-mandate.md`). Discovery is grammar-agnostic - this skill identifies inputs by frontmatter fields (`integration_status`, `lifecycle_mode`, `asset_id`) not by filename grammar; both the legacy `TYPE-NNN_slug.md` and new `TYPE-YYYYMMDD-hhmm-<slug>.md` filenames are valid. Reads use `encoding='utf-8', errors='replace'`.
- `consuming_plan: string (optional)` - the PLAN whose ideate / Steps is absorbing this input. Used in the confirmation prompt.
</inputs>

**Rehydrate procedure:** See [workflows/rehydrate-input.md](workflows/rehydrate-input.md) for the step-by-step.

<constraints>
- Never move, rename, or delete the input file EXCEPT via the Step-4 late-auto-retire path (gates: integrated + non-reference + all-feeds-retired).
- Never flip `integration_status` without operator confirmation. The skill SURFACES the input and PROMPTS for the flip; the operator's response triggers the mutation.
- Never modify the input's content body -- frontmatter mutation only (integration_status field for inputs; last_consulted + consulted_by for assets).
- Reference-mode inputs (`lifecycle_mode: reference`) still get integration_status flipped on consumption; auto-retire is the exemption, not the integration tracking.
- Step 4 mirrors plan-pipeline section 4F step 7 (auto-retire absorbed inputs). Keep the two paths in sync -- the difference is timing (this skill at integration; section 4F at PLAN-retire).
- **Asset mode: never stamp frontmatter if the memory-file write fails at A4** (S4 atomicity ordering -- clean-retry property). If A4 raises, halt; do NOT proceed to A5 frontmatter mutation.
- **Asset mode: memory directory resolution.** Read `CLAUDE_PROJECT_MEMORY_DIR` environment variable first. If unset, fall back to `~/.claude/projects/D--projects-plan-foundry-dev/memory/` (dev-only hardcoded slug per AC2c D4c -- productionising slug-derivation is out of scope). If the resolved directory does not exist, surface one-line warning and skip memory write (S2 degraded path, normal in CI). Frontmatter stamp still proceeds in the degraded path.
</constraints>

<success_criteria>
- Input content surfaced as named per-section blocks to the operator.
- On operator confirmation: `integration_status: integrated` written to the input's frontmatter (single-field edit).
- Input file body unchanged.
- If Step 4 gates pass: input moved to `Retired/<basename>` with verified post-condition (source absent, destination non-zero).
- Skill returned a `<pipeline-result>` block with structured payload (path, prior_status, new_status, lifecycle_mode, late_auto_retired, will_auto_retire_at_4F).
</success_criteria>
