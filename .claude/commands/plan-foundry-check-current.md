---
description: Two-tier currency check. Tier 1 — is the local bundle current with origin/main (if not, `cd ~/.claude/plan_foundry && git pull`). Tier 2 — is this project's recorded bundle version equal to the bundle HEAD (if not, `/plan-foundry-sync`).
---

Invoke `Skill("plan-foundry-check-current")` and report the result.

The skill runs `lib/check_current.py`, which compares:
1. **Bundle tier:** local bundle clone HEAD vs `origin/main`. Status ∈ {`current`, `behind`, `ahead`, `diverged`, `wrong_remote`, `no_bundle`}.
2. **Project tier:** current project's `.claude/.plan-foundry-bundle-version` SHA vs the bundle's local HEAD. Status ∈ {`current`, `behind`, `drift`, `not_initialised`, `legacy_symlink`, `unknown`}.

Output is structured JSON with both tiers under `bundle` and `project` keys.

After invocation, report:
- Each tier's `status` and human-readable `message`.
- If bundle is `behind`: the exact `cd ~/.claude/plan_foundry && git pull` command.
- If project is `behind` or `drift`: the exact `/plan-foundry-sync` instruction.
- If project is `legacy_symlink`: the `/init-plan-foundry` instruction to migrate.
- If `wrong_remote` or `no_bundle`: surface the diagnostic so the human can fix the install.
