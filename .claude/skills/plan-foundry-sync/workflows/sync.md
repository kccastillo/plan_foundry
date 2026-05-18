# plan-foundry-sync workflow

Pull the latest plan_foundry bundle content into the current project. Five-step procedure; each step PASSes, SKIPPEDs, or FAILs.

## Step 1: Resolve bundle install path

Read `PLAN_FOUNDRY_BUNDLE_PATH` from the environment; default to `~/.claude/plan_foundry/`. Verify the path exists and contains `.claude/skills/init-plan-foundry/operating-rules.md`.

- **Bundle missing** → FAIL with diagnostic "plan_foundry bundle not found at {path} — clone https://github.com/kccastillo/plan_foundry into ~/.claude/plan_foundry first." Abort.
- **OK** → record as `BUNDLE_PATH`. PASS.

## Step 2: Compute target root and validate target state

Target is the current working directory. Validate:

- `<target>/.claude/` exists and is a **real directory** (not a symlink, not absent). If absent or symlink, FAIL with diagnostic "run /init-plan-foundry first — this project has no real bundle copy installed." Abort.
- `<target>/.claude/.plan-foundry-bundle-version` exists. If absent, FAIL with diagnostic "this project has no recorded bundle version — run /init-plan-foundry to migrate from a legacy install." Abort.

Record the existing version's `sha` field as `PREVIOUS_SHA` for the final report.

## Step 3: Copy bundle-managed paths

Call the shared helper:

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(BUNDLE_PATH) / ".claude/skills/_shared"))
import bundle_copy
report = bundle_copy.copy_bundle_managed(
    pathlib.Path(BUNDLE_PATH) / ".claude",
    pathlib.Path(TARGET_ROOT) / ".claude",
)
```

`copy_bundle_managed` copies the four bundle-managed top-level subdirs (`skills/`, `agents/`, `commands/`, `hooks/`) from bundle into target. It never deletes. Returns a `CopyReport` with `files_copied`, `files_unchanged`, `project_additions`, `stale_in_target`.

PASS regardless of whether files were copied — sync is idempotent and reports the no-op case explicitly.

## Step 4: Refresh the version pin

```python
new_version = bundle_copy.write_version_file(
    pathlib.Path(BUNDLE_PATH),
    pathlib.Path(TARGET_ROOT) / ".claude",
)
```

Records `sha`, `tag`, `synced` at `<target>/.claude/.plan-foundry-bundle-version`. PASS.

## Step 5: Report

Emit a structured summary to the human:

```
plan-foundry-sync: <PREVIOUS_SHA[:8]> → <new sha[:8]>
  Files copied:        N
  Files unchanged:     M
  Project additions:   K  (preserved — files under bundle-managed paths but not in the bundle)
  Stale in target:     S  (bundle files no longer upstream — preserved; clean manually if desired)

[if stale_in_target non-empty:]
Stale files:
  - <path>
  - <path>
```

PASS.

## Reporting (wire format)

Return a `<pipeline-result>` JSON block:

```json
{
  "outcome": "success",
  "payload": {
    "previous_sha": "<40-char>",
    "new_sha": "<40-char>",
    "tag": "<exact-match-tag-or-empty>",
    "synced": "<iso8601>",
    "files_copied": [...],
    "files_unchanged_count": N,
    "project_additions": [...],
    "stale_in_target": [...]
  },
  "summary": "synced <prev[:8]> → <new[:8]>: N copied, M unchanged"
}
```

`outcome: exception` if Step 1 or Step 2 FAILed (no usable bundle, or target not initialised).
