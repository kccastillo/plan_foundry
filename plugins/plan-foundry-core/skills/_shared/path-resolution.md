# Path resolution in markdown command/skill bodies

## Problem

Plugin scripts (`*.py` helpers) need to be invoked from markdown command bodies, SKILL.md prose, and agent definitions. The naive pattern is cwd-relative:

```bash
python plugins/plan-foundry-core/skills/write-plan/scripts/next_id.py PLAN
```

This works in the foundry's own dogfood session (where cwd is the repo root) but **breaks in consumer install**. When a consumer runs `/plugin install plan-foundry-core@plan-foundry`, the plugin lives at `~/.claude/plugins/<marketplace>/plan-foundry-core/` — not at `plugins/plan-foundry-core/` relative to their cwd.

Claude Code does provide a `CLAUDE_PLUGIN_ROOT` env var that points at the plugin's install location, but with a wrinkle:

- In **JSON contexts** (settings.json, plugin.json, hook configs), `${CLAUDE_PLUGIN_ROOT}` template substitution works.
- In **markdown contexts** (slash command bodies, SKILL.md text, agent prose), template substitution **fails** (upstream bug [anthropics/claude-code#9354](https://github.com/anthropics/claude-code/issues/9354)).

But Claude Code still exposes `CLAUDE_PLUGIN_ROOT` as an environment variable when invoking commands. So while template substitution fails in markdown, **bash variable expansion** at command-execution time succeeds.

## The pattern

Use bash parameter expansion with a dogfood fallback:

```bash
python "${CLAUDE_PLUGIN_ROOT:-plugins/plan-foundry-core}/skills/write-plan/scripts/next_id.py" PLAN
```

How it resolves:

| Context | `CLAUDE_PLUGIN_ROOT` | Resolved path |
|---|---|---|
| Foundry dogfood (cwd = repo root) | unset | `plugins/plan-foundry-core/skills/write-plan/scripts/next_id.py` |
| Consumer install | `~/.claude/plugins/.../plan-foundry-core` | `~/.claude/plugins/.../plan-foundry-core/skills/write-plan/scripts/next_id.py` |

Both forms resolve correctly because:
- Claude Code does not template-substitute `${CLAUDE_PLUGIN_ROOT:-...}` in markdown — bug #9354 means the brace expression is passed through to bash verbatim.
- Bash interprets `${VAR:-default}` as standard parameter expansion: use `$VAR` if set + non-empty; otherwise use `default`.

## When to use this pattern

- Any markdown body (command, SKILL.md, agent) that invokes a Python helper script that ships in the plugin tree.
- Any markdown body referencing a file path inside `plugins/<plugin-name>/`.

## When NOT to use this pattern

- **JSON contexts** — use the documented `${CLAUDE_PLUGIN_ROOT}` template substitution there. It works correctly in JSON and the fallback isn't needed (consumers' install path is always supplied).
- **Inside Python helper scripts** — they should self-locate via `Path(__file__).resolve().parent` (no env var needed).
- **Plugin-relative references that AREN'T executable paths** — markdown links between docs (`../write-input/SKILL.md`) use plain relative paths.

## Cross-plugin invocations

When a plugin invokes a script in a SIBLING plugin, the fallback differs:

```bash
# inside foundry-keeper invoking a plan-foundry-core script:
python "${CLAUDE_PLUGIN_ROOT:-plugins/plan-foundry-core}/skills/write-plan/scripts/next_id.py" PLAN
```

Note the fallback still points at `plugins/plan-foundry-core` (not `plugins/foundry-keeper`). The fallback is a foundry-dogfood-relative path; the env var (in consumer install) points at whatever plugin's invocation triggered the command. If a plugin needs to call into a sibling plugin's script in consumer-install contexts, the env-var-set path may not be the right plugin root — verify per-case before relying on this.

## Verification

- `scripts/audit-foundry.py` flags bare cwd-relative `python plugins/<plugin>/...` invocations under the `path-patterns` category.
- The pattern above is recognised as resolved (not flagged).
- See `TESTREPORT-001_audit-foundry-baseline.md` for the baseline that established this fix.
