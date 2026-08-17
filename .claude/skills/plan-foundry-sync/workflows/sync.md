# plan-foundry-sync workflow (AC6)

Pull the latest plan_foundry bundle content into the current project via on-demand network clone. Each step below PASSes, SKIPPEDs, or FAILs.

## Required sequence (PLAN-AH7 Step 1 - load-bearing, do not reorder)

The receipt-backed quarantine mechanism (PLAN-AH7) requires this exact order:

1. read the existing receipt (before the clone, alongside the existing pin read in Step 1 below)
2. clone
3. copy
4. classify
5. quarantine
6. sweep
7. write the new receipt

If the receipt were written any earlier than step 7 - in particular immediately after the copy - `classify_stale`'s `gone_upstream` would always be empty, quarantine would never fire on any consumer, and `receipt_absent` would never report true. The mechanism would appear to work while silently doing nothing. See `_shared/bundle_copy.py` module docstring for the mirrored statement of this invariant.

PLAN-AK6 adds further steps this ordering must hold: a handover to the freshly-cloned bundle's own `sync.py` (Step 2a, below), an incomplete-sync marker written just before Step 3's copy and cleared only after the version pin, and the version pin (Step 4 below) moving from immediately-after-the-copy to immediately-after-the-receipt - the last write of a completed run, not an early one.

### Document order is not execution order

The step headings and numbers below are frozen, because other artefacts cite them: `_shared/harness-contract.md:211` cites Step 3, `lib/sync.py:462` cites Step 2b, `lib/sync.py:520` and `:823` cite Step 3a, and `_shared/deprecation-policy.md:122-123` cites this file's shim-then-delete lifecycle and quarantine cross-reference by name. Renumbering to restore reading order would break every one of those citations, so three steps are deliberately left on the page out of the order they run in. Read the order from this list, never from position:

Step 0 -> Step 1 -> Step 2 -> Step 2a -> Step 2b -> **Step 2c** -> Step 3 -> Step 3's conflicts-file write -> Step 3a -> **Step 4a** -> **Step 3b** -> gitattributes pin -> hooks path -> Step 4b -> Step 4c's receipt write -> **Step 4** (the version pin) -> Step 4c's marker clear -> Step 5 -> Step 6.

The three printed out of order are bolded above:

- **Step 2c** is printed after Step 4 and runs before Step 3 - it is the first write to the target in the whole run (`lib/sync.py:766`).
- **Step 4** is printed between Step 3 and Step 2c and runs second-to-last of all the writes, after Step 4c's receipt (`lib/sync.py:1059`).
- **Step 3b** is printed before Step 4a and runs after it (`lib/sync.py:976-984`, against the settings merge at `:924-968`).

Two further stages run inside this sequence and carry no numbered step in this document at all: the gitattributes pin (`lib/sync.py:991-998`) and the `core.hooksPath` wiring (`lib/sync.py:1004-1010`). They are named here because `payload.failed_step` can name either of them (`lib/sync.py:337-348`), so an operator reading a failure report will meet a step name this document otherwise never introduces.

## Step 0: Check who owns the installed `_shared/`

Runs before every other step, because every other step loads its helpers from that directory.

Read `<target>/.claude/skills/_shared/bundle-contract.json` with plain `json` and compare its top-level `bundle` key to `plan_foundry`. Perform that read inline - import nothing from `_shared/` to do so, because this check decides whether `_shared/` can be trusted.

- Key equals `plan_foundry`, or the file is absent, malformed, or carries no `bundle` key: take the ordinary path. The absent case is the pre-identity state of every consumer installed before the key existed, and sync trusts that state.
- Key names a different bundle: another bundle descended from this lineage is installed in this repo and owns the directory. Clone the bundle first (Step 2), then take `bundle_copy`, `bundle_fetch` and `claude_md_block` from the clone's `_shared/` rather than from the installed `_shared/`, and record the diversion as a `bundle identity:` diagnostic. Do not clone twice - the clone taken here is the one Step 2 uses.

Left unchecked, every later import in the process resolves to the foreign copies. The mild outcome is a `TypeError` on a keyword the foreign `copy_bundle_managed` does not take. The bad outcome is `bundle_fetch.BUNDLE_URL` pointing at the other bundle's repo, so this sync clones and installs a different product under plan_foundry's version pin and reports success. See ARCHITECTURE.md, Invariant: Bundle Namespace Ownership.

## Step 1: Validate target state

Target root is the current working directory. Validate:

- `<target>/.claude/` exists and is a **real directory** (not a symlink, not absent). If absent or symlink, FAIL with diagnostic "run /init-plan-foundry first - this project has no real bundle copy installed." Abort.
- `<target>/.claude/.plan-foundry-bundle-version` exists. If absent, FAIL with diagnostic "this project has no recorded bundle version - run /init-plan-foundry first." Abort.

Record the existing version's `sha` field as `PREVIOUS_SHA` for the final report.

**Read the install receipt now (PLAN-AK5), namespaced by bundle identity:**

```python
receipt = bundle_copy.read_receipt(target_claude, bundle="plan_foundry")
```

