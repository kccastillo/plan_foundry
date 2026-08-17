# Audit Checklist

Run every check on every audit. Group findings by severity: **blocker** (hard-cap breach, dead reference, anti-pattern) -> **warn** (soft-cap, structural risk) -> **suggestion** (progressive-disclosure opportunity).

## A. Size and budget

This section is the only home for the cap values. No CI check and no git hook enforces either cap, so an audit run is the only thing that reports a breach.

- A1. Compare the line count against the soft cap of 150, and flag the file when the count is over.
- A2. Compare the line count against the hard cap of 300, and block add-mode proposals when the count is over.
- A3. Estimate the instruction count by counting each bullet, table row, and emphasised rule, then flag the file when the count approaches 100. The figure of 100 is inherited from the external CLAUDE.md-hygiene framework this checklist was built from, and no measurement in this repository supports it, so treat it as a review trigger rather than a limit.

## B. Trinity present (top of file)
- B1. Project oneliner - single paragraph, names framework + tech stack + domain.
- B2. Key Commands - only the most-frequent (<=3 commands inline, with the rest as a pointer). <!-- tally-ok: a cap on how many may appear, not a count of how many do -->
- B3. Caveats - non-obvious project quirks (e.g., "do not modify schema.prisma directly").
A missing element is a blocker.

## C. Instruction weighting (Lost-in-the-Middle)
- C1. Most critical rules in the top ~30 lines or bottom ~20 lines, not buried mid-file.
- C2. IMPORTANT / MUST / NEVER markers used on load-bearing rules.
- C3. When `.claude/CONTEXT_CONSTITUTION.md` exists, a pointer to it appears in the top 10 lines of CLAUDE.md. Skip this check when that file is absent.
Buried critical content is a blocker.

## D. Anti-pattern detection
See [anti-patterns.md](anti-patterns.md). Flag every match.

## E. Reference health
- E1. Every pointer to `.claude/references/*.md`, `ARCHITECTURE.md`, or other in-repo files resolves to an existing file.
- E2. Every pointer to a skill (`Skill("name")` or `.claude/skills/name/`) resolves.
- E3. No pointers to retired files (check `Retired/` for matching basenames).
A dead reference is a blocker.

## F. Progressive-disclosure opportunities
- F1. Any inline section >=20 lines that documents codebase-derivable facts (architecture, schemas, command lists) -> suggest moving to `.claude/references/`.
- F2. Any inline section >=10 lines that is only relevant for specific file types -> suggest moving it into a reference that only the work touching those files loads. Do not recommend a path-based rule-loading mechanism: no such harness surface is registered in `.claude/skills/_shared/harness-contract.md`, which is where every harness dependency this bundle relies on must be recorded.
- F3. Any large block of caveats specific to one subsystem -> suggest a subsystem-specific reference.

## G. Static-maintenance (drift)
- G1. Tool/library version numbers inline - flag for verification against `requirements.txt` / `package.json`.
- G2. File paths inline - verify that each one exists. A dead path is a blocker.
- G3. References to people, projects, or external systems - flag for review (cannot auto-verify).

## H. Context-rot positioning
- H1. Does CLAUDE.md document the scratchpad pattern (Workbench/ for plans, memory for cross-session)? Required.
- H2. Does CLAUDE.md document subagent triggers (when to delegate vs. handle inline)? Required.
- H3. Does CLAUDE.md establish content labelling (e.g., naming external-source content distinctly)? Suggestion if missing.
- H4. When `.claude/CONTEXT_CONSTITUTION.md` exists, does CLAUDE.md point to it from the top? Required in that case only. The file is present only on team-scoped projects, and its absence is never a finding.

## I. Constitution-specific (only when auditing CONTEXT_CONSTITUTION.md)
- I1. Every rot mode named (Poisoning / Distraction / Confusion / Clash).
- I2. Every fix named (Write / Select / Compress / Isolate).
- I3. Project-specific imperative rules present (>=6 rules tied to actual project workflows).
- I4. Recovery protocol on rot detection documented.

## J. Scope coverage
- J1. Every `.claude/skills/_shared/*.md` helper present in the tree is checked against sections A, C, D and E, as with the other in-scope files. The set is a glob rather than a fixed list, so audit whatever the glob returns.
- J2. No helper carries marginalia: commentary about itself, about its provenance, or a parked question for the reader.
- J3. No helper references a working artefact - a PLAN, an input, a handoff, a request, or any path under a working directory - because the helper outlives every such artefact.
