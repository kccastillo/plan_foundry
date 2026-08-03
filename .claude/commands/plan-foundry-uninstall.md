---
description: Cleanly remove plan_foundry from this repo. Deletes the four bundle-managed dirs, version pin, .gitignore entries, and CLAUDE.md sentinel block. Leaves Workbench/, Retired/, and project-local .claude/ files (settings.local.json, plan-foundry.config) untouched. Offline; idempotent.
---

Read `.claude/skills/plan-foundry-uninstall/SKILL.md` and follow the workflow it
describes. Read the file directly rather than dispatching the Skill tool: the skill
carries `disable-model-invocation: true`, and whether that flag blocks a Skill-tool
call made from a command body is unsettled.