`read_receipt` reads `<target>/.claude/.bundle-receipts/plan_foundry.files` first. When
that path is absent, `read_receipt` falls back to the legacy
`<target>/.claude/.plan-foundry-bundle-files` and adopts that legacy receipt only when
its `sha` header equals `PREVIOUS_SHA` (the version pin read just above) - proof the
legacy receipt is this bundle's own, since only this bundle writes the pin. A legacy
receipt whose `sha` does not match, and a target carrying no receipt at all, are not
trusted, so `receipt` is `None` and every write this run proceeds unverified (see Step
3's divergence check below). This comparison is only meaningful because the receipt is
read here, before Step 4 refreshes the pin - reading the receipt any later would compare
the legacy sha against the *incoming* pin rather than against the pin this bundle
actually wrote last.

## Step 2: Clone the bundle on demand

Run via the shared helper:

```python
import sys, pathlib
shared = pathlib.Path(__file__).resolve().parent.parent.parent / "_shared"
sys.path.insert(0, str(shared))
import bundle_fetch
bundle_path = bundle_fetch.clone_bundle(TARGET_ROOT, ref=REF)   # default REF="main"
```

`clone_bundle` runs `git clone --depth=1 --branch <ref> https://github.com/kccastillo/plan_foundry <target>/.plan-foundry-tmp/`, removing any stale `.plan-foundry-tmp/` first.

- **Network/auth failure** -> FAIL with the error from `git clone`'s stderr. Abort.
- **Wrong ref** (clone succeeds but `.claude/` missing in clone) -> FAIL with diagnostic. Abort.
- **OK** -> record `bundle_path` (= `<target>/.plan-foundry-tmp/`). PASS.

## Step 2a: Hand over to the cloned bundle's own sync.py (PLAN-AK6 D2/D3)

Runs immediately after the clone (Step 2), before anything else - no target file has been written yet, so a failed handover costs nothing but the clone. The parent is old code invoking a possibly-new bundle, so the parent must verify the calling convention before relying on the child's answer:

```python
import importlib.util

clone_sync = bundle_path / ".claude" / "skills" / "plan-foundry-sync" / "lib" / "sync.py"

# The probe is the INSTALLED sync.py's own `_reexec_supported` - the parent
# generation is the one doing the verifying, and a clone old enough to fail
# this probe has no `_reexec_supported` to load in the first place. Loaded
# under an explicit module name so that Step 2b below can still bind the
# CLONE's module as `sync`, which a plain `import sync` here would shadow.
installed_sync_path = pathlib.Path(__file__).resolve().parent.parent / "lib" / "sync.py"
spec = importlib.util.spec_from_file_location("installed_pf_sync", installed_sync_path)
installed_sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installed_sync)

supported = installed_sync._reexec_supported(clone_sync)  # runs `<clone_sync> --help`, checks both flag literals appear
```

- **Supported** (`--help` exits zero and names both `--prefetched-bundle` and `--no-reexec`): run the clone's own `sync.py` as a child process, passing `--target-root`, `--ref`, `--prefetched-bundle <clone path>`, `--no-reexec`, and `--allow-in-flight` when set. Parse its stdout as the wire-format JSON result. On a parsed dict result, relay that result unchanged except for prepending a diagnostic naming the handover - **every step below this one, including the pre-flight step that follows, is skipped**, because the child re-runs those steps itself as the generation that should own the verdict. On a result that fails to parse, or a non-zero exit: clean up the tmp clone and return `outcome: exception` stating the handover failed and nothing in the target was written.
- **Not supported** (a `--ref` older than this PLAN, whose clone has never heard of these flags): record a diagnostic naming the clone as pre-handover, and continue into Step 2b below exactly as sync ran before this PLAN. This floor - never behaving worse than pre-PLAN sync - is deliberate, because a consumer syncing to an old ref must not be worse off.

## Step 2b: Pre-flight - the in-flight protection (PLAN-AH8, guarantee 2)

This file is the procedure an operator-driven sync actually follows, so a pre-flight wired only into `lib/sync.py` would never run here - the step stays, and calls `sync.py`'s own `compute_preflight_verdict` function instead of reproducing its body (PLAN-AL8 D1). The earlier inline copy here had drifted from `sync.py`, missing the `ImportError` guard and the sentinel binding `compute_preflight_verdict` now carries in the one place both callers use. Runs after the clone (Step 2) and the handover probe (Step 2a) and before the copy (Step 3) - only reached when Step 2a did not hand over.

Import `compute_preflight_verdict` from the freshly-cloned bundle's own `plan-foundry-sync/lib/sync.py` (NOT the target's installed copy):

```python
sync_lib_dir = bundle_path / ".claude" / "skills" / "plan-foundry-sync" / "lib"
sys.path.insert(0, str(sync_lib_dir))
import sync as sync_lib

verdict, in_flight_plans, read_deprecations_fn, ledger_unavailable_reason = (
    sync_lib.compute_preflight_verdict(bundle_path, target_claude, TARGET_ROOT)
)
```

`compute_preflight_verdict` imports `preflight` from the freshly-cloned bundle's `_shared/` under an `ImportError` guard, same pattern as `gitignore_entries` in Step 3b below and as the `gitattributes_pin` and `hooks_path` imports at `lib/sync.py:991-1010`, which this document gives no numbered step of their own - **not** `claude_md_block`, which is loaded from the target's already-installed helpers and is guarded on `OSError`, not `ImportError`. The function returns the version-step `verdict`, any `in_flight_plans`, and the values Step 3a's deprecation-ledger read needs below: `read_deprecations_fn` and `ledger_unavailable_reason`. Carry each of those returned values forward.

