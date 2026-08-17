---
name: retire
description: 'Move files to a tracked Retired/ folder when they are no longer needed, redundant, or superseded. Use proactively whenever an artefact has served its purpose - audit docs, temp research, replaced configs, completed working files. Retired/ is a tracked directory, and the caller commits the move with the retire change.'
---

<objective>
Move a file to a tracked `Retired/` folder, removing the file from the active codebase while preserving its body and git history. The caller commits and pushes the move. When a plan invokes this skill, the executor records the invocation in the plan's Executor Notes.
</objective>

<essential_principles>
Move the named file to `<anchor>/Retired/` (anchored at repo root via `git rev-parse --show-toplevel`, or, when git is unavailable, at the nearest ancestor containing `.claude/` or `CLAUDE.md`, and never relative to the source file's parent directory). Do not modify content or invent additional retirements.
The caller commits and pushes, because `retire` never runs git itself.
Wire format: end the response with the literal `<pipeline-result>` containing a JSON code fence. Emit no XML payload and no HTML escaping. The orchestrator text-scans for that block and reads `outcome` out of it to choose the next branch, so a return that omits the block, or wraps it in escaped markup, is unparseable and stalls the pipeline.
</essential_principles>

<quick_start>
Invoke with: `Skill("retire", "path/to/file.md")`

Returns: confirmation that the file has been retired. The caller then commits and pushes.
</quick_start>

**Retirement procedure:** See [workflows/retire-file.md](workflows/retire-file.md)

**Bulk sweep:** `scripts/sweep.py` ships with this skill and retires a whole backlog at once, rather than one named file. Invoke it as `python .claude/skills/retire/scripts/sweep.py <workbench_dir> [--age-days N] [--dry-run]`. It scans `<workbench_dir>` for `*.md` files whose frontmatter carries `status: done` and whose last commit is older than `--age-days` (default 7), falling back to file mtime when the file is untracked, and moves each one to `Retired/`. `--dry-run` lists the eligible files and moves nothing. It exits 0 when nothing is eligible. Two constraints: the script resolves the destination as `Retired/` beside the directory it is given, not by the anchor rule above, so point it at the repo-root `Workbench/` and nowhere else. It runs no git command, so the caller commits the moves exactly as for a single retire.

<success_criteria>
- The file no longer exists in the original location
- The file exists at `<anchor>/Retired/[filename]`, with the destination anchored at repo root via `git rev-parse --show-toplevel`, or, when git is unavailable, at the nearest ancestor containing `.claude/` or `CLAUDE.md`, and never relative to the source file's location
- The file at the destination has non-zero size, so the body was preserved rather than truncated
- `Retired/` is absent from .gitignore, because a retired file stays tracked and the caller commits the move
- Self-verification ran (workflow Step 5), and a post-condition violation returns `outcome: exception` rather than `success`. This is the worker-side half of a two-sided check, and the orchestrator re-verifies the same post-conditions independently in plan-pipeline section 4F, because a subagent is not a reliable narrator of its own side effects
- The confirmation was returned to the user
- If part of plan execution, the plan's Executor Notes record the invocation
</success_criteria>