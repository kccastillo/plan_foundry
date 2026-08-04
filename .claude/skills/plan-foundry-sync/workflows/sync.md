# plan-foundry-sync workflow (AC6)

Pull the latest plan_foundry bundle content into the current project via on-demand network clone. Six-step procedure; each step PASSes, SKIPPEDs, or FAILs.

## Required sequence (PLAN-AH7 Step 1 - load-bearing, do not reorder)

The receipt-backed quarantine mechanism (PLAN-AH7) requires this exact order:

1. read the existing receipt (before the clone, alongside the existing pin read in Step 1 below)
2. clone
3. copy
4. classify
5. quarantine
6. sweep
7. write the new receipt

If the receipt were written any earlier than step 7 - in particular immediately after the copy, which is where the version pin is written and where the natural reading would put it - `classify_stale`'s `gone_upstream` would always be empty, quarantine would never fire on any consumer, and `receipt_absent` would never report true. The mechanism would appear to work while silently doing nothing. See `_shared/bundle_copy.py` module docstring for the mirrored statement of this invariant.

## Step 0: Check who owns the installed `_shared/`

Runs before every other step, because every other step's helpers come out of that directory.

Read `<target>/.claude/skills/_shared/bundle-contract.json` with plain `json` and compare its top-level `bundle` key to `plan_foundry`. Read it inline - import nothing from `_shared/` to do it, because this is the check that decides whether `_shared/` can be trusted.

- Key equals `plan_foundry`, or the file is absent, malformed, or carries no `bundle` key: ordinary path. The absent case is the pre-identity state that every consumer installed before the key existed is in, and it is trusted.
- Key names a different bundle: another bundle descended from this lineage is installed in this repo and owns the directory. Clone the bundle first (Step 2), then take `bundle_copy`, `bundle_fetch` and `claude_md_block` from the clone's `_shared/` rather than the installed one, and record the diversion as a `bundle identity:` diagnostic. Do not clone twice - the clone taken here is the one Step 2 uses.

Left unchecked, the foreign copies are what every later import in the process resolves to. The mild outcome is a `TypeError` on a keyword the foreign `copy_bundle_managed` does not take. The bad one is `bundle_fetch.BUNDLE_URL` pointing at the other bundle's repo, so this sync clones and installs a different product under plan_foundry's version pin and reports success. See ARCHITECTURE.md, Invariant: Bundle Namespace Ownership.

## Step 1: Validate target state

Target root is the current working directory. Validate:

- `<target>/.claude/` exists and is a **real directory** (not a symlink, not absent). If absent or symlink, FAIL with diagnostic "run /init-plan-foundry first - this project has no real bundle copy installed." Abort.
- `<target>/.claude/.plan-foundry-bundle-version` exists. If absent, FAIL with diagnostic "this project has no recorded bundle version - run /init-plan-foundry first." Abort.

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

- **Network/auth failure** -> FAIL with the error from `git clone`'s stderr. Abort.
- **Wrong ref** (clone succeeds but `.claude/` missing in clone) -> FAIL with diagnostic. Abort.
- **OK** -> record `bundle_path` (= `<target>/.plan-foundry-tmp/`). PASS.

## Step 2a: Pre-flight - the in-flight protection (PLAN-AH8, guarantee 2)

This is a parallel inline implementation of `sync.py`'s pre-flight, not documentation of it - this file is the path an operator-driven sync actually walks, and a pre-flight wired only into `lib/sync.py` would never run here. Precedent and shape: AH7 mirrored its receipt and quarantine logic into this same file (Step 3a, and the final `write_receipt` block). Runs after the clone (Step 2) and before the copy (Step 3).

Import `preflight` from the freshly-cloned bundle's `_shared/` (NOT the target's installed copy) under an `ImportError` guard, same pattern as `gitignore_entries`/`gitattributes_pin`/`hooks_path` below - **not** `claude_md_block`, which arrives via the target's already-installed helpers and is guarded on `OSError`, not `ImportError`:

```python
bundle_shared = bundle_path / ".claude" / "skills" / "_shared"
sys.path.insert(0, str(bundle_shared))
import preflight

verdict = preflight.compare_against_clone(target_claude, bundle_path)
in_flight_plans = []
if verdict == "major_step":
    in_flight_plans = preflight.scan_in_flight_plans(TARGET_ROOT)
```

Behaviour, matching `sync.py`'s Step exactly:

- **`major_step` and `in_flight_plans` non-empty, and `--allow-in-flight` was not passed** -> halt. Clean up the tmp clone (`bundle_fetch.cleanup_tmp(TARGET_ROOT)`) and return `outcome: "blocked"` with `payload.in_flight_plans` (the PLAN paths) and `payload.blocked_reason` naming the version step. This is a deliberate refusal to proceed, not a crash - it is the third value in sync's `outcome` enum (`success` / `exception` / `blocked`), a consumer-visible contract change appropriate to a v2.0.0 wave. Do not overload `exception`.
- **`major_step` and `in_flight_plans` non-empty, and `--allow-in-flight` was passed** -> continue; note the override in diagnostics.
- **`pin_predates_contract`** -> warn and continue. This is the crossing sync that installs the substrate itself; halting it would block the fix it delivers, and under the pre-major-minor commitment it is a minor rather than the major it guards.
- **`unavailable`** -> warn and continue. An unknown state must never become a halt.
- **Anything else (`same`, `minor_step`)** -> continue.
- **Bundle predates the `preflight` helper** (`ImportError`) -> skip gracefully (`verdict = "unavailable"`), do not crash the sync.

`--allow-in-flight` is an optional CLI flag alongside `--ref`, defaulting to `False`.

## Step 3: Copy bundle-managed paths

```python
import bundle_copy
contract = bundle_copy.read_bundle_contract(bundle_path)
report = bundle_copy.copy_bundle_managed(
    bundle_path / ".claude",
    pathlib.Path(TARGET_ROOT) / ".claude",
    # Keeps a deprecation shim from overwriting a destination that exists and
    # is not itself a shim. Skipped paths arrive in report.shim_skipped and
    # must be surfaced (PLAN-AJ6 D1).
    deprecations=contract.get("deprecations", []),
)
```

Copies the four bundle-managed subdirs (`skills/`, `agents/`, `commands/`, `hooks/`) from the tmp clone into the target's `.claude/`. This step performs receipt-backed quarantine, not a direct delete - see Step 3a below. Returns a `CopyReport` with `files_copied`, `files_unchanged`, `project_additions`, `stale_in_target`.

PASS regardless of whether files were copied - sync is idempotent.

## Step 4: Refresh the version pin

```python
new_version = bundle_copy.write_version_file(
    bundle_path,
    pathlib.Path(TARGET_ROOT) / ".claude",
)
```

Records `sha`, `tag`, `synced` at `<target>/.claude/.plan-foundry-bundle-version` (gitignored). PASS.

## Step 3a: Classify, quarantine, sweep (PLAN-AH7, guarantee 3)

Runs after the copy (Step 3) and the version pin refresh (Step 4), and strictly before the receipt write (Step 4c). Uses the receipt read in Step 1 (before the clone):

```python
bundle_files = set(report.files_copied) | set(report.files_unchanged)
target_files = bundle_files | set(report.project_additions) | set(report.stale_in_target)
classification = bundle_copy.classify_stale(bundle_files, target_files, receipt)
# gone_upstream ONLY, minus anything whose bytes no longer match the receipt
still_ours = [r for r in classification.gone_upstream if not modified_since_install(r)]
bundle_copy.quarantine(target_claude, still_ours)
swept = bundle_copy.sweep_quarantine(target_claude)
```

- `classification.gone_upstream` (in the receipt, no longer in the bundle, still on disk) is the only set ever passed to `quarantine()`. `consumer_owned` (on disk, in neither receipt nor bundle) is never touched.
- Within `gone_upstream`, a path whose on-disk sha256 differs from the one the receipt records is **not** quarantined. The receipt says we installed that path; the bytes say what is there now is not what we wrote, so something else owns it - a sibling bundle shipping the same path, or the consumer's own edit - and moving it out would be taking someone else's live file. Those paths are reported under `modified_since_install_preserved` and left where they are.
- `quarantine()` moves files to `.claude/.plan-foundry-quarantine/<UTC-YYYYMMDDTHHMMSSZ>/<relpath>` via `shutil.move` - no delete primitive. `sweep_quarantine()` is the only function permitted to delete, and only whole quarantine directories aged past 30 days with a well-formed timestamp name.
- When `receipt is None` (bootstrap, or a missing/corrupt receipt), nothing is quarantined - `classify_stale` populates `unknown` instead of `gone_upstream`, and the report carries `receipt_absent: true` with the reason "no install receipt - nothing quarantined; a receipt is written by this sync and the next sync can act." Absent must not read as clean.
- Each candidate file's recorded sha256 is compared against its on-disk hash (taken before any move) and flagged `modified_since_install` if they differ. That flag is what routes it to `modified_since_install_preserved` above.
- `dangling_hook_registrations` (Step 3c) is checked against the paths actually moved, not against all of `gone_upstream` - a hook left in place is not a dangling registration.

### The shim-then-delete lifecycle (PLAN-AH9, guarantee 4)

A deprecated surface **keeps its path** and gains a shim body for at least one minor release; only at the next major does the path disappear from the bundle - at which point `classify_stale` (above) sees it as `gone_upstream` and this step quarantines it. **The shim is what makes the eventual quarantine safe**, because by then every consumer has had a release in which invoking the deprecated surface told them what replaced it, rather than a missing-file error with no diagnostic.

