---
name: retire
description: Move files to a gitignored Retired/ folder when they are no longer needed, redundant, or superseded. Use proactively whenever an artefact has served its purpose — audit docs, temp research, replaced configs, completed working files.
---

<objective>
Move a file to a gitignored `Retired/` folder, removing it from the active codebase while preserving it locally. Caller is responsible for committing and pushing the removal. Plan execution should log that this skill was invoked.
</objective>

<essential_principles>
Move the named file to `Retired/`; do not modify content or invent additional retirements.
Caller commits and pushes — `retire` never touches git itself.
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23. No XML payload, no HTML escaping.
</essential_principles>

<quick_start>
Invoke with: `Skill("retire", "path/to/file.md")`

Returns: Confirmation that file has been retired. Caller is responsible for git commit and push.
</quick_start>

**Retirement procedure:** See [workflows/retire-file.md](workflows/retire-file.md)

<success_criteria>
- File no longer exists in original location
- File exists in `Retired/[filename]`
- File at destination has non-zero size (body preserved, not truncated)
- `Retired/` is in .gitignore
- Self-verification ran (workflow Step 6); post-condition violation results in `outcome: exception` not `success` (PLAN-AA2 defense-in-depth pattern; the orchestrator side independently verifies in plan-pipeline §4F)
- Monthly LOG Status Table row for the retired PLAN reflects retirement (Status column = `done` or `retired`; Notes column appended with `Retired YYYY-MM-DD via plan-retirer.`) — workflow Step 7 (D-γ fix, hiccup-log-supplement 2026-05-17)
- Confirmation returned to user
- If part of plan execution, plan LOG notes the invocation
</success_criteria>