Behaviour, matching the PLAN-AH8 guarantee 2 pre-flight block in `sync.py` exactly - the `compute_preflight_verdict` call and the `major_step` halt that immediately follows it, at `lib/sync.py:687-725`. `sync.py` numbers no steps of its own, so the correspondence is to that block rather than to a step number:

- **`major_step` and `in_flight_plans` non-empty, and `--allow-in-flight` was not passed** -> halt. Clean up the tmp clone (`bundle_fetch.cleanup_tmp(TARGET_ROOT)`) and return `outcome: "blocked"` with `payload.in_flight_plans` (the PLAN paths) and `payload.blocked_reason` naming the version step. This is a deliberate refusal to proceed, not a crash - `blocked` joins `success` and `exception` in sync's `outcome` enum, a consumer-visible contract change appropriate to a v2.0.0 wave. Do not overload `exception`.
- **`major_step` and `in_flight_plans` non-empty, and `--allow-in-flight` was passed** -> continue, and note the override in diagnostics.
- **`pin_predates_contract`** -> warn and continue. This is the crossing sync that installs the substrate itself, so halting the sync would block the fix that same sync delivers, and under the pre-major-minor commitment the version step is a minor rather than the major this protection guards.
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
    # PLAN-AK5: the divergence check (below).
    receipt=receipt,
    force=FORCE_OVERWRITE_DIVERGED,
)
```

Copies the bundle-managed subdirs (`skills/`, `agents/`, `commands/`, `hooks/`) from the tmp clone into the target's `.claude/`. This step performs receipt-backed quarantine, not a direct delete - see Step 3a below. Returns a `CopyReport` carrying all seven of `files_copied`, `files_unchanged`, `project_additions`, `stale_in_target`, `shim_skipped`, `refused_not_ours` and `forced_overwrites` (`_shared/bundle_copy.py:87-95`). The last three are the fields this document's divergence check and shim handling below depend on, so a reader who takes the first four as the whole report will miss them.

PASS regardless of whether files were copied - sync is idempotent.

### The divergence check (PLAN-AK5, D6)

For each destination whose bytes differ from the incoming source, `copy_bundle_managed`
now checks ownership against `receipt` before copying:

- **No receipt at all** (`receipt is None`) - every destination copies exactly as it did
  before this PLAN, and nothing new is recorded. This is the pre-receipt consumer, so the
  report carries one stated `ownership_unverified` condition rather than a list of every
  file this run could not verify (see "Reporting refusals and block changes" below).
- **A receipt is present, and the destination's recorded sha256 matches its current
  bytes** - copy as today. This is the ordinary upgrade case.
- **A receipt is present, and the destination is absent from the receipt or its recorded
  sha256 no longer matches** - this bundle did not write what is on disk now. With
  `--force-overwrite-diverged` **not** passed (the default), the copy is refused: the
  destination's bytes are left untouched and its display string is recorded in
  `payload["refused_not_ours"]`. With the flag passed, the copy proceeds and the path is
  also recorded in `payload["forced_overwrites"]`.

A refused path never appears in `files_copied`, `files_unchanged`, `project_additions`,
or `stale_in_target` - a refused path must not reach Step 3a's classification, and must
not be recorded as this bundle's own in the receipt Step 4c writes. A forced overwrite is
the opposite: the path is recorded in `files_copied`, so the path also enters the next
receipt and the conflict self-clears on the following sync.

`--force-overwrite-diverged` is an optional CLI flag alongside `--ref` and
`--allow-in-flight`, defaulting to `False` - opt-in, never a default. A consumer whose
*installed* `sync.py` predates this flag cannot pass the flag to that copy at all, so the
route is to invoke the freshly-cloned bundle's own `sync.py` directly (at
`<target>/.plan-foundry-tmp/.claude/skills/plan-foundry-sync/lib/sync.py`, immediately
after Step 2's clone and before Step 5 cleans the clone up) and pass the flag there.

### The standing conflicts file (PLAN-AK5, D7)

Immediately after this step's copy and before Step 3a's classify/quarantine/sweep -
positioned there so a run that raises later still leaves a *current* conflicts file
rather than the previous run's:

```python
import os

conflicts_path = bundle_copy.receipt_path(target_claude, "plan_foundry").parent / "plan_foundry.conflicts"
conflicts_path.parent.mkdir(parents=True, exist_ok=True)
conflicts_tmp = conflicts_path.with_suffix(conflicts_path.suffix + ".tmp")
conflicts_body = "\n".join(sorted(report.refused_not_ours))
if conflicts_body:
    conflicts_body += "\n"
