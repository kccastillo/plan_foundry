---
name: handoff-next-session
description: Write a session handoff note at end-of-session capturing what landed, what's open, conventions to know, and a resumption checklist. Retires the prior session's handoff before writing the new one. Output lands at `Workbench/HANDOFF-NEXT-SESSION.md`. Trigger phrases: "handoff to next session", "write session handoff", "create handoff note", "handoff next session".
---

<objective>
Codify the session-handoff pattern as a durable, idempotent skill. Each invocation retires any existing `Workbench/HANDOFF-NEXT-SESSION.md` and writes a fresh one from the template, populated with current-session observations. The file is plugin-managed: humans should not hand-edit it; running the skill replaces it.
</objective>

<essential_principles>
Plugin retains content authority over `Workbench/HANDOFF-NEXT-SESSION.md` — the skill replaces the file on every invocation. Humans refresh by re-running, not hand-editing.
Retire-then-write contract — every invocation first retires any existing handoff (move to `Retired/`), then writes a fresh one. The prior session's handoff is stale once a new session has read it.
Self-contained orientation — the handoff body must enable a cold next-session to resume work without conversation history. Include: what landed, what's open / queued / paused, conventions worth knowing, resumption checklist.
Manual invocation only — no SessionStart hook auto-bootstrap (file-mutating actions on session start are surprising).
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a project with `Workbench/` directory present (i.e., plan-foundry already bootstrapped via `init-foundry`).
</preconditions>

<inputs>
None. The skill operates on the current working directory and conversation context.
</inputs>

**Handoff procedure:** See [workflows/write-handoff.md](workflows/write-handoff.md) for the step-by-step write.

<constraints>
- Always retire the existing `HANDOFF-NEXT-SESSION.md` before writing the new one (or note SKIPPED if absent — first-time invocation).
- Never write multiple handoff files; the location is exactly `Workbench/HANDOFF-NEXT-SESSION.md` (stable filename).
- Never run git operations — the caller commits and pushes the handoff change.
- Never invoke this skill on session start automatically — it's a manual end-of-session action.
</constraints>

<success_criteria>
- Any prior `Workbench/HANDOFF-NEXT-SESSION.md` has been moved to `Retired/`
- A fresh `Workbench/HANDOFF-NEXT-SESSION.md` exists with all template sections populated
- The body is a coherent, standalone orientation for a cold next-session reader
- The skill returns a structured per-step PASS / SKIPPED / FAIL report
</success_criteria>
