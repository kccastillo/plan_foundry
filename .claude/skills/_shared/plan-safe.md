---
title: Plan-safe Definition
description: The plan-safe standard - the criteria a PLAN's Steps must meet to run mechanically, how a Step is sized to its executor tier, and how verification items are written.
created: 2026-05-01
---

# Plan-safe definition

A plan is "plan-safe" (executable mechanically, without design work) when every step is:
- **Concrete:** specific file paths, exact command syntax, no "likely" or "probably"
- **Unambiguous:** no judgement calls, and the executor runs the steps rather than redesigning them
- **Atomic:** one step at a time, with a clear success or failure condition
- **Safe:** no destructive operations without explicit Human approval, and no bypasses (--no-verify, --force)
- **Testable:** verification criteria are independent and checkable

Example of plan-safe: "Read `.claude/skills/retire/SKILL.md`. Verify frontmatter `name: retire`. Move the `<essential_principles>` block into `workflows/retire-file.md` under a new `## Essential principles` heading, and replace the block in SKILL.md with a link to that file. Commit with message 'chore: trim retire SKILL.md'"

Example of NOT plan-safe: "Audit SKILL.md and extract any residual content. Use your judgement." (ambiguous, requires interpretation)

**When authoring plans:** refer to [.claude/skills/execute-plan/workflows/execute-steps.md](../execute-plan/workflows/execute-steps.md) for the execution protocol, and ensure every step passes this definition.

**Mechanical Steps must be filesystem-tool-shaped (F1 Option C, PLAN 202605011900).** Express mechanical Steps as Read/Write/Edit/Glob/Grep operations, not shell-shaped (`mkdir`, `cp`, `echo > file`, `cat file`, `sed -i`, `grep ... file`). The plan-executor agents disallow Bash structurally, so shell-shaped Steps will fail at runtime. Shell commands belong in the Verification section as `verify:`/`acceptance:` items - those run in the orchestrator's outcome-verifying phase (parent context, allowlist works correctly).

> Executor capability boundaries are defined in `.claude/skills/_shared/executor-capability-boundary.md`.

> Platform portability is defined in `.claude/skills/_shared/platform-portability.md`.

## Verification format requirement (per PLAN 202605011400 decision 25)

Every PLAN's `## Verification` section item must be shell-runnable, with one of the following annotations on the line directly below the prose checkbox:

- `verify: <shell command>` - state assertion (file exists, grep matches, command exit code). Exit 0 = pass.
- `acceptance: <shell command>` - spec-level behavioural check that exercises the deliverable. Exit 0 = pass. **Every PLAN must include at least one `acceptance:` item.**
- `verify: human` - reserved for genuine authority: scope amendments, stakeholder-facing framing, political judgement, risk acceptance. Surfaced for the Human to inspect, and does not auto-fail.
- `verify: orchestrator` - performed by any non-executor agent (the orchestrator or a dispatched verifier). Independence is satisfied because the verifier is categorically not the executor. The verdict and evidence are recorded durably in `verification_state.orchestrator_attestations` (see phase-state-machine.md). No operator action is required, and a `verify: orchestrator` item never enters `human_pending`.

The orchestrator runs all `verify:` and `acceptance:` commands as a separate outcome-verification phase (after plan-executor returns success, before advancing to complete). Failures override the executor's self-reported success.

### Tier boundary - independence vs authority

`verify: orchestrator` is for **independence** - the executor must not self-certify this item, but any non-executor agent can verify the item. The tier name identifies who may attest, and that party is never the plan-executor.

`verify: human` is reserved for **authority** - decisions whose stakes only the operator may accept: scope amendments, stakeholder-facing framing, political judgement, risk acceptance. Machine-checkable content that merely needs independence MUST use `verify: orchestrator`, not `verify: human`.

The executor-never-self-certifies invariant is fully preserved by this tier, because the orchestrator and any dispatched verifier are categorically not the executor. Use the single canonical spelling `verify: orchestrator` and do not introduce `verify: independent` or `verify: agent` as synonyms. One tier carries one name, so the pipeline's exact match on the annotation, and the vocabulary, remain unambiguous.

### skills-as-deliverable carve-out (per PLAN 202605011900 F3)

PLANs whose deliverable is a Claude skill (or other artefact not invokable from a shell) MAY satisfy the at-least-one-`acceptance:` requirement via an artefact-property check (frontmatter parses, workflow content present, gate-clauses present) PLUS a `verify: human` for the actual invocation behaviour. Claude invokes a skill directly rather than through a shell, so a true behavioural acceptance command cannot exist for one. The artefact-property `acceptance:` therefore keeps the mechanical gate active without forcing a fictional shell-acceptance command, and the `verify: human` keeps invocation fidelity in the loop.

## Executor t-shirt sizing - when a Step cannot be made haiku-safe

Not every job can be reduced to the haiku-safe bar above, and forcing a job down to that bar is
not the goal. Some work needs light judgement (Sonnet), and a little needs design-at-execution
(Opus). The bar a PLAN must clear is the bar of **its assigned executor tier**, not always
Haiku's. "Not haiku-safe" is therefore a **sizing outcome, not automatically a Blocker**: the job
still occurs, routed to the tier that can run it rather than silently stuck.

