# plan-foundry-core Config Loader

## Purpose

A reading helper that centralises the logic for loading project-local configuration. Skills import this helper to avoid duplicating the load-and-default logic across the codebase.

## Config File

**Path:** `.claude/plan-foundry.config` (JSON, optional — the file need not exist).

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
| `workbenchDir` | `"Workbench"` | Directory where PLAN, LOG, RESEARCH, ADVICE files live |
| `retiredDir`   | `"Retired"`   | Directory where retired/superseded files are moved |

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
logPath = "{workbenchDir}/{YYYYMM}010000_LOG_{YYYYMM}.md"
```

## Skills That Consume This Config

The following skills inside `plan-foundry-core` read configurable paths and must apply this helper at runtime:

| Skill         | Key(s) Used            |
|---------------|------------------------|
| `write-plan`  | `workbenchDir`         |
| `write-input` | `workbenchDir`         |
| `retire`      | `retiredDir`           |
| `plan-pipeline` | `workbenchDir`       |
| `execute-plan` | `workbenchDir`        |
| `lessons-learned` | `workbenchDir`    |

## Failure Behaviour

- Config file absent → use all defaults silently (not an error).
- Config file present but malformed JSON → use all defaults and emit a warning to the operator: "plan-foundry.config is malformed JSON — using defaults."
- Config file present, valid JSON, unrecognised keys → silently ignore unknown keys; apply recognised keys normally.

## Notes for Plugin Users

To override defaults, create `.claude/plan-foundry.config` at the project root with only the keys you wish to override. For example, if your project uses `Workbench/` as the workbench directory:

```json
{
  "workbenchDir": "CustomDir"
}
```

This file is NOT version-controlled by the bundle — it belongs to the consuming project.
