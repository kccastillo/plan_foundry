---
name: plan-foundry-uninstall
description: 'Cleanly remove plan_foundry from the current project. Deletes the four bundle-managed dirs (`.claude/{skills,agents,commands,hooks}`), the version pin (`.claude/.plan-foundry-bundle-version`), the bundle entries from `.gitignore`, and the operating-rules sentinel block from `CLAUDE.md`. Leaves `Workbench/`, `Retired/`, and any project-local files under `.claude/` (`settings.local.json`, `plan-foundry.config`, custom scripts) untouched - those are operator data, not bundle code. Local-only; works offline. Trigger phrases - "uninstall plan_foundry", "remove plan_foundry", "uninstall plan-foundry".'
---

<objective>
Tool-removal, not data-deletion. After uninstall, the project should have no trace of plan_foundry's bundle code or scaffolding pins, but every PLAN file, Retired artefact, and project-local config remains exactly where the operator left it. Matches the pip/npm/Rails convention: removing the tool never destroys user data.
</objective>

<essential_principles>
Bundle code only. Delete `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`, and the version pin file. These are derived state, regenerable by re-running install.
Operator data untouched. `Workbench/` (PLAN files), `Retired/` (closed-out artefacts), and anything under `.claude/` that isn't a bundle-managed dir - never touched. If the operator wants to delete them too, that's a manual `rm -rf` they can run themselves.
Idempotent. Running uninstall when plan_foundry is already absent succeeds with a "nothing to remove" report.
Offline. No network. No git clone. Works in any environment.
Gitignore + CLAUDE.md reversed. Remove exactly the entries that init-plan-foundry added - by line match against the canonical list - and remove the CLAUDE.md sentinel block (start marker through end marker, inclusive).
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a target project (CWD is the project root).
- The skill is local-only; works regardless of network state.
</preconditions>

**Uninstall procedure:** See [workflows/uninstall.md](workflows/uninstall.md).

The skill is implemented by [lib/uninstall.py](lib/uninstall.py).

<constraints>
- Never delete `Workbench/`, `Retired/`, or anything under `.claude/` other than the four bundle-managed dirs + the version pin file.
- Never delete CLAUDE.md itself - only the content between the plan-foundry sentinel markers and the markers themselves.
- Never touch the surrounding `.gitignore` content - only remove the canonical plan_foundry entries.
- Report what was kept (Workbench/, Retired/, project-local .claude/ files) so the operator knows what manual cleanup, if any, they may still want.
</constraints>

<success_criteria>
- `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`, `.claude/.plan-foundry-bundle-version` are absent.
- `.gitignore` has the plan_foundry-managed entries removed (other entries preserved verbatim).
- `CLAUDE.md` has the sentinel block (start marker, body, end marker) removed.
- `Workbench/`, `Retired/`, and any project-local `.claude/*` files (settings.local.json, plan-foundry.config, custom scripts) remain exactly as they were.
- Report names every path that was removed and lists what was kept.
</success_criteria>
