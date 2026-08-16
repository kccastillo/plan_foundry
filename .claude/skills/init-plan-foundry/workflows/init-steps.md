# init-plan-foundry workflow (AC6)

Idempotent nine-step bootstrap. Each step PASSes (the operation landed), SKIPPEDs (already present, no action needed), or FAILs (operation could not complete; report and continue unless explicitly fatal).

Under the AC6 model, the bundle source is fetched on demand from the public URL into a transient `<target>/.plan-foundry-tmp/`. No reliance on any path outside the target - runs in sandboxed Claude Code sessions (mobile, web, restricted desktop) with network access.

## Step 0: Bundle-source self-detection (pre-flight)

Refuses to run if CWD IS the plan_foundry bundle source itself - the bundle source's `.claude/` is real tracked content, not a derived copy. Detect, first hit wins:

1. Basename of `TARGET_ROOT` (= cwd) equals `plan_foundry_dev` or `plan_foundry` -> bundle-source.
2. Else, read `.git/config` from `TARGET_ROOT`. If a remote `origin` URL contains the substring `kccastillo/plan_foundry_dev` or `kccastillo/plan_foundry` (and not as part of a longer name) -> bundle-source.
3. Else, not this bundle's source.

Then check for a *foreign* bundle - one that is not ours. Name matching above only catches our own repo, so a target shipping a different bundle passes it. `preflight.detect_foreign_bundle(TARGET_ROOT, BUNDLE_PATH)` returns a diagnostic when either signal fires, first hit wins:

1. The target carries `.claude/skills/_shared/bundle-contract.json` and its bytes differ from the incoming bundle's. Two contracts means two bundles.
2. Git tracks files under `.claude/{skills,agents,commands,hooks}`. A consumer gitignores those; a repo that tracks them owns that content as source.

If foreign: FAIL Step 0 with the returned `foreign-bundle-detected: ...` diagnostic and abort. Fail-open on a missing git or a non-repo target - signal 2 cannot be evaluated, so it does not fire. Raised from paper_trail_dev, which passed the name check and would have had its tracked product overwritten (PLAN-AJ6 D3).

If bundle-source: FAIL Step 0 with diagnostic "running init-plan-foundry inside the bundle source itself - this skill is for consumer projects. Bundle development happens directly in the source tree." Abort.

Otherwise: record `TARGET_ROOT = cwd`. PASS.

## Step 0b: Repository-presence check (advisory)

Runs `git rev-parse --is-inside-work-tree` in `TARGET_ROOT`, before any of
`Workbench/`, `Retired/` or `.gitignore` reaches the target. Advisory
only - it never fails the bootstrap and never runs `git init` on the
consumer's behalf.

- **`true`** -> PASS. Also runs `git rev-parse --show-toplevel` to
  distinguish `TARGET_ROOT` being the repository root itself from being a
  subdirectory of one that encloses it; either way the status is PASS
  (an enclosing repository still gives commits somewhere to attach to),
  but the diagnostic note names which case applies.
- **Anything else (non-zero exit, no git on `PATH`, unexpected output)**
  -> SKIPPED, with a diagnostic naming the missing repository and its
  concrete cost: commits, retire history and the durability pass have
  nothing to attach to.

