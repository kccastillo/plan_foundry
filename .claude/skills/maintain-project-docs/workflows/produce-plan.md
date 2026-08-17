# Produce a PLAN

This workflow covers the audit, add and prune modes. The user's phrasing determines the mode, and the mode determines which template is filled.

## Step 0: Determine mode

| User says... | Mode |
|---|---|
| "audit", "review", "check", "is it still good", monthly RECUR- trigger | **audit** |
| "add X", "include X", "should we add" | **add** |
| "prune", "remove", "trim", "drop the dead reference" | **prune** |

If the phrasing is ambiguous, ask once. Do not produce a PLAN until the mode is clear.

## Step 1: Load files in scope

For each file in scope, check whether it exists at the path given below and load it when present. A file that does not exist is skipped silently and is never flagged as drift. Typical contexts:
- Foundry-maintainer project: every file listed below exists.
- Consumer project that installed plan-foundry: usually only `CLAUDE.md` exists, because `ARCHITECTURE.md` is foundry-internal and is not shipped.

Files:
- `CLAUDE.md`
- `.claude/CONTEXT_CONSTITUTION.md`
- `ARCHITECTURE.md`
- `.claude/skills/_shared/*.md` - every helper the glob returns, not a fixed list. These are in scope per the skill's Files-in-scope section, and checklist section J covers them.

(`AGENT_RULES.md` was previously in scope and was dissolved on 2026-05-14 per Option Y of ADVICE-003. If a consumer project still has an `AGENT_RULES.md` from an earlier plan-foundry version, the silent-skip absent-file semantics apply, because the file is no longer in the scope list.)

For each loaded file, count lines and compare them against the caps in audit-checklist A1 and A2, which is where those two numbers live. Nothing in CI enforces either cap, so recording the breach here is the only report it gets.

**init-plan-foundry sentinel-marker detection (CLAUDE.md only).** When loading `CLAUDE.md`, scan for the literal strings `<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->`, then handle whichever case matches:
- Both absent -> there is no marker block, so the CLAUDE.md content is entirely consumer-authored. Audit normally.
- Exactly one start and one end, end after start -> record the byte range between the markers as `MARKER_BLOCK_RANGE`. Treat that range as bundle-managed for audit purposes (see Step 2).
- Any other count or order -> record a `marker-malformed` blocker finding for the audit report with the literal one-line repair instruction: "Refresh the block by running `Skill(\"init-plan-foundry\")` or manually remove the malformed marker(s) and re-run init-plan-foundry." Do NOT enter `MARKER_BLOCK_RANGE`, and audit the entire file normally for the rest of the run.

## Step 2: Run mode-specific work

### audit
- Run audit-checklist sections A (size/budget), C (instruction weighting), D (anti-patterns), E (reference health) against every loaded file.
- Run audit-checklist section B ("Trinity present") against `CLAUDE.md` only, and skip section B for every other file.
- For `CLAUDE.md` specifically, if `MARKER_BLOCK_RANGE` is set, exclude that byte range from sections A, C, D, E (init-plan-foundry manages the content there, so do not flag that content for line-budget, instruction-weighting, anti-pattern, or reference-health drift). Section B applies to the surrounding consumer-authored content as normal. If a `marker-malformed` finding was recorded in Step 1, include it as a blocker in the report.
- Match every loaded file against [../references/anti-patterns.md](../references/anti-patterns.md).
- Group findings: blockers -> warns -> suggestions.
- For each finding: record file + line range + check ID + verdict + recommended fix.
- Never propose modifications inside `MARKER_BLOCK_RANGE` - if the bundle-managed content needs updating, the recommended fix is "re-run `Skill(\"init-plan-foundry\")` to refresh from the bundle's operating-rules.md".

### add
- Identify the section(s) where the addition belongs.
- Compute the proposed diff (exact lines to add, in context).
- Check the budget: would the addition push the file over the soft cap, or over the hard cap?
- Check dedupe: does an existing rule cover this?
- If the addition would breach the hard cap, escalate: produce a prune-mode PLAN first, and refuse to produce the add-mode PLAN until the prune executes.

### prune
- Identify removal candidates. For each: file + line range + reason for removal + impact assessment.
- For pointers: check whether the pointed-to content needs to migrate elsewhere first.
- For caveats: check whether the caveat is still load-bearing (search the codebase for the underlying concern).

## Step 3: Write the PLAN

Use the appropriate template:
- audit -> `templates/audit-plan-template.md`
- add -> `templates/add-plan-template.md`
- prune -> `templates/prune-plan-template.md`

Filename: `{YYYYMMDDHHMI}_PLAN_maintain-project-docs-{mode}.md`. If invoked from monthly RECUR- task: `{YYYYMMDDHHMI}_PLAN_RECUR-monthly-claude-md-audit.md` (and append to History rather than creating a new PLAN - see plan-conventions).

Hand the filled template to the `write-plan` skill rather than writing the PLAN directly.

**Plain output.** The PLAN path above assumes the planning bundle is installed. When it is absent, there is no Workbench and no `write-plan` skill to hand to, so fill the same template and write the result as a markdown findings file in the project root instead. `--output plain` forces that path, and `--output workbench` forces the PLAN path and fails when the bundle is absent.

## Step 4: Report

```
Skill: maintain-project-docs (mode: <audit|add|prune>)
PLAN written: <filename>
Findings: <N blockers, M warns, K suggestions>  [audit only]
Budget impact: <delta lines, status vs. caps>  [add/prune only]
Next step: the human to approve, then hand to execute-plan
```
