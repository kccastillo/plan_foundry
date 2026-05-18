---
description: Bootstrap a target repository with the plan_foundry skill scaffold — creates .claude symlink to ~/.claude/plan_foundry/.claude, scaffolds Workbench/ and Retired/, seeds the monthly LOG, and inlines operating-rules into CLAUDE.md.
---

Invoke `Skill("init-plan-foundry")` and follow the workflow it returns. The skill:

1. Detects the bundle location (default `~/.claude/plan_foundry/`).
2. Creates the coarse symlink `<cwd>/.claude → ~/.claude/plan_foundry/.claude`.
3. Scaffolds `Workbench/`, `Retired/`, and the current-month LOG.
4. Updates `.gitignore` to include `Retired/`, `Workbench/.heartbeat/`, and `.claude`.
5. Inlines `operating-rules.md` content into the target's `CLAUDE.md` via sentinel block.
6. Surfaces "RESTART Claude Code for project-local skills to register".
