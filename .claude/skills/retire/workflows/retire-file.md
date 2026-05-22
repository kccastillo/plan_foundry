# Retire a File

## Process

1. **Validate input**: Confirm file path exists and is readable.
2. **Create Retired folder**: If `Retired/` doesn't exist, create it at repo root.
3. **Move file**: Move the target file to `Retired/` preserving filename and relative structure where reasonable. (Per PLAN-AD0 D2-A 2026-05-22, `Retired/` is a tracked directory — the moved file should be committed as part of the retire change. Do NOT add `Retired/` to `.gitignore`.)
4. **Confirm**: Return success message with source and destination paths.
5. **Self-verify post-condition**: Before returning success, verify all of the following on the actual filesystem. If ANY check fails, return `outcome: exception` with `diagnostics.reason` naming the specific check that failed. Do NOT return success when a post-condition is violated.
   - Source path (original location) no longer exists.
   - Destination path (`Retired/<basename>`) exists.
   - Destination is readable.
   - Destination file size is non-zero (i.e. body was preserved, not truncated to empty).
   - **Rationale:** the 2026-05-13 retirements lost 3 (or more) PLAN bodies because the subagent executing this skill ran `git rm` instead of `mv` and self-reported success. Per AA2 research (Kubernetes controllers, BFT-MapReduce, RPA orchestrators, AgentFixer 2026): workers self-check locally; orchestrators verify independently. This step is the worker self-check half of the defense-in-depth pattern; plan-pipeline §4F runs the orchestrator-side check.
6. **Update monthly LOG** (D-γ fix, 2026-05-17 hiccup-log-supplement): when retiring a PLAN file matching `Workbench/PLAN-*.md`, update the corresponding row in the monthly LOG (`Workbench/{YYYYMM}010000_LOG_{YYYYMM}.md` where YYYYMM matches the PLAN's `log_month` frontmatter; default = current month if absent):
   - Find the row in the LOG's Status Table whose first column matches the retired PLAN's filename (before move).
   - Update the Status column (column 5) to `done` (or `retired` if the PLAN's frontmatter `status` was already terminal-but-not-done, e.g. `cancelled`).
   - Append to the Notes column (column 6): `Retired YYYY-MM-DD via plan-retirer.` (or `... via manual retire.` if the skill was invoked outside the plan-retirer agent).
   - If no row exists (PLAN was authored outside the LOG-tracking flow), add a new row at the top of the Status Table with the appropriate fields.
   - **Rationale:** D-γ (Reeve traceback 2026-05-17): plan-retirer was returning success without updating the LOG, leaving the LOG Status Table showing the retired PLAN's prior pre-retire state. The audit trail for "what happened to PLAN X" then required reading commit history rather than the LOG. The LOG is the foundry's canonical row-state record; retiring without updating it breaks the contract.
7. **Plan note**: When used in a plan, the plan execution log should include "retire skill invoked on [filename]".

## Examples

**Usage in a skill:**
```
Skill("retire", "old_document.md")
```

**Return:**
```
✓ Retired old_document.md → Retired/old_document.md
```

**In plan execution:**
The execute-plan skill will note in Executor Notes: "retire skill invoked on old_document.md"