---
name: rehydrate-handoff
description: Discover all handoff files at session start (glob `Workbench/HANDOFF-*.md` — the reserved default plus any thread-scoped `HANDOFF-<scope>.md`) and surface them as structured orientation (what's on main, what's open/queued/paused, conventions, pitfalls, resumption checklist). When more than one handoff exists, lists them (scope + last-modified + title) and asks which to surface/resume; a single handoff surfaces directly. Surface-then-retire per file — after surfacing, prompts the operator "absorbed? retire this handoff? [y/N]" and on confirmation moves it to `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md` (timestamp-suffixed, mirroring handoff-next-session's retire convention). No-op when no handoff is present. Trigger phrases: "rehydrate handoff", "catch me up", "what's pending", "what's the state", "resume session", "list handoffs".
---

<objective>
Consume-side companion to handoff-next-session. The write side (handoff-next-session) ends a session by retiring any prior handoff *for a scope* and writing a fresh one. The read side (this skill) starts a session by discovering all handoff files (`Workbench/HANDOFF-*.md` — the reserved default and any thread-scoped files), surfacing the chosen one as structured orientation, then offering to retire it once the operator confirms its content has been absorbed. Together they form a producer/consumer lifecycle across multiple concurrent threads: write per-scope at end-of-session, discover+select+read+retire per-scope at start-of-session. Filename grammar: see [../handoff-next-session/references/handoff-naming.md](../handoff-next-session/references/handoff-naming.md).
</objective>

<essential_principles>
Surface-then-retire: the skill mutates disk ONLY on explicit operator confirmation after surfacing. Auto-retiring on read would risk losing forensic content if the operator hasn't actually absorbed the handoff; never-retiring leaves stale handoffs accumulating when sessions end without a fresh handoff write.
Surface structurally: parse the handoff's H2 sections and present them as named blocks, not as one prose dump — the consumer (the orchestrator + Human) needs to skim, not read linearly.
Discover all, surface one: glob `Workbench/HANDOFF-*.md`. Zero → graceful no-op. Exactly one → surface it directly. More than one → list them (scope, last-modified, title line) and ask which to surface/resume rather than dumping every body. Retire is per-file on confirm; selecting and retiring one handoff never affects the others.
No-op gracefully: if no handoff is present (first-time invocation in a fresh project, or all already retired), return a structured "nothing to rehydrate" surface, not an error.
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
- Never modify any handoff file's content — surface verbatim, retire (move) only.
- Retire only on explicit operator confirmation; never auto-retire without surfacing first. Retire is per-file — confirming retire on the selected handoff never touches the others.
- Destination path on retire: `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md` (`<scope>` is `NEXT-SESSION` for the reserved default; timestamp-suffixed; mirrors handoff-next-session's retire convention to avoid collisions).
- Never block on missing handoff — first-session projects and fully-retired projects both produce "nothing to rehydrate" + PASS, not an error.
</constraints>

<success_criteria>
- All `Workbench/HANDOFF-*.md` files were discovered; when >1, the operator was shown a selectable list before any body was surfaced.
- The selected handoff's content (if any present) was surfaced as structured per-section blocks to the operator.
- If operator confirmed retire: the selected file moved to `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md` (non-zero size, readable at destination, absent at source); no other handoff was touched.
- If operator deferred retire: file unchanged in `Workbench/`.
- Skill returned a `<pipeline-result>` block with structured payload (including `handoffs_found: [...]`, `selected_scope`, `retired: bool`, and `retired_path: string | null`).
</success_criteria>
