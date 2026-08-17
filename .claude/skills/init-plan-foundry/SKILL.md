---
name: init-plan-foundry
disable-model-invocation: true
description: 'Bootstrap a target repository with the plan_foundry skill scaffold. Clones the public plan_foundry bundle on demand into `<target>/.plan-foundry-tmp/`, copies `.claude/{skills,agents,commands,hooks}` into the target, scaffolds `Workbench/` and `Retired/`, updates `.gitignore`, inlines operating-rules into `CLAUDE.md` via paired sentinel markers, merges bundle-declared settings (e.g. AskUserQuestion deny) into `<target>/.claude/settings.json` without clobbering consumer entries, records the bundle version pin at `.claude/.plan-foundry-bundle-version`, and deletes the tmp clone. Network required. Idempotent - re-running converges to the same state. Optional `--ref <tag-or-branch>` pins to a specific bundle version. Trigger phrases - "initialise plan_foundry", "set up plan_foundry", "bootstrap plan_foundry", "init plan_foundry".'
---

<objective>
Make a target project plan_foundry-aware. Under the AC6 network-clone model (PLAN-AC6, 2026-05-19), the bundle is fetched on demand from `https://github.com/kccastillo/plan_foundry` into a transient `<target>/.plan-foundry-tmp/`. Bootstrap takes effect in layers. (a) Copy the bundle's `.claude/{skills,agents,commands,hooks}` into the target's `.claude/` as real per-project content and record the bundle version pin at `.claude/.plan-foundry-bundle-version`. (b) Create project state directories and files (Workbench/, Retired/, .gitignore entries that gitignore bundle-managed paths plus the transient `.plan-foundry-tmp/`). (c) Inline the bundle's operating-rules.md content into the target's CLAUDE.md between paired sentinel markers. The tmp clone is deleted at the end of every run. Re-runs converge from every precursor state listed in `workflows/init-steps.md` Step 2.
</objective>

<essential_principles>
Idempotent. Every operation checks-first-then-acts, so running the skill twice over an unchanged bundle changes only the two timestamps that record when the run happened: `synced=` in the version pin and `written=` in the install receipt, both of which are rewritten on every run.
Bundle retains content authority. Bundle-managed paths (`.claude/{skills,agents,commands,hooks}`) and the operating-rules block of CLAUDE.md are owned by the bundle, and the skill overwrites those on every run. Humans should not hand-edit bundle-managed files or between CLAUDE.md sentinel markers - edits are lost on re-run.
Non-destructive to project-local content. Inside `.claude/`, anything not under the bundle-managed dirs `skills`, `agents`, `commands` and `hooks` is project-local and preserved. Outside the sentinel-bounded CLAUDE.md block, the skill never modifies CLAUDE.md.
`plan-foundry-sync` quarantines bundle files that no longer exist upstream (PLAN-AH7), moving them to `.claude/.plan-foundry-quarantine/<UTC-timestamp>/` rather than removing them. `sweep_quarantine` is the only function permitted to delete anything, and only whole quarantine directories aged past 30 days. Project-added skills/agents under those dirs (e.g. `.claude/skills/my-project-skill/`) are left alone.
Sandbox-safe. Reads and writes are strictly inside the target repo's working tree. The transient `.plan-foundry-tmp/` is also inside the target.
Network required. No offline fallback exists, so a failed clone ends the operation cleanly with a diagnostic.
Self-reporting. Return a per-step PASS / SKIPPED / FAIL report.
Repository-presence advisory. Bootstrap surfaces a warning when the target is not a git working tree and never blocks on that warning. Bootstrap never runs `git init` on the consumer's behalf (see `<constraints>` and `workflows/init-steps.md` Step 0b).
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a target project (CWD is the project root).
- Network reachable to `https://github.com/kccastillo/plan_foundry`.
- `git` available on `PATH`.
- Target is not the bundle source itself (Step 0 detects that case and fails the run).
</preconditions>

