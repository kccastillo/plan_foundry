# init-plan-foundry workflow

Idempotent nine-step bootstrap. Each step PASSes (the operation landed), SKIPPEDs (already present, no action needed), or FAILs (operation could not complete; report and continue).

## Step 1: Resolve bundle install path

Read `PLAN_FOUNDRY_BUNDLE_PATH` from the environment; default to `~/.claude/plan_foundry/` (expanduser). Verify the path exists and contains `.claude/skills/init-plan-foundry/operating-rules.md`.

- **Bundle missing or operating-rules.md absent** → FAIL Step 1 with diagnostic "plan_foundry bundle not found at {path} — clone https://github.com/kccastillo/plan_foundry into ~/.claude/plan_foundry first." Abort.
- **OK** → record the absolute path as `BUNDLE_PATH` and the operating-rules.md path as `BUNDLE_OPERATING_RULES_PATH`. PASS.

## Step 2: Compute target repo root and detect bundle-source

The current working directory IS the target repo root. Record as `TARGET_ROOT`.

**Bundle-source detection (per PLAN-AC5 D8).** If the current target IS the bundle source itself, this skill should not run — the bundle source's `.claude/` is real tracked content, not a derived copy. Detect, first hit wins:

1. Basename of `TARGET_ROOT` equals `plan_foundry_dev` or `plan_foundry` → bundle-source.
2. Else, read `.git/config` from `TARGET_ROOT`. If a remote `origin` URL contains the substring `kccastillo/plan_foundry_dev` or `kccastillo/plan_foundry` (and not as part of a longer name) → bundle-source.
3. Else, not bundle-source.

If bundle-source: FAIL Step 2 with diagnostic "running init-plan-foundry inside the bundle source itself — this skill is for consumer projects. Bundle development happens directly in the source tree." Abort.

Otherwise: PASS.

## Step 3: Copy bundle content into the target's `.claude/`

Compute `TARGET_CLAUDE = TARGET_ROOT/.claude`; `BUNDLE_CLAUDE = BUNDLE_PATH/.claude`.

The skill must converge to the same end state from four precursor states (per PLAN-AC5 D5):

| Precursor | Action |
|---|---|
| `TARGET_CLAUDE` absent | Create the directory; copy bundle-managed paths in. PASS with `precursor=absent`. |
| `TARGET_CLAUDE` is a symlink whose `os.readlink` resolves (after `os.path.realpath`) to `BUNDLE_CLAUDE` | Read symlink, `os.remove(TARGET_CLAUDE)`, then create directory and copy. PASS with `precursor=symlink-legacy` and a "migrated from AC3 symlink" diagnostic. |
| `TARGET_CLAUDE` is a symlink resolving elsewhere, or a broken symlink (target absent) | FAIL with diagnostic "<target>/.claude is a symlink to {resolved-or-missing}; expected {BUNDLE_CLAUDE}. Resolve manually." Abort. |
| `TARGET_CLAUDE` is a real directory | Treat as already-migrated. Copy bundle-managed paths in (overwriting bundle files that differ; preserving project-local content). PASS with `precursor=real-dir` and a list of any bundle-managed files that were overwritten (for user awareness). |

**Copy mechanism.** Use the shared helper at `.claude/skills/_shared/bundle_copy.py`:

```python
import sys
sys.path.insert(0, str(BUNDLE_PATH / ".claude/skills/_shared"))
import bundle_copy
report = bundle_copy.copy_bundle_managed(BUNDLE_CLAUDE, TARGET_CLAUDE)
```

`copy_bundle_managed` copies the four bundle-managed top-level subdirs (`skills/`, `agents/`, `commands/`, `hooks/`) from bundle into target. It never deletes from target. Returns a `CopyReport` with:
- `files_copied`: bundle files newly written or overwritten (divergent content)
- `files_unchanged`: bundle files identical in target (no I/O)
- `project_additions`: files in target's bundle-managed paths whose parent subdir is NOT in the bundle (project's own skills/agents — preserved)
- `stale_in_target`: files in target's bundle-managed paths whose parent subdir IS in the bundle but the file is not (likely renamed/dropped upstream — preserved, listed for user awareness per D9)

**Write the version pin.** After copy, call `bundle_copy.write_version_file(BUNDLE_PATH, TARGET_CLAUDE)` to record bundle commit SHA, tag (if any), and sync timestamp at `TARGET_CLAUDE/.plan-foundry-bundle-version`. The file is one source of truth for "what version is this project running"; never inferred from file contents.

Report Step 3 outcome with `precursor`, `files_copied`/`files_unchanged`/`project_additions`/`stale_in_target` counts, and the recorded version sha.

## Step 4: Ensure Workbench/ directory

Check if `Workbench/` exists in the target root. If absent, create it (use Write tool with a `Workbench/.gitkeep` placeholder to materialise the directory) — PASS. If present, SKIPPED.

## Step 5: Ensure current-month LOG file

Read `Workbench/` and look for any file matching `*_LOG_YYYYMM.md` where `YYYYMM` is the current year-month. If present, SKIPPED. If absent, create `Workbench/YYYYMMDDHHMI_LOG_YYYYMM.md` (using current timestamp) with this exact body:

