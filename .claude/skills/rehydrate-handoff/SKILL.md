---
name: rehydrate-handoff
description: Read Workbench/HANDOFF-NEXT-SESSION.md at session start and surface its content as structured orientation (what's on main, what's open/queued/paused, conventions, pitfalls, resumption checklist). Read-only — does NOT retire the handoff (retire happens on next handoff-next-session write). No-op when handoff is absent or empty. Trigger phrases: "rehydrate handoff", "catch me up", "what's pending", "what's the state", "resume session".
---

<objective>
Consume-side companion to handoff-next-session. The write side (handoff-next-session) ends a session by retiring any prior handoff and writing a fresh one. The read side (this skill) starts a session by reading that handoff and surfacing it as structured orientation. Together they form a producer/consumer lifecycle: write at end-of-session, read at start-of-session.
</objective>

<essential_principles>
Read-only: the skill does NOT mutate disk. Retire-on-write is handoff-next-session's job; double-retiring would create timestamped archive churn and risk losing forensic content.
Surface structurally: parse the handoff's H2 sections and present them as named blocks, not as one prose dump — the consumer (the orchestrator + Human) needs to skim, not read linearly.
No-op gracefully: if HANDOFF is absent (first-time invocation in a fresh project, or already-rehydrated this session), return a structured "nothing to rehydrate" surface, not an error.
Idempotent: invoking twice in one session is fine — the file is still on disk after the first call (no retire), so the second call returns the same content. The skill does not track per-session "consumed" state.
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a project with `Workbench/` directory present (plan_foundry already bootstrapped via init-plan-foundry).
</preconditions>

<inputs>
None. The skill operates on the current working directory.
</inputs>

**Read procedure:** See [workflows/read-handoff.md](workflows/read-handoff.md) for the step-by-step.

<constraints>
- Never move, rename, or delete `Workbench/HANDOFF-NEXT-SESSION.md`. Retire is handoff-next-session's responsibility (on the next write).
- Never write to disk. The skill's only side-effects are conversational surfaces.
- Never block on missing handoff — first-session projects and already-rehydrated sessions both produce "nothing to rehydrate" + PASS, not an error.
</constraints>

<success_criteria>
- HANDOFF content (if present) was surfaced as structured per-section blocks to the operator.
- HANDOFF file on disk is unchanged (still in Workbench/, still bit-identical).
- Skill returned a `<pipeline-result>` block with structured payload.
</success_criteria>