Each size fixes which `assigned_to:` values a PLAN may carry, and `assigned_to:` selects the
executor (see
[../write-plan/references/assigned_to-field.md](../write-plan/references/assigned_to-field.md) and
the phase-state-machine executor-tier table):

| Size | `assigned_to:` | Executor (model) | When a Step lands here                                                                 |
|------|----------------|------------------|----------------------------------------------------------------------------------------|
| **S**  | empty / `haiku`* | `plan-executor` (**Sonnet**)        | Fully haiku-safe: every Step concrete, atomic, unambiguous, safe, testable. **The cleanest, lowest-risk shape** - still the authoring target even though it now runs on Sonnet. |
| **M**  | `sonnet`        | `plan-executor-sonnet` (**Sonnet**) | Cannot reduce to fully-mechanical without losing fidelity - needs light judgement, larger context, or cross-Step reasoning. Decomposition would fragment a coherent unit. |
| **L**  | `opus`          | `plan-executor-opus` (**Opus**)   | Genuinely design-heavy at execution time: a Step needs design decisions that cannot be pre-specified. **Escape hatch - prefer decomposition first (decision 16 anti-monolithic principle).** |
| **XL** | `human`         | none - not dispatched  | Not executor-safe at any tier as one PLAN. Must be decomposed into a plan-of-plans, or gated `[Human]`. Sized XL and routed - **never silently blocked.** |

**Execution floor is Sonnet (recalibrated 2026-07-04).** Haiku is retired *as an execution tier*: S and M both run on `plan-executor`/`plan-executor-sonnet` (Sonnet 5), and only L escalates to Opus. `*assigned_to: haiku` is a legacy alias that still routes to the Sonnet default executor. "Haiku-safe" survives as the idiomatic name for the **fully-mechanical S bar** (the strictest, lowest-risk authoring shape) - it names a plan property, not the executor model. The S-vs-M distinction is authoring granularity (how mechanical the plan is); both execute on Sonnet.

**Tier-relative Blocker definition and the sizing decision (what audit-haiku-safe records instead
of only blocking).** Extends decision 14: a **Blocker** is any finding that would cause the PLAN's
*assigned tier* (not always Haiku) to halt, error, or be forced into a judgement call above its
remit. When a Step crosses that line, the auditor picks one remedy and records which:

1. **Decompose** - if the judgement can be pre-resolved by splitting the Step into smaller mechanical
   Steps, keep the PLAN at **S** and emit a decomposition Blocker (the historical behaviour). A Step
   needing judgement inside `size: S` is a Blocker only when splitting removes the judgement; when it
   does not, the remedy is remedy 2 below.
2. **Size up** - if the judgement is irreducible, the remedy is a **re-size**, not a Blocker: recommend
   the correct size (M/L), have the Human set `size:` and the matching `assigned_to:`, and record the
   sizing rationale in the PLAN's Context section. A Step that needs Opus-level design inside a PLAN
   declared `size: M` (sonnet) is a re-size to **L**, not a Blocker. A PLAN correctly sized to its tier and
   clearing that tier's bar is `checked`, not blocked.

**Authoring vs execution tier are different axes.** The tier that *authors/decomposes* a PLAN to a
runnable state may be higher than the tier that *executes* it - getting a job to Sonnet-executable
(M) can itself require Opus-level decomposition up front (a parent plan-of-plans, size L). Size the
PLAN by its **execution** tier; do the authoring uplift in the parent.

**Frontmatter.** `size:` is an optional PLAN frontmatter field taking `S | M | L | XL`. When present
it MUST agree with `assigned_to:` per the table above; a mismatch is an audit-haiku-safe Blocker.
When absent, size is inferred from `assigned_to:` (empty/`haiku` -> S). A PLAN with non-haiku-safe
Steps and no recorded size/tier is incompletely sized - the auditor recommends a size rather than
passing it silently.

## Oversized PLAN advisory (PSZ001)

A PLAN whose top-level Step count exceeds **12** earns advisory finding `PSZ001` from
`audit-haiku-safe` unless the PLAN's frontmatter `audit_acknowledgements:` list contains
`PSZ001`.

**Rationale:** Execution-context degradation and per-step error compounding scale with run
length (ADVICE-004 gap G1; ceiling locked as D1 in PLAN-AC7). The mitigation is decomposition
into a plan-of-plans or sequential PLANs.

**Severity:** Not-blocker advisory. The check is heuristic - a genuinely large atomic PLAN may
still pass with a recorded acknowledgement. PSZ001 is never a hard Blocker.

**Acknowledgement suppression:** Add `PSZ001` to the PLAN's `audit_acknowledgements:` field to
suppress the finding. Record the rationale for non-decomposition in the PLAN's Context section.

**Step-counting algorithm (D4):** Count lines matching regex `^\d+\.\s+` (one or more digits,
period, whitespace, content) appearing between the `## Steps` heading and the next `## ` heading.
Top-level only - sub-items (leading whitespace before digit, or letter-prefixed like `a.`) are
not counted.
