---
title: plan-foundry-core Config Loader
description: The project-local plan-foundry.config contract - its schema, defaults, failure behaviour, and which consumer actually reads it.
created: 2026-08-17
---

# plan-foundry-core Config Loader

## Purpose

A reading helper that centralises the logic for loading project-local configuration. Skills import this helper to avoid duplicating the load-and-default logic across the codebase.

## Config File

**Path:** `.claude/plan-foundry.config` (JSON, optional - the file need not exist).

**Schema:**
```json
{
  "workbenchDir": "Workbench",
  "retiredDir":   "Retired"
}
```

Both keys are optional. If the file is absent or a key is missing, the default baked in below applies.

## Defaults

| Key            | Default     | Description                                      |
|----------------|-------------|--------------------------------------------------|
| `workbenchDir` | `"Workbench"` | Directory where PLAN, RESEARCH and ADVICE files live |
| `retiredDir`   | `"Retired"`   | Directory where retired/superseded files are moved |

## What Actually Reads This Config

`test-foundry` is the only consumer. Its `workflows/run-tests.md` instructs the
agent running it to prefer `workbenchDir` over the default when the config
declares one.

No Python helper reads this file, and the core lifecycle skills - `write-plan`,
`write-input`, `retire`, `plan-pipeline`, `execute-plan` - resolve `Workbench`
and `Retired` as fixed paths. `next_id.py` hardcodes both. Do not write a PLAN
or a Step on the assumption that setting `workbenchDir` moves where those skills
write.

Until 2026-08-10 this section was a table naming those five skills as consumers
that "must apply this helper at runtime". None of them ever did. The table was
removed rather than implemented, and the reasoning is worth keeping because the
same question will recur: relocating `Workbench` and `Retired` is a capability
nobody has asked for, the five named skills are the ones a wrong path breaks
most expensively, and the defect reported was a document naming consumers that
do not exist, rather than a consumer asking for relocation and being denied. The
fix for a false claim is to stop making the claim.

The config itself stays, because `test-foundry` honours it and a consumer may
already have set the key.

## How to Use in a Skill

In any skill step that needs a configurable path, apply this procedure before constructing a file path:

1. Attempt to Read `.claude/plan-foundry.config`.
2. If the file exists and is valid JSON, parse it.
3. Extract the relevant key (`workbenchDir` or `retiredDir`). If the key is absent or the file cannot be parsed, use the default.
4. Use the resolved value as the directory prefix in all subsequent file-path construction.

**Example (pseudo-code):**
```
config = readJSON(".claude/plan-foundry.config") OR {}
workbenchDir = config.workbenchDir OR "Workbench"
retiredDir   = config.retiredDir   OR "Retired"
```

The example carried a fourth line deriving a `logPath` until 2026-08-10. The
only thing that ever read it was `.claude/hooks/foundry-log.py`, decommissioned
along with the monthly LOG the path pointed at, so the line documented a key
with no reader and a filename shape nothing writes.

## Failure Behaviour

- Config file absent -> use all defaults silently (not an error).
- Config file present but malformed JSON -> use all defaults and emit a warning to the operator: "plan-foundry.config is malformed JSON - using defaults."
- Config file present, valid JSON, unrecognised keys -> silently ignore unknown keys; apply recognised keys normally.

## Notes for Plugin Users

To override defaults, create `.claude/plan-foundry.config` at the project root with only the keys you wish to override. For example, if your project uses `Workbench/` as the workbench directory:

```json
{
  "workbenchDir": "CustomDir"
}
```

This file is NOT version-controlled by the bundle - it belongs to the consuming project.
