---
name: plan-foundry-check-current
description: Single-tier currency check for plan_foundry. Reads this project's `.claude/.plan-foundry-bundle-version` pin and compares it to the remote bundle's HEAD via `git ls-remote https://github.com/kccastillo/plan_foundry`. If behind, surfaces "run /plan-foundry-sync" as the next step. Network required (graceful failure if unreachable). Trigger phrases — "check plan_foundry current", "is plan_foundry current", "plan-foundry-check-current".
---

# plan-foundry-check-current

Single-tier currency check for plan_foundry. Reads the project's bundle pin and compares to the remote HEAD. Under the AC6 model there is no local bundle clone — the only relevant question is "does this project match the remote?"

## Preconditions

- Running in a Claude Code session inside a target project (CWD is the project root).
- `git` available on `PATH`.
- Network access reachable to `https://github.com/kccastillo/plan_foundry` (graceful `remote_unreachable` status if not).

## Procedure

See [workflows/check.md](workflows/check.md) for the per-step procedure.

The skill is implemented by [lib/check_current.py](lib/check_current.py).

## Output schema

```json
{
  "status": "current | behind_or_diverged | not_initialised | legacy_symlink | remote_unreachable | unknown",
  "project_sha": "<8-char-or-empty>",
  "remote_sha": "<8-char-or-empty>",
  "ref": "HEAD",
  "message": "<one-line human-readable>"
}
```

## Invocation

```
python .claude/skills/plan-foundry-check-current/lib/check_current.py
python .claude/skills/plan-foundry-check-current/lib/check_current.py --target-root /some/project
```