conflicts_tmp.write_text(conflicts_body, encoding="utf-8")
os.replace(conflicts_tmp, conflicts_path)
```

There is no `write_atomically` helper anywhere in the bundle - the atomicity is the four lines above, spelled out here exactly as `lib/sync.py:788-793` spells them out. A no-refusal run writes a zero-byte file, and the trailing newline is added only when there is at least one path to terminate.

Sync writes the conflicts file on **every** run, one refused path per line, sorted,
through a `.tmp` sibling and atomic replace - the same pattern `write_receipt` uses. The
file is written empty (never left stale, never deleted) when there are no refusals this
run, which is what makes an unresolved conflict re-report on the next sync and the one
after, and lets a resolved conflict self-clear rather than persist forever.

## Step 4: Refresh the version pin (PLAN-AK6: last write, not an early one)

The pin write runs **after** Step 4c's receipt write, as the last write of the run before the incomplete-sync marker is cleared - see Step 4c below for where the write occurs and why. The sha/tag data is resolved read-only, before the copy, so the marker (Step 2c) can name the target sha the run is moving toward:

This fence is an outline of position rather than a copyable block - the `...` stands for every step in between, and the copyable form of the pin write is Step 4c's fence below:

```python
new = bundle_copy.resolve_version(bundle_path)  # read-only, before the copy
...
# ... every step below, through the receipt write ...
bundle_copy.write_version_file(
    bundle_path,
    pathlib.Path(TARGET_ROOT) / ".claude",
    data=new,
)  # the last write except for clearing the marker
```

`write_version_file`'s signature is `write_version_file(bundle_root, target_claude, data=None)` (`_shared/bundle_copy.py:390-394`), so `bundle_root` is a **required** first positional argument. Passing `data=new` means `bundle_root` is never read on this call - the supplied dict is written verbatim - but omitting the argument is not a shortcut. The earlier form of this fence, `write_version_file(target_claude, data=new)`, raises `TypeError: write_version_file() missing 1 required positional argument: 'target_claude'` - verified against `_shared/bundle_copy.py` - and the two-positional form `write_version_file(target_claude, new)` is worse still, because it binds the target as `bundle_root` and the version dict as `target_claude` and fails only on reaching the filesystem. `lib/sync.py:1059` passes `bundle_path` first, so this fence does too.

Records `sha`, `tag`, `synced` and `schema_version` at `<target>/.claude/.plan-foundry-bundle-version` (gitignored). Every step between the resolve and this write is what makes the pin's claim true - writing the pin earlier certifies work the run has not yet done.

## Step 2c: Mark the sync incomplete (PLAN-AK6 D5)

Immediately before Step 3's copy - the first write to the target in the whole run:

```python
bundle_copy.mark_sync_incomplete(target_claude, PREVIOUS_SHA, new["sha"])
```

Writes `<target>/.claude/.plan-foundry-sync-incomplete` (gitignored), naming the sha the run started at, the sha the run is moving to, and when the run started. Cleared only after Step 4's pin write succeeds (see Step 4c). A run that starts and does not finish leaves this marker in place, and `/plan-foundry-check-current` reads the marker ahead of any sha comparison (D6) and reports the interrupted state. A run that finds a marker already present at its own start reports that marker and proceeds. The repair for an incomplete sync is another sync, so refusing would wedge the only exit.

## Step 3a: Classify, quarantine, sweep (PLAN-AH7, guarantee 3)

Runs after the copy (Step 3), and strictly before Step 4c's receipt write and the version pin refresh that now follows that write. Uses the receipt read in Step 1 (before the clone):

```python
# The closed legacy-orphan list is subtracted here so the legacy list and the
# ordinary classification never double-report the same file - see "Legacy
# orphan excision" below.
legacy_orphans = sync_lib._legacy_orphan_relpaths(target_claude)

bundle_files = set(report.files_copied) | set(report.files_unchanged)
target_files = (
    bundle_files | set(report.project_additions) | set(report.stale_in_target)
) - set(legacy_orphans)
classification = bundle_copy.classify_stale(bundle_files, target_files, receipt)

# gone_upstream ONLY, minus anything whose bytes no longer match the receipt.
# There is no `modified_since_install` function to call - the flag of that
# name is computed right here, by hashing each candidate on disk and
# comparing against the sha256 the receipt recorded.
receipt_files = receipt.get("files", {}) if receipt else {}
to_quarantine = []
for rel in classification.gone_upstream:
    try:
        on_disk = bundle_copy._file_sha256(target_claude / rel)
    except OSError:
        on_disk = None
    recorded = receipt_files.get(rel)
    modified = on_disk is not None and recorded is not None and on_disk != recorded
    if not modified:
        to_quarantine.append(rel)

bundle_copy.quarantine(target_claude, to_quarantine)

# Same primitive for the legacy orphans, then prune the empty shells the
# moves leave behind - quarantine() moves files, never directories.
bundle_copy.quarantine(target_claude, legacy_orphans)
sync_lib._prune_empty_legacy_dirs(target_claude)

