# init-plan-foundry workflow (AC6)

The bootstrap procedure below is idempotent. Each step PASSes (the operation landed), SKIPPEDs (already present, no action needed), or FAILs (the operation could not complete, and the step is reported before the run continues unless the step is explicitly fatal).

Under the AC6 model, the bundle source is fetched on demand from the public URL into a transient `<target>/.plan-foundry-tmp/`. Bootstrap relies on no path outside the target, so bootstrap runs in sandboxed Claude Code sessions (mobile, web, restricted desktop) that have network access.

## Step 0: Bundle-source self-detection (pre-flight)

Bootstrap refuses to run when CWD is the plan_foundry bundle source itself, because the bundle source's `.claude/` is real tracked content rather than a derived copy. Detect the bundle source with these signals, first hit wins:

1. Basename of `TARGET_ROOT` (= cwd) equals `plan_foundry_dev` or `plan_foundry` -> bundle-source.
2. Else, read `.git/config` from `TARGET_ROOT`. If a remote `origin` URL contains the substring `kccastillo/plan_foundry_dev` or `kccastillo/plan_foundry` (and not as part of a longer name) -> bundle-source.
3. Else, not this bundle's source.

Then check for a *foreign* bundle - one that is not ours. The name matching above only catches our own repo, so a target shipping a different bundle passes the name check. `preflight.detect_foreign_bundle(TARGET_ROOT, BUNDLE_PATH)` returns a diagnostic when either signal fires, first hit wins:

1. The target carries `.claude/skills/_shared/bundle-contract.json` and its bytes differ from the incoming bundle's. Two contract files mean two bundles are installed.
2. Git tracks files under `.claude/{skills,agents,commands,hooks}`. A consumer gitignores those paths, whereas a repo that tracks them owns that content as source.

If foreign: FAIL Step 0 with the returned `foreign-bundle-detected: ...` diagnostic and abort. Bootstrap fails open on a missing git or a non-repo target, because signal 2 cannot be evaluated there and so never fires. This check exists because paper_trail_dev passed the name check and would have had its tracked product overwritten (PLAN-AJ6 D3).

If bundle-source: FAIL Step 0 with diagnostic "running init-plan-foundry inside the bundle source itself - this skill is for consumer projects. Bundle development happens directly in the source tree." Abort.

Otherwise: record `TARGET_ROOT = cwd`. PASS.

## Step 0b: Repository-presence check (advisory)

Bootstrap runs `git rev-parse --is-inside-work-tree` in `TARGET_ROOT`,
before any of `Workbench/`, `Retired/` or `.gitignore` reaches the target.
The check is advisory only, never fails the bootstrap, and never runs
`git init` on the consumer's behalf.

- **`true`** -> PASS. Bootstrap also runs `git rev-parse --show-toplevel`
  to distinguish `TARGET_ROOT` being the repository root itself from being
  a subdirectory of an enclosing repository. Either case is a PASS, because
  an enclosing repository still gives commits somewhere to attach to, and
  the diagnostic note names which case applies.
- **Anything else (non-zero exit, no git on `PATH`, unexpected output)**
  -> SKIPPED, with a diagnostic naming the missing repository and its
  concrete cost: commits, retire history and the durability pass have
  nothing to attach to.

This closes the repository-absence failure mode named in
FOUNDRYREQ-horse-chestnut-brickhouse-20260805-1707-nothing-checks-that-session-material-landed-somewhere-durable
(the cheapest of the report's failure modes, and checkable before a single
file is scaffolded). The report's other failure modes are named
follow-on work rather than built here: a session-end tracked-and-committed
scan (candidate host `handoff-next-session`, with the open question being
which files count as "this session's" and how staleness is scanned without
asking the executing agent to self-report), and a paste-in capture prompt
(no candidate host, and the prompt fires at a conversational moment rather
than a filesystem-scannable one).

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

