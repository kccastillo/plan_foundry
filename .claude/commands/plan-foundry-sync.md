---
description: Pull the latest plan_foundry bundle content into the current project. Copies the bundle's `.claude/{skills,agents,commands,hooks}` over the project's, preserving project-local additions; refreshes the version pin at `.claude/.plan-foundry-bundle-version`; reports drift.
---

Read `.claude/skills/plan-foundry-sync/SKILL.md` and follow the workflow it describes.
Read the file directly rather than dispatching the Skill tool: the skill carries
`disable-model-invocation: true`, and whether that flag blocks a Skill-tool call made
from a command body is unsettled. Reading the file is not affected either way. The
skill:

1. Detects the bundle location (default `~/.claude/plan_foundry/`).
2. Validates the project is initialised (real `.claude/` directory, version-pin file present). Refuses to run on legacy symlink installs (run `/init-plan-foundry` to migrate) or uninitialised projects.
3. Copies bundle-managed paths into the project (`skills/`, `agents/`, `commands/`, `hooks/`); performs receipt-backed quarantine of files no longer shipped upstream rather than deleting them outright (PLAN-AH7).
4. Refreshes the version pin at `.claude/.plan-foundry-bundle-version` (records bundle SHA, tag, sync timestamp).
5. Reports: previous SHA -> new SHA, files copied, files unchanged, project additions preserved, stale-in-target list (bundle files no longer upstream - surviving but worth flagging).

To update the bundle itself before syncing: `cd ~/.claude/plan_foundry && git pull`. Use `/plan-foundry-check-current` to see whether the bundle (or this project) is behind.
