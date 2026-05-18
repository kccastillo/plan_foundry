---
name: plan-foundry-check-current
description: Two-tier currency check for plan_foundry. Tier 1 — is the local bundle at ~/.claude/plan_foundry current with origin/main? Tier 2 — is THIS project's recorded bundle version (`.claude/.plan-foundry-bundle-version`) equal to the bundle's HEAD? Surfaces an actionable next step for each tier (`cd ~/.claude/plan_foundry && git pull` for tier 1; `/plan-foundry-sync` for tier 2). Trigger phrases — "check plan_foundry current", "is plan_foundry current", "plan-foundry-check-current".
---

# plan-foundry-check-current

Two-tier currency check for plan_foundry:

- **Tier 1 (bundle vs upstream):** is the locally cloned bundle at `~/.claude/plan_foundry/` at `origin/main` HEAD?
- **Tier 2 (project vs bundle):** does the current project's `.claude/.plan-foundry-bundle-version` match the bundle's current HEAD?

Both tiers are reported in one JSON output. Either can be up-to-date independently of the other.

## Preconditions

- The plan_foundry bundle is cloned at `~/.claude/plan_foundry/` (default) or at a path passed via `--bundle-path <p>` or the `PLAN_FOUNDRY_BUNDLE_PATH` environment variable.
- Network access available for `git fetch origin main` (tier 1 falls back gracefully if offline — uses whatever `origin/main` is locally).
- Tier 2 is skipped when `--no-target-check` is passed (use when checking from outside any project context).

## Procedure

See [workflows/check.md](workflows/check.md) for the per-step procedure.

The skill is implemented by [lib/check_current.py](lib/check_current.py).

## Output schema

```json
{
  "bundle": {
    "status": "current | behind | ahead | diverged | wrong_remote | no_bundle",
    "local_sha": "<8-char>",
    "remote_sha": "<8-char>",
    "behind_by": 0,
    "ahead_by": 0,
    "message": "<one-line human-readable>"
  },
  "project": {
    "status": "current | behind | drift | not_initialised | legacy_symlink | unknown",
    "project_sha": "<8-char-or-empty>",
    "bundle_sha": "<40-char-or-empty>",
    "message": "<one-line human-readable>"
  }
}
```

For backward compatibility with pre-AC5 consumers, the top-level JSON also mirrors the `bundle` tier's fields (`status`, `local_sha`, `remote_sha`, `behind_by`, `ahead_by`, `message`).

## Invocation

```
python .claude/skills/plan-foundry-check-current/lib/check_current.py
python .claude/skills/plan-foundry-check-current/lib/check_current.py --bundle-path /some/other/path
python .claude/skills/plan-foundry-check-current/lib/check_current.py --no-target-check
python .claude/skills/plan-foundry-check-current/lib/check_current.py --target-root /some/project
```
