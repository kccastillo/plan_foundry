---
name: ideate
description: 'Proportionality gate plus an eight-phase ideation cadence. Invoking it first assesses how much of plan_foundry the work needs and offers four rungs - just do it, plan it, audit it, full arc - with a recommendation; no phase runs before the human picks, and only full arc walks the cadence. The cadence shapes a problem into a plan-ready idea and hands it to plan-pipeline - Clarify, Survey, Converge, Spec-Draft, Self-Critique, Spec-Refine, Cross-Spec-Reconcile, Consolidate, with two risk-assessment gates firing between Converge/Spec-Draft and Spec-Draft/Self-Critique. Imposes requirement-before-mechanism discipline and presents options with a stated lean. Runs ONLY in the parent session (interactive). Phases 1-3 work without the bundle; phases 4-8 require plan-foundry-core and produce a reviewed, reconciled PLAN. Override with --output workbench|plain. Trigger phrases: "let''s ideate", "let''s think through X", "help me think about Y", "ideate Z", "what should we do about W", "spec this out", "critique this spec", "ship it", "resume ideate <plan-id>".'
---

## Output mode (soft dependency on plan-foundry-core)

This skill works **with or without** the plan_foundry bundle's audit machinery wired in:

- **With core:** at Converge close, the plan-ready idea is transcribed as a Workbench PLAN via `Skill("write-plan")`. Mid-arc inputs are written via `Skill("write-input")`.
- **Without core:** at Converge close, the plan-ready idea is written as plain markdown in the project root. Mid-arc inputs stay inline in the conversation.
- **Override flag:** `--output workbench` forces Workbench mode (errors if core is absent). `--output plain` forces plain mode regardless.

**Detection logic:** at output time, attempt `Skill("write-plan")` / `Skill("write-input")`. If they resolve, use Workbench mode. If not, fall back to plain.

## Gate 0 - how much of the machinery this needs

**Runs before Phase 1. No phase runs before the Human picks a rung.**

Assess the work against the three questions in
[../_shared/proportionality-gate.md](../_shared/proportionality-gate.md), present
all four rungs with a recommendation, and take the Human's pick. The rungs are
`just do it`, `plan it`, `audit it` and `full arc`. Only `full arc` walks phases
1-8 of this skill. `proportionality-gate.md`'s `## Mechanism per rung` section
states exactly which skill call the agent makes once a lower rung is picked.

The full arc costs most of a day. Say what the recommended rung costs and what it
skips, so the Human sees what they are agreeing to.

<essential_principles>
Run only in the parent session - never inside a subagent (per parent PLAN 202605011400 decision 10). The conversational arc requires Human turn-taking, which subagents cannot offer.

Gate 0 decides whether the phases run at all. Once `full arc` is picked, walk the phases in order. Do not skip and do not merge. Per-phase goals, entry and exit conditions, and anti-patterns are defined once in [workflows/ideate-arc.md](workflows/ideate-arc.md) (phases 1-3) and [workflows/cadence-phases.md](workflows/cadence-phases.md) (phases 4-8).

This skill never writes to disk. Every PLAN write goes through `plan-writer`; every input write goes through `write-input`.

Exit on Human signal. Ideation completion is never inferred.

**Research-bot returns are persisted before the arc advances** (PLAN-AB8). This applies to *any* phase that dispatches research bots - Clarify expand-research, Survey 2.B, Self-Critique, Cross-Spec-Reconcile - not just Survey. The PLAN's `linked_inputs` must reference the new input filenames. Memory-file synthesis does not substitute for the on-disk artefact. Forensic backstop: audit-sufficiency S701 (Lens 9) catches dispatch-without-input when this step is bypassed.

**Survey, Self-Critique and Cross-Spec-Reconcile output uses inverted-pyramid format:** a 1-2 sentence headline, then a tradeoff table carrying a `decision-tier` column (locked / forced / judgement), then prose only for `judgement`-tier or novel items. Never dump prose upfront. The `decision-tier` column is the triage signal - `forced` items are resolved autonomously, `judgement` items go to the Human.

At Converge close, classify every decision touched per decision 15, so the downstream `[Human]` checkpoint surfaces only the real-judgement-call class. Taxonomy definitions: See `../audit-sufficiency/workflows/audit-sufficiency-steps.md` - Step 4.
</essential_principles>

<preconditions>
- Running in the parent session (Human-interactive). Not runnable from a subagent context - there is no channel back to the Human mid-run.
- A user request or trigger that initiates ideation about a problem to be shaped into a plan.
- Optionally: an existing PLAN draft, which is re-ideated in place rather than re-authored.
</preconditions>

