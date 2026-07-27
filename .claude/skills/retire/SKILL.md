---
name: retire
description: 'Move files to a tracked Retired/ folder when they are no longer needed, redundant, or superseded. Use proactively whenever an artefact has served its purpose - audit docs, temp research, replaced configs, completed working files. (Retired/ became a tracked directory per PLAN-AD0 D2-A 2026-05-22; the move is committed as part of the retire change.)'
---

<objective>
Move a file to a tracked `Retired/` folder, removing it from the active codebase while preserving its body and git history. Caller is responsible for committing and pushing the move. Plan execution should log that this skill was invoked.
</objective>

<essential_principles>
Move the named file to `<repo-root>/Retired/` (anchored at repo root via `git rev-parse --show-toplevel`; never relative to the source file's parent directory); do not modify content or invent additional retirements.
Caller commits and pushes - `retire` never touches git itself.
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23. No XML payload, no HTML escaping.
</essential_principles>

<quick_start>
Invoke with: `Skill("retire", "path/to/file.md")`

Returns: Confirmation that file has been retired. Caller is responsible for git commit and push.
</quick_start>

**Retirement procedure:** See [workflows/retire-file.md](workflows/retire-file.md)

<success_criteria>
- File no longer exists in original location
- File exists in `<repo-root>/Retired/[filename]` (destination anchored at repo root via `git rev-parse --show-toplevel`; NOT relative to the source file's location)
- File at destination has non-zero size (body preserved, not truncated)
- `Retired/` is NOT in .gitignore (per PLAN-AD0 D2-A 2026-05-22 - retired files are tracked)
- Self-verification ran (workflow Step 5); post-condition violation results in `outcome: exception` not `success` (PLAN-AA2 defense-in-depth pattern; the orchestrator side independently verifies in plan-pipeline section 4F)
- If `log_month >= '202606'`: LOG update is a no-op (slim-LOG era has no Status Table). If `log_month <= '202605'`: LOG Status Table updated per the fat-LOG era legacy path (Status column = `done` or `retired`; Notes column appended with `Retired YYYY-MM-DD via plan-retirer.`) - workflow Step 6 (D-γ fix, hiccup-log-supplement 2026-05-17)
- Confirmation returned to user
- If part of plan execution, plan LOG notes the invocation
</success_criteria>