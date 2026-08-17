# Retire a File

## Process

1. **Validate input**: Confirm the file path exists and is readable.
2. **Create Retired folder**: If `Retired/` does not exist, create the folder at repo root. **Run from repo root.** Resolve the anchor once at skill entry: first try `$(git rev-parse --show-toplevel)`. If that fails (git unavailable, or cwd is outside any git worktree), walk up from cwd for the nearest ancestor directory containing `.claude/` or `CLAUDE.md` and use that ancestor as the anchor instead. Compute `retired_dir` as `<anchor>/Retired` - always relative to the resolved anchor, never relative to the source file's parent directory. Halt immediately with `outcome: exception` only if neither `git rev-parse --show-toplevel` nor the `.claude/`/`CLAUDE.md` walk-up resolves an anchor - do not fall back to a relative path. (Precedent: `.claude/skills/_shared/push_policy.py`'s `_resolve_repo_root` and `init-plan-foundry/lib/run_install.py` already anchor against project markers when git is unavailable or ambiguous.)
3. **Move file**: Move the target file to `retired_dir/` (computed in Step 2 - repo root `Retired/`). Do not use `Path(plan_path).parent / 'Retired'` or any path derived from the source file's location. (`Retired/` is a tracked directory, so the caller commits the moved file with the retire change. Do not add `Retired/` to `.gitignore`.)
4. **Confirm**: Return success message with source and destination paths.
5. **Self-verify post-condition**: Before returning success, verify all of the following on the filesystem. If any check fails, return `outcome: exception` with `diagnostics.reason` naming the check that failed. Do not return success when a post-condition is violated.
   - Source path (original location) no longer exists.
   - Destination path (`Retired/<basename>`) exists.
   - **Destination anchor check:** Confirm the destination path is under `<repo-root>/Retired/`, meaning the path does not begin with `Workbench/Retired/` or with any path derived from the source file's parent directory. If this check fails, return `outcome: exception` with a diagnostic message naming the destination path that was written.
   - Destination is readable.
   - Destination file size is non-zero, which confirms the body was preserved rather than truncated to empty.
   - **Rationale:** check the filesystem rather than trust the move call. An agent that deletes the file instead of moving it, or that writes an empty destination, can still reach this point believing the retire succeeded, and the body is then unrecoverable from the working tree. Existence and non-zero size are what distinguish a real move from that failure.
6. **Plan note**: When a plan invokes this skill, the plan's Executor Notes should include "retire skill invoked on [filename]".

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
The execute-plan skill records this line in Executor Notes: "retire skill invoked on old_document.md"