<inputs>
Optional `--ref <tag-or-branch>` argument. Default `main`. Example: `/init-plan-foundry v0.5.0`.
</inputs>

**Init procedure:** See [workflows/init-steps.md](workflows/init-steps.md) for the step-by-step bootstrap.

<constraints>
- Bootstrap never removes anything from the target. A file under a bundle-managed path that the bundle no longer ships is listed in the Step 2 `CopyReport` as `stale_in_target` and left on disk - the receipt-backed quarantine that acts on it belongs to `plan-foundry-sync`, as stated above, because a fresh bootstrap has no prior install receipt to classify against. Bootstrap does write that receipt, at `.claude/.bundle-receipts/plan_foundry.files`, immediately after the copy, and it is the record a later sync classifies against.
- Never modify the target's project-local content under `.claude/` (anything not under skills/agents/commands/hooks).
- Outside the sentinel-bounded marker block, never modify the target's CLAUDE.md.
- Never commit or push against the target's own repo - bootstrap is a filesystem-level change, and commit cadence is the target's choice. Beyond `git clone` from the public bundle URL into `.plan-foundry-tmp/`, bootstrap also runs git operations against the target repository itself. Via `_step_repo_presence`, bootstrap runs an advisory-only `git rev-parse --is-inside-work-tree` (plus, on a PASS, a `git rev-parse --show-toplevel` read to distinguish the target being a repository root from being a subdirectory of one) before anything else is written into the target. Via `_step_hooks_path`, bootstrap runs `git rev-parse --git-dir`, a `core.hooksPath` read, and (when unset) a `core.hooksPath` write, deliberately sequenced after the line-ending pin so a fresh clone gets its first hooks-path wiring, per `_shared/hooks_path.py`. None of these ever writes git history or config the consumer did not already choose to have written (the `core.hooksPath` write is the sole exception, and only when unset).
- Never write outside the target's working tree.
- Always clean up `<target>/.plan-foundry-tmp/` at end of run (success or failure path).
- On detected sentinel-marker malformation (start or end count != 1, or end appears before start), FAIL the relevant step with `markers-malformed` diagnostic - do not attempt automatic recovery.
- If `<target>/.claude` is a symlink that does not resolve to a path containing `plan_foundry` (legacy AC3 install), FAIL Step 2 with `symlink-target-mismatch` - do not silently overwrite.
- If running inside the bundle source itself (basename match or git-config substring match per Step 0), FAIL Step 0 with `bundle-source-init-refused` - bundle development happens directly in the source tree.
</constraints>

<success_criteria>
- `<target>/.claude` is a real directory (not a symlink) containing copies of the bundle's `skills/`, `agents/`, `commands/`, `hooks/`.
- `<target>/.claude/.plan-foundry-bundle-version` exists with `sha=`, `tag=`, `synced=` and `schema_version=` lines.
- Workbench/ exists.
- Retired/ exists.
- .gitignore contains every entry in `REQUIRED_GITIGNORE_ENTRIES` (`_shared/gitignore_entries.py`), less any entry dropped because git already tracks content beneath it - a dropped entry is reported as a diagnostic rather than written. (Per PLAN-AD0 D2-A 2026-05-22, `Retired/` is intentionally tracked, not gitignored, so it is not in that tuple.)
- Target CLAUDE.md (created or existing) contains a single pair of `<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->` markers wrapping the current operating-rules.md content byte-for-byte.
- `<target>/.claude/settings.json` contains `AskUserQuestion` in `permissions.deny`. Consumer's own `allow`/`deny` entries and `hooks` block are preserved - the merge is non-clobbering. Re-running the skill is idempotent, so the deny entry is never duplicated. The bundle-injected deny is not removed by `plan-foundry-uninstall` (uninstall un-merge is out of scope per PLAN-AH2).
- `<target>/.plan-foundry-tmp/` does not exist after the run.
- The human is shown a "RESTART Claude Code for project-local skills to register" notice.
- The skill returns a structured per-step report.
</success_criteria>
