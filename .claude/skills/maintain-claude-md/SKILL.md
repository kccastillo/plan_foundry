---
name: maintain-claude-md
description: Audit, propose additions to, or propose removals from CLAUDE.md, .claude/CONTEXT_CONSTITUTION.md, and ARCHITECTURE.md (the three maintainer-or-agent-facing docs in the Option-E-as-revised doc landscape; AGENT_RULES.md was dissolved 2026-05-14 per Option Y of ADVICE-003). Triggered by "audit CLAUDE.md", "audit ARCHITECTURE", "add X to CLAUDE.md", "prune CLAUDE.md", or the monthly RECUR- task. Output lands as a Workbench PLAN (if plan-foundry-core is installed) or plain markdown (standalone). Override with --output workbench|plain.
---

# maintain-claude-md

## What this skill does

Maintains CLAUDE.md and `.claude/CONTEXT_CONSTITUTION.md` as living configuration. Three modes, all dispatched by phrasing:

- **audit** — "audit CLAUDE.md", "is CLAUDE.md still good", "review the constitution", or the monthly RECUR- trigger. Scans both files against the checklist and produces a punch-list output.
- **add** — "add X to CLAUDE.md", "should we add Y to the constitution". Proposes the addition with the exact diff embedded; flags placement, dedupe risk, and budget impact.
- **prune** — "prune CLAUDE.md", "remove the dead reference to X", "trim CLAUDE.md". Proposes specific removals.

## Output mode (soft dependency on plan-foundry-core)

This plugin works **with or without** `plan-foundry-core` installed:

- **With core:** Output is written as a Workbench PLAN via `Skill("write-plan")`. The user approves the PLAN before any file edit happens.
- **Without core:** Output is written as a plain markdown file (`claude-md-audit-findings.md` in the project root). Same content, no Workbench integration.
- **Override flag:** `--output workbench` forces PLAN output (errors if core not installed). `--output plain` forces plain markdown regardless of core availability.

**Detection logic:** At output time, attempt `Skill("write-plan")`. If it resolves, use Workbench mode. If not, fall back to plain markdown. The `--output` flag bypasses detection.

## Files in scope

- `CLAUDE.md` — always audited if present
- `.claude/CONTEXT_CONSTITUTION.md` — audited if present
- `ARCHITECTURE.md` — audited if present (added 2026-05-13 per ADVICE-002 doc-set rationalisation)

**Note on AGENT_RULES.md.** Previously in scope (added 2026-05-13). Dissolved 2026-05-14 per Option Y of ADVICE-003 — meta-policy consolidated into CLAUDE.md, structural-reference content was duplication of canonical sources elsewhere. The file no longer exists at the foundry root, so the skill no longer audits it. If a consumer project still has an `AGENT_RULES.md` from an earlier plan-foundry version, the skill silent-skips it (consistent with the absent-file semantics below — the file is simply not in the scope list).

**Absent-file semantics.** Each listed file is audited only if it exists at the project root. Files that do not exist are silent-skipped, never flagged as drift. This makes the skill safe to run in both contexts: a foundry-maintainer project (where all three files exist) and a consumer project that has installed plan-foundry (where typically only CLAUDE.md exists — `ARCHITECTURE.md` is a foundry-internal doc that consumers do not ship).

**Audit checklist applicability.** The skill applies audit-checklist sections A (size/budget), C (instruction weighting), D (anti-patterns), and E (reference health) to every audited file. Section B ("Trinity present") is CLAUDE.md-specific and skipped for the other three files.

