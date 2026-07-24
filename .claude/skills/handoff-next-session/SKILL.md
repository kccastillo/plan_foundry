---
name: handoff-next-session
description: Write a session handoff note at end-of-session capturing the four-part content contract — session roadmap (ordered phases, gates, checkpoints; the never-empty spine), agentic & model plan (per delegated step: model + one-clause rationale), next-handoff trigger (expected/anticipated seam; advisory), and open blocking decisions/constraints. All handoff filenames use the mandatory unified datetime grammar `Workbench/HANDOFF-YYYYMMDD-hhmm-<slug>.md` (datetime + gist slug supplied at write time; colon-free; per PLAN-AF6 D1 + PLAN-AH0 D1); unscoped handoffs compose a datetime+slug name (not the legacy fixed default). Naming convention (including grammar coexistence) in references/handoff-naming.md. Closeout contract: either updated-into-successor (forward work remains) or retired-outright (roadmap fully discharged, no successor written). Trigger phrases: "handoff to next session", "write session handoff", "create handoff note", "handoff next session", "handoff <thread> thread", "scoped handoff".
---

<objective>
Codify the session-handoff pattern as a durable, idempotent skill. Each invocation resolves a target handoff file — all handoffs (scoped or unscoped) use the mandatory unified datetime grammar `Workbench/HANDOFF-YYYYMMDD-hhmm-<slug>.md` (datetime + gist-slug supplied at write time by the agent, colon-free, per PLAN-AF6 D1 + PLAN-AH0 D1). The legacy `HANDOFF-NEXT-SESSION.md` fixed default is **never written** as a new handoff; an unscoped invocation composes a fresh datetime+slug name. The skill retires any existing handoff *for that scope only*, and writes a fresh one from the template, populated with current-session observations. Multiple thread-scoped handoffs coexist; writing one never touches another. The files are bundle-managed: humans should not hand-edit them; running the skill replaces the targeted scope's file. Filename grammar and coexistence rules: see [references/handoff-naming.md](references/handoff-naming.md).
</objective>

<essential_principles>
Plugin retains content authority over each scope's handoff file — the skill replaces the targeted scope's file on every invocation. Humans refresh by re-running, not hand-editing.
Per-scope closeout contract with two terminal states — every invocation first assesses whether forward work remains for the scope. If yes (actionable roadmap items, in-flight PLANs, or queued/paused work): retire any existing handoff for the resolved scope and write a fresh successor (terminal state: updated-into-successor). If no (roadmap fully discharged, nothing forward) or the operator explicitly requests it: retire any existing handoff and write no successor (terminal state: retired-outright). A different scope's handoff is never read, moved, or overwritten — this is what lets multiple thread handoffs coexist. See [references/handoff-naming.md](references/handoff-naming.md) for the per-scope invariant.
Four-part content contract — the handoff body's spine is the `## Session roadmap` (ordered phases, gates, and checkpoints — never an action list alone, never empty). Backed by three companion sections: `## Agentic & model plan` (per delegated roadmap step: foreground vs subagent; model and one-clause rationale for each delegated step); `## Next-handoff trigger` (the expected/anticipated seam to stop-write-clear — explicitly advisory and overridable); and open `## Blocking decisions` / `## Constraints & do-nots`. Together these sections answer not only *what* but *how the session should be run* — agentic delegation, model tiering, and the pre-planned stop point — so a cold next-session can orient and execute without re-litigating those choices.
Self-contained orientation — the `## Session roadmap` (and companion sections) must enable a cold next-session to resume work without conversation history. Each surfaced item MUST be written with full context — the motivation and reasoning behind it, not a one-line pointer (per ADVICE-018 / E4).
Mandatory Audit & Execution-Readiness Gate — every handoff runs the four standing checks (execution-readiness verdict, audit-verdict provenance, ideation status, unrecorded scope-collision/supersession) plus a per-PLAN size, and renders them as a non-deletable gate section so a NOT-READY plan can never be mistaken for a ready one. A PLAN is execution-ready ONLY at `pipeline_phase: checked`. This gate is the one exception to the forward-only "delete empty sections" rule — it is always populated (a per-PLAN table or the literal "No in-flight PLANs"). Full definition: [references/readiness-gate.md](references/readiness-gate.md).
Machine-readable Plan-state baseline — the same per-PLAN pass also writes a `## Plan-state baseline` fenced-yaml block into the handoff, recording each in-flight PLAN's `pipeline_phase`, `status`, and `last_executor_outcome` as a machine-readable mapping. This block is consumed by `rehydrate-handoff` Step 0 (via `.claude/skills/_shared/resume_preflight.py`) as the `expected_plan_states` input for the resumption drift preflight. Like the readiness gate, this section is never deleted (written as `{}` when no in-flight PLANs exist).
Manual invocation only — no SessionStart hook auto-bootstrap (file-mutating actions on session start are surprising).
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a project with `Workbench/` directory present (i.e., plan_foundry already bootstrapped via `init-plan-foundry`).
</preconditions>

