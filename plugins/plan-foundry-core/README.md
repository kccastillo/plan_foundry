# plan-foundry-core

Core planning and execution skills for the plan-foundry harness — run PLANs through a full pipeline from ideation to retirement, with audited quality gates and a durable disk-state model.

## Install

```
/plugin marketplace add plan-foundry-core
/plugin install plan-foundry-core
```

After install, optionally create `.claude/plan-foundry.config` at your project root to override directory defaults (see Configuration below).

## Skills

| Skill | What it does |
|---|---|
| `write-plan` | Transcribe plans into the Workbench directory; manage monthly LOG and status tables |
| `write-input` | Write RESEARCH/ADVICE files to Workbench; unblock plans waiting on input |
| `execute-plan` | Execute PLAN steps in order; populate Executor Notes; update LOG |
| `plan-pipeline` | End-to-end planning orchestrator — walks a PLAN through drafting → drafted → checked → executing → verifying → complete |
| `audit-haiku-safe` | Mechanical plan-safety audit — checks each step is concrete, atomic, unambiguous, safe, testable |
| `audit-sufficiency` | Conceptual plan audit — interrogates assumptions, validation path, test fidelity, and meta-design |
| `lessons-learned` | Maintain a lean Lessons Learned section in the monthly LOG; two modes: `jot` and `curate-forward` |
| `retire` | Move files to the gitignored Retired directory when no longer needed |
| `init-foundry` | Bootstrap plan-foundry into a consumer project (idempotent project-state + CLAUDE.md awareness) |
| `handoff-next-session` | Write a session handoff note at end-of-session; retires the prior handoff before writing a fresh one |

## Subagents

The following agent files are included and dispatched by `plan-pipeline`:

| Agent | Role | Model |
|---|---|---|
| `plan-writer` | Transcribes or updates PLAN files at draft checkpoints | sonnet |
| `sufficiency-auditor` | Runs `audit-sufficiency` against a PLAN | opus |
| `plan-safety-auditor` | Runs `audit-haiku-safe` against a PLAN | sonnet |
| `plan-executor` | Executes a checked PLAN (default tier) | haiku |
| `plan-executor-sonnet` | Executes a checked PLAN (sonnet tier) | sonnet |
| `plan-executor-opus` | Executes a checked PLAN (opus tier) | opus |
| `plan-retirer` | Retires a completed PLAN to Retired/ | sonnet |

## Configuration

Create `.claude/plan-foundry.config` at your project root (optional):

```json
{
  "workbenchDir": "Workbench",
  "retiredDir":   "Retired"
}
```

Both keys are optional. Defaults: `workbenchDir = "Workbench"`, `retiredDir = "Retired"`. If the file is absent or a key is missing, the default applies. See `skills/_shared/config-loader.md` for the full spec.

**Skill description budget note:** Claude Code allocates a fixed context budget for skill listings. With multiple plugins active simultaneously, descriptions may be truncated under load. Keep skill descriptions tight and prefer natural-language triggers over explicit `/plugin:skill` invocations where possible.

## Source

Part of [plan-foundry](../../README.md) — the plan-foundry harness mono-repo.
