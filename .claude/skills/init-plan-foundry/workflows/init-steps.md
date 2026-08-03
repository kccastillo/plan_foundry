# init-plan-foundry workflow (AC6)

Idempotent nine-step bootstrap. Each step PASSes (the operation landed), SKIPPEDs (already present, no action needed), or FAILs (operation could not complete; report and continue unless explicitly fatal).

Under the AC6 model, the bundle source is fetched on demand from the public URL into a transient `<target>/.plan-foundry-tmp/`. No reliance on any path outside the target - runs in sandboxed Claude Code sessions (mobile, web, restricted desktop) with network access.

## Step 0: Bundle-source self-detection (pre-flight)

Refuses to run if CWD IS the plan_foundry bundle source itself - the bundle source's `.claude/` is real tracked content, not a derived copy. Detect, first hit wins:

1. Basename of `TARGET_ROOT` (= cwd) equals `plan_foundry_dev` or `plan_foundry` -> bundle-source.
2. Else, read `.git/config` from `TARGET_ROOT`. If a remote `origin` URL contains the substring `kccastillo/plan_foundry_dev` or `kccastillo/plan_foundry` (and not as part of a longer name) -> bundle-source.
3. Else, not bundle-source.

If bundle-source: FAIL Step 0 with diagnostic "running init-plan-foundry inside the bundle source itself - this skill is for consumer projects. Bundle development happens directly in the source tree." Abort.

Otherwise: record `TARGET_ROOT = cwd`. PASS.

## Step 1: Clone the bundle into `.plan-foundry-tmp/`

Run via the shared helper:

```python
import sys, pathlib
shared = pathlib.Path(__file__).resolve().parent.parent / "_shared"
sys.path.insert(0, str(shared))
import bundle_fetch
bundle_path = bundle_fetch.clone_bundle(TARGET_ROOT, ref=REF)   # default REF="main"
```

This runs `git clone --depth=1 --branch <ref> https://github.com/kccastillo/plan_foundry <target>/.plan-foundry-tmp/`, removing any stale `.plan-foundry-tmp/` first.

- **Network/auth failure** -> FAIL Step 1 with the error from `git clone`'s stderr. Abort.
- **Wrong ref** (clone succeeds but `.claude/` missing) -> FAIL with diagnostic. Abort.
- **OK** -> record `BUNDLE_PATH` (= `<target>/.plan-foundry-tmp/`). Note also `BUNDLE_OPERATING_RULES_PATH = BUNDLE_PATH / ".claude/skills/init-plan-foundry/operating-rules.md"`. PASS.

## Step 2: Copy bundle content into the target's `.claude/`

Compute `TARGET_CLAUDE = TARGET_ROOT/.claude`; `BUNDLE_CLAUDE = BUNDLE_PATH/.claude`.

The skill must converge to the same end state from four precursor states:

| Precursor | Action |
|---|---|
| `TARGET_CLAUDE` absent | Create the directory; copy bundle-managed paths in. PASS with `precursor=absent`. |
| `TARGET_CLAUDE` is a legacy AC3 symlink (`os.readlink` resolves to something containing `plan_foundry`) | `os.remove(TARGET_CLAUDE)`, then create directory and copy. PASS with `precursor=symlink-legacy` and a "migrated from AC3 symlink" diagnostic. |
| `TARGET_CLAUDE` is a symlink elsewhere, or a broken symlink | FAIL with diagnostic "<target>/.claude is a symlink to {resolved-or-missing}; resolve manually." Abort. |
| `TARGET_CLAUDE` is a real directory | Treat as already-migrated. Copy bundle-managed paths in (overwriting bundle files that differ; preserving project-local content). PASS with `precursor=real-dir` and a list of any bundle-managed files that were overwritten. |

**Copy mechanism.** Use `_shared/bundle_copy.py`:

```python
import bundle_copy
report = bundle_copy.copy_bundle_managed(BUNDLE_CLAUDE, TARGET_CLAUDE)
```

`copy_bundle_managed` copies the four bundle-managed top-level subdirs (`skills/`, `agents/`, `commands/`, `hooks/`) from bundle into target. This step does not remove anything from the target - the receipt-backed quarantine that acts on stale files (PLAN-AH7) is `plan-foundry-sync`'s job, not this skill's: a fresh bootstrap has no prior install receipt to compare against. Returns a `CopyReport`.

**Write the version pin.** After copy, call `bundle_copy.write_version_file(BUNDLE_PATH, TARGET_CLAUDE)` to record bundle commit SHA, tag (if any), and timestamp at `TARGET_CLAUDE/.plan-foundry-bundle-version` (gitignored).

Report Step 2 outcome with `precursor`, file counts, and the recorded version sha.

## Step 3: Ensure `Workbench/` directory

Check if `Workbench/` exists. If absent, create it with a `Workbench/.gitkeep` placeholder - PASS. If present, SKIPPED.

## Step 4: Ensure `Retired/` directory

