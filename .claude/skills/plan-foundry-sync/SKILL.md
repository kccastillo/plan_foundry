---
name: plan-foundry-sync
description: Pull the latest plan_foundry bundle content into the current project. Copies the bundle's `.claude/{skills,agents,commands,hooks}` over the target's, overwriting bundle-managed files while preserving project-local additions. Updates `.claude/.plan-foundry-bundle-version`. Reports files copied, files unchanged, project additions preserved, and stale files (bundle-managed paths whose bundle counterpart no longer exists). Trigger phrases — "sync plan_foundry", "update plan_foundry bundle", "pull bundle", "plan foundry sync".
---

<objective>
Propagate bundle updates into the current project. Where `init-plan-foundry` bootstraps a target (creates Workbench/, Retired/, CLAUDE.md sentinel block, gitignore entries, AND copies the bundle), `plan-foundry-sync` does ONLY the copy + version-pin refresh. Use it any time the bundle has advanced and you want this project to pick up the changes.
</objective>

<essential_principles>
Bundle authority. Bundle-managed files (`.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`) are overwritten with the bundle's current content; local hand-edits are clobbered. The bundle is the source of truth for these paths.
Never delete from target. Bundle files renamed or removed upstream survive in the target — listed as `stale_in_target` in the sync report so the user can manually clean. Auto-prune is out of scope (per PLAN-AC5 D9).
Project-local content untouched. Anything under `.claude/` that is not under the four bundle-managed dirs (settings.local.json, plan-foundry.config, project-added scripts) is never touched.
Version pin refreshed. Every successful sync writes `.claude/.plan-foundry-bundle-version` with the bundle's current commit SHA, tag (if any), and UTC sync timestamp.
Self-reporting. Return a structured report (files copied, files unchanged, project additions preserved, stale files, previous and new SHA).
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a target project (CWD is the project root).
- The plan_foundry bundle is cloned at `~/.claude/plan_foundry/` (default) or at the path in `PLAN_FOUNDRY_BUNDLE_PATH`.
- The target has been initialised via `/init-plan-foundry` — i.e. `<target>/.claude/` is a real directory (not a symlink, not absent) containing a `.plan-foundry-bundle-version` file. If not, the skill FAILs with diagnostic "run /init-plan-foundry first" and aborts.
</preconditions>

<inputs>
None. The skill operates on the current working directory.
</inputs>

**Sync procedure:** See [workflows/sync.md](workflows/sync.md) for the per-step procedure.

The skill is implemented by [lib/sync.py](lib/sync.py), which uses the shared helper `_shared/bundle_copy.py`.

<constraints>
- Never delete from the target's bundle-managed paths.
- Never touch project-local files under `.claude/` (anything not under the four bundle-managed dirs).
- Never run `git pull` in the bundle — sync only copies what's already in the local bundle clone. Use `/plan-foundry-check-current` (or `cd ~/.claude/plan_foundry && git pull`) to update the bundle itself.
- Refuse to run if `<target>/.claude` is a symlink (legacy AC3 install) — surface "run /init-plan-foundry to migrate this project off the legacy symlink layout" and abort.
- Refuse to run if `<target>/.claude/.plan-foundry-bundle-version` is absent — surface "run /init-plan-foundry first" and abort.
</constraints>

<success_criteria>
- Bundle-managed paths in target match the bundle byte-for-byte (modulo `stale_in_target` files which survive but are reported).
- `.plan-foundry-bundle-version` exists with current bundle SHA, tag, and a fresh `synced` timestamp.
- Sync report lists previous SHA → new SHA, file counts (copied / unchanged / project_additions / stale_in_target), and any stale-file paths so the user can manually clean.
</success_criteria>