Compute `TARGET_CLAUDE = TARGET_ROOT/.claude` and `BUNDLE_CLAUDE = BUNDLE_PATH/.claude`.

The skill must converge to the same end state from every precursor state in the table below:

| Precursor | Action |
|---|---|
| `TARGET_CLAUDE` absent | Create the directory, then copy bundle-managed paths in. PASS with `precursor=absent`. |
| `TARGET_CLAUDE` is a legacy AC3 symlink (`os.readlink` resolves to something containing `plan_foundry`) | `os.remove(TARGET_CLAUDE)`, then create directory and copy. PASS with `precursor=symlink-legacy` and a "migrated from AC3 symlink" diagnostic. |
| `TARGET_CLAUDE` is a symlink elsewhere, or a broken symlink | FAIL with diagnostic "<target>/.claude is a symlink to {resolved-or-missing}; resolve manually." Abort. |
| `TARGET_CLAUDE` is a real directory | Treat as already-migrated. Copy bundle-managed paths in (overwriting bundle files that differ while preserving project-local content). PASS with `precursor=real-dir` and a list of any bundle-managed files that were overwritten. |

**Copy mechanism.** Use `_shared/bundle_copy.py`:

```python
import bundle_copy
contract = bundle_copy.read_bundle_contract(BUNDLE_PATH)
report = bundle_copy.copy_bundle_managed(
    BUNDLE_CLAUDE, TARGET_CLAUDE, deprecations=contract.get("deprecations", [])
)
```

`copy_bundle_managed` copies the bundle-managed top-level subdirs `skills/`, `agents/`, `commands/` and `hooks/` from bundle into target. This step does not remove anything from the target - the receipt-backed quarantine that acts on stale files (PLAN-AH7) is `plan-foundry-sync`'s job, not this skill's: a fresh bootstrap has no prior install receipt to compare against. `copy_bundle_managed` returns a `CopyReport`.

Passing `deprecations` stops the copy from writing a deprecation shim over a destination that exists and is not itself a shim. Those paths are recorded in `report.shim_skipped` and must be surfaced. A shim advertising a successor product must never overwrite the successor, which is exactly what installing this bundle into that successor's own source repo would otherwise do (PLAN-AJ6 D1).

**Write the version pin.** After copy, call `bundle_copy.write_version_file(BUNDLE_PATH, TARGET_CLAUDE)` to record bundle commit SHA, tag (if any), and timestamp at `TARGET_CLAUDE/.plan-foundry-bundle-version` (gitignored).

Report Step 2 outcome with `precursor`, file counts, and the recorded version sha.

## Step 3: Ensure `Workbench/` directory

Check if `Workbench/` exists. If absent, create it with a `Workbench/.gitkeep` placeholder - PASS. If present, SKIPPED.

## Step 5: Ensure `Retired/` directory

If absent, create with `Retired/.gitkeep` - PASS. If present, SKIPPED.

## Step 6: Ensure `.gitignore` entries

Read `.gitignore` (create if absent). Bundle-managed paths under `.claude/` and the transient tmp clone are derived state, and they MUST NOT be in the target's git history. Project-local files under `.claude/` (everything not under `skills`, `agents`, `commands` and `hooks`) are tracked.

The required entries are `REQUIRED_GITIGNORE_ENTRIES` in `_shared/gitignore_entries.py`. Read the tuple there rather than from a copy: a restated copy is what drifted out of date before. `ensure_gitignore_entries` in the same module performs the append, and the append is non-clobbering, append-only and idempotent, adding each absent entry on its own line and leaving every existing line alone.

`ensure_gitignore_entries` first passes the list through `filter_tracked`, which drops any entry with git-tracked content beneath it and returns those as `skipped_tracked`. A dropped entry means the target owns that path, so a repo that ships its own `.claude/` content is not silently untracked by an install. Surface the dropped entries as a diagnostic - they are never written.

