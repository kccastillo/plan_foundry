---
name: handoff-next-session
description: 'Write a session handoff at end-of-session so a cold next session can resume without conversation history. Assesses whether forward work remains, retires the prior handoff for this scope only, and writes a successor from the template - or retires outright when the roadmap is fully discharged. Content contract and filename grammar are defined in templates/handoff-template.md and references/handoff-naming.md. Trigger phrases: "handoff to next session", "write session handoff", "create handoff note", "handoff next session", "handoff <thread> thread", "scoped handoff".'
---

<objective>
Codify the session-handoff pattern as a durable, idempotent skill. Each invocation resolves one target file, retires any existing handoff *for that scope only*, and writes a fresh one from the template populated with current-session observations. Multiple thread-scoped handoffs coexist. The files are bundle-managed: humans refresh by re-running the skill, not by hand-editing.

Filename grammar, the reserved-token rule, and the legacy-form coexistence rules live in [references/handoff-naming.md](references/handoff-naming.md) and are applied at write-handoff.md Step 0. They are not restated here.
</objective>

<essential_principles>
Content authority sits with the skill - it replaces the targeted scope's file on every invocation.

Per-scope isolation is the invariant that lets thread handoffs coexist: a different scope's handoff is never read, moved, or overwritten. Retire is strictly per-scope.

Two terminal states, assessed before anything is written: **updated-into-successor** when forward work remains, **retired-outright** when the roadmap is fully discharged or the operator asks for it. Procedure at write-handoff.md Step 1.

The `## Session roadmap` is the spine and is never empty. The full content contract - which sections exist, which are mandatory, and what each must carry - is defined once in [templates/handoff-template.md](templates/handoff-template.md) and applied at write-handoff.md Step 3.

Self-contained orientation is the point of the artefact. Every surfaced item carries its motivation and reasoning, not a one-line pointer, because the next session reads this cold (ADVICE-018). The gist slug in the filename is a discovery aid and never a substitute for the body.

Two sections are computed rather than authored and are never deleted: the `## Audit & execution-readiness gate` (definition in [references/readiness-gate.md](references/readiness-gate.md)) and the machine-readable `## Plan-state baseline`, which `rehydrate-handoff` consumes as the resumption drift input. Both are produced by a single per-PLAN pass at write-handoff.md Step 2.5.

A PLAN is execution-ready ONLY at `pipeline_phase: checked`. Nothing else reads as READY.

Manual invocation only - no SessionStart auto-bootstrap, because file-mutating actions on session start are surprising.

Wire format: end the response with a literal `<pipeline-result>` JSON code fence, per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a project with `Workbench/` present (plan_foundry bootstrapped via `init-plan-foundry`).
</preconditions>

<inputs>
Optional `scope` (string) - a thread slug naming the workstream, supplied by the trigger phrase ("handoff <thread> thread") or as a skill argument. The scope is preserved in the body banner, not in the filename. Otherwise the skill operates on the current working directory and conversation context.
</inputs>

**Handoff procedure:** See [workflows/write-handoff.md](workflows/write-handoff.md) for the step-by-step write.

<constraints>
- **Never run git operations.** The caller commits and pushes. The handoff must be committed and pushed before any pull request is created or updated - see `## Handoff-before-PR ordering` in operating-rules.md.
- **Never invoke automatically on session start.** This is a manual end-of-session action.
</constraints>

<success_criteria>
- Any prior handoff for the resolved scope was moved to `Retired/`; no other scope's handoff was touched.
- `payload.terminal_state` is one of `updated` or `retired-outright`.
- When `updated`: the successor exists, `## Session roadmap` and `## Lessons & decision rationale` are present and non-empty, and the remaining contract sections satisfy the template's rules.
- `## Audit & execution-readiness gate` and `## Plan-state baseline` are present and populated - the gate as a per-PLAN table or "No in-flight PLANs", the baseline as a yaml mapping or `{}`. No NOT-READY plan reads as ready.
- The body is a coherent standalone orientation for a cold reader.
- The skill returns a per-step PASS / SKIPPED / FAIL report including `payload.terminal_state`.
</success_criteria>
