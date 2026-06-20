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
3. **Delegate broad searches to subagents** — For any search expected to read more than five files or 1,500 lines, spawn an Explore or general-purpose subagent pinned to a cheap tier — pass `model: haiku` for mechanical file-find/grep/read; use `model: sonnet` only when the search needs judgement. Handle inline otherwise.

## Lifecycle

Every PLAN moves through a fixed lifecycle: `drafting → drafted → checked → executing → outcome-verifying → complete`. State is durable on disk in PLAN frontmatter; re-entry is idempotent. The `plan-pipeline` skill orchestrates phase transitions.

## plan_foundry vs this-project boundary

plan_foundry is an upstream dependency installed into this repo as a bundle. It is not a workstream of this repo. When working inside this project, do not fix, patch, refactor, or extend plan_foundry — even if the bug, misfire, infinite loop, or enhancement opportunity is discovered while doing this project's work. Symptoms count as "plan_foundry behaviour" when they originate in any bundled skill, agent, slash command, hook, or in the pipeline state-machine itself; project work that merely *uses* the bundle is in-scope.

**Hard guardrail.** Never edit files under `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, or `.claude/hooks/`. Those four directories are bundle-managed and are overwritten by `/plan-foundry-sync` on the next refresh — any in-place patch will be silently destroyed. Project-local additions belong elsewhere in `.claude/` (e.g. `settings.local.json`, `plan-foundry.config`, custom scripts outside the four managed dirs).

**Detection-then-handoff procedure.** When you observe plan_foundry behaviour worth fixing or improving:

1. **Detect and stop.** Recognise the symptom belongs to plan_foundry (bundled skill/agent/command/hook misbehaviour, pipeline-phase confusion, recurring orchestrator deviation, missing affordance). Do not open a PLAN, ADVICE, or RESEARCH in this project to prosecute it.
2. **Capture, don't prosecute.** Write the observation as a properly-typed RESEARCH or ADVICE file in the consumer project's own `Workbench/` via `write-input` — ADVICE if the finding shapes how plan_foundry should be used, RESEARCH if it is a data drop / reproduction trace. Tag the frontmatter `feeds_plan: ""` or `advises_plan: ""` (target unknown at consumer-side; plan_foundry maintainer fills in on transfer). Use a slug like `plan-foundry-observation-<short-name>` so it is identifiable on transfer. These are real artefacts in the consumer's Workbench and DO enter that project's INDEX — they document a real observation, recorded at the moment of observation.
3. **Carry on.** If the symptom blocks immediate work, apply the smallest in-conversation workaround and note it inline in the captured RESEARCH/ADVICE body. Resume this project's task.
4. **Hand off upstream.** Periodically (or at session-end), copy the typed `plan-foundry-observation-*` RESEARCH/ADVICE files from the consumer's `Workbench/` into the plan_foundry repo's `Workbench/` at <https://github.com/kccastillo/plan_foundry> for triage there. The plan_foundry side decides whether each finding becomes a bug, an enhancement PLAN, or retrospective input. The captures arrive already-typed — no staging dock, no later triage step. Once transferred, the consumer-side copies can be retired via `Skill("retire", ...)`.

Rationale: keeping the boundary sharp prevents this project's Workbench from filling with upstream concerns, prevents speculative patches to bundle code that the next sync will erase, and ensures plan_foundry's own backlog reflects real consumer friction rather than guesswork.

## Mobile/web caveat

Claude Code mobile and web apps DO read the project-local `.claude/{skills,agents,commands}/` once the bundle has been copied into the project. The AC6 network-clone model is specifically designed so install, sync, and uninstall work in those sandboxed sessions — network is available, filesystem writes stay inside the target.

## Further reference

- Bundle source: https://github.com/kccastillo/plan_foundry
- BOOTSTRAP.md (at the bundle root) — single-file procedure the agent follows on first contact.
- ARCHITECTURE.md (in the plan_foundry repo) — design philosophy and the named invariants register.