If absent, create with `Retired/.gitkeep` - PASS. If present, SKIPPED.

## Step 5: Ensure `.gitignore` entries

Read `.gitignore` (create if absent). Bundle-managed paths under `.claude/` and the transient tmp clone are derived state; they MUST NOT be in the target's git history. Project-local files under `.claude/` (everything not under the four bundle-managed dirs) ARE tracked.

Required entries (append any that are absent, on their own line):

```
Workbench/.heartbeat/
.plan-foundry-tmp/
.claude/skills/
.claude/agents/
.claude/commands/
.claude/hooks/
.claude/.plan-foundry-bundle-version
```

Note: per PLAN-AD0 D2-A (2026-05-22), `Retired/` is intentionally tracked (not gitignored) so retired PLAN bodies and rolled-over LOGs survive fresh clones and CI containers.

**Legacy bare-`.claude` entry.** Detect a bare `.claude` line and report its presence; do not auto-remove. The user can remove it in one edit; the bundle gitignore entries above replace it correctly.

If all required entries present and no legacy bare-`.claude` line, SKIPPED. Otherwise PASS.

## Step 6: Ensure target `CLAUDE.md` sentinel block

Read `BUNDLE_OPERATING_RULES_PATH` (from Step 1) and record its content as `OPERATING_RULES_CONTENT`.

Check `CLAUDE.md` in the target root.

**If absent:** Create using `../templates/claude-md-stub.md` (substitute `{{OPERATING_RULES_CONTENT}}`). PASS.

**If present:** Count occurrences of `<!-- plan-foundry:init-plan-foundry:start -->` (`START_COUNT`) and `<!-- plan-foundry:init-plan-foundry:end -->` (`END_COUNT`).

- **`START_COUNT == 0 && END_COUNT == 0`:** Append the sentinel block (with `OPERATING_RULES_CONTENT` in the middle). PASS.
- **`START_COUNT == 1 && END_COUNT == 1` and end-after-start:** Extract current content between markers. If byte-equal to `OPERATING_RULES_CONTENT`, SKIPPED. Otherwise replace and PASS.
- **Any other case:** FAIL with diagnostic "CLAUDE.md sentinel markers are malformed."

Sentinel block format:

```
<!-- plan-foundry:init-plan-foundry:start -->
<!-- WARNING: content between these markers is managed by the plan_foundry init-plan-foundry skill. Re-running the skill replaces everything between the markers with the current operating-rules.md from the bundle. Do not hand-edit between markers - edits will be lost on re-run. -->

{{OPERATING_RULES_CONTENT}}
<!-- plan-foundry:init-plan-foundry:end -->
```

## Step 6b: Merge bundle settings into target settings.json

After the CLAUDE.md sentinel block (Step 6) and **before** cleaning up the tmp clone (Step 7), merge the bundle's declared settings fragment into the target's `settings.json`.

```python
from merge_settings import merge_bundle_settings  # loaded from bundle's _shared/
fragment = BUNDLE_PATH / ".claude" / "skills" / "_shared" / "bundle-settings.json"
target_settings = TARGET_ROOT / ".claude" / "settings.json"
report = merge_bundle_settings(target_settings, fragment)
```

**Non-clobbering contract:**
- For each list under `permissions.*` (e.g. `deny`, `allow`), the fragment's entries are appended only if not already present (order preserved, no duplicates).
- Any pre-existing consumer entries (`allow`, `deny` entries, `hooks`, and all other keys) are never removed, reordered, or mutated.
- If the target `settings.json` is absent, empty, or unparseable, it is treated as `{}` and the result is written from scratch - no raise.
- Running the merge twice is a no-op (idempotent).

**Out of scope:** The bundle-injected `AskUserQuestion` deny is NOT removed by `plan-foundry-uninstall`. Whether uninstall should strip bundle-injected deny entries is a separate design question (see PLAN-AH2 section Out of scope).

PASS if entries were added; SKIPPED if all entries were already present.

## Step 7: Cleanup the tmp clone

```python
bundle_fetch.cleanup_tmp(TARGET_ROOT)
```

Removes `<target>/.plan-foundry-tmp/`. Windows-safe. In a `finally` block so it runs even if Steps 2-6 raised. PASS.

## Step 8: Surface restart notice

Print: "RESTART Claude Code for project-local skills to register. After restart, slash commands like `/init-plan-foundry`, `/plan-foundry-check-current`, `/plan-foundry-sync`, `/plan-foundry-uninstall`, `/test-foundry` will be available; `Skill(\"plan-pipeline\")` etc. will resolve."

## Reporting

Return a `<pipeline-result>` JSON block:
- `outcome`: `success` if no FAILs; `exception` if Step 0, 1, or 2 FAILed.
- `payload.step_results`: object with keys `step_0` through `step_8`, each value `PASS` / `SKIPPED` / `FAIL`.
- `payload.summary`: one-line summary including precursor state and SHA pinned.
- `diagnostics`: per-step notes, including the full `CopyReport` from Step 2.
