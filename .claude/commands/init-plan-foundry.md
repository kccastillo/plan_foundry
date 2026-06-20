---
description: Bootstrap a target repository with the plan_foundry skill scaffold — clones the public bundle into `<target>/.plan-foundry-tmp/`, copies `.claude/{skills,agents,commands,hooks}` into the target, scaffolds Workbench/ and Retired/, seeds the monthly LOG, updates .gitignore, inlines operating-rules into CLAUDE.md, records the version pin, and deletes the tmp clone. Network required.
---

Invoke `Skill("init-plan-foundry")` and follow the workflow it returns. The skill:

1. Refuses to run inside the bundle source itself (basename or origin-URL match).
2. Clones `https://github.com/kccastillo/plan_foundry` (or the supplied `--ref`) into `<target>/.plan-foundry-tmp/`.
3. Copies the bundle's `.claude/{skills,agents,commands,hooks}` into the target's `.claude/`; records the bundle commit SHA at `.claude/.plan-foundry-bundle-version`. Migrates from a legacy AC3 symlink in-place if present.
4. Scaffolds `Workbench/`, `Retired/`, and the current-month LOG.
5. Updates `.gitignore` to gitignore bundle-managed paths (`.claude/skills/` etc.), the transient `.plan-foundry-tmp/`, and the version pin.
6. Inlines `operating-rules.md` content into the target's `CLAUDE.md` via sentinel block.
7. Deletes `.plan-foundry-tmp/`.
8. Surfaces "RESTART Claude Code for project-local skills to register".

Subsequent updates: `/plan-foundry-sync`. Currency check: `/plan-foundry-check-current`. Clean removal: `/plan-foundry-uninstall`.
