# plan-foundry

A **deliberative** planning system for Claude Code, packaged as a four-plugin marketplace.

## What it's for, and what it isn't

Plan-foundry helps a human collaborate with an agent to produce a *good* PLAN before any code is written — audited, durable, and ready to execute. Use it for high-stakes architectural decisions, refactors, novel features, or any work where the cost of building the wrong thing is higher than the cost of thinking carefully first.

It is **not** a throughput tool. If you want an autonomous agent to ship code as fast as possible, reach for a [ralph loop](https://ralphloop.sh/), a multi-agent swarm, or Claude Code's native Agent Teams. Plan-foundry is deliberately sequential, deterministic, and human-in-the-loop. That is the feature, not the limitation — parallelism doesn't help you think harder, and a plan that's wrong faster is still wrong.

## How it works

Every piece of intended work is written as a PLAN file in a `Workbench/` directory with structured frontmatter. Every PLAN moves through a fixed lifecycle (drafting → audit → checked → executing → outcome-verifying → complete) under the supervision of an orchestrator skill. Two audit passes catch mistakes before they become commits. Skills are modular Markdown prompts, each pinned to a specific model tier — Opus for conceptual judgement, Sonnet for mechanical review and execution, Haiku for cheap structured work.

## Install

```
/plugin marketplace add kccastillo/plan_foundry
/plugin install plan-foundry-core@plan-foundry
```

Install additional plugins as needed:

```
/plugin install claude-md-maintenance@plan-foundry
/plugin install ideate@plan-foundry
/plugin install foundry-keeper@plan-foundry
```

After installing `plan-foundry-core`, run `Skill("init-foundry")` (or say *"set up plan-foundry"*) in your project to create the `Workbench/` directory, an initial monthly LOG, the `Retired/` gitignore entries, and an operating-rules block in your `CLAUDE.md` (inlined between paired sentinel markers managed by the skill). The skill is idempotent — safe to run multiple times. Re-running the skill replaces the content between the sentinel markers with the latest plugin version of the operating rules; do not hand-edit between the markers (edits are lost on re-run).

> **Note for Windows users:** Local-path install (`/plugin marketplace add kccastillo/plan_foundry is blocked by Claude Code [bug #11243](https://github.com/anthropics/claude-code/issues/11243) — a path-join issue that strips the directory separator. Use the GitHub install above instead.

## Plugins

| Plugin | What it does | Dependencies |
|---|---|---|
| [plan-foundry-core](plugins/plan-foundry-core/README.md) | Core planning and execution skills — write plans, audit, execute, retire. The Workbench INDEX is auto-regenerated at `Workbench/INDEX.md` after every phase transition and is the canonical kanban view of all PLANs. | — |
| [claude-md-maintenance](plugins/claude-md-maintenance/README.md) | Audit and maintain CLAUDE.md / CONTEXT_CONSTITUTION.md against context-rot | Optional: plan-foundry-core |
| [ideate](plugins/ideate/README.md) | Three-phase ideation arc (Clarify → Survey → Converge) for shaping problems into plans | Optional: plan-foundry-core |
| [foundry-keeper](plugins/foundry-keeper/README.md) | Self-improvement: unified operation log + monthly summariser for pattern analysis | Optional: plan-foundry-core |

## Design philosophy

Plan-foundry tackles three structural problems in ad-hoc agent setups: deterministic triggering (no "should I run the audit now?" judgement — phase state machine decides), no race conditions (single re-entry point, sequential audits, idempotent on-disk state), and smaller agents harnessed (each skill pinned to a model tier; subagents declare explicit skill registries). See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design philosophy and the invariants the harness depends on.

## Optional dependencies

Plugins that benefit from `plan-foundry-core` (`claude-md-maintenance`, `ideate`, `foundry-keeper`) use **runtime feature detection** — they check if `Skill("write-plan")` resolves and fall back to plain markdown if not. Each supports an `--output workbench|plain` override flag. No hard dependency in `marketplace.json` (Claude Code's dependency mechanism is required-only, not optional).

## Configuration

Create `.claude/plan-foundry.config` in your project root (optional):

```json
{
  "workbenchDir": "Workbench",
  "retiredDir": "Retired"
}
```

Both keys are optional. Defaults: `workbenchDir = "Workbench"`, `retiredDir = "Retired"`.

## Repository structure

The prod repo holds only the install surface: plugin trees, marketplace manifest, README, LICENSE.

```
.claude-plugin/
  marketplace.json            # Plugin marketplace manifest (Claude Code spec)
plugins/
  plan-foundry-core/          # Core planning + execution skills
    .claude-plugin/
      plugin.json             # Per-plugin manifest
    skills/                   # Skill definitions (auto-discovered)
    agents/                   # Subagent definitions (auto-discovered)
    commands/                 # Slash command definitions
  claude-md-maintenance/
  ideate/
  foundry-keeper/
LICENSE
README.md
```

