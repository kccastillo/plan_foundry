# Sufficiency-Audit Exemplar

This file is the calibration target for the `audit-sufficiency` skill. The exemplar below records the kind of output an Opus-pass sufficiency audit produces, which differs qualitatively from the mechanical, contract-checking work of the `audit-haiku-safe` skill.

Mechanical plan-safety review (is each step concrete, testable, atomic) and conceptual sufficiency review (are the assumptions sound, what is missing, is this over-engineered) are different operations. Both run at Opus grade today - `plan-safety-auditor` was recalibrated to Opus on 2026-08-03, and `.claude/skills/plan-pipeline/lib/test_model_budget.py` asserts both pins - so the two are separated by what they look at rather than by model tier, and they remain different skills.

## The exemplar audit (what an `audit-sufficiency` pass produces)

### 1. Foundational: framework support unverified

We have designed around load-bearing assumptions that have never been confirmed in the actual Claude Code version in use:

- **Pinned-model agent definitions in `.claude/agents/`** with `model: haiku|sonnet|opus` frontmatter. Does the Agent tool's `subagent_type` parameter accept custom names from `.claude/agents/`?
- **`Skill("...")` calls from inside a subagent.** Does a dispatched subagent inherit the parent's skill registry?
- **`run_in_background: true` semantics.** Does notification handling work in a *skill* context rather than only in chat?

If any assumption is wrong, parts of the architecture need redesign. Verify the assumptions before committing to building.

### 2. Bootstrap delays validation until everything is built

We modify execute-plan, retire, write-bus-plan, and bus-conventions, then create 4 agents and 3 skills, and only then exercise the pipeline at child 4. If a foundational assumption is wrong, we discover the problem after ~10 file mutations. Consider a smaller MVP path: ship `audit-haiku-safe` standalone first, validate pinned-model subagents with one tiny agent, and defer the full orchestrator. <!-- tally-ok: the counts are those of the past review this exemplar records, and changing them would falsify it -->

### 3. Dogfood target is contrived

`note-jot` is synthetic, so building the skill does not prove the pipeline survives real planning friction. The next real PLAN already in the LOG (e.g. `rationalise-claude-md`) would be a more honest test.

### 4. Orchestrator edge cases unspecified

- Missing agent file -> fall back to parent-session invocation, not crash.
- Malformed check-plan output (no `Blockers: N` line) -> halt with "review unparseable", not silently advance.
- Child PLAN fails its own check-plan -> blocks parent advancement, so this case needs explicit handling.

### 5. Memory note staleness

`feedback_retire_push.md` says retire commits and pushes, but after decision 13 retire no longer does. The user-observed invariant holds, because commit-after-retire still happens one layer up, although the literal text of the memory note misleads. Update the note.

### 6. Meta: 16 decisions before any file is written

A future executor (or future Claude) reading the PLAN cold has to absorb 16 decisions before understanding what we are building. Consider a "decisions digest" header - 3-4 bullets - with the full list as an appendix, which shortens onboarding.

## What this exemplar teaches the `audit-sufficiency` skill

Pattern of the review:
1. **Question load-bearing assumptions** - find the parts the design depends on that nobody has verified. Surface them before they become silent failures.
2. **Audit the validation path** - when is the design first tested? If testing comes late, what is at risk when a foundational assumption is wrong?
3. **Interrogate test fidelity** - does the dogfood/test target exercise real friction, or is the target a contrived smoke test?
4. **Surface unhandled edge cases at the orchestration layer** - what if a referenced artefact is missing? What if a sub-output is malformed? What if a downstream component fails?
5. **Find stale references** - anything elsewhere in the codebase / memory / docs that this design contradicts? Update the stale text, or that text will mislead the next reader.
6. **Step back to the meta level** - is the design over-engineered? Could the design be smaller? What is the minimum viable version?

Lenses exercised here: assumption, validation, fidelity, edges, freshness, meta - six of the nine the current procedure applies. This exemplar does not exercise lenses 7-9 (spec-acceptance fidelity, rigour-heuristics-applied, audit-trail durability), so calibrate those against [`../workflows/audit-sufficiency-steps.md`](../workflows/audit-sufficiency-steps.md) rather than against this file.

The `audit-haiku-safe` skill operates on a different lens: per-step concreteness, atomicity, judgement-call detection, line-number accuracy, exact-text completeness. That skill runs *after* sufficiency passes, because Haiku-safety-checking an insufficient plan gains nothing.
