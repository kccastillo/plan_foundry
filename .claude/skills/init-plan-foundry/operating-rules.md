# plan_foundry operating rules

This file is the canonical source for the operating rules that plan_foundry expects in any project that has installed it. The `init-plan-foundry` skill reads this file at runtime and pastes its content inline into the consumer's `CLAUDE.md` between a paired set of HTML-comment sentinel markers named `plan-foundry:init-plan-foundry:start` and `plan-foundry:init-plan-foundry:end`. Re-running `init-plan-foundry` replaces the content between those markers with the current version of this file.

## Install

plan_foundry ships as a portable network-cloned bundle. There is no global install. To bootstrap a fresh project, open a Claude Code session in the project root and paste:

> Bootstrap plan_foundry from https://github.com/kccastillo/plan_foundry into this repo.

The agent will (1) run `git clone --depth=1 https://github.com/kccastillo/plan_foundry .plan-foundry-tmp/` inside the project, (2) copy the bundle's `.claude/{skills,agents,commands,hooks}` into the project's `.claude/`, (3) scaffold `Workbench/`, `Retired/`, the current-month LOG, update `.gitignore`, inline these operating rules into `CLAUDE.md` between sentinel markers, (4) record the bundle commit SHA at `.claude/.plan-foundry-bundle-version`, and (5) delete `.plan-foundry-tmp/`. Network is required; the operation is sandbox-safe (everything happens inside the target repo).

After the bootstrap, re-running `/init-plan-foundry` refreshes from the latest bundle. `/plan-foundry-sync` does the same minus the scaffolding (no Workbench/Retired/CLAUDE.md edits).

## Sync

To pull the latest bundle content into a project after upstream changes:

```
/plan-foundry-sync
```

Sync clones `https://github.com/kccastillo/plan_foundry` into `<target>/.plan-foundry-tmp/`, overwrites bundle-managed files (`skills/`, `agents/`, `commands/`, `hooks/`) with the bundle's current content, refreshes `.claude/.plan-foundry-bundle-version`, and deletes the tmp clone. Never deletes from the target — project additions under bundle-managed paths survive. Files renamed or removed upstream are reported as `stale_in_target` so you can clean them manually.

Tag pinning: `/plan-foundry-sync v0.5.0` checks out a specific bundle version.

Project-local files under `.claude/` (`settings.local.json`, `plan-foundry.config`, custom scripts, anything not under the four bundle-managed dirs) are tracked by the project's git and never touched by sync.

## Currency

`/plan-foundry-check-current` reads this project's `.claude/.plan-foundry-bundle-version` and queries the remote bundle's `HEAD` via `git ls-remote https://github.com/kccastillo/plan_foundry`. If the project pin differs from remote HEAD, run `/plan-foundry-sync`.

## Uninstall

`/plan-foundry-uninstall` removes the four bundle-managed dirs, the version pin, the bundle `.gitignore` entries, and the CLAUDE.md sentinel block. `Workbench/`, `Retired/`, monthly LOG, and project-local `.claude/` files are left untouched — those are operator data, not bundle code. Offline; idempotent.

## Operating rules

1. **All plans go to Workbench/** — Every piece of planned work lives as a PLAN file, never chat-only. Trigger phrases like "let's plan X" or "ideate Y" fire the appropriate plan_foundry skills.
2. **Research and advice to Workbench/** — RESEARCH (data drops) and ADVICE (strategic notes) go via the `write-input` skill. Writing an input auto-clears any PLAN that was blocked waiting on it.
3. **Delegate broad searches to subagents** — For any search expected to read more than five files or 1,500 lines, spawn an Explore or general-purpose subagent. Handle inline otherwise.

## Lifecycle

Every PLAN moves through a fixed lifecycle: `drafting → drafted → checked → executing → outcome-verifying → complete`. State is durable on disk in PLAN frontmatter; re-entry is idempotent. The `plan-pipeline` skill orchestrates phase transitions.

## Mobile/web caveat

Claude Code mobile and web apps DO read the project-local `.claude/{skills,agents,commands}/` once the bundle has been copied into the project. The AC6 network-clone model is specifically designed so install, sync, and uninstall work in those sandboxed sessions — network is available, filesystem writes stay inside the target.

## Further reference

- Bundle source: https://github.com/kccastillo/plan_foundry
- BOOTSTRAP.md (at the bundle root) — single-file procedure the agent follows on first contact.
- ARCHITECTURE.md (in the plan_foundry repo) — design philosophy and the named invariants register.