swept = bundle_copy.sweep_quarantine(target_claude)
```

- `classification.gone_upstream` (in the receipt, no longer in the bundle, still on disk) is the only set ever passed to `quarantine()`. `consumer_owned` (on disk, in neither receipt nor bundle) is never touched.
- Within `gone_upstream`, a path whose on-disk sha256 differs from the one the receipt records is **not** quarantined. The receipt records that path as one this bundle installed, but the on-disk bytes differ from what this bundle wrote, so something else owns the path now - a sibling bundle shipping the same path, or the consumer's own edit - and moving that path out would be taking someone else's live file. Those paths are reported under `modified_since_install_preserved` and left where they are.
- `quarantine()` moves files to `.claude/.plan-foundry-quarantine/<UTC-YYYYMMDDTHHMMSSZ>/<relpath>` via `shutil.move` - no delete primitive. `sweep_quarantine()` is the only function permitted to delete, and only whole quarantine directories aged past 30 days with a well-formed timestamp name.
- When `receipt is None` (bootstrap, or a missing/corrupt receipt), nothing is quarantined - `classify_stale` populates `unknown` instead of `gone_upstream`, and the report carries `receipt_absent: true` with the reason "no install receipt - nothing quarantined; a receipt is written by this sync and the next sync can act." Absent must not read as clean.
- Each candidate file's recorded sha256 is compared against its on-disk hash (taken before any move) and flagged `modified_since_install` if they differ. That flag is what routes the file to `modified_since_install_preserved` above.
- `dangling_hook_registrations` (see "Dangling hook registrations" further down this same Step 3a - there is no Step 3c in this document) is checked against the paths actually moved, rather than against all of `gone_upstream`, because a hook left in place is not a dangling registration.

### The shim-then-delete lifecycle (PLAN-AH9, guarantee 4)

A deprecated surface **keeps its path** and gains a shim body for at least one minor release, and only at the next major does the path disappear from the bundle - at which point `classify_stale` (above) classifies that path as `gone_upstream` and this step quarantines the path. **The shim is what makes the eventual quarantine safe**, because by then every consumer has had a release in which invoking the deprecated surface told them what replaced that surface, rather than a missing-file error with no diagnostic.

The shim itself is authored maintainer-side, at the moment a ledger entry is added, via `scripts/generate-deprecation-shim.py` (never shipped to consumers - the script is excluded from `promote.sh`'s `ALLOWLIST` by construction). Sync does not generate shims and only reads the ledger to annotate a quarantine.

Immediately after `quarantine()` above, cross-reference the quarantined paths against the deprecation ledger by calling `sync.py`'s `build_file_kind_ledger`, using the `read_deprecations_fn` Step 2b already derived, instead of reproducing the read (PLAN-AL8 D1):

```python
file_kind_ledger = sync_lib.build_file_kind_ledger(bundle_path, read_deprecations_fn)
```

For any quarantined path with a matching entry, the report carries `replaced_by` and `note` alongside the path, rather than a bare path. `build_file_kind_ledger` filters to file-path-addressed entries only (kind in skill | reference | hook), since a kind: helper entry's path is a file.py::symbol string that can never equal a quarantined file path. The function degrades to an empty ledger, rather than raising, in either case Step 2b's `ledger_unavailable_reason` already names - carry that reason forward into the `ledger_unavailable` diagnostic instead of re-deriving the reason here.

### Dangling hook registrations (PLAN-AH9, generalised PLAN-AK8)

`.claude/settings.json` registers hooks **by path**, and the settings merge (Step 4a below) only adds entries - it never removes one. Quarantining a dropped hook therefore leaves a registration pointing at a moved file, which errors on every tool call. The condition must be reported loudly rather than left silent, so after quarantine, check whether any quarantined path still appears in the target's `.claude/settings.json` text, and record any hits as `dangling_hook_registrations` in the sync report. This is a diagnostic, not a halt.

`.claude/settings.local.json` is never written by sync (`operating-rules.md`: "tracked by the project's git and never touched by sync"), but a hand-installed or pre-`merge_settings`-era hook registration can still remain in that file - `settings.local.json` is where the incident registration behind PLAN-AK8 was found. Sync reads (never writes) that file for the same marker set and records any hits as `dangling_hook_registrations_local`. Because sync cannot repair this file, sync also appends, on a non-empty result, a diagnostics line naming the file and stating that sync will not touch settings.local.json. That line also notes the fix needs the session restarted once the entry is removed by hand: the registration is read once at session start, so an edit mid-session does not stop the hook firing for the rest of that session.

### Legacy orphan excision

`foundry-log` (skill + agent + `PostToolUse` hook) left the bundle at v1.14.0, before the receipt substrate above existed. `classify_stale`'s `gone_upstream` only ever reaches a path recorded in some past receipt, and no receipt was ever written while these paths still shipped - the ordinary mechanism above can never reach them, on any future sync, for a consumer who installed before the receipt existed. This is a closed, one-off gap, not a timing gap a later sync closes on its own.

`sync.py` carries a hardcoded, closed list (`LEGACY_ORPHAN_DIRS`, `LEGACY_ORPHAN_FILES`) for exactly this gap, checked immediately after the copy (Step 3) and excluded from the ordinary classification above so the legacy list and the ordinary classification never double-report the same file. Anything on that list still present on disk is quarantined with the same `bundle_copy.quarantine()` primitive as everything else - recoverable, not deleted - and any now-empty directory shell the move leaves behind is pruned. This is not a general mechanism: a surface removed the ordinary way (ledger entry + shim, PLAN-AH9) never needs an entry here, because a receipt already records its path by the time the surface is dropped. Do not add future removals to this list.

Separately, and on **every** sync regardless of whether the files above were found this run, `sync.py` structurally strips any `hooks.*` entry in the target's `.claude/settings.json` whose command references `foundry-log.py` (`LEGACY_ORPHAN_HOOK_MARKERS`) - the case a human who already deleted the files by hand but left the registration behind still needs closed. As of PLAN-AK8, this same structural strip also covers any hook this run's ordinary `classify_stale`/`to_quarantine` path drops, not only the closed legacy list. `_strip_dangling_hook_commands` is called with `LEGACY_ORPHAN_HOOK_MARKERS` plus the receipt-verified quarantined hook paths, one general call rather than a second, duplicate mechanism. Every other key in `settings.json`, including an unrelated hook entry in the same event list, is untouched. Reported as `dangling_hook_entries_removed` in the payload, and empty when there was nothing to remove.

## Step 3b: Gitignore convergence for the new paths

Immediately after the settings merge (Step 4a), importing from the freshly-cloned bundle's `_shared/` (same ImportError-guarded pattern as `gitattributes_pin`):

```python
import gitignore_entries
gi_status, gi_added, gi_skipped_tracked = gitignore_entries.ensure_gitignore_entries(target_root)
# gi_skipped_tracked names entries NOT written because git already tracks
# content under them - the target owns those paths (PLAN-AJ6 D4). Surface it.
```

Converges every path in `gitignore_entries.REQUIRED_GITIGNORE_ENTRIES` (which now
includes `.claude/.bundle-receipts/`, PLAN-AK5, alongside the legacy
`.claude/.plan-foundry-bundle-files` and `.claude/.plan-foundry-quarantine/`) into every
already-installed consumer's `.gitignore`, not just fresh installs - `init-plan-foundry`
alone cannot reach the existing consumers this substrate serves.

## Step 4a: Merge bundle settings into target settings.json

After copying bundle-managed paths and running Step 3a's classify/quarantine/sweep (Steps 3 and 3a), and **before** cleaning up the tmp clone (Step 5), merge the bundle's declared settings fragment into the target's `settings.json`. This step runs at `lib/sync.py:924-968`, so under PLAN-AK6's pin-last ordering it runs **before** the version pin is refreshed at `lib/sync.py:1059`, not after - a settings merge that raises leaves the pin naming the previous version. Load the helper from the **freshly-cloned bundle's** `_shared/` (not the target's installed copy, which does not contain `merge_settings.py` on pre-AH2 consumers):

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

**Accepted trade-off:** "persist on every update" means sync re-adds the deny even if a consumer deliberately removed the deny entry. Given the tool's mobile bugs and the prose-first methodology, this default is intentional (PLAN-AH2 section Context).

**Out of scope:** `plan-foundry-uninstall` does not strip the bundle-injected deny (PLAN-AH2 section Out of scope).

`settings_report` is recorded in the payload as `settings_merge: {status, entries_added, entries_already_present}` and appended to `diagnostics`.

## Step 4b: Refresh the CLAUDE.md operating-rules block

After Step 4a's settings merge, Step 3b's gitignore convergence, and the gitattributes and hooks-path stages this document gives no numbered step to, and **before** cleaning up the tmp clone (Step 5), read `operating-rules.md` from the freshly-cloned bundle and apply the sentinel-block logic to the host project's `CLAUDE.md`. This step runs at `lib/sync.py:1012-1040`, so it is the last step before Step 4c's receipt write, and it too runs **before** the version pin is refreshed at `lib/sync.py:1059`:

```python
operating_rules_path = bundle_path / ".claude" / "skills" / "init-plan-foundry" / "operating-rules.md"
operating_rules = operating_rules_path.read_text(encoding="utf-8")

