---
name: plan-foundry-sync
disable-model-invocation: true
description: 'Pull the latest plan_foundry bundle content into the current project. Clones the public plan_foundry repo into a transient `<target>/.plan-foundry-tmp/`, copies `.claude/{skills,agents,commands,hooks}` over the target''s, refreshes `.claude/.plan-foundry-bundle-version`, refreshes the operating-rules sentinel block in the root `CLAUDE.md`, merges bundle-declared settings (e.g. AskUserQuestion deny) into `<target>/.claude/settings.json` without clobbering consumer entries, and deletes the tmp clone. Network required. Optional `--ref <tag-or-branch>` pins to a specific bundle version. Trigger phrases - "sync plan_foundry", "update plan_foundry bundle", "pull bundle", "plan foundry sync".'
---

<objective>
Propagate bundle updates into the current project. Under the AC6 network-clone model (PLAN-AC6, 2026-05-19), every sync invocation fetches a fresh shallow clone from `https://github.com/kccastillo/plan_foundry` into `<target>/.plan-foundry-tmp/`, copies bundle-managed paths into `<target>/.claude/`, refreshes the version pin, and deletes the tmp clone. No reliance on any path outside the target - works in sandboxed Claude Code sessions (mobile, web, restricted desktop) that have network but no filesystem access outside the project.
</objective>