Note: per PLAN-AD0 D2-A (2026-05-22), `Retired/` is intentionally tracked (not gitignored) so retired PLAN bodies and rolled-over LOGs survive fresh clones and CI containers, which is why `Retired/` is absent from that tuple.

**Legacy bare-`.claude` entry.** Detect a bare `.claude` line and report its presence, but do not auto-remove that line. The user can remove the bare line in one edit, and the bundle gitignore entries above replace the bare line correctly.

PASS if any entry was appended, otherwise SKIPPED. A legacy bare-`.claude` line adds a diagnostic and never changes the step status.

## Step 6b: Pin `.gitattributes` line endings

Ensure the target's `.gitattributes` pins line endings for bundle-managed hook scripts, so a hook is never shipped CRLF-mangled. PASS if an entry was added. SKIPPED if the entry is already present.

## Step 6c: Merge `core.hooksPath`

Read and, if needed, write the target's `core.hooksPath` git config so the bundle's hooks directory is wired in. Step 6c must run after Step 6b, because wiring hooks before the line-ending pin is in place would ship a CRLF-mangled hook that fails on every Windows consumer while exiting 0, which makes broken and working look identical. PASS if the config was written. SKIPPED if the config is already correct.

## Step 7: Ensure target `CLAUDE.md` sentinel block

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

## Step 7b: Merge bundle settings into target settings.json

After the CLAUDE.md sentinel block (Step 7) and **before** cleaning up the tmp clone (Step 8), merge the bundle's declared settings fragment into the target's `settings.json`.

```python
from merge_settings import merge_bundle_settings  # loaded from bundle's _shared/
fragment = BUNDLE_PATH / ".claude" / "skills" / "_shared" / "bundle-settings.json"
target_settings = TARGET_ROOT / ".claude" / "settings.json"
report = merge_bundle_settings(target_settings, fragment)
```

**Non-clobbering contract:**
- For each list under `permissions.*` (e.g. `deny`, `allow`), the fragment's entries are appended only if not already present (order preserved, no duplicates).
- Any pre-existing consumer entries (`allow`, `deny` entries, `hooks`, and all other keys) are never removed, reordered, or mutated.
- If the target `settings.json` is absent, empty, or unparseable, the merge treats the file as `{}` and writes the result from scratch rather than raising.
- Running the merge twice is a no-op (idempotent).

**Out of scope:** The bundle-injected `AskUserQuestion` deny is not removed by `plan-foundry-uninstall`. Whether uninstall should strip bundle-injected deny entries is a separate design question (see PLAN-AH2 section Out of scope).

PASS if entries were added. SKIPPED if all entries were already present.

## Step 8: Cleanup the tmp clone

```python
bundle_fetch.cleanup_tmp(TARGET_ROOT)
```

`cleanup_tmp` removes `<target>/.plan-foundry-tmp/` and is Windows-safe. Bootstrap calls `cleanup_tmp` from a `finally` block, so cleanup runs even if Steps 2-7 raised. PASS.

## Step 9: Surface restart notice

Print: "RESTART Claude Code for project-local skills to register. After restart, slash commands like `/init-plan-foundry`, `/plan-foundry-check-current`, `/plan-foundry-sync`, `/plan-foundry-uninstall`, `/test-foundry` will be available; `Skill(\"plan-pipeline\")` etc. will resolve."

## Reporting

Return a `<pipeline-result>` JSON block:
- `outcome`: `success` if no step FAILed, and `exception` if Step 0, 1, or 2 FAILed.
- `payload.step_results`: object with keys `step_0`, `step_0b`, `step_1`, `step_2`, `step_3`, `step_5`, `step_6`, `step_6b`, `step_6c`, `step_7`, `step_7b`, `step_8`, `step_9` (no `step_4`), each value `PASS` / `SKIPPED` / `FAIL`.
- `payload.summary`: one-line summary including precursor state and SHA pinned.
- `diagnostics`: per-step notes, including the full `CopyReport` from Step 2.
