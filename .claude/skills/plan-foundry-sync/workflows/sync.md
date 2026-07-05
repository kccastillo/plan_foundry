# plan-foundry-sync workflow (AC6)

Pull the latest plan_foundry bundle content into the current project via on-demand network clone. Six-step procedure; each step PASSes, SKIPPEDs, or FAILs.

## Step 1: Validate target state

Target root is the current working directory. Validate:

- `<target>/.claude/` exists and is a **real directory** (not a symlink, not absent). If absent or symlink, FAIL with diagnostic "run /init-plan-foundry first — this project has no real bundle copy installed." Abort.
- `<target>/.claude/.plan-foundry-bundle-version` exists. If absent, FAIL with diagnostic "this project has no recorded bundle version — run /init-plan-foundry first." Abort.

Record the existing version's `sha` field as `PREVIOUS_SHA` for the final report.

## Step 2: Clone the bundle on demand

Run via the shared helper:

```python
import sys, pathlib
shared = pathlib.Path(__file__).resolve().parent.parent.parent / "_shared"
sys.path.insert(0, str(shared))
import bundle_fetch
bundle_path = bundle_fetch.clone_bundle(TARGET_ROOT, ref=REF)   # default REF="main"
```

This runs `git clone --depth=1 --branch <ref> https://github.com/kccastillo/plan_foundry <target>/.plan-foundry-tmp/`, removing any stale `.plan-foundry-tmp/` first.

- **Network/auth failure** → FAIL with the error from `git clone`'s stderr. Abort.
- **Wrong ref** (clone succeeds but `.claude/` missing in clone) → FAIL with diagnostic. Abort.
- **OK** → record `bundle_path` (= `<target>/.plan-foundry-tmp/`). PASS.

## Step 3: Copy bundle-managed paths

```python
import bundle_copy
report = bundle_copy.copy_bundle_managed(
    bundle_path / ".claude",
    pathlib.Path(TARGET_ROOT) / ".claude",
)
```

Copies the four bundle-managed subdirs (`skills/`, `agents/`, `commands/`, `hooks/`) from the tmp clone into the target's `.claude/`. Never deletes. Returns a `CopyReport` with `files_copied`, `files_unchanged`, `project_additions`, `stale_in_target`.

PASS regardless of whether files were copied — sync is idempotent.

## Step 4: Refresh the version pin

```python
new_version = bundle_copy.write_version_file(
    bundle_path,
    pathlib.Path(TARGET_ROOT) / ".claude",
)
```

Records `sha`, `tag`, `synced` at `<target>/.claude/.plan-foundry-bundle-version` (gitignored). PASS.

## Step 4b: Refresh the CLAUDE.md operating-rules block

After copying bundle-managed paths and refreshing the version pin (Steps 3–4), and **before** cleaning up the tmp clone (Step 5), read `operating-rules.md` from the freshly-cloned bundle and apply the sentinel-block logic to the host project's `CLAUDE.md`:

```python
operating_rules_path = bundle_path / ".claude" / "skills" / "init-plan-foundry" / "operating-rules.md"
operating_rules = operating_rules_path.read_text(encoding="utf-8")
cmd_status, cmd_note = claude_md_block.apply_operating_rules_block(target_root, operating_rules)
```

Behaviour:

- **Markers present (normal case):** The content between `<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->` is replaced with the bundle's current `operating-rules.md` text. All host-authored content outside the markers is preserved verbatim. Returns `("PASS", "replaced-block")` or `("SKIPPED", "already current")` if the block body already matches.
- **Markers absent:** The sentinel block is appended to the existing `CLAUDE.md` with an appropriate separator. Returns `("PASS", "appended-block")`.
- **CLAUDE.md absent:** A stub `CLAUDE.md` is created containing a header and the sentinel block. Returns `("PASS", "created")`.
- **Malformed markers (end before start, or duplicate markers):** Returns `("FAIL", <reason>)` **without writing the file** — the host `CLAUDE.md` is left byte-for-byte unchanged. This is non-destructive and retry-safe: the bundle-managed dirs and version pin are already updated (idempotent operations); the operator fixes their `CLAUDE.md` markers and re-runs sync.
- **operating-rules.md absent in bundle** (old bundle predating this feature): treated as `("SKIPPED", "operating-rules.md absent in bundle")` — not a crash.

`cmd_status`/`cmd_note` are recorded in `payload["claude_md"]` and appended to `result["diagnostics"]` and the `summary` string. If `cmd_status == "FAIL"`, sync surfaces `outcome: exception` to alert the operator.

This step runs inside the `try` block that guards the `finally: cleanup_tmp()`, so the bundle is still on disk when `operating-rules.md` is read.

## Step 5: Clean up the tmp clone

```python
bundle_fetch.cleanup_tmp(TARGET_ROOT)
```

Removes `<target>/.plan-foundry-tmp/`. Windows-safe (clears the readonly bit on git's pack files). The cleanup is in a `finally` block so it runs even if Step 3 or 4 raised. PASS.

## Step 6: Report

Emit a structured summary to the human:

```
plan-foundry-sync: <PREVIOUS_SHA[:8]> → <new sha[:8]> (ref=<ref>)
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
    "ref": "main",
    "previous_sha": "<40-char>",
    "new_sha": "<40-char>",
    "tag": "<exact-match-tag-or-empty>",
    "synced": "<iso8601>",
    "files_copied": [...],
    "files_unchanged_count": N,
    "project_additions": [...],
    "stale_in_target": [...]
  },
  "summary": "synced <prev[:8]> → <new[:8]> (ref=<ref>): N copied, M unchanged"
}
```

`outcome: exception` if Step 1 FAILed (target not initialised) or Step 2 FAILed (clone error).

## Notes

- **Tag pinning.** `/plan-foundry-sync v0.5.0` passes `ref=v0.5.0` to the clone.
- **Crashed prior run.** If `.plan-foundry-tmp/` already exists when sync starts (from a crashed prior run), Step 2 removes it before cloning.
- **Network required.** No offline fallback. If the user is offline, the operation cleanly fails — uninstall remains available since it is local-only.
