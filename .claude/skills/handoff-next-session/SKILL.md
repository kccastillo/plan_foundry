---
name: handoff-next-session
description: 'Write a session handoff at end-of-session so a cold next session can resume without conversation history. Assesses whether forward work remains, retires the prior handoff for this scope only, and writes a successor from the template - or retires outright when the roadmap is fully discharged. Content contract and filename grammar are defined in templates/handoff-template.md and references/handoff-naming.md. Trigger phrases: "handoff to next session", "write session handoff", "create handoff note", "handoff next session", "handoff <thread> thread", "scoped handoff".'
---

<objective>
Codify the session-handoff pattern as a durable, idempotent skill. Each invocation resolves one target file, retires any existing handoff *for that scope only*, and writes a fresh one from the template populated with current-session observations, so multiple thread-scoped handoffs coexist. The files are bundle-managed: humans refresh by re-running the skill, not by hand-editing.

Filename grammar, the reserved-token rule, and the legacy-form coexistence rules are defined in [references/handoff-naming.md](references/handoff-naming.md) and applied at write-handoff.md Step 0, rather than restated here.
</objective>

<essential_principles>
Content authority belongs to the skill, which replaces the targeted scope's file on every invocation.

Per-scope isolation is the invariant that lets thread handoffs coexist: a different scope's handoff is never read, moved, or overwritten, because retire is strictly per-scope.

The terminal state is assessed before anything is written: **updated-into-successor** when forward work remains, **retired-outright** when the roadmap is fully discharged or the operator requests retire-outright. Step 1 of write-handoff.md states the procedure.

The `## Session roadmap` is the spine and is never empty. The full content contract - which sections exist, which are mandatory, and what each must carry - is defined once in [templates/handoff-template.md](templates/handoff-template.md) and applied at write-handoff.md Step 3.

Self-contained orientation is the point of the artefact. Every surfaced item carries its motivation and reasoning, not a one-line pointer, because the next session reads this cold (ADVICE-018). The gist slug in the filename is a discovery aid and never a substitute for the body.

The `## Audit & execution-readiness gate` (definition in [references/readiness-gate.md](references/readiness-gate.md)) and the machine-readable `## Plan-state baseline`, which `rehydrate-handoff` consumes as the resumption drift input, are computed rather than authored and are never deleted. A single per-PLAN pass at write-handoff.md Step 2.5 produces both sections.

A further computed, never-hand-edited and never-deleted section - `## Carried-claims baseline` - gives a claim in `## Constraints & do-nots` or `## Blocking decisions` a persistent `CLAIM-<id>`, re-checks the claim when the claim names a command, catches a silent drop, and forces an unresolved repeat into `## Blocking decisions` at the escalation threshold. [references/claim-carry-gate.md](references/claim-carry-gate.md) defines the section, and write-handoff.md Step 2.6 produces the block, writing `{}` when no claim is carried.

A PLAN is execution-ready only at `pipeline_phase: checked`. Nothing else reads as READY.

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
- Any prior handoff for the resolved scope was moved to `Retired/`, and no other scope's handoff was touched.
- `payload.terminal_state` is one of `updated` or `retired-outright`.
- When `updated`: the successor exists, `## Session roadmap` and `## Lessons & decision rationale` are present and non-empty, and the remaining contract sections satisfy the template's rules.
- `## Audit & execution-readiness gate`, `## Plan-state baseline` and `## Carried-claims baseline` are present and populated - the gate as a per-PLAN table or "No in-flight PLANs", each baseline as a yaml mapping or `{}`. No NOT-READY plan reads as ready.
- The body is a coherent standalone orientation for a cold reader.
- The skill returns a per-step PASS / SKIPPED / FAIL report including `payload.terminal_state` and `step_2_6`.
</success_criteria>
