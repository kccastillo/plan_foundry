---
name: plan-foundry-uninstall
disable-model-invocation: true
description: 'Cleanly remove plan_foundry from the current project. Deletes the bundle-managed dirs (`.claude/{skills,agents,commands,hooks}`), the version pin (`.claude/.plan-foundry-bundle-version`), the bundle entries from `.gitignore`, and the operating-rules sentinel block from `CLAUDE.md`. Leaves `Workbench/`, `Retired/`, and any project-local files under `.claude/` (`settings.local.json`, `plan-foundry.config`, custom scripts) untouched - those are operator data, not bundle code. Local-only and works offline. Trigger phrases - "uninstall plan_foundry", "remove plan_foundry", "uninstall plan-foundry".'
---

<objective>
Uninstall removes the tool and leaves the operator's data in place. After uninstall, the project should have no trace of plan_foundry's bundle code or scaffolding pins, but every PLAN file, Retired artefact, and project-local config remains exactly where the operator left it. Uninstall follows the pip/npm/Rails convention: removing the tool never destroys user data.
</objective>

<essential_principles>
Bundle code only. Delete `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`, and the bundle-managed state files and directories that [workflows/uninstall.md](workflows/uninstall.md) Step 2 names - the version pin, the legacy install receipt, the incomplete-sync marker, the quarantine tree, and the namespaced receipt directory. These are derived state, regenerable by re-running install.
Operator data untouched. Uninstall never touches `Workbench/` (PLAN files), `Retired/` (closed-out artefacts), or anything under `.claude/` that is not a bundle-managed dir. If the operator wants to delete those as well, that is a manual `rm -rf` the operator can run.
Idempotent. Running uninstall when plan_foundry is already absent succeeds with a "nothing to remove" report.
Offline. Uninstall makes no network call and no git clone, so uninstall works in any environment.
Gitignore + CLAUDE.md reversed. By exact line match, remove the canonical list `REQUIRED_GITIGNORE_ENTRIES` in `_shared/gitignore_entries.py` plus the legacy `Retired/` line that `init-plan-foundry` stopped adding at PLAN-AD0 D2-A, and remove the CLAUDE.md sentinel block (start marker through end marker, inclusive).
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a target project (CWD is the project root).
- The skill is local-only and works regardless of network state.
</preconditions>

**Uninstall procedure:** See [workflows/uninstall.md](workflows/uninstall.md).

The skill is implemented by [lib/uninstall.py](lib/uninstall.py).

<constraints>
- Never delete `Workbench/`, `Retired/`, or anything under `.claude/` other than the bundle-managed dirs `skills`, `agents`, `commands` and `hooks` plus the bundle-managed state paths listed in [workflows/uninstall.md](workflows/uninstall.md) Step 2.
- Never delete CLAUDE.md itself - only the content between the plan-foundry sentinel markers and the markers themselves.
- Never touch the surrounding `.gitignore` content - only remove the canonical plan_foundry entries.
- Report what was kept (Workbench/, Retired/, project-local .claude/ files) so the operator knows what manual cleanup, if any, they may still want.
</constraints>

<success_criteria>
- `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/hooks/` and every bundle-managed state path listed in [workflows/uninstall.md](workflows/uninstall.md) Step 2 are absent.
- `.gitignore` has the plan_foundry-managed entries removed (other entries preserved verbatim).
- `CLAUDE.md` has the sentinel block (start marker, body, end marker) removed.
- `Workbench/`, `Retired/`, and any project-local `.claude/*` files (settings.local.json, plan-foundry.config, custom scripts) remain exactly as they were.
- Report names every path that was removed and lists what was kept.
</success_criteria>
