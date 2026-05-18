# plan_foundry operating rules

This file is the canonical source for the operating rules that plan_foundry expects in any project that has installed it. The `init-plan-foundry` skill reads this file at runtime and pastes its content inline into the consumer's `CLAUDE.md` between a paired set of HTML-comment sentinel markers named `plan-foundry:init-plan-foundry:start` and `plan-foundry:init-plan-foundry:end` (see `workflows/init-steps.md` for the exact form). Re-running `init-plan-foundry` replaces the content between those markers with the current version of this file.

## Install

plan_foundry ships as a portable copy-paste bundle. Install once per machine:

```
git clone https://github.com/kccastillo/plan_foundry ~/.claude/plan_foundry
```

In each target project, run `/init-plan-foundry` (or `Skill("init-plan-foundry")`). The skill copies the bundle's `.claude/{skills,agents,commands,hooks}` into the target as real per-project content, scaffolds `Workbench/` and `Retired/`, seeds the current-month LOG, updates `.gitignore` (gitignoring bundle-managed paths so they don't churn the project's git history), inlines these operating rules into `CLAUDE.md` via sentinel block, and records the bundle commit SHA at `.claude/.plan-foundry-bundle-version`.

To pull subsequent bundle updates into a project, run `/plan-foundry-sync`. Sync overwrites bundle-managed files (skills / agents / commands / hooks) with the bundle's current content; it never deletes from the target, so project additions under those paths (e.g. `.claude/skills/my-project-skill/`) survive. Files renamed or removed upstream are reported in the sync output so you can clean them manually.

Project-local files under `.claude/` (`settings.local.json`, `plan-foundry.config`, anything not under the four bundle-managed dirs) are tracked by the project's git and never touched by sync.

To update all projects after pulling fresh bundle changes:

```
cd ~/.claude/plan_foundry && git pull
# then in each project:
/plan-foundry-sync
```

The bundle no longer auto-propagates — each project pins to a specific bundle commit visible at `.claude/.plan-foundry-bundle-version`. The trade-off is explicit sync friction in exchange for visible drift, per-project version pinning, and a real home for project-local config.

## Operating rules

1. **All plans go to Workbench/** — Every piece of planned work lives as a PLAN file, never chat-only. Trigger phrases like "let's plan X" or "ideate Y" fire the appropriate plan_foundry skills.
2. **Research and advice to Workbench/** — RESEARCH (data drops) and ADVICE (strategic notes) go via the `write-input` skill. Writing an input auto-clears any PLAN that was blocked waiting on it.
3. **Delegate broad searches to subagents** — For any search expected to read more than five files or 1,500 lines, spawn an Explore or general-purpose subagent. Handle inline otherwise.

## Lifecycle

Every PLAN moves through a fixed lifecycle: `drafting → drafted → checked → executing → outcome-verifying → complete`. State is durable on disk in PLAN frontmatter; re-entry is idempotent. The `plan-pipeline` skill orchestrates phase transitions.

## Currency

`/plan-foundry-check-current` reports two states:

1. **Bundle currency.** Is `~/.claude/plan_foundry` at `origin/main`? If behind, run `cd ~/.claude/plan_foundry && git pull` to update the bundle clone.
2. **Project currency.** Does this project's `.claude/.plan-foundry-bundle-version` SHA match the bundle's current HEAD? If behind, run `/plan-foundry-sync` to copy the latest bundle content into this project.

Either state can be up-to-date independently of the other — sync is per-project and explicit.

## Mobile/web caveat

Claude Code mobile and web apps do NOT read project-local `.claude/{skills,agents,commands}/`. Operating rules inlined into `CLAUDE.md` (this content) ARE visible there, but skill, agent, and slash command invocations only work in Claude Code desktop sessions.

## Further reference

- Bundle source and documentation: https://github.com/kccastillo/plan_foundry
- ARCHITECTURE.md (in the plan_foundry repo) covers design philosophy, strategic principles, and the named invariants register.