<inputs>
Optional `scope` (string) — a thread slug naming the workstream this handoff is for. The scope is typically supplied by the trigger phrase ("handoff <thread> thread") or as a skill argument. Whether or not a scope is given, the target filename always uses the mandatory datetime+slug grammar `Workbench/HANDOFF-YYYYMMDD-hhmm-<gist-slug>.md`. The scope is preserved in the body banner (per write-handoff.md Step 4), not in the filename. The reserved token `NEXT-SESSION` must not be used as a scope or gist slug. The skill operates on the current working directory and conversation context.
</inputs>

**Handoff procedure:** See [workflows/write-handoff.md](workflows/write-handoff.md) for the step-by-step write.

<constraints>
- Always retire the existing handoff *for the resolved scope* before writing the new one (or note SKIPPED if absent — first-time invocation for that scope).
- One file per invocation: `Workbench/HANDOFF-YYYYMMDD-hhmm-<gist-slug>.md` — the datetime+slug grammar is mandatory for all new writes (per PLAN-AH0 D1). The legacy `HANDOFF-NEXT-SESSION.md` is never written; an unscoped invocation composes a datetime+slug name. The scope (when present) is preserved in the body banner. Never read, move, or overwrite a different scope's handoff — per-scope retire only (see references/handoff-naming.md).
- Never run git operations — the caller commits and pushes the handoff change. The handoff MUST be committed and pushed before any pull request is created or updated — the PR treats a pushed, current durable state as its precondition. (Handoff-before-PR ordering rule; see `## Handoff-before-PR ordering` in operating-rules.md.)
- Each surfaced handoff item (next-step, blocking decision) MUST be written with **full context**: the motivation and reasoning (the *why*) behind each item, not a one-line pointer — so the next session can act on it cold without conversation history. The gist-slug filename and any PR narrative are discovery aids only, never substitutes for the exploded handoff body. (Per ADVICE-018 / E4.)
- Never invoke this skill on session start automatically — it's a manual end-of-session action.
</constraints>

<success_criteria>
- Any prior handoff *for the resolved scope* has been moved to `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md`; no other scope's handoff was touched
- Closeout terminal state resolved to one of two values: updated-into-successor (a fresh `Workbench/HANDOFF-YYYYMMDD-hhmm-<gist-slug>.md` exists with all four-part contract sections populated) or retired-outright (no successor written; reported in `payload.terminal_state`)
- When terminal state is updated-into-successor: the `## Session roadmap` is present and non-empty (never empty; this is the spine); `## Agentic & model plan` and `## Next-handoff trigger` are present unless explicitly inapplicable (all foreground / no meaningful stop point)
- The mandatory `## Audit & execution-readiness gate` section is present and populated (per-PLAN table or "No in-flight PLANs") — the four standing checks ran for every `Workbench/` PLAN and no NOT-READY plan reads as ready
- The body is a coherent, standalone orientation for a cold next-session reader
- The skill returns a structured per-step PASS / SKIPPED / FAIL report, including `payload.terminal_state`
</success_criteria>