<essential_principles>
Bundle authority. Bundle-managed files (`.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`) are overwritten with the freshly-cloned bundle's content; local hand-edits are clobbered.
Sync now performs receipt-backed quarantine of stale bundle files (reverses PLAN-AC5 D9, which previously held that auto-prune is out of scope). A path recorded in the install receipt (PLAN-AH7) that is no longer shipped by the bundle is moved - never deleted - to `.claude/.plan-foundry-quarantine/<UTC-timestamp>/`; a path on disk that the receipt never recorded (consumer-owned) is left untouched; a path the receipt recorded whose bytes have since changed is left untouched too, because something else owns it now, and is reported under `modified_since_install_preserved`. `sweep_quarantine` removes only whole quarantine directories aged past 30 days, and it is the sole function permitted to delete anything.
Bundle namespace ownership. `.claude/skills/_shared/` is plan_foundry's, and sync checks who owns the installed copy before loading a helper from it - `bundle-contract.json`'s `bundle` key, read inline, importing nothing from `_shared/`. A value naming a different bundle means a sibling bundle from this lineage is installed here; sync clones first and takes its helpers from the clone. Unchecked, the foreign `bundle_fetch` would clone the other bundle's repo and install a different product under plan_foundry's pin without a word. See ARCHITECTURE.md, Invariant: Bundle Namespace Ownership.
Project-local content untouched. Anything under `.claude/` that is not under the four bundle-managed dirs is never touched, including a project's `.claude/writing-style-local.md` supplement (see `_shared/writing-style.md`, "Project-local supplement"). The one explicit exception is the operating-rules sentinel block in the root `CLAUDE.md` (not under `.claude/`): the content between `<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->` is refreshed on every sync. All other `CLAUDE.md` content and all other project-local content remain untouched. If markers are absent, the block is appended. If markers are malformed, sync surfaces `outcome: exception` and leaves `CLAUDE.md` byte-for-byte unchanged (non-destructive).
Tmp clone is ephemeral. `.plan-foundry-tmp/` is cleaned up at the end of every sync, even on partial failure. It is gitignored.
Network required. No offline fallback. Failure to clone -> operation fails with diagnostic.
Version pin refreshed. Every successful sync writes `.claude/.plan-foundry-bundle-version` with the cloned bundle's commit SHA, tag (if any), and UTC sync timestamp.
Operating-rules refreshed. Every sync reads `operating-rules.md` from the cloned bundle and updates the sentinel block in the host project's root `CLAUDE.md`. The bundle-managed block is identified by sentinel markers; all host-authored content outside the markers is preserved verbatim.
In-flight protection (PLAN-AH8, guarantee 2). Before copying, sync compares the target's version pin against the freshly-cloned bundle's own tag and `schema_version` (never the remote's latest tag - `sync()` clones a specific `--ref`, so remote-latest can both false-halt and silently pass). If that comparison shows a major version step AND `Workbench/` has PLANs mid-pipeline (`pipeline_phase` in `drafting`/`drafted`/`checked`/`executing`/`outcome-verifying`), sync halts with `outcome: "blocked"` - a third value alongside `success` and `exception`, naming a deliberate refusal to proceed rather than a crash. `--allow-in-flight` overrides the halt. A pin written before this protection existed (`pin_predates_contract`) or an underivable comparison (`unavailable`) warn and continue rather than halting - the crossing sync that installs this very protection must not be the one it blocks.
Deprecation shim-then-delete (PLAN-AH9, guarantee 4). Quarantined paths (see receipt-backed quarantine above) are cross-referenced against the deprecation ledger (`preflight.read_deprecations`); a match reports `replaced_by` and `note` instead of a bare path. Full policy - the two address spaces, shim lifecycle, and worked example - is `.claude/skills/_shared/deprecation-policy.md`.
Handover to one generation of code (PLAN-AK6 D2/D3). Before touching the target, sync probes the freshly-cloned bundle's own `sync.py` for handover support (`--help` naming both `--prefetched-bundle` and `--no-reexec`) and, when supported, re-execs it as a child process with `--prefetched-bundle <clone path> --no-reexec`, relaying its result unchanged. This closes a version-skew crash: the installed caller lazily imports several helpers from the freshly-cloned bundle mid-run, and a caller and callee from different generations can crash on a changed return arity. A clone predating the handover mechanism falls back to running in process, exactly as sync ran before this PLAN - an old ref is no worse off. `--no-reexec` is the operator's bypass if a handover misbehaves in the field; `--prefetched-bundle` is set by the handover itself on the child it spawns, not by an operator.
Pin-last, and a loud incomplete sync (PLAN-AK6 D4/D5/D6/D7). The version pin (`.claude/.plan-foundry-bundle-version`) is now the last write of a completed run, after the install receipt, rather than immediately after the copy - every step in between is what makes the pin's claim true. An incomplete-sync marker (`.claude/.plan-foundry-sync-incomplete`) is written immediately before the copy - the first write to the target - and cleared only after the pin write; a run that starts and does not finish leaves it in place, naming the sha it was moving to. `/plan-foundry-check-current` reads the marker ahead of any sha comparison and before the network call, so a target part-way through a failed sync is never reported `current` or merely `behind`. A run that finds a marker from an earlier, unfinished run reports it (`payload.previous_run_incomplete`) and proceeds - the repair for an incomplete sync is another sync. A run that fails part-way returns `outcome: exception` naming the failed step, the steps completed, and the marker's path (see [workflows/sync.md](workflows/sync.md), "Reporting an incomplete sync").
Refuses, reports, never clobbers silently (PLAN-AK5). The install receipt is namespaced by bundle identity at `.claude/.bundle-receipts/<bundle>.files` (a legacy `.claude/.plan-foundry-bundle-files` receipt is still read and adopted when its `sha` header matches this bundle's pin, and is never deleted). Before overwriting a bundle-managed path whose bytes differ from the incoming source, sync checks the receipt: a path absent from it, or recorded with a different sha256 than what is on disk now, is judged not this bundle's own and the write is refused rather than applied - the destination's bytes are left untouched and the path is named in `payload["refused_not_ours"]`, the `summary` string, and a standing conflicts file (`.claude/.bundle-receipts/<bundle>.conflicts`) that re-reports an unresolved refusal on every subsequent sync until the divergence is gone. `--force-overwrite-diverged` opts into overwriting a refused path anyway; never a default. A target with no receipt at all (pre-receipt install, or an unmatched legacy receipt) is not refused anything - every write proceeds as before and `payload["ownership_unverified"]` names the condition rather than staying silent. Separately, a sentinel-block replacement that would remove or reverse a line of the host `CLAUDE.md`'s managed prose is *reported*, not refused: `payload["claude_md"]["change_status"]` is `"non-additive"` and `removed_lines`/`added_lines` name what changed, verbatim, before the block is replaced as it always was. See [workflows/sync.md](workflows/sync.md), "Reporting refusals and block changes".
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a target project (CWD is the project root).
- Network reachable to `https://github.com/kccastillo/plan_foundry`.
- `git` available on `PATH`.
- The target has been initialised - i.e. `<target>/.claude/` is a real directory (not a symlink, not absent) containing `.plan-foundry-bundle-version`. If not, the skill FAILs with diagnostic "run /init-plan-foundry first" and aborts.
</preconditions>

<inputs>
Optional `--ref <tag-or-branch>` argument. Default `main`. Examples: `/plan-foundry-sync`, `/plan-foundry-sync v0.5.0`.

Optional `--allow-in-flight` flag (PLAN-AH8). Overrides the pre-flight halt described below when a major version step is detected while PLANs are in flight. Default `False`.

Optional `--no-reexec` flag (PLAN-AK6). Forces this run to stay in process rather than handing over to the cloned bundle's own `sync.py` - the operator's bypass if a handover misbehaves. Default `False`.

Optional `--prefetched-bundle <path>` argument (PLAN-AK6). Set by the handover itself on the child process it spawns, so the child reuses the parent's clone instead of fetching a second time. Not intended for an operator to pass by hand.

Optional `--force-overwrite-diverged` flag (PLAN-AK5). Overwrites, rather than refuses, a bundle-managed path this run judges "not ours" (see essential_principles above). Default `False`; opt-in, never a default. Forwarded through the AK6 handover automatically when set.
</inputs>

**Sync procedure:** See [workflows/sync.md](workflows/sync.md) for the per-step procedure.

The skill is implemented by [lib/sync.py](lib/sync.py), which uses the shared helpers `_shared/bundle_copy.py` and `_shared/bundle_fetch.py`.

<constraints>
- Performs receipt-backed quarantine of the target's bundle-managed paths (PLAN-AH7); never a direct delete. `sweep_quarantine` is the only function permitted to delete anything, and only whole quarantine directories aged past 30 days.
- Never touch project-local files under `.claude/` (anything not under the four bundle-managed dirs).
- The root `CLAUDE.md` operating-rules sentinel block (between `<!-- plan-foundry:init-plan-foundry:start -->` / `<!-- plan-foundry:init-plan-foundry:end -->`) is refreshed on sync; all other `CLAUDE.md` content is preserved. This is the only project-local file outside `.claude/` that sync touches.
- Never write outside the target repo's working tree.
- Always clean up `<target>/.plan-foundry-tmp/` at end of run (success or failure path).
- Refuse to run if `<target>/.claude` is a symlink (legacy AC3 install) - surface "run /init-plan-foundry to migrate this project" and abort.
- Refuse to run if `<target>/.claude/.plan-foundry-bundle-version` is absent - surface "run /init-plan-foundry first" and abort.
- Refuse (not clobber) a bundle-managed path whose bytes diverge from what the receipt records this bundle last wrote, unless `--force-overwrite-diverged` is passed (PLAN-AK5). A refused path is left untouched and never enters the receipt this run writes.
</constraints>

<success_criteria>
- Bundle-managed paths in target match the fetched bundle byte-for-byte (modulo `stale_in_target` files which survive but are reported).
- `.plan-foundry-bundle-version` exists with current bundle SHA, tag, and a fresh `synced` timestamp.
- `<target>/.claude/settings.json` contains `AskUserQuestion` in `permissions.deny`. Consumer's own `allow`/`deny` entries and `hooks` block are preserved - the merge is non-clobbering. Re-running sync is idempotent; the deny entry is never duplicated. The bundle-injected deny is NOT removed by `plan-foundry-uninstall` (uninstall un-merge is out of scope per PLAN-AH2).
- `<target>/.plan-foundry-tmp/` does not exist after the run.
- Sync report lists previous SHA -> new SHA, ref fetched, file counts (copied / unchanged / project_additions / stale_in_target), and any stale-file paths so the user can manually clean.
</success_criteria>