The shim itself is authored maintainer-side, at the moment a ledger entry is added, via `scripts/generate-deprecation-shim.py` (never shipped to consumers - it is excluded from `promote.sh`'s `ALLOWLIST` by construction). Sync does not generate shims; it only reads the ledger to annotate a quarantine.

Immediately after `quarantine()` above, cross-reference the quarantined paths against the deprecation ledger:

```python
bundle_shared = bundle_path / ".claude" / "skills" / "_shared"
sys.path.insert(0, str(bundle_shared))
import preflight

read_deprecations = getattr(preflight, "read_deprecations", None)
ledger = read_deprecations(bundle_path) if read_deprecations else []
# Filter to file-path-addressed entries before matching - kind in
# skill | reference | hook only. A kind: helper entry's path is a
# file.py::symbol string that can never equal a quarantined file path,
# and it must not even be offered to the matcher.
file_kind_ledger = {e["path"]: e for e in ledger if e.get("kind") in ("skill", "reference", "hook")}
```

For any quarantined path with a matching entry, the report carries `replaced_by` and `note` alongside the path, rather than a bare path. Use the same two-case degradation as Step 2a's `preflight` import (module absent vs. `read_deprecations` absent) - proceed with an empty ledger rather than raising, and name which case applied in a `ledger_unavailable` diagnostic.

### Dangling hook registrations (PLAN-AH9)

`.claude/settings.json` registers hooks **by path**, and the settings merge (Step 4a below) only adds entries - it never removes one. Quarantining a dropped hook therefore leaves a registration pointing at a moved file, which errors on every tool call. Loud rather than silent: after quarantine, check whether any quarantined path still appears in the target's `.claude/settings.json` text, and record any hits as `dangling_hook_registrations` in the sync report. This is a diagnostic, not a halt.

## Step 3b: Gitignore convergence for the new paths

Immediately after the settings merge (Step 4a), importing from the freshly-cloned bundle's `_shared/` (same ImportError-guarded pattern as `gitattributes_pin`):

```python
import gitignore_entries
gi_status, gi_added, gi_skipped_tracked = gitignore_entries.ensure_gitignore_entries(target_root)
# gi_skipped_tracked names entries NOT written because git already tracks
# content under them - the target owns those paths (PLAN-AJ6 D4). Surface it.
```

Converges `.claude/.plan-foundry-bundle-files` and `.claude/.plan-foundry-quarantine/` into every already-installed consumer's `.gitignore`, not just fresh installs - `init-plan-foundry` alone cannot reach the existing consumer population this substrate exists for.

## Step 4a: Merge bundle settings into target settings.json

After copying bundle-managed paths and refreshing the version pin (Steps 3-4), and **before** cleaning up the tmp clone (Step 5), merge the bundle's declared settings fragment into the target's `settings.json`. Load the helper from the **freshly-cloned bundle's** `_shared/` (not the target's installed copy, which may not contain `merge_settings.py` on pre-AH2 consumers):

```python
bundle_shared = bundle_path / ".claude" / "skills" / "_shared"
sys.path.insert(0, str(bundle_shared))
import merge_settings

fragment_path = bundle_shared / "bundle-settings.json"
target_settings = target_root / ".claude" / "settings.json"
settings_report = merge_settings.merge_bundle_settings(target_settings, fragment_path)
```

**Non-clobbering contract:**
- For each list under `permissions.*` (e.g. `deny`, `allow`), the fragment's entries are appended only if not already present.
- Pre-existing consumer entries (`allow`, `deny`, `hooks`, and all other keys) are never removed, reordered, or mutated.
- Absent, empty, or unparseable target is treated as `{}` - no raise.
- Idempotent: running twice is a no-op.

**Accepted tradeoff:** "persist on every update" means sync re-adds the deny even if a consumer deliberately removed it. Given the tool's mobile bugs and the prose-first methodology, this default is intentional (PLAN-AH2 section Context).

**Out of scope:** `plan-foundry-uninstall` does not strip the bundle-injected deny (PLAN-AH2 section Out of scope).

`settings_report` is folded into the payload as `settings_merge: {status, entries_added, entries_already_present}` and appended to `diagnostics`.

## Step 4b: Refresh the CLAUDE.md operating-rules block

After copying bundle-managed paths and refreshing the version pin (Steps 3-4), and **before** cleaning up the tmp clone (Step 5), read `operating-rules.md` from the freshly-cloned bundle and apply the sentinel-block logic to the host project's `CLAUDE.md`:

```python
operating_rules_path = bundle_path / ".claude" / "skills" / "init-plan-foundry" / "operating-rules.md"
operating_rules = operating_rules_path.read_text(encoding="utf-8")
cmd_status, cmd_note = claude_md_block.apply_operating_rules_block(target_root, operating_rules)
```