<inputs>
- `seed: string` - the user's initial problem statement, question, or topic.
- `existing_plan_path: string (optional)` - when provided, ideation iterates on that PLAN's Objective and Context rather than starting fresh.
</inputs>

<output_schema>
**This skill returns no structured `<pipeline-result>` block** - it is conversational and runs in the parent session, not as a one-shot subagent. Its output is conversational state, plus checkpoint side-effects written by `plan-writer` and `write-input` (see the arc workflows for which checkpoints fire where).

**How `pipeline_phase` advances from `drafting` to `drafted`:** the skill does not flip phase state and the orchestrator does not monitor the conversation. The mechanism is re-invocation. When the Human signals completion with any phrase that triggers `plan-pipeline`'s matcher, the next `plan-pipeline` invocation reads `pipeline_phase: drafting`, confirms the PLAN has its expected sections, flips to `drafted`, and enters the audit loop. Phase advance is durable on disk and orchestrator re-entry is idempotent (decision 18).
</output_schema>

<exception_conditions>
- Existing PLAN at `existing_plan_path` unreadable or malformed - surface it and ask whether to start fresh or fix the file first.
- Human goes silent mid-arc - not an exception. Ideation waits for the next Human turn.

**Subagent-invocation safeguard (structural, not runtime-detected):** there is intentionally NO `ideate-runner` agent file in `.claude/agents/`. The Agent tool's `subagent_type` only accepts agent names that exist on disk, so this skill cannot be dispatched as a subagent - it can only be invoked via `Skill("ideate")` from the parent. The skill does not introspect its execution context; the absence of the agent file *is* the safeguard. **Do not create one.**
</exception_conditions>

## Eight-phase cadence

Phases 1-3 are the original arc and are self-sufficient. Phases 4-8 require the bundle's severity-surface library, plan-template frontmatter, and dispatch routing - all present once `init-plan-foundry` has run.

1. **Clarify** - reframe the problem, establish requirements
2. **Survey** - lay out options with tradeoffs, state a lean
3. **Converge** - lock decisions, classify per decision 15
4. **Spec-Draft** - write full Steps + Verification into the PLAN
5. **Self-Critique** - structured critique gate with severity-surface
6. **Spec-Refine** - revise the spec against critique findings
7. **Cross-Spec-Reconcile** - check conflicts with other in-flight PLANs
8. **Consolidate** - finalise, flip `pipeline_phase: drafted`, hand off

**State tracking:** phases 4-8 track progress via the `ideate_phase` frontmatter enum, which is orthogonal to `pipeline_phase`. `pipeline_phase` stays `drafting` throughout, flipping to `drafted` only at Phase 8. PLAN-AH3 added four gate phases - `risk_assess_idea`, `risk_assess_spec`, and their `*_blocked` counterparts. The two gates fire automatically; the two blocked states halt automation until a human clears them via `"resume ideate <plan-id>"`. Full enum: [references/phase-transitions.md](references/phase-transitions.md).

**Per-phase workflow:** [workflows/cadence-phases.md](workflows/cadence-phases.md). **Routing table:** [references/phase-transitions.md](references/phase-transitions.md).

**Trigger-phrase semantics beyond the obvious:**
- `"spec this out"` - at Converge close, fires Gate A (Risk-Assess-Idea) rather than transitioning straight to Spec-Draft. Gate A makes its own `advance_phase` call once checks pass.
- `"ship it"` - early exit from Spec-Refine to Consolidate, skipping Phase 7.
- `"resume ideate <plan-id>"` - when `ideate_phase` is `risk_assess_idea_blocked` or `risk_assess_spec_blocked`, resume means calling `advance_phase()` on the back-edge (`*_blocked -> *`) and **re-running the gate**, not resuming into the blocked phase.

<constraints>
- Never write to disk directly. Hand off to `plan-writer` for PLAN writes, `write-input` for inputs.
- Never run as a subagent, and never create an agent file that would allow it.
</constraints>

<success_criteria>
- The phases were walked in order, with transitions visible in the conversation.
- The requirement was acknowledged before any mechanism was discussed, and Survey presented at least two options with tradeoffs and a stated lean (or stated explicitly that no alternative exists).
- Decisions touched were classified per decision 15 at Converge close.
- Any input needed was written via `write-input`, and the filenames reached the PLAN's `linked_inputs`.
- `plan-writer` was dispatched at checkpoint moments, so the PLAN is durable on disk before ideation closes.
- The skill ran entirely in the parent session.
</success_criteria>
