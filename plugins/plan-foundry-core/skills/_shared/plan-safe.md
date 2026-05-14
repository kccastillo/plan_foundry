# Plan-safe definition

A plan is "plan-safe" (executable mechanically, without design work) when every step is:
- **Concrete:** specific file paths, exact command syntax, no "likely" or "probably"
- **Unambiguous:** no judgment calls; the executor runs the steps, not redesigns them
- **Atomic:** one step at a time; clear success/failure condition
- **Safe:** no destructive operations without explicit Human approval; no bypasses (--no-verify, --force)
- **Testable:** verification criteria are independent and checkable

Example of plan-safe: "Read SKILL.md from `.claude/skills/retire/SKILL.md`. Verify frontmatter `name: retire`. Extract `<process>` block (lines 43–68) to `workflows/retire-steps.md`. Commit with message 'chore: trim retire SKILL.md'"

Example of NOT plan-safe: "Audit SKILL.md and extract any residual content. Use your judgment." (ambiguous, requires interpretation)

**When authoring plans:** refer to [.claude/skills/execute-plan/workflows/execute-steps.md](../execute-plan/workflows/execute-steps.md) for the execution protocol and [.claude/skills/execute-plan/references/log-rules.md](../execute-plan/references/log-rules.md) for the LOG contract, and ensure every step passes this definition.

**Mechanical Steps must be filesystem-tool-shaped (F1 Option C, PLAN 202605011900).** Express mechanical Steps as Read/Write/Edit/Glob/Grep operations, not shell-shaped (`mkdir`, `cp`, `echo > file`, `cat file`, `sed -i`, `grep ... file`). The plan-executor agents disallow Bash structurally, so shell-shaped Steps will fail at runtime. Shell commands belong in the Verification section as `verify:`/`acceptance:` items — those run in the orchestrator's outcome-verifying phase (parent context, allowlist works correctly).

## Executor capability boundaries (per PLAN-009)

Steps must not ask `plan-executor` (or its tier variants `plan-executor-sonnet`, `plan-executor-opus`) to perform any of the following. Each has a different mechanism but the rule is uniform: **route through orchestrator (parent session) instead.**

- **(a) Raw `Bash`.** Denied at the tool-permission layer via `disallowedTools` (F1 Option C, PLAN 202605011900). Use Read/Edit/Write/Glob/Grep filesystem tools, or `python -c` for shell-equivalent operations within the executor's `python` allowance, instead. Audit-haiku-safe blocker if a Step's prose or `verify:`/`acceptance:` shell name `bash`/`sh` directly inside Step bodies (not the Verification section, which runs in parent context).
- **(b) Skills excluded by orchestrator-ownership decisions.** Currently: `retire` (parent PLAN 202605011400 decision 3 — orchestrator owns retire via 4F or, for closeout-style PLANs, via direct parent-session retire). Audit-haiku-safe blocker if a Step says "invoke `retire`" / "use `Skill('retire')`" / "call retire skill" / equivalent.
- **(c) Skills that are parent-session-only by structural convention.** Currently: `ideate` (decision 10 — no agent file exists; cannot be dispatched). Audit-haiku-safe blocker if a Step asks the executor to run ideate; route ideation to parent session.
- **(d) Skills that orchestrate other skills.** Currently: `plan-pipeline` (the orchestrator itself), `write-bus-input` (runs in parent during ideation per decision 12). These run in parent context by design. Audit-haiku-safe blocker if a Step asks the executor to invoke them.

Source of truth for the per-skill list: this section. Source of truth for tool-permission exclusions: `.claude/agents/plan-executor.md` `disallowedTools`. When the lists drift, **this section is canonical for audit purposes**; update it whenever an exclusion changes.

The runtime defence is the executor agents' `Exception conditions` clause — a Step that slips past audit still produces `outcome: exception` rather than silent no-op (PLAN-009 Step 2).

## Verification format requirement (per PLAN 202605011400 decision 25)

Every PLAN's `## Verification` section item must be shell-runnable, with one of the following annotations on the line directly below the prose checkbox:

- `verify: <shell command>` — state assertion (file exists, grep matches, command exit code). Exit 0 = pass.
- `acceptance: <shell command>` — spec-level behavioural check that exercises the deliverable. Exit 0 = pass. **Every PLAN must include at least one `acceptance:` item.**
- `verify: human` — genuinely subjective item; surfaced for Human eyeball but does not auto-fail.

The orchestrator runs all `verify:` and `acceptance:` commands as a separate outcome-verification phase (after plan-executor returns success, before advancing to complete). Failures override the executor's self-reported success.

### skills-as-deliverable carve-out (per PLAN 202605011900 F3)

PLANs whose deliverable is a Claude skill (or other artefact not invokable from a shell) MAY satisfy the at-least-one-`acceptance:` requirement via an artefact-property check (frontmatter parses, workflow content present, gate-clauses present) PLUS a `verify: human` for the actual invocation behaviour. The skills-as-deliverable carve-out keeps the mechanical gate active without forcing a fictional shell-acceptance command. Claude skills are invoked by Claude, not by a shell; a true behavioural acceptance command cannot exist for them. The artefact-property `acceptance:` keeps the mechanical gate active; the `verify: human` keeps invocation fidelity in the loop.
