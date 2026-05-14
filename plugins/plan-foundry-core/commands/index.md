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
