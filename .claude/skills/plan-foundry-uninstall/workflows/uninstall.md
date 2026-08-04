# plan-foundry-uninstall workflow

Six-step removal procedure. Each step PASSes, SKIPPEDs (nothing to do), or FAILs (and is reported but does not halt the remaining steps - uninstall is best-effort idempotent).

## Step 1: Remove bundle-managed dirs

Delete (recursively, idempotent) any of these that exist under the target's `.claude/`:

```
.claude/skills/
.claude/agents/
.claude/commands/
.claude/hooks/
```

Use Windows-safe rmtree (clears the readonly bit). Each path that existed and was removed is recorded; absent paths are SKIPPED.

## Step 2: Remove version pin


## Step 3: Reverse `.gitignore` entries

Read `.gitignore`. Remove any of these exact lines if present:

```
Retired/
Workbench/.heartbeat/
.plan-foundry-tmp/
.claude/skills/
.claude/agents/
.claude/commands/
.claude/hooks/
.claude/.plan-foundry-bundle-version
```

Preserve all other lines verbatim. If the resulting `.gitignore` is empty, delete the file.

**First, check who owns the installed `_shared/`.** The entry list comes from `.claude/skills/_shared/gitignore_entries.py`, and a sibling bundle from this lineage installed in the same repo may own that directory. Read `.claude/skills/_shared/bundle-contract.json`'s top-level `bundle` key inline, importing nothing from `_shared/` to do it. If it names a bundle other than `plan_foundry`, skip this step entirely and report it as SKIPPED with the owner named, so the operator removes the entries by hand. Reversing a foreign entry list strips the other bundle's `.gitignore` lines and leaves plan_foundry's behind, which is the inversion of what uninstall is for. An absent, malformed, or key-less contract is the pre-identity state and is trusted. See ARCHITECTURE.md, Invariant: Bundle Namespace Ownership. Every other uninstall step is unaffected - none of them read a `_shared/` helper.

Note: `Workbench/.heartbeat/` is a bundle-managed gitignore entry (init added it), but the directory itself is operator data - it remains on disk. The `Retired/` entry is listed here for cleanup of legacy installs only - since PLAN-AD0 D2-A (2026-05-22) `init-plan-foundry` no longer adds `Retired/` to `.gitignore` (retired artefacts are tracked). On a fresh install that line will not be present; on a legacy install we strip it so the post-uninstall state matches current policy. The directory itself always remains on disk.

## Step 4: Remove the CLAUDE.md sentinel block

Check `CLAUDE.md` exists. If absent, SKIPPED.

Look for the sentinel markers:
- Start: `<!-- plan-foundry:init-plan-foundry:start -->`
- End: `<!-- plan-foundry:init-plan-foundry:end -->`

If both present and well-formed (start before end, exactly one of each):
- Delete the start line, end line, and every line between them (inclusive).
- Also delete one trailing blank line if present (cosmetic).
- Preserve all other CLAUDE.md content verbatim.

If markers absent or malformed: SKIPPED with diagnostic (don't FAIL - file may have been hand-edited).

## Step 5: Cleanup transient state

Remove `.plan-foundry-tmp/` if present (in case a prior install/sync crashed without cleanup).

## Step 6: Report

Emit a structured summary:

```
plan-foundry-uninstall: removed N paths.

Removed:
  - .claude/skills/
  - .claude/agents/
  - ...
  - <N .gitignore lines>
  - CLAUDE.md sentinel block

Kept (operator data - manual cleanup if no longer wanted):
  - Workbench/   (PLAN files, audit records)
  - Retired/     (closed-out artefacts)
  - .claude/settings.local.json   (project-scoped Claude Code config)
  - .claude/plan-foundry.config   (if present)
  - <any other project-local .claude/ file>
```

## Reporting (wire format)

Return a `<pipeline-result>` JSON block:

```json
{
  "outcome": "success",
  "payload": {
    "removed": ["<path>", ...],
    "skipped": ["<path>", ...],
    "kept": ["<path>", ...]
  },
  "summary": "uninstalled plan_foundry; removed N paths; kept Workbench/, Retired/, M project-local files"
}
```

`outcome: success` even if some steps were SKIPPED (nothing to remove is a valid end state). `outcome: exception` only if a delete actually fails on disk.