**init-plan-foundry sentinel-marker awareness (host CLAUDE.md).** When the audited CLAUDE.md contains a `<!-- plan-foundry:init-plan-foundry:start -->` ... `<!-- plan-foundry:init-plan-foundry:end -->` block placed there by the `init-plan-foundry` skill, the audit treats the content between the markers as plugin-managed:
- **Skip sections A/C/D/E** for the content between markers (the inlined operating-rules.md is owned by the plugin, not by the consumer; auditing it for line-budget or instruction-weighting drift would falsely flag plugin content).
- **Verify the marker pair is well-formed** — exactly one `:start` marker, exactly one `:end` marker, end appearing after start. Malformed markers are a blocker finding labelled `marker-malformed` with a one-line repair instruction: "Refresh the block by running `Skill(\"init-plan-foundry\")` or manually remove the malformed marker(s) and re-run init-plan-foundry."
- **Never propose modifications inside the markers.** If the inlined content needs updating (e.g., plugin's `operating-rules.md` evolved), the human re-runs init-plan-foundry to replace the between-markers content from the current plugin version.

The skill does NOT audit `.claude/references/*.md` (those are progressive-disclosure targets — bulk is fine there). It does check that pointers in CLAUDE.md and ARCHITECTURE.md to those files resolve.

## Lessons promotion-candidate review (T06 hook)

When run in **audit** mode (monthly RECUR- or on-demand), the skill reads the current month's `## Lessons Learned` section of the monthly LOG and identifies **promotion candidates** — lessons with `recurrences: N` where `N >= 3`. These are recurring observations that the human may want to codify into CLAUDE.md as permanent operating rules.

For each promotion candidate, the audit output includes a finding of the form:

> **[lessons-promotion]** Lesson `[<category>] (src: <source>; recurrences: <N>)` in this month's LOG has recurred N times. Consider codifying into CLAUDE.md (suggested home: `## Agent execution rules` if it's a behavioural rule; `## Working style` if it's a human-preference rule; new subsection otherwise). After codification, drop the lesson from next month's `curate-forward` output.

The audit does NOT auto-promote — it surfaces, the human decides. This wires T06's recurrence-counter machinery into the rot-defence loop without breaking the "human approves every CLAUDE.md change via Workbench PLAN" contract.

If no promotion candidates exist this month, the audit output notes "No lessons-promotion candidates this month" and moves on.

## Line-cap policy

- **Soft warn:** 150 lines. Above this, audit flags it as "approaching cap" and prune mode is suggested.
- **Hard fail:** 300 lines. Above this, audit blocks new additions and forces a prune PLAN before any add PLAN can land.

Both files have the same caps unless overridden in their frontmatter.

## Workflow

See [workflows/produce-plan.md](workflows/produce-plan.md) for the unified procedure.

## Audit checklist

See [references/audit-checklist.md](references/audit-checklist.md) — camelCase + context-rot checks.

## Anti-patterns

See [references/anti-patterns.md](references/anti-patterns.md) — what to flag and why.

## PLAN templates

See [templates/audit-plan-template.md](templates/audit-plan-template.md), [templates/add-plan-template.md](templates/add-plan-template.md), [templates/prune-plan-template.md](templates/prune-plan-template.md).

<essential_principles>
Output is always a file (Workbench PLAN or plain markdown per output mode above) — never direct edits to CLAUDE.md or CONTEXT_CONSTITUTION.md, never chat-only findings.
Audits use the checklist verbatim; do not invent new rules ad-hoc — propose new rules through an add-mode PLAN against the checklist itself.
Mode is inferred from user phrasing; if ambiguous, ask once before producing anything.
The monthly RECUR- task is a visibility mechanism, not auto-execution — it shows in the LOG's Recurring Task Tracker; the human or the active session triggers it.
</essential_principles>

<constraints>
- Never edit CLAUDE.md, .claude/CONTEXT_CONSTITUTION.md, or ARCHITECTURE.md directly from this skill — always via a file output (Workbench PLAN or plain markdown)
- Never write findings to chat only — always to a file
- Never audit `.claude/references/*.md` — those are intentionally bulky
- Soft warn at 150 lines, hard fail at 300 lines per file
- If CLAUDE.md is over hard cap, block all add-mode PLANs until a prune-mode PLAN executes
- Do not modify the audit checklist from inside an audit run — propose changes via add mode
</constraints>

<success_criteria>
- An output file exists (Workbench PLAN with valid frontmatter, or plain markdown in project root)
- The PLAN body contains specific, actionable findings (file + line range + verdict + recommended fix)
- Monthly LOG Status Table has a row for the new PLAN
- The human can approve the PLAN and hand it to `execute-plan` without further design
</success_criteria>
