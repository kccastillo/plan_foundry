---
name: plan-foundry-check-current
description: Check whether the locally installed plan_foundry bundle is current with origin/main. Surfaces "up-to-date" or "behind by N commits — run `cd ~/.claude/plan_foundry && git pull`". Trigger phrases — "check plan_foundry current", "is plan_foundry current", "plan-foundry-check-current".
---

# plan-foundry-check-current

Check whether the locally installed plan_foundry bundle is at `origin/main` HEAD.

## Preconditions

- The plan_foundry bundle is cloned at `~/.claude/plan_foundry/` (the default) or at a path passed via `--bundle-path <p>` or the `PLAN_FOUNDRY_BUNDLE_PATH` environment variable.
- Network access available for `git fetch origin main`.

## Procedure

See [workflows/check.md](workflows/check.md) for the per-step procedure.

The skill is implemented by [lib/check_current.py](lib/check_current.py), which:

1. Detects the bundle install location (default `~/.claude/plan_foundry/`; overridable via `--bundle-path` or `PLAN_FOUNDRY_BUNDLE_PATH`).
2. Verifies the bundle's git remote `origin` URL points at `kccastillo/plan_foundry`. If not, surfaces `status: wrong_remote` and exits 0 (diagnostic-mode, not crash).
3. Runs `git fetch origin main`.
4. Compares `git rev-parse HEAD` to `git rev-parse origin/main`.
5. Reports structured JSON to stdout.

## Output schema

```json
{
  "status": "current | behind | ahead | diverged | wrong_remote | no_bundle",
  "local_sha": "<8-char>",
  "remote_sha": "<8-char>",
  "behind_by": 0,
  "ahead_by": 0,
  "message": "<one-line human-readable>"
}
```

## Invocation

```
python .claude/skills/plan-foundry-check-current/lib/check_current.py
python .claude/skills/plan-foundry-check-current/lib/check_current.py --bundle-path /some/other/path
```
