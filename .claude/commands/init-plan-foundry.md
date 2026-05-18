---
description: Bootstrap a target repository with the plan_foundry skill scaffold — copies the bundle into .claude/, scaffolds Workbench/ and Retired/, seeds the monthly LOG, updates .gitignore, inlines operating-rules into CLAUDE.md, and records the bundle version pin.
---

Invoke `Skill("init-plan-foundry")` and follow the workflow it returns. The skill:

1. Detects the bundle location (default `~/.claude/plan_foundry/`).
2. Refuses to run inside the bundle source itself.
3. Copies the bundle's `.claude/{skills,agents,commands,hooks}` into the target's `.claude/` (migrating from a legacy AC3 symlink in-place if present); records the bundle commit SHA at `.claude/.plan-foundry-bundle-version`.
4. Scaffolds `Workbench/`, `Retired/`, and the current-month LOG.
5. Updates `.gitignore` to gitignore bundle-managed paths (`.claude/skills/` etc.) while leaving project-local files under `.claude/` trackable.
6. Inlines `operating-rules.md` content into the target's `CLAUDE.md` via sentinel block.
7. Surfaces "RESTART Claude Code for project-local skills to register".

To pull subsequent bundle updates into the project, run `/plan-foundry-sync`. To check both bundle-vs-upstream and project-vs-bundle currency, run `/plan-foundry-check-current`.
