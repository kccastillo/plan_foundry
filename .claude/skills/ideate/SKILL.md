---
name: ideate
description: Eight-phase ideation cadence pipeline (Clarify → Survey → Converge → Spec-Draft → Self-Critique → Spec-Refine → Cross-Spec-Reconcile → Consolidate) for shaping a problem into a plan-ready idea and handing it off to plan-pipeline. Phases 1–3 are the existing three-phase arc (core-optional). Phases 4–8 require plan-foundry-core and produce a reviewed, reconciled PLAN file. Imposes "requirement before mechanism" discipline; presents options with a recommendation. Runs ONLY in the parent session (interactive). With plan-foundry-core installed, transcribes plans to Workbench and persists RESEARCH/ADVICE mid-arc; without core, outputs plain markdown (phases 1–3 only). Override with --output workbench|plain. Trigger phrases: "let's ideate", "let's think through X", "help me think about Y", "ideate Z", "what should we do about W", "spec this out", "critique this spec", "ship it", "resume ideate <plan-id>".
---

## Output mode (soft dependency on plan-foundry-core)

This skill works **with or without** the plan_foundry bundle's audit machinery wired in:

- **With core:** At Converge close, the plan-ready idea is transcribed as a Workbench PLAN via `Skill("write-plan")`. Mid-arc RESEARCH/ADVICE inputs are written via `Skill("write-input")`.
- **Without core:** At Converge close, the plan-ready idea is written as plain markdown in the project root. Mid-arc inputs stay inline in the conversation (not persisted to disk).
- **Override flag:** `--output workbench` forces Workbench mode (errors if core not installed). `--output plain` forces plain mode regardless.

**Detection logic:** At output time, attempt `Skill("write-plan")` / `Skill("write-input")`. If they resolve, use Workbench mode. If not, fall back to plain.

<essential_principles>
Run only in the parent session — never inside a subagent (per parent PLAN 202605011400 decision 10). The conversational arc requires Human turn-taking which subagents cannot offer.
Walk three explicit phases in order: Clarify → Survey → Converge. Do not skip; do not merge.
Refuse to discuss mechanism until the requirement is stated and the Human has acknowledged it (Working style: "Requirement before solution").
Present options in full with tradeoffs, then state which one you lean toward and explain why (Working style: "When offering options").
Exit on Human signal — no automatic detection of "ideation complete".
This skill does NOT write the PLAN file itself. The orchestrator (or Human) dispatches `plan-writer` to transcribe at checkpoints.
When a question genuinely needs external data or a strategic decision worth persisting, invoke `write-input` to drop a RESEARCH or ADVICE Workbench file (decision 12).
At Converge close, classify decisions touched per decision 15 (Already-locked / Mechanically-forced / Real-judgement-call) so downstream `[Human]` checkpoints can triage cleanly.
At Phase 2 (Survey): run expand-explode first — brainstorm ≥3 options per cluster plus the "obvious anti-option" (what would be wrong here and why). Then run the research-anchor: auto-dispatch one general-purpose research bot per Real-judgement-call cluster when ≥2 such clusters exist; below that floor, use orchestrator discretion. Research bots use the `_shared/research-prompt-template.md` sub-questions verbatim. See `workflows/cadence-phases.md` § Phase 2 for the full procedure.
Research-bot returns are persisted via `Skill("write-input")` before the orchestrator advances past the dispatching phase (per PLAN-AB8, applies to any phase that dispatches research bots — Clarify expand-research, Survey 2.B, Self-Critique research dispatch, Cross-Spec-Reconcile research dispatch — not just Survey). The PLAN's `linked_inputs` array must reference the new RESEARCH filename(s). Memory-file synthesis does NOT substitute for the on-disk Workbench artefact. Forensic backstop: audit-sufficiency S701 (Lens 9) catches dispatch-without-RESEARCH if this procedural step is bypassed.
Survey, Self-Critique, and Cross-Spec-Reconcile output follows inverted-pyramid format: headline summary (1–2 sentences) first, then a tradeoff table with a `decision-tier` column (locked / forced / judgement), then prose only for `judgement`-tier or novel items. Never dump all prose upfront. The `decision-tier` column is the triage signal — `forced` items are resolved by the orchestrator autonomously; `judgement` items are the ones surfaced to the Human for decision.
</essential_principles>

<preconditions>
- Running in the parent session (Human-interactive). NOT runnable from a subagent context (no channel back to the Human mid-run).
- A user request or trigger that initiates ideation about a problem to be shaped into a plan.
- Optionally: an existing PLAN draft if iterating on prior ideation (will be re-ideated in place rather than re-authored from scratch).
</preconditions>

<inputs>
- `seed: string` — the user's initial problem statement, question, or topic for ideation.
- `existing_plan_path: string (optional)` — if provided, ideation iterates on the existing PLAN's Objective and Context rather than starting fresh.
</inputs>

<output_schema>
**This skill does not return a structured `<pipeline-result>` block** — it is conversational and runs in the parent session, not as a one-shot subagent. Its "output" is:

1. **Conversational state in the parent** — the Clarify→Survey→Converge arc unfolds as a normal Human/Claude exchange.
2. **Checkpoint side-effects** — at clarify-locked and survey-converged moments, the Human (or orchestrator) dispatches `plan-writer` to write or update a PLAN file in `Workbench/`. The skill itself does not write to disk.
3. **Optional Workbench inputs** — when the Clarify or Survey phase surfaces a question requiring external data (RESEARCH) or a persisted decision (ADVICE), invoke `write-input` to land the file. The PLAN's `linked_inputs` array gets the filename when `plan-writer` next writes.
4. **Decision classification at Converge close** — produces a triage of decisions touched during ideation:
   - **Already locked:** Human proposed/affirmed.
   - **Mechanically forced:** no alternative.
   - **Real judgement call:** needs Human answer.
   This classification accompanies the final PLAN write so the subsequent `[Human]` design-review checkpoint can surface only the third class (per decision 15).

