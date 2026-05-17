# plan-foundry operating rules

This file is the canonical source for the operating rules that plan-foundry expects in any project that has installed it. The `init-foundry` skill reads this file at runtime and pastes its content inline into the consumer's `CLAUDE.md` between a paired set of HTML-comment sentinel markers named `plan-foundry:init-foundry:start` and `plan-foundry:init-foundry:end` (see `init-foundry/workflows/init-steps.md` for the exact form). Re-running init-foundry replaces the content between those markers with the current version of this file.

## Operating rules

1. **All plans go to Workbench/** — Every piece of planned work lives as a PLAN file, never chat-only. Trigger phrases like "let's plan X" or "ideate Y" fire the appropriate plan-foundry skills.
2. **Research and advice to Workbench/** — RESEARCH (data drops) and ADVICE (strategic notes) go via the `write-input` skill. Writing an input auto-clears any PLAN that was blocked waiting on it.
3. **Delegate broad searches to subagents** — For any search expected to read more than five files or 1,500 lines, spawn an Explore or general-purpose subagent. Handle inline otherwise.

## Lifecycle

Every PLAN moves through a fixed lifecycle: `drafting → drafted → checked → executing → outcome-verifying → complete`. State is durable on disk in PLAN frontmatter; re-entry is idempotent. The `plan-pipeline` skill orchestrates phase transitions.

## Further reference

- Plugin source and documentation: https://github.com/kccastillo/plan_foundry
- ARCHITECTURE.md (in the plan-foundry repo) covers design philosophy, strategic principles, and the named invariants register.
