---
description: Check whether the locally installed plan_foundry bundle (at ~/.claude/plan_foundry/) is current with origin/main. Reports up-to-date or "behind by N commits — run `cd ~/.claude/plan_foundry && git pull`".
---

Invoke `Skill("plan-foundry-check-current")` and report the result.

The skill runs `lib/check_current.py`, which fetches `origin/main` and compares the bundle's local HEAD against it. Output is structured JSON with `status` ∈ {`current`, `behind`, `ahead`, `diverged`, `wrong_remote`, `no_bundle`}.

After invocation, report:
- `status` and the human-readable `message`
- If `behind`: the exact `cd ~/.claude/plan_foundry && git pull` command to run
- If `wrong_remote` or `no_bundle`: surface the diagnostic so the human can fix the install