This closes the repository-absence failure mode named in
FOUNDRYREQ-horse-chestnut-brickhouse-20260805-1707-nothing-checks-that-session-material-landed-somewhere-durable
(cheapest of the report's three failure modes, checkable before a single
file is scaffolded). The report's other two failure modes are named
follow-on work, not built here: a session-end tracked-and-committed scan
(candidate host `handoff-next-session`; open question is which files count
as "this session's" and how staleness is scanned without asking the
executing agent to self-report), and a paste-in capture prompt (no
candidate host; fires at a conversational moment, not a filesystem-
scannable one).

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
contract = bundle_copy.read_bundle_contract(BUNDLE_PATH)
report = bundle_copy.copy_bundle_managed(
    BUNDLE_CLAUDE, TARGET_CLAUDE, deprecations=contract.get("deprecations", [])
)
```

`copy_bundle_managed` copies the four bundle-managed top-level subdirs (`skills/`, `agents/`, `commands/`, `hooks/`) from bundle into target. This step does not remove anything from the target - the receipt-backed quarantine that acts on stale files (PLAN-AH7) is `plan-foundry-sync`'s job, not this skill's: a fresh bootstrap has no prior install receipt to compare against. Returns a `CopyReport`.

Passing `deprecations` makes the copy refuse to write a deprecation shim over a destination that exists and is not itself a shim. Those paths land in `report.shim_skipped` and must be surfaced. A shim advertising a successor product must never overwrite the successor, which is exactly what installing this bundle into that successor's own source repo would otherwise do (PLAN-AJ6 D1).

**Write the version pin.** After copy, call `bundle_copy.write_version_file(BUNDLE_PATH, TARGET_CLAUDE)` to record bundle commit SHA, tag (if any), and timestamp at `TARGET_CLAUDE/.plan-foundry-bundle-version` (gitignored).

Report Step 2 outcome with `precursor`, file counts, and the recorded version sha.

## Step 3: Ensure `Workbench/` directory

Check if `Workbench/` exists. If absent, create it with a `Workbench/.gitkeep` placeholder - PASS. If present, SKIPPED.

## Step 5: Ensure `Retired/` directory

If absent, create with `Retired/.gitkeep` - PASS. If present, SKIPPED.

## Step 6: Ensure `.gitignore` entries

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

## Step 6b: Pin `.gitattributes` line endings

Ensure the target's `.gitattributes` pins line endings for bundle-managed hook scripts, so a hook is never shipped CRLF-mangled. PASS if an entry was added; SKIPPED if already present.

## Step 6c: Merge `core.hooksPath`

Read and, if needed, write the target's `core.hooksPath` git config so the bundle's hooks directory is wired in. Must run after Step 6b - wiring hooks before the line-ending pin is in place would ship a CRLF-mangled hook that fails on every Windows consumer while exiting 0, so broken and working look identical. PASS if the config was written; SKIPPED if already correct.

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
- If the target `settings.json` is absent, empty, or unparseable, it is treated as `{}` and the result is written from scratch - no raise.
- Running the merge twice is a no-op (idempotent).

**Out of scope:** The bundle-injected `AskUserQuestion` deny is NOT removed by `plan-foundry-uninstall`. Whether uninstall should strip bundle-injected deny entries is a separate design question (see PLAN-AH2 section Out of scope).

PASS if entries were added; SKIPPED if all entries were already present.

## Step 8: Cleanup the tmp clone

```python
bundle_fetch.cleanup_tmp(TARGET_ROOT)
```

Removes `<target>/.plan-foundry-tmp/`. Windows-safe. In a `finally` block so it runs even if Steps 2-7 raised. PASS.

## Step 9: Surface restart notice

Print: "RESTART Claude Code for project-local skills to register. After restart, slash commands like `/init-plan-foundry`, `/plan-foundry-check-current`, `/plan-foundry-sync`, `/plan-foundry-uninstall`, `/test-foundry` will be available; `Skill(\"plan-pipeline\")` etc. will resolve."

## Reporting

Return a `<pipeline-result>` JSON block:
- `outcome`: `success` if no FAILs; `exception` if Step 0, 1, or 2 FAILed.
- `payload.step_results`: object with keys `step_0`, `step_0b`, `step_1`, `step_2`, `step_3`, `step_5`, `step_6`, `step_6b`, `step_6c`, `step_7`, `step_7b`, `step_8`, `step_9` (no `step_4`), each value `PASS` / `SKIPPED` / `FAIL`.
- `payload.summary`: one-line summary including precursor state and SHA pinned.
- `diagnostics`: per-step notes, including the full `CopyReport` from Step 2.
