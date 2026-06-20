---
name: handoff-next-session
description: Write a session handoff note at end-of-session capturing what landed, what's open, conventions to know, and a resumption checklist. Supports multiple concurrent thread-scoped handoffs — an optional scope writes `Workbench/HANDOFF-<scope>.md` and retires only that scope's prior handoff; unscoped writes the reserved default `Workbench/HANDOFF-NEXT-SESSION.md`. Naming convention in references/handoff-naming.md. Trigger phrases: "handoff to next session", "write session handoff", "create handoff note", "handoff next session", "handoff <thread> thread", "scoped handoff".
---

<objective>
Codify the session-handoff pattern as a durable, idempotent skill. Each invocation resolves a target handoff file from an optional `scope` — `Workbench/HANDOFF-<scope>.md` when scoped, or the reserved default `Workbench/HANDOFF-NEXT-SESSION.md` when not — retires any existing handoff *for that scope only*, and writes a fresh one from the template, populated with current-session observations. Multiple thread-scoped handoffs coexist; writing one never touches another. The files are bundle-managed: humans should not hand-edit them; running the skill replaces the targeted scope's file. Filename grammar: see [references/handoff-naming.md](references/handoff-naming.md).
</objective>

<essential_principles>
Plugin retains content authority over each scope's handoff file — the skill replaces the targeted scope's file on every invocation. Humans refresh by re-running, not hand-editing.
Per-scope retire-then-write contract — every invocation first retires any existing handoff *for the resolved scope only* (move to `Retired/`), then writes a fresh one. The prior session's handoff for that scope is stale once a new session has read it. A different scope's handoff is never read, moved, or overwritten — this is what lets multiple thread handoffs coexist. See [references/handoff-naming.md](references/handoff-naming.md) for the per-scope invariant.
Self-contained orientation — the handoff body must enable a cold next-session to resume work without conversation history. Include: what landed, what's open / queued / paused, conventions worth knowing, resumption checklist.
Manual invocation only — no SessionStart hook auto-bootstrap (file-mutating actions on session start are surprising).
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a project with `Workbench/` directory present (i.e., plan_foundry already bootstrapped via `init-plan-foundry`).
</preconditions>

<inputs>
Optional `scope` (string) — a thread slug naming the workstream this handoff is for. When given, the target file is `Workbench/HANDOFF-<scope>.md` (slug normalised to lowercase-kebab). When absent, the target is the reserved default `Workbench/HANDOFF-NEXT-SESSION.md`. The scope is typically supplied by the trigger phrase ("handoff <thread> thread") or as a skill argument. Otherwise the skill operates on the current working directory and conversation context.
</inputs>

**Handoff procedure:** See [workflows/write-handoff.md](workflows/write-handoff.md) for the step-by-step write.

<constraints>
- Always retire the existing handoff *for the resolved scope* before writing the new one (or note SKIPPED if absent — first-time invocation for that scope).
- One file per scope: `Workbench/HANDOFF-<scope>.md`, or the reserved default `Workbench/HANDOFF-NEXT-SESSION.md` when unscoped. Never read, move, or overwrite a different scope's handoff — per-scope retire only (see references/handoff-naming.md).
- Never run git operations — the caller commits and pushes the handoff change.
- Never invoke this skill on session start automatically — it's a manual end-of-session action.
</constraints>

<success_criteria>
- Any prior handoff *for the resolved scope* has been moved to `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md`; no other scope's handoff was touched
- A fresh `Workbench/HANDOFF-<scope>.md` (or `HANDOFF-NEXT-SESSION.md` when unscoped) exists with all template sections populated
- The body is a coherent, standalone orientation for a cold next-session reader
- The skill returns a structured per-step PASS / SKIPPED / FAIL report
</success_criteria>