# PLAN-AK5: report a non-additive change BEFORE applying it, while the
# clone is still on disk. Resolved via getattr, not a direct attribute
# access - an installed claude_md_block.py may predate this function.
block_change_report = getattr(claude_md_block, "block_change_report", None)
if block_change_report is not None:
    block_report = block_change_report(target_root, operating_rules)
    # block_report["status"] is "additive" | "non-additive" | "unavailable";
    # fold into payload["claude_md"] as change_status/removed_lines/added_lines.

cmd_status, cmd_note = claude_md_block.apply_operating_rules_block(target_root, operating_rules)
```

**This step reports, and does not refuse.** `apply_operating_rules_block` still runs and
still replaces the block regardless of `change_status` - the sentinel block keeps its
replace-wholesale contract, which is the right contract for rules the bundle governs.
A `change_status` of `"non-additive"` means a line present in the block before this
sync is absent from the block afterwards, and the report names which lines went rather
than stopping the replace.

Behaviour:

- **Markers present (normal case):** The content between `<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->` is replaced with the bundle's current `operating-rules.md` text. All host-authored content outside the markers is preserved verbatim. Returns `("PASS", "replaced-block")` or `("SKIPPED", "already current")` if the block body already matches.
- **Markers absent:** The sentinel block is appended to the existing `CLAUDE.md` with an appropriate separator. Returns `("PASS", "appended-block")`.
- **CLAUDE.md absent:** A stub `CLAUDE.md` is created containing a header and the sentinel block. Returns `("PASS", "created")`.
- **Malformed markers (end before start, or duplicate markers):** Returns `("FAIL", <reason>)` **without writing the file** - the host `CLAUDE.md` is left byte-for-byte unchanged. `apply_operating_rules_block` **returns** that verdict rather than raising (`_shared/claude_md_block.py:77` and `:88`), so this outcome does not stop the run. `sync.py` records the FAIL and continues straight on to write the receipt, write the version pin, and clear the incomplete-sync marker exactly as a clean run does (`lib/sync.py:1034-1061`). By the time the operator reads the result, the bundle-managed dirs and the version pin are therefore both already updated and no incomplete-sync marker is left behind, so nothing in the tree needs repairing. This is non-destructive and retry-safe: the operator fixes their `CLAUDE.md` markers and re-runs sync, and every other operation is idempotent.
- **operating-rules.md absent in bundle** (old bundle predating this feature): treated as `("SKIPPED", "operating-rules.md absent in bundle")` - not a crash.

`cmd_status`/`cmd_note` are recorded in `payload["claude_md"]` and appended to `result["diagnostics"]` and the `summary` string. If `cmd_status == "FAIL"`, sync surfaces `outcome: exception` to alert the operator (`lib/sync.py:1196-1197`).

**This is the one `outcome: exception` that is not an incomplete sync**, and telling the two apart decides what the operator does next. The run completed every write, so the payload carries the ordinary completed-run shape (`lib/sync.py:1092-1130`) with no `failed_step`, no `steps_completed`, no `partially_applied` and no `incomplete_marker`. Do not apply "Reporting an incomplete sync" below to this case - that section's third item tells the operator the version pin was not advanced, and here the pin **was** advanced. Distinguish the two by looking for `payload.failed_step`: present means a step raised part-way and the tree is partially applied, absent means the run finished and only the host `CLAUDE.md` was left alone.

This step runs inside the `try` block that guards the `finally: cleanup_tmp()`, so the bundle is still on disk when `operating-rules.md` is read.

## Step 4c: Write the new receipt, then the version pin, then clear the marker (PLAN-AH7 + PLAN-AK6)

After every step above, including quarantine and sweep, in this order:

```python
bundle_copy.write_receipt(
    target_claude,
    report.files_copied + report.files_unchanged,
    new["sha"],
    bundle="plan_foundry",  # PLAN-AK5: namespaced, so a sibling bundle cannot overwrite this record
)
bundle_copy.write_version_file(bundle_path, target_claude, data=new)  # Step 4, moved here
bundle_copy.clear_sync_incomplete(target_claude)  # Step 2c's marker, cleared last
```

Without the `bundle=` argument, this write goes to the shared legacy filename a sibling
bundle also writes, which is the record the divergence check in Step 3 depends on -
see D4 in PLAN-AK5's Context for why the namespacing, not the detection logic, is what
makes the check possible at all.

This is the load-bearing ordering rule from Step 1: writing the receipt any earlier - in particular immediately after the copy, which is the natural place an implementer drifts to - makes `gone_upstream` always empty and quarantine never fire on any consumer, silently. The version pin and the marker clear follow the receipt rather than precede the receipt (PLAN-AK6 D4/D5): every step above is what makes the pin's claim true, so a failure anywhere above must leave the pin naming the previous version and the marker still in place.

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
    "refused_not_ours": [...],
    "forced_overwrites": [...],
    "ownership_unverified": null,
    "claude_md": {"status": "PASS|SKIPPED|FAIL", "note": "...", "change_status": "additive|non-additive|unavailable", "removed_lines": [...], "added_lines": [...]},
    "settings_merge": {"status": "PASS|SKIPPED", "entries_added": [...], "entries_already_present": [...]},
    "gitattributes": {"status": "PASS|SKIPPED", "pins_added": [...]},
    "hooks_path": {"status": "PASS|SKIPPED", "note": "..."},
    "gitignore_convergence": {"status": "PASS|SKIPPED", "entries_added": [...], "entries_skipped_tracked": [...]},
    "shim_skipped": [...],
    "quarantine": {
      "receipt_absent": false,
      "reason": "<present only when receipt_absent is true>",
      "gone_upstream_quarantined": [{"path": "...", "sha256": "...", "modified_since_install": false, "replaced_by": "...", "note": "..."}],
      "modified_since_install_preserved": [{"path": "...", "sha256": "...", "modified_since_install": true}],
      "consumer_owned_preserved": [...],
      "unknown": [...],
      "swept": [...],
      "legacy_orphans_quarantined": [...],
      "ledger_unavailable": null
    },
    "dangling_hook_registrations": [...],
    "dangling_hook_registrations_local": [...],
    "dangling_hook_entries_removed": [...],
    "previous_run_incomplete": null
  },
  "summary": "synced <prev[:8]> -> <new[:8]> (ref=<ref>): N copied, M unchanged, K project additions preserved, S stale, CLAUDE.md <status> (<note>), settings <status>"
}
```