Behaviour:

- **Markers present (normal case):** The content between `<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->` is replaced with the bundle's current `operating-rules.md` text. All host-authored content outside the markers is preserved verbatim. Returns `("PASS", "replaced-block")` or `("SKIPPED", "already current")` if the block body already matches.
- **Markers absent:** The sentinel block is appended to the existing `CLAUDE.md` with an appropriate separator. Returns `("PASS", "appended-block")`.
- **CLAUDE.md absent:** A stub `CLAUDE.md` is created containing a header and the sentinel block. Returns `("PASS", "created")`.
- **Malformed markers (end before start, or duplicate markers):** Returns `("FAIL", <reason>)` **without writing the file** - the host `CLAUDE.md` is left byte-for-byte unchanged. This is non-destructive and retry-safe: the bundle-managed dirs and version pin are already updated (idempotent operations); the operator fixes their `CLAUDE.md` markers and re-runs sync.
- **operating-rules.md absent in bundle** (old bundle predating this feature): treated as `("SKIPPED", "operating-rules.md absent in bundle")` - not a crash.

`cmd_status`/`cmd_note` are recorded in `payload["claude_md"]` and appended to `result["diagnostics"]` and the `summary` string. If `cmd_status == "FAIL"`, sync surfaces `outcome: exception` to alert the operator.

This step runs inside the `try` block that guards the `finally: cleanup_tmp()`, so the bundle is still on disk when `operating-rules.md` is read.

## Step 4c: Write the new receipt (PLAN-AH7 - must be LAST)

The final action inside the `try` block, after every step above, including quarantine and sweep:

```python
bundle_copy.write_receipt(
    target_claude,
    report.files_copied + report.files_unchanged,
    new["sha"],
)
```

This is the load-bearing ordering rule from Step 1: writing the receipt any earlier - in particular immediately after Step 4's version-pin write, which is the natural place an implementer drifts to - makes `gone_upstream` always empty and quarantine never fire on any consumer, silently.

## Step 5: Clean up the tmp clone

```python
bundle_fetch.cleanup_tmp(TARGET_ROOT)
```

Removes `<target>/.plan-foundry-tmp/`. Windows-safe (clears the readonly bit on git's pack files). The cleanup is in a `finally` block so it runs even if Step 3 or 4 raised. PASS.

## Step 6: Report

Emit a structured summary to the human:

```
plan-foundry-sync: <PREVIOUS_SHA[:8]> -> <new sha[:8]> (ref=<ref>)
  Files copied:        N
  Files unchanged:     M
  Project additions:   K  (preserved - files under bundle-managed paths but not in the bundle)
  Stale in target:     S  (bundle files no longer upstream - preserved; clean manually if desired)

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
    "stale_in_target": [...],
    "gitignore_convergence": {"status": "PASS|SKIPPED", "entries_added": [...]},
    "quarantine": {
      "receipt_absent": false,
      "gone_upstream_quarantined": [{"path": "...", "sha256": "...", "modified_since_install": false, "replaced_by": "...", "note": "..."}],
      "modified_since_install_preserved": [{"path": "...", "sha256": "...", "modified_since_install": true}],
      "consumer_owned_preserved": [...],
      "unknown": [...],
      "swept": [...],
      "ledger_unavailable": null
    },
    "dangling_hook_registrations": [...]
  },
  "summary": "synced <prev[:8]> -> <new[:8]> (ref=<ref>): N copied, M unchanged"
}
```

`outcome: exception` if Step 1 FAILed (target not initialised) or Step 2 FAILed (clone error).

`outcome: blocked` (PLAN-AH8) if Step 2a halted on a major version step with in-flight PLANs and `--allow-in-flight` was not passed. This is a deliberate refusal to proceed, not a failure - a consumer switching on `exception` alone would misreport this as a crash. The payload shape for `blocked` is:

```json
{
  "outcome": "blocked",
  "payload": {
    "in_flight_plans": ["Workbench/PLAN-XX0_example.md"],
    "blocked_reason": "sync crosses a major version step (pin vs. the cloned bundle) while PLAN(s) are in flight"
  },
  "summary": "sync blocked: major version step with N PLAN(s) in flight - re-run with --allow-in-flight to override"
}
```

## Notes

- **Tag pinning.** `/plan-foundry-sync v0.5.0` passes `ref=v0.5.0` to the clone.
- **Crashed prior run.** If `.plan-foundry-tmp/` already exists when sync starts (from a crashed prior run), Step 2 removes it before cloning.
- **Network required.** No offline fallback. If the user is offline, the operation cleanly fails - uninstall remains available since it is local-only.
- **In-flight override (PLAN-AH8).** `--allow-in-flight` overrides the Step 2a halt on a major version step with in-flight PLANs. Use only when the operator has confirmed the in-flight work is safe to proceed under the incoming bundle.
