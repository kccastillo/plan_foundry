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

## Platform portability (per PLAN-AB3, H3 hiccup-log 2026-05-16)

Every `verify:` and `acceptance:` command MUST run on the foundry's CI baseline without modification. A command that silently fails or requires rewriting on CI is a plan-safety violation.

**CI baseline (the default platform):** Ubuntu Linux + Python 3.11 + pytest + pyyaml + git + gh + POSIX shell with bash-isms allowed. Commands that rely on this baseline require no annotation.

**Opt-out annotation:** when portability is genuinely impossible, add a trailing comment on the same line:
- `# platform: posix` — command is POSIX-specific; runs only on POSIX platforms during outcome-verify; audit skips the portability check for that item.
- `# platform: windows` — command is Windows-specific; runs only on Windows during outcome-verify; audit skips the portability check for that item.

**Forbidden patterns (when no `# platform:` annotation is present):** unannotated commands containing any of the following patterns will trigger a `warn`-severity finding from `audit-haiku-safe`:

| Pattern | Rationale |
|---------|-----------|
| `/tmp/` | Linux-only temp path; use `tempfile` Python module for portable alternatives |
| `/dev/null` | POSIX-only null device; use `subprocess.DEVNULL` or redirect suppression in Python |
| `bash -c` | Explicitly invokes bash; unavailable or differently-pathed on Windows |
| `test -[a-zA-Z]` | POSIX `test` builtin; use Python `os.path.exists()` / `pathlib` patterns instead |
| `> /dev/` | Redirect to `/dev/` pseudo-device; POSIX-only |
| `2>/dev/null` | POSIX stderr suppression; use Python subprocess or annotate |
| `&&` in compound commands | Works in bash but breaks PowerShell 5.1; split into separate commands or annotate |

**Origin:** H3 from `202605160300_RESEARCH_hiccup-log.md` — Reeve's Plan B used `> /tmp/dump.json && test -s /tmp/dump.json` (POSIX-only on a Windows project); plan-safety audit caught it as a blocker in iteration 1. This section closes the gap at authoring time.

**Audit enforcement:** `audit-haiku-safe` Step 4b extracts every `verify:` and `acceptance:` line from the PLAN's Verification section, checks each for the presence of a `# platform:` annotation, and scans unannotated lines for the forbidden-pattern set. See `audit-haiku-safe/workflows/audit-haiku-safe-steps.md` Step 4b for the full procedure and `audit-haiku-safe/lib/platform_portability.py` for the lint module.

## Oversized PLAN advisory (PSZ001)

A PLAN whose top-level Step count exceeds **12** earns advisory finding `PSZ001` from
`audit-haiku-safe` unless the PLAN's frontmatter `audit_acknowledgements:` list contains
`PSZ001`.

**Rationale:** Execution-context degradation and per-step error compounding scale with run
length (ADVICE-004 gap G1; ceiling locked as D1 in PLAN-AC7). The mitigation is decomposition
into a plan-of-plans or sequential PLANs.

**Severity:** Not-blocker advisory. The check is heuristic — a genuinely large atomic PLAN may
still pass with a recorded acknowledgement. PSZ001 is never a hard Blocker.

**Acknowledgement suppression:** Add `PSZ001` to the PLAN's `audit_acknowledgements:` field to
suppress the finding. Record the rationale for non-decomposition in the PLAN's Context section.

**Step-counting algorithm (D4):** Count lines matching regex `^\d+\.\s+` (one or more digits,
period, whitespace, content) appearing between the `## Steps` heading and the next `## ` heading.
Top-level only — sub-items (leading whitespace before digit, or letter-prefixed like `a.`) are
not counted.

## Verification format requirement (per PLAN 202605011400 decision 25)

Every PLAN's `## Verification` section item must be shell-runnable, with one of the following annotations on the line directly below the prose checkbox:

- `verify: <shell command>` — state assertion (file exists, grep matches, command exit code). Exit 0 = pass.
- `acceptance: <shell command>` — spec-level behavioural check that exercises the deliverable. Exit 0 = pass. **Every PLAN must include at least one `acceptance:` item.**
- `verify: human` — genuinely subjective item; surfaced for Human eyeball but does not auto-fail.

The orchestrator runs all `verify:` and `acceptance:` commands as a separate outcome-verification phase (after plan-executor returns success, before advancing to complete). Failures override the executor's self-reported success.

### skills-as-deliverable carve-out (per PLAN 202605011900 F3)

PLANs whose deliverable is a Claude skill (or other artefact not invokable from a shell) MAY satisfy the at-least-one-`acceptance:` requirement via an artefact-property check (frontmatter parses, workflow content present, gate-clauses present) PLUS a `verify: human` for the actual invocation behaviour. The skills-as-deliverable carve-out keeps the mechanical gate active without forcing a fictional shell-acceptance command. Claude skills are invoked by Claude, not by a shell; a true behavioural acceptance command cannot exist for them. The artefact-property `acceptance:` keeps the mechanical gate active; the `verify: human` keeps invocation fidelity in the loop.
