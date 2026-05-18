# plan_foundry operating rules

This file is the canonical source for the operating rules that plan_foundry expects in any project that has installed it. The `init-plan-foundry` skill reads this file at runtime and pastes its content inline into the consumer's `CLAUDE.md` between a paired set of HTML-comment sentinel markers named `plan-foundry:init-plan-foundry:start` and `plan-foundry:init-plan-foundry:end` (see `workflows/init-steps.md` for the exact form). Re-running `init-plan-foundry` replaces the content between those markers with the current version of this file.

## Install

plan_foundry ships as a portable copy-paste bundle. Install once per machine:

```
git clone https://github.com/kccastillo/plan_foundry ~/.claude/plan_foundry
```

Then, in each target repository, run the `init-plan-foundry` skill (or the `/init-plan-foundry` slash command). The skill creates a single coarse symlink `<target>/.claude → ~/.claude/plan_foundry/.claude` so the target inherits every plan_foundry skill, agent, and command. Update all targets at once with `cd ~/.claude/plan_foundry && git pull`.

## Operating rules

1. **All plans go to Workbench/** — Every piece of planned work lives as a PLAN file, never chat-only. Trigger phrases like "let's plan X" or "ideate Y" fire the appropriate plan_foundry skills.
2. **Research and advice to Workbench/** — RESEARCH (data drops) and ADVICE (strategic notes) go via the `write-input` skill. Writing an input auto-clears any PLAN that was blocked waiting on it.
3. **Delegate broad searches to subagents** — For any search expected to read more than five files or 1,500 lines, spawn an Explore or general-purpose subagent. Handle inline otherwise.

## Lifecycle

Every PLAN moves through a fixed lifecycle: `drafting → drafted → checked → executing → outcome-verifying → complete`. State is durable on disk in PLAN frontmatter; re-entry is idempotent. The `plan-pipeline` skill orchestrates phase transitions.

## Currency

Check whether the local plan_foundry bundle is at `origin/main` with the `plan-foundry-check-current` skill. If behind, update with `cd ~/.claude/plan_foundry && git pull`.

## Mobile/web caveat

Claude Code mobile and web apps do NOT read project-local `.claude/{skills,agents,commands}/`. Operating rules inlined into `CLAUDE.md` (this content) ARE visible there, but skill, agent, and slash command invocations only work in Claude Code desktop sessions.

## Further reference

- Bundle source and documentation: https://github.com/kccastillo/plan_foundry
- ARCHITECTURE.md (in the plan_foundry repo) covers design philosophy, strategic principles, and the named invariants register.