**How `pipeline_phase` advances from `drafting` to `drafted`:** the skill itself does NOT flip phase state, and the orchestrator does NOT actively monitor the conversation. The mechanism is re-invocation: when the Human signals ideation is complete (e.g. "ok write it up", "ready to plan it", "let's audit this", or any phrase that triggers `plan-pipeline`'s matcher), the next invocation of `plan-pipeline` reads the PLAN's current `pipeline_phase: drafting`, sees that ideation has produced a drafted PLAN with all expected sections (Objective, Context with decision-classification, Steps, Verification with acceptance: items), flips `pipeline_phase: drafted`, and proceeds into the audit loop. Phase advance is durable on disk and orchestrator re-entry is idempotent (decision 18).
</output_schema>

<exception_conditions>
- Existing PLAN at `existing_plan_path` is unreadable or malformed — surface and ask the Human whether to start fresh or fix the file first.
- Human goes silent across the arc (mid-ideation pause without a returning prompt) — not technically an exception; ideation simply waits for the next Human turn.

**Subagent-invocation safeguard (structural, not detected at runtime):** there is intentionally NO `ideate-runner` agent file in `.claude/agents/`. Because the Agent tool's `subagent_type` parameter only accepts agent names that exist on disk, this skill cannot be dispatched as a subagent — it can only be invoked via `Skill("ideate")` from the parent session. The skill itself does not introspect its execution context (no documented mechanism for that); the absence-of-agent-file is the safeguard.
</exception_conditions>

**Ideation procedure (phases 1–3):** See [workflows/ideate-arc.md](workflows/ideate-arc.md).

## Eight-Phase Cadence (extends three-phase arc)

The ideate skill now encodes an eight-phase design cadence that extends the existing three-phase arc with five new phases (4–8). The cadence produces a reviewed, reconciled PLAN file and hands it off to plan-pipeline at Phase 8.

**Phase summary:**
1. **Clarify** (existing) — reframe the problem, establish requirements
2. **Survey** (existing) — lay out options with tradeoffs, state lean
3. **Converge** (existing) — lock decisions, classify per decision 15
4. **Spec-Draft** (new) — write full Steps + Verification into the PLAN
5. **Self-Critique** (new) — structured critique gate with severity-surface
6. **Spec-Refine** (new) — revise spec to address critique findings
7. **Cross-Spec-Reconcile** (new) — check conflicts with other in-flight PLANs
8. **Consolidate** (new) — finalise, flip `pipeline_phase: drafted`, hand off

**State tracking:** Phases 4–8 track progress via `ideate_phase` enum field in PLAN frontmatter (orthogonal to `pipeline_phase`). During phases 4–8, `pipeline_phase` remains `drafting`. At Phase 8 completion, `pipeline_phase` flips to `drafted` and plan-pipeline takes over.

**Core requirement:** Phases 1–3 are self-sufficient (no bundle dependency). Phases 4–8 require the plan_foundry bundle's severity-surface library, plan-template frontmatter, and dispatch routing — all present once `init-plan-foundry` has run.

**Per-phase workflow:** See [workflows/cadence-phases.md](workflows/cadence-phases.md).

**Phase-transition routing table:** See [references/phase-transitions.md](references/phase-transitions.md).

**New trigger phrases:**
- `"spec this out"` — transition from Converge to Spec-Draft (Phase 3 → 4)
- `"critique this spec"` — trigger Phase 5 (Self-Critique) on current PLAN draft
- `"ship it"` — early-exit from Spec-Refine to Consolidate (skip Phase 7)
- `"resume ideate <plan-id>"` — resume an in-progress ideate session from disk state

<constraints>
- Never propose a mechanism before the requirement is acknowledged. If Clarify hasn't closed, redirect Survey-phase prompting back to Clarify.
- Never present a single option as if it were the only one. If only one option fits, state that explicitly with "no real alternative" and skip Survey.
- Never write to disk yourself. Hand off to `plan-writer` (foreground subagent dispatch) for any PLAN write or update; hand off to `write-input` for RESEARCH/ADVICE writes.
- Never run as a subagent. The structural safeguard is the absence of any agent file in `.claude/agents/` that would dispatch this skill — do not create one. If a future change introduces such an agent, this skill's interactive contract breaks.
- Never silently exit ideation. The Human signals exit; the skill does not infer it.
</constraints>

<success_criteria>
- All three phases (Clarify, Survey, Converge) were walked, in order, with explicit transitions visible in conversation.
- Requirement was stated and acknowledged before any mechanism was discussed.
- At Survey, ≥2 options were presented in full with tradeoffs and a stated lean.
- At Converge, the chosen approach was sharpened to plan-ready specificity.
- Decisions touched during the arc were classified per decision 15 at Converge close.
- If RESEARCH or ADVICE was needed, the appropriate Workbench input was written via `write-input` and the resulting filename is captured for `plan-writer`'s `linked_inputs` array.
- Plan-writer was dispatched at checkpoint moments (clarify-locked, survey-converged) so the PLAN file is durable on disk before ideation closes.
- Skill ran entirely in the parent session.
</success_criteria>