The `summary` string is built at `lib/sync.py:1180-1195` and is longer than a copied/unchanged count. Two clauses are appended conditionally: `; refused to overwrite N path(s) not written by this bundle: [...]` when `refused_not_ours` is non-empty, and `; CLAUDE.md sentinel block lost line(s) - see diagnostics` when `change_status` is `"non-additive"`. Those two clauses are how a refusal and a non-additive block change reach an operator who reads only the summary, so a paraphrase that drops them breaks the reporting obligations stated further below.

`previous_run_incomplete` (PLAN-AK6) carries the marker left by an earlier, unfinished run against this same target, or `null` when none was found. The field is present whether this run reached `success` or `exception`, because the field names a fact about a *prior* run rather than this one.

`outcome: exception` if Step 1 FAILed (target not initialised), Step 2 FAILed (clone error), Step 2a's handover failed before anything was written, a later step (Step 3 through Step 4c) raised part-way through, or Step 4b returned `cmd_status == "FAIL"` on malformed `CLAUDE.md` markers (`lib/sync.py:1196-1197`). Only the raised-part-way case has the payload shape "Reporting an incomplete sync" below describes. The malformed-markers case is a **completed** run - every write landed, including the version pin - and carries the ordinary completed-run payload instead, as Step 4b sets out.

