# Retire a File

## Process

1. **Validate input**: Confirm file path exists and is readable.
2. **Create Retired folder**: If `Retired/` doesn't exist, create it at repo root. **Run from repo root.** Compute `retired_dir` as `$(git rev-parse --show-toplevel)/Retired` - always relative to the repo root, never relative to the source file's parent directory. This anchor is resolved once at skill entry. If `git rev-parse --show-toplevel` fails (git unavailable, or cwd is outside any git worktree), halt immediately with `outcome: exception` - do not fall back to a relative path.
3. **Move file**: Move the target file to `retired_dir/` (computed in Step 2 - repo root `Retired/`). Do NOT use `Path(plan_path).parent / 'Retired'` or any path derived from the source file's location. (Per PLAN-AD0 D2-A 2026-05-22, `Retired/` is a tracked directory - the moved file should be committed as part of the retire change. Do NOT add `Retired/` to `.gitignore`.)
4. **Confirm**: Return success message with source and destination paths.
5. **Self-verify post-condition**: Before returning success, verify all of the following on the actual filesystem. If ANY check fails, return `outcome: exception` with `diagnostics.reason` naming the specific check that failed. Do NOT return success when a post-condition is violated.
   - Source path (original location) no longer exists.
   - Destination path (`Retired/<basename>`) exists.
   - **Destination anchor check:** Confirm the destination path is under `<repo-root>/Retired/` (i.e. the path does NOT begin with `Workbench/Retired/` or any path derived from the source file's parent directory). If this check fails, return `outcome: exception` with a diagnostic message identifying the actual destination path.
   - Destination is readable.
   - Destination file size is non-zero (i.e. body was preserved, not truncated to empty).
   - **Rationale:** the 2026-05-13 retirements lost 3 (or more) PLAN bodies because the subagent executing this skill ran `git rm` instead of `mv` and self-reported success. Per AA2 research (Kubernetes controllers, BFT-MapReduce, RPA orchestrators, AgentFixer 2026): workers self-check locally; orchestrators verify independently. This step is the worker self-check half of the defense-in-depth pattern; plan-pipeline section 4F runs the orchestrator-side check.
6. **Plan note**: When used in a plan, the plan's Executor Notes should include "retire skill invoked on [filename]".

## Examples

**Usage in a skill:**
```
Skill("retire", "old_document.md")
```

**Return:**
```
✓ Retired old_document.md -> Retired/old_document.md
```

**In plan execution:**
The execute-plan skill will note in Executor Notes: "retire skill invoked on old_document.md"