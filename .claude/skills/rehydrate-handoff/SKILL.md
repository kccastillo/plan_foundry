---
name: rehydrate-handoff
description: Read Workbench/HANDOFF-NEXT-SESSION.md at session start and surface its content as structured orientation (what's on main, what's open/queued/paused, conventions, pitfalls, resumption checklist). Surface-then-retire — after surfacing, prompts the operator "absorbed? retire handoff? [y/N]" and on confirmation moves the file to `Retired/HANDOFF-NEXT-SESSION-{YYYYMMDDHHMI}.md` (timestamp-suffixed, mirroring handoff-next-session's retire convention). No-op when handoff is absent or empty. Trigger phrases: "rehydrate handoff", "catch me up", "what's pending", "what's the state", "resume session".
---

<objective>
Consume-side companion to handoff-next-session. The write side (handoff-next-session) ends a session by retiring any prior handoff and writing a fresh one. The read side (this skill) starts a session by reading that handoff and surfacing it as structured orientation, then offering to retire the handoff once the operator confirms its content has been absorbed. Together they form a producer/consumer lifecycle: write at end-of-session, read+retire at start-of-session (covers the case where a session ends without a fresh handoff write).
</objective>

<essential_principles>
Surface-then-retire: the skill mutates disk ONLY on explicit operator confirmation after surfacing. Auto-retiring on read would risk losing forensic content if the operator hasn't actually absorbed the handoff; never-retiring leaves stale handoffs accumulating when sessions end without a fresh handoff write.
Surface structurally: parse the handoff's H2 sections and present them as named blocks, not as one prose dump — the consumer (the orchestrator + Human) needs to skim, not read linearly.
No-op gracefully: if HANDOFF is absent (first-time invocation in a fresh project, or already retired), return a structured "nothing to rehydrate" surface, not an error.
Idempotent: invoking twice in one session is fine — first invocation either retires (operator confirmed) or leaves on disk (operator deferred); second invocation finds either the absent state (no-op) or the same content (re-prompt). No per-session "consumed" tracking required.
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
- Never modify `Workbench/HANDOFF-NEXT-SESSION.md` content — surface verbatim, retire (move) only.
- Retire only on explicit operator confirmation; never auto-retire without surfacing first.
- Destination path on retire: `Retired/HANDOFF-NEXT-SESSION-{YYYYMMDDHHMI}.md` (timestamp-suffixed; mirrors handoff-next-session's retire convention to avoid collisions).
- Never block on missing handoff — first-session projects and already-retired sessions both produce "nothing to rehydrate" + PASS, not an error.
</constraints>

<success_criteria>
- HANDOFF content (if present) was surfaced as structured per-section blocks to the operator.
- If operator confirmed retire: file moved to `Retired/HANDOFF-NEXT-SESSION-{YYYYMMDDHHMI}.md` (non-zero size, readable at destination, absent at source).
- If operator deferred retire: file unchanged in `Workbench/`.
- Skill returned a `<pipeline-result>` block with structured payload (including `retired: bool` and `retired_path: string | null`).
</success_criteria>