`outcome: blocked` (PLAN-AH8) if Step 2b halted on a major version step with in-flight PLANs and `--allow-in-flight` was not passed. This is a deliberate refusal to proceed, not a failure - a consumer switching on `exception` alone would misreport this as a crash. The payload shape for `blocked` is:

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

## Reporting refusals and block changes

A refusal in Step 3, or a non-additive block change in Step 4b, is not a failed sync,
so `outcome` stays `success`. A consumer with no ownership record must still see the
refusal, because a refusal can leave the target holding this bundle's new generation at
every path except the refused ones. The operator-facing reply the human actually reads
must contain:

- **Every refused path, named individually**, with a statement that the path was not
  written and that the install is now mixed at that path - a summary stating only "N
  paths refused" does not satisfy this. `payload["refused_not_ours"]` is the list, and
  `payload["ownership_unverified"]` names the reason when no receipt could be trusted at
  all this run.
- **Every removed sentinel-block line, quoted verbatim** - `payload["claude_md"]["removed_lines"]`
  when `change_status` is `"non-additive"`. The operator needs the removed lines
  themselves, because a flag stating that the block changed does not identify them.
- **The standing conflicts file, named by path** -
  `.claude/.bundle-receipts/plan_foundry.conflicts` - so the operator knows an unresolved
  refusal re-reports on the next sync and the one after rather than scrolling past once.

## Reporting an incomplete sync

When Step 3 through Step 4c **raises** part-way through (PLAN-AK6 D7), the operator-facing reply must contain, in this order. This section applies only to a raised exception - Step 4b's malformed-markers `("FAIL", ...)` return is not one, and applying this section to it would tell the operator the pin was not advanced when it was:

1. **The step that failed** - `payload.failed_step`, one of `copy`, `conflicts`, `quarantine`, `settings_merge`, `gitignore`, `gitattributes`, `hooks_path`, `claude_md`, `receipt`, `version_pin`, or `unknown`. The order of that list is `_SYNC_STEPS_IN_ORDER` at `lib/sync.py:337-348`, and `failed_step` is the first name in it not already in `steps_completed`.
2. **The steps that completed** - `payload.steps_completed`, the ordered list of step names cleared before the failure.
3. **A statement that the version pin was not advanced** - the pin at `<target>/.claude/.plan-foundry-bundle-version` still names `payload.previous_sha`, not `payload.target_sha`.
4. **The marker's path** - `payload.incomplete_marker`, the POSIX path of `.claude/.plan-foundry-sync-incomplete`, which is left in place deliberately.
5. **The instruction to run the sync again** - the repair for an incomplete sync is another sync, and the run that finds this marker at its own start reports the marker (via `previous_run_incomplete` above) and proceeds rather than refusing.

Payload shape for this case:

```json
{
  "outcome": "exception",
  "payload": {
    "steps_completed": ["copy", "quarantine"],
    "partially_applied": true,
    "failed_step": "settings_merge",
    "previous_sha": "<40-char>",
    "target_sha": "<40-char>",
    "incomplete_marker": ".claude/.plan-foundry-sync-incomplete",
    "previous_run_incomplete": null
  },
  "summary": "sync stopped part-way at step 'settings_merge' - the version pin was not advanced and the target is partially applied; a marker at .claude/.plan-foundry-sync-incomplete records it, and the repair is to run the sync again"
}
```

## Notes

- **Tag pinning.** `/plan-foundry-sync v0.5.0` passes `ref=v0.5.0` to the clone.
- **Crashed prior run.** If `.plan-foundry-tmp/` already exists when sync starts (from a crashed prior run), Step 2 removes it before cloning.
- **Network required.** No offline fallback. If the user is offline, the operation cleanly fails - uninstall remains available because uninstall is local-only.
- **In-flight override (PLAN-AH8).** `--allow-in-flight` overrides the Step 2b halt on a major version step with in-flight PLANs. Use only when the operator has confirmed the in-flight work is safe to proceed under the incoming bundle.
- **Handover fall-back (PLAN-AK6).** `--no-reexec` forces this run to stay in process rather than handing over to the cloned bundle's own `sync.py` - the operator's bypass if a handover misbehaves in the field. `--prefetched-bundle <path>` is set by the handover itself on the child process the handover spawns, and an operator does not pass the flag by hand.
- **Force-overwrite a diverged path (PLAN-AK5).** `--force-overwrite-diverged` overwrites every path this run classifies as "not ours" instead of refusing that path - opt-in, never a default, and the escape hatch for a path that would otherwise be stuck refused forever. Forwarded through the AK6 handover automatically when set, and a consumer whose installed `sync.py` predates the flag reaches the flag by invoking the freshly-cloned bundle's own `sync.py` directly (see Step 3's divergence check above).
