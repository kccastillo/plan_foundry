---
description: Cleanly remove plan_foundry from this repo. Deletes the four bundle-managed dirs, version pin, .gitignore entries, and CLAUDE.md sentinel block. Leaves Workbench/, Retired/, and project-local .claude/ files (settings.local.json, plan-foundry.config) untouched. Offline; idempotent.
---

Invoke the plan-foundry-uninstall skill: `Skill("plan-foundry-uninstall")`.
