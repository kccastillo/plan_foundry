# Foundry Log Schema (v1)

Append-only JSONL. One JSON object per line. Every line includes `schema_version` for forward compatibility.

## Common fields (all kinds)

| Field | Type | Required | Description |
|---|---|---|---|
| `ts` | ISO 8601 string | yes | UTC timestamp |
| `schema_version` | integer | yes | Always `1` for this version |
| `kind` | string enum | yes | Event type discriminator |
| `session_id` | string | yes | Claude Code session UUID |

## Kind: `skill_call`

Fired by PostToolUse hook when `tool_name == "Skill"`.

| Field | Type | Description |
|---|---|---|
| `skill` | string | Skill name invoked |
| `args` | string | Arguments passed |
| `ok` | boolean | Whether the call succeeded |

## Kind: `tool_use`

Fired by PostToolUse hook for non-Skill tools.

| Field | Type | Description |
|---|---|---|
| `tool` | string | Tool name (e.g. "Bash", "Read", "Edit") |
| `summary` | string | First 120 chars of tool input for context |

## Kind: `subagent_start`

Fired by PostToolUse hook when `tool_name == "Agent"`.

| Field | Type | Description |
|---|---|---|
| `agent` | string | Agent/subagent type |
| `description` | string | Agent task description |

## Kind: `subagent_stop`

Fired when a background agent task completes (if detectable via hook).

| Field | Type | Description |
|---|---|---|
| `agent` | string | Agent/subagent type |
| `outcome` | string | Success/failure indicator |

## Kind: `session_start`

Fired by SessionStart hook.

| Field | Type | Description |
|---|---|---|
| `cwd` | string | Working directory at session start |

## Kind: `session_stop`

Fired by Stop hook.

| Field | Type | Description |
|---|---|---|
| `duration_hint` | string | Approximate session duration if available |

## Kind: `hiccup`

Manual entry via `foundry-log note-hiccup`. Human-observed event worth tracking.

| Field | Type | Description |
|---|---|---|
| `summary` | string | What happened |
| `source` | string | `"human-noted"` for manual entries, `"migrated"` for imports from legacy `_hiccups.md` |

## Default log path

`.claude/_foundry_log.jsonl` - configurable via `.claude/plan-foundry.config` `logPath` key.
