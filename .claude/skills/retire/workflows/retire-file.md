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
6. **Update monthly LOG** (D-γ fix, 2026-05-17 hiccup-log-supplement; conditionalised per PLAN-AB9 D6, 2026-05-23): when retiring a PLAN file matching `Workbench/PLAN-*.md`, **first read the PLAN's `log_month` frontmatter** (default = current month YYYYMM if absent).
   - **Gate (AB9 D6 — slim-LOG cutover 2026-06-01):** if `log_month` ≥ `202606`, this whole step is a **no-op** — the June 2026 LOG and every LOG thereafter is slim and has no Status Table to update. INDEX.md and the PLAN's frontmatter `status` are canonical for retired-state. (String-compare on the YYYYMM literal — `"202605" <= "202606"` etc. — sorts correctly across the year-end boundary, e.g. `"202612" < "202701"`, so no calendar arithmetic is needed.)
   - **Legacy path** — proceed only if `log_month` ≤ `202605` (fat-LOG era). Update the corresponding row in the monthly LOG (`Workbench/{YYYYMM}010000_LOG_{YYYYMM}.md`):
     - Find the row in the LOG's Status Table whose first column matches the retired PLAN's filename (before move).
     - Update the Status column (column 5) to `done` (or `retired` if the PLAN's frontmatter `status` was already terminal-but-not-done, e.g. `cancelled`).
     - Append to the Notes column (column 6): `Retired YYYY-MM-DD via plan-retirer.` (or `... via manual retire.` if the skill was invoked outside the plan-retirer agent).
     - If no row exists (PLAN was authored outside the LOG-tracking flow), add a new row at the top of the Status Table with the appropriate fields.
   - **Rationale (D-γ):** plan-retirer was returning success without updating the LOG, leaving the LOG Status Table showing the retired PLAN's prior pre-retire state. The audit trail for "what happened to PLAN X" then required reading commit history rather than the LOG. The LOG is the foundry's canonical row-state record for the fat-LOG era; retiring without updating it broke the contract.
   - **Rationale (AB9 D6 cutover):** from `log_month ≥ 202606` onward, the slim-LOG contract drops the Status Table entirely (PLAN-AB9 D1 + ADVICE-006 §3). INDEX is canonical for active and recently-retired state; PLAN frontmatter is canonical for `status`. There is no Status Table row to update, so the LOG-update step has nothing to do — it is intentionally a no-op rather than a misfire.
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