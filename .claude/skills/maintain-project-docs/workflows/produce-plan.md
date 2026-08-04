# Produce a PLAN

Unified workflow for all three modes. Mode is inferred from the user's phrasing; the workflow shapes which template gets filled.

## Step 0: Determine mode

| User says... | Mode |
|---|---|
| "audit", "review", "check", "is it still good", monthly RECUR- trigger | **audit** |
| "add X", "include X", "should we add" | **add** |
| "prune", "remove", "trim", "drop the dead reference" | **prune** |

If ambiguous, ask once. Do not produce a PLAN until mode is clear.

## Step 1: Load files in scope

For each of the three files-in-scope, check existence at the project root and load if present. Files that do not exist are silent-skipped (do not flag as drift). Typical contexts:
- Foundry-maintainer project: all three files exist.
- Consumer project that installed plan-foundry: usually only `CLAUDE.md` exists; `ARCHITECTURE.md` is foundry-internal and not shipped.

Files:
- `CLAUDE.md`
- `.claude/CONTEXT_CONSTITUTION.md`
- `ARCHITECTURE.md`

(`AGENT_RULES.md` was previously in scope; dissolved 2026-05-14 per Option Y of ADVICE-003. If a consumer project still has an `AGENT_RULES.md` from an earlier plan-foundry version, the silent-skip absent-file semantics apply - the file is no longer in the scope list.)

For each loaded file, count lines and compare to caps (soft 150, hard 300). Record findings.

**init-plan-foundry sentinel-marker detection (CLAUDE.md only).** When loading `CLAUDE.md`, scan for the literal strings `<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->`. Three cases:
- Both absent -> no marker block; CLAUDE.md content is entirely consumer-authored. Audit normally.
- Exactly one start and one end, end after start -> record the byte range between the markers as `MARKER_BLOCK_RANGE`. Treat that range as bundle-managed for audit purposes (see Step 2).
- Any other count or order -> record a `marker-malformed` blocker finding for the audit report with the literal one-line repair instruction: "Refresh the block by running `Skill(\"init-plan-foundry\")` or manually remove the malformed marker(s) and re-run init-plan-foundry." Do NOT enter `MARKER_BLOCK_RANGE`; audit the entire file normally for the rest of the run.

## Step 2: Run mode-specific work

### audit
- Run audit-checklist sections A (size/budget), C (instruction weighting), D (anti-patterns), E (reference health) against every loaded file.
- Run audit-checklist section B ("Trinity present") against `CLAUDE.md` only; skip for the other three files.
- For `CLAUDE.md` specifically, if `MARKER_BLOCK_RANGE` is set, exclude that byte range from sections A, C, D, E (the content there is bundle-managed by init-plan-foundry; do not flag for line-budget, instruction-weighting, anti-pattern, or reference-health drift). Section B applies to the surrounding consumer-authored content as normal. If a `marker-malformed` finding was recorded in Step 1, include it as a blocker in the report.
- Match every loaded file against [../references/anti-patterns.md](../references/anti-patterns.md).
- Group findings: blockers -> warns -> suggestions.
- For each finding: record file + line range + check ID + verdict + recommended fix.
- Never propose modifications inside `MARKER_BLOCK_RANGE` - if the bundle-managed content needs updating, the recommended fix is "re-run `Skill(\"init-plan-foundry\")` to refresh from the bundle's operating-rules.md".

### add
- Identify the section(s) where the addition belongs.
- Compute the proposed diff (exact lines to add, in context).
- Check budget: would this push over soft cap? Hard cap?
- Check dedupe: does an existing rule cover this?
- If hard cap would be breached, escalate: produce a prune-mode PLAN first, refuse to produce the add-mode PLAN until prune executes.

### prune
- Identify removal candidates. For each: file + line range + reason for removal + impact assessment.
- For pointers: check if the pointed-to content needs to migrate elsewhere first.
- For caveats: check if still load-bearing (search the codebase for the underlying concern).

## Step 3: Write the PLAN

Use the appropriate template:
- audit -> `templates/audit-plan-template.md`
- add -> `templates/add-plan-template.md`
- prune -> `templates/prune-plan-template.md`

Filename: `{YYYYMMDDHHMI}_PLAN_maintain-project-docs-{mode}.md`. If invoked from monthly RECUR- task: `{YYYYMMDDHHMI}_PLAN_RECUR-monthly-claude-md-audit.md` (and append to History rather than create new - see plan-conventions).

Hand the filled template to `write-plan` skill - do not write it directly.

## Step 4: Report

```
Skill: maintain-project-docs (mode: <audit|add|prune>)
PLAN written: <filename>
Findings: <N blockers, M warns, K suggestions>  [audit only]
Budget impact: <delta lines, status vs. caps>  [add/prune only]
Next step: the human to approve, then hand to execute-plan
```