```
---
title: "[Project Name] Work Log — [Month Year]"
type: log
month: YYYY-MM
status: open
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
---

## Status Table

| Plan File | Title | Assigned | Priority | Status | Due |
|---|---|---|---|---|---|

## Recurring Task Tracker

| Task | Slug | Cadence | Last Done | Next Due | Status |
|---|---|---|---|---|---|

## Context Inputs This Month

| Input File | Type | From | Feeds Plan | Integrated? |
|---|---|---|---|---|

## Lessons Learned

_(none carried forward)_
```

Replace `YYYY-MM`, `YYYY-MM-DD` placeholders with the current date. PASS.

## Step 6: Ensure Retired/ directory

Check if `Retired/` exists. If absent, create it with a `Retired/.gitkeep` placeholder — PASS. If present, SKIPPED.

## Step 7: Ensure .gitignore entries

Read `.gitignore` (create if absent). Bundle-managed paths under `.claude/` are derived state (regenerable via `/plan-foundry-sync`); they should NOT be in the target's git history. Project-local files under `.claude/` (everything not under the four bundle-managed dirs) ARE tracked.

Required entries (append any that are absent, on their own line):

```
Retired/
Workbench/.heartbeat/
.claude/skills/
.claude/agents/
.claude/commands/
.claude/hooks/
.claude/.plan-foundry-bundle-version
.claude/_foundry_log.jsonl
```

**Legacy bare-`.claude` entry.** A pre-AC5 install path (or the AC3 symlink era) may have left a bare `.claude` line in the target's `.gitignore`. Step 7 detects a bare `.claude` line (not `.claude/skills/` etc., just literally `.claude` or `.claude/`) and reports its presence in the diagnostic, **but does not auto-remove it** — leaving it in place blanket-gitignores everything under `.claude/`, including project-local files the user may want tracked. The skill surfaces a "consider removing the bare `.claude` line and using path-specific entries" note; user-removable in one edit.

If all required entries already present and no legacy bare-`.claude` line exists, SKIPPED. Otherwise PASS with a diagnostic listing entries added and any legacy line detected.

## Step 8: Ensure target CLAUDE.md awareness (inline content between sentinel markers)

First, read `BUNDLE_OPERATING_RULES_PATH` (from Step 1) and record its full content as `OPERATING_RULES_CONTENT`.

Then check if `CLAUDE.md` exists in the target root.

**If absent:** Create `CLAUDE.md` using the template at `../templates/claude-md-stub.md` (read the template, substitute `{{OPERATING_RULES_CONTENT}}` with `OPERATING_RULES_CONTENT`, write the result to `CLAUDE.md`). PASS.

**If present:** Read the file. Count occurrences of `<!-- plan-foundry:init-plan-foundry:start -->` (call it `START_COUNT`) and `<!-- plan-foundry:init-plan-foundry:end -->` (call it `END_COUNT`).

- **If `START_COUNT == 0` AND `END_COUNT == 0`** (sentinels absent): Append the following block to the end of the file (preserve a leading blank line if the file does not already end with one):

  ```

  <!-- plan-foundry:init-plan-foundry:start -->
  <!-- WARNING: content between these markers is managed by the plan_foundry init-plan-foundry skill. Re-running the skill replaces everything between the markers with the current operating-rules.md from the bundle. Do not hand-edit between markers — edits will be lost on re-run. -->

  {{OPERATING_RULES_CONTENT}}
  <!-- plan-foundry:init-plan-foundry:end -->
  ```

  Substitute `{{OPERATING_RULES_CONTENT}}` with the content read above. PASS.

- **If `START_COUNT == 1` AND `END_COUNT == 1` AND end appears AFTER start** (sentinels well-formed): Extract the current content between the start and end markers (exclusive of the marker lines themselves). Strip one leading newline and one trailing newline. Compare byte-for-byte to `OPERATING_RULES_CONTENT`. If equal, SKIPPED. Otherwise replace the between-markers content with `OPERATING_RULES_CONTENT`. PASS.

- **Any other case** (`START_COUNT != 1` OR `END_COUNT != 1` OR end appears BEFORE start): FAIL with diagnostic "CLAUDE.md sentinel markers are malformed (START_COUNT=N, END_COUNT=M); manual repair required."

## Step 9: Surface restart notice

Print to the human: "RESTART Claude Code for project-local skills to register. After restart, slash commands like `/init-plan-foundry`, `/plan-foundry-check-current`, `/plan-foundry-sync`, `/test-foundry` will be available; `Skill(\"plan-pipeline\")` etc. will resolve."

## Reporting

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` if no FAILs; `exception` if Step 1, 2, or 3 FAILed (skill cannot proceed without the bundle path / non-bundle-source target / writable `.claude` with valid precursor state).
- `payload.step_results`: object with keys `step_1` through `step_9`, each value one of `PASS` / `SKIPPED` / `FAIL`.
- `payload.summary`: one-line human-readable summary including precursor state for Step 3 (e.g. "Step 3 PASSED from precursor=symlink-legacy: 47 files copied, version pinned to abc1234").
- `diagnostics`: any per-step diagnostic notes, including the full `CopyReport` from Step 3 (`stale_in_target` list, `project_additions` count) so the user can spot drift.
