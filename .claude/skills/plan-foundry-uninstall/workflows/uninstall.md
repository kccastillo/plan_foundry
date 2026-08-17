# plan-foundry-uninstall workflow

The removal procedure below runs its steps in order. Each step PASSes, SKIPPEDs (nothing to do), or FAILs. A FAIL is reported but does not halt the remaining steps, because uninstall is best-effort idempotent.

## Step 1: Remove bundle-managed dirs

Delete (recursively, idempotent) any of these that exist under the target's `.claude/`:

```
.claude/skills/
.claude/agents/
.claude/commands/
.claude/hooks/
```

Use Windows-safe rmtree (clears the readonly bit). Each path that existed and was removed is recorded. Absent paths are SKIPPED.

## Step 2: Remove version pin

Delete the bundle-managed state files and directories under the target's `.claude/`, in the order `_remove_files` uses (`lib/uninstall.py:113-154`):

- `.claude/.plan-foundry-bundle-version` - the version pin, holding the `sha=`, `tag=`, `synced=` and `schema_version=` lines that install and sync write.
- `.claude/.plan-foundry-bundle-files` - the legacy single-file install receipt, superseded by the namespaced receipts below but still read as a fallback while any consumer holds one.
- `.claude/.plan-foundry-sync-incomplete` - the incomplete-sync marker a crashed `/plan-foundry-sync` leaves behind. A target being uninstalled mid-repair must not leave that marker for whatever installs next to trip over.
- `.claude/.plan-foundry-quarantine/` - the whole quarantine tree, holding every timestamped directory sync moved files into when the bundle stopped shipping them.
- `.claude/.bundle-receipts/` - the whole namespaced install-receipt directory, holding `<bundle>.files` for each bundle installed here. Uninstall removes the directory rather than only `plan_foundry.files`, so a sibling bundle's receipt goes with it.

Use the same Windows-safe rmtree as Step 1 for the two directories, and `unlink` for the three files. A path that is not present is a no-op and is not listed in `removed`. A path that survives the attempt is recorded in `failed`, which sets `outcome: exception` for the whole run.

This whole removal pass runs only when the target's `.claude/` exists (`lib/uninstall.py:239-247`). Where `.claude/` is already absent, the run reports `.claude/ (already absent)` under `skipped` and performs no file removal at all.

## Step 3: Reverse `.gitignore` entries

Complete the ownership check described further down this step before removing a single line. `lib/uninstall.py` performs that check when the module is imported (`lib/uninstall.py:52`), which is before Step 1 removes `.claude/skills/`, so the answer is already in hand by the time this step runs and does not depend on a `_shared/` that Step 1 has just deleted.

With the check passed, read `.gitignore` and remove any of these exact lines if present:

```
Retired/
Workbench/.heartbeat/
Workbench/.orchestrator.lock
.plan-foundry-tmp/
.claude/skills/
.claude/agents/
.claude/commands/
.claude/hooks/
.claude/.plan-foundry-bundle-version
.claude/.plan-foundry-bundle-files
.claude/.plan-foundry-quarantine/
.claude/.plan-foundry-sync-incomplete
.claude/.bundle-receipts/
```

That block is a managed inline copy of `REQUIRED_GITIGNORE_ENTRIES` in `_shared/gitignore_entries.py`, prefixed with the `Retired/` line `lib/uninstall.py:73` prepends. The copy stays in place rather than becoming a pointer because Step 1 removes `.claude/skills/`, so the canonical module is off disk by the time a reader would follow the pointer. Realign the block whenever that tuple changes.

Preserve all other lines verbatim. If the resulting `.gitignore` is empty, delete the file.

**The ownership check that precedes the removal.** The entry list comes from `.claude/skills/_shared/gitignore_entries.py`, and a sibling bundle from this lineage installed in the same repo may own that directory. Read `.claude/skills/_shared/bundle-contract.json`'s top-level `bundle` key inline, importing nothing from `_shared/` for that read, and take the reading before Step 1 deletes `.claude/skills/`. If that key names a bundle other than `plan_foundry`, skip this step entirely and report this step as SKIPPED with the owner named, so the operator removes the entries by hand. Reversing a foreign entry list strips the other bundle's `.gitignore` lines and leaves plan_foundry's behind, which is the inversion of what uninstall is for. An absent, malformed, or key-less contract is the pre-identity state and is trusted. See ARCHITECTURE.md, Invariant: Bundle Namespace Ownership. Every other uninstall step is unaffected - none of them read a `_shared/` helper.

`Workbench/.heartbeat/` is a bundle-managed gitignore entry (`init-plan-foundry` added the entry), but the directory itself is operator data, so the directory remains on disk. The `Retired/` entry is listed here for cleanup of legacy installs only - since PLAN-AD0 D2-A (2026-05-22) `init-plan-foundry` no longer adds `Retired/` to `.gitignore` (retired artefacts are tracked). On a fresh install that line will not be present. On a legacy install uninstall strips the line so the post-uninstall state matches current policy. The `Retired/` directory itself always remains on disk.

## Step 4: Remove the CLAUDE.md sentinel block

Check `CLAUDE.md` exists. If absent, SKIPPED.

Look for the sentinel markers:
- Start: `<!-- plan-foundry:init-plan-foundry:start -->`
- End: `<!-- plan-foundry:init-plan-foundry:end -->`

If both present and well-formed (start before end, exactly one of each):
- Delete the start line, end line, and every line between them (inclusive).
- Also delete one trailing blank line if present (cosmetic).
- Preserve all other CLAUDE.md content verbatim.

If markers absent or malformed: SKIPPED with diagnostic (do not FAIL, because the file may have been hand-edited).

## Step 5: Cleanup transient state

Remove `.plan-foundry-tmp/` if present (in case a prior install/sync crashed without cleanup).

`lib/uninstall.py` removes this path inside the same `_remove_files` pass as Step 2 (`lib/uninstall.py:148-153`), so the condition recorded in Step 2 applies here too: a target whose `.claude/` is already absent keeps a stray `.plan-foundry-tmp/`.

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
  - .claude/writing-style-local.md   (project-local style supplement, if present)
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
    "kept": ["<path>", ...],
    "failed": ["<path>", ...]
  },
  "summary": "uninstalled plan_foundry; removed N path(s); kept M operator-data path(s)"
}
```

`outcome: success` even if some steps were SKIPPED (nothing to remove is a valid end state). `outcome: exception` if a delete fails on disk - a path survives after the readonly-bit retry, or the version pin / receipt file cannot be unlinked. The `failed` payload key is only present when non-empty and lists every path that could not be removed, by the same relative form used in `removed`.
