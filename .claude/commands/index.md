---
description: Regenerate the Workbench INDEX (markdown + JSON) on demand.
---

Invoke `Skill("update-workbench-index")` and report the result.

Regenerates `Workbench/INDEX.md` and `Workbench/.index.json` from the current state of all PLAN files and `.audit/` data in `Workbench/`. Pure projection - idempotent and deterministic. Does not modify any PLAN file.

After invoking the skill, report:
- Whether the regen succeeded or failed
- How many PLANs were indexed
- How many alerts were detected (with a brief summary if any)
- Confirm both output files exist

If the skill returns `outcome: exception`, surface the diagnostics and suggest remediation.

**Direct entrypoint.** For scripted use, call the projector itself:

```bash
python .claude/skills/update-workbench-index/scripts/build_index.py [workbench_dir]
```

There is no longer a combined entrypoint. `regenerate_state.py` existed only to
compose this projector with a second pass over the monthly LOG's Context Inputs
table; that LOG was dissolved 2026-07-28, leaving a wrapper around a single
call. INDEX regeneration is one script again.
