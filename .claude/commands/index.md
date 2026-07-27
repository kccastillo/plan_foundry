---
description: Regenerate the Workbench INDEX (markdown + JSON) on demand.
---

Invoke `Skill("update-workbench-index")` and report the result.

Regenerates `Workbench/INDEX.md` and `Workbench/.index.json` from the current state of all PLAN files and `.audit/` data in `Workbench/`. Pure projection — idempotent and deterministic. Does not modify any PLAN file.

After invoking the skill, report:
- Whether the regen succeeded or failed
- How many PLANs were indexed
- How many alerts were detected (with a brief summary if any)
- Confirm both output files exist

If the skill returns `outcome: exception`, surface the diagnostics and suggest remediation.

**Combined entrypoint (INDEX + Context Inputs).** When you want both the INDEX
and the monthly LOG's Context Inputs table refreshed in one action, use
`scripts/regenerate_state.py` instead:

```bash
python .claude/skills/update-workbench-index/scripts/regenerate_state.py [workbench_dir] [--write]
```

Without `--write` (the default, D3 Option A), it regenerates INDEX and reports
any Context Inputs drift without touching the LOG.  With `--write`, it also
reconciles the LOG's Context Inputs table in place, preserving authored Advises
and Notes cells on surviving rows.  Use this as the standard pre-PR discipline
so the two maintenance actions collapse to one command.
