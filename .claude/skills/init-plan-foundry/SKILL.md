---
name: init-plan-foundry
description: Bootstrap a target repository with the plan_foundry skill scaffold. Copies the bundle's `.claude/{skills,agents,commands,hooks}` into the target as real per-project content, scaffolds Workbench/ and Retired/, seeds the current-month LOG, updates .gitignore (gitignoring bundle-managed paths so they don't churn the project's git history), inlines operating-rules into the target's CLAUDE.md via paired sentinel markers, and records the bundle version at .claude/.plan-foundry-bundle-version. Idempotent — running twice converges to the same state. Subsequent bundle updates are pulled in per-project via /plan-foundry-sync. Migrates legacy AC3 symlink installs in-place. Trigger phrases — "initialise plan_foundry", "set up plan_foundry", "bootstrap plan_foundry", "init plan_foundry".
---

<objective>
Make a target project plan_foundry-aware after the bundle is cloned at ~/.claude/plan_foundry/. Three layers: (a) copy the bundle's `.claude/{skills,agents,commands,hooks}` into the target's `.claude/` as real per-project content and record the bundle version pin at `.claude/.plan-foundry-bundle-version`; (b) create project state directories and files (Workbench/, Retired/, monthly LOG, .gitignore entries that gitignore bundle-managed paths but track project-local files); (c) inline the bundle's operating-rules.md content into the target's CLAUDE.md between paired sentinel markers (`<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->`). Re-running the skill detects the markers and replaces content between them with the current operating-rules.md. The skill converges from four precursor states (absent `.claude/`, legacy AC3 symlink, real-directory hand-copy, or symlink-elsewhere) to the same end state, so it's safe to re-run after any prior install attempt.
</objective>

<essential_principles>
Idempotent. Every operation checks-first-then-acts; running the skill twice over an unchanged bundle produces only a refreshed `synced` timestamp in the version pin.
Bundle retains content authority. Bundle-managed paths (`.claude/{skills,agents,commands,hooks}`) and the operating-rules block of CLAUDE.md are owned by the bundle; the skill overwrites those on every run. Humans should not hand-edit bundle-managed files or between CLAUDE.md sentinel markers — edits are lost on re-run (warning is included in the inserted CLAUDE.md block).
Non-destructive to project-local content. Inside `.claude/`, anything not under the four bundle-managed dirs is project-local and preserved. Outside the sentinel-bounded CLAUDE.md block, the skill never modifies CLAUDE.md.
Never delete from target. Bundle files that no longer exist upstream survive in the target's bundle-managed dirs (reported as `stale_in_target` for user awareness). Project-added skills/agents under those dirs (e.g. `.claude/skills/my-project-skill/`) survive too.
Self-reporting. Return a per-step PASS / SKIPPED / FAIL report so the human sees exactly what changed.
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a target project (CWD is the project root).
- The plan_foundry bundle is cloned at `~/.claude/plan_foundry/` (the default). Override via the `PLAN_FOUNDRY_BUNDLE_PATH` environment variable if installed elsewhere.
- The bundle's `.claude/skills/init-plan-foundry/operating-rules.md` is reachable.
- Target is NOT the bundle source itself (Step 2 detects and refuses).
</preconditions>

<inputs>
None. The skill operates on the current working directory.
</inputs>

**Init procedure:** See [workflows/init-steps.md](workflows/init-steps.md) for the step-by-step bootstrap.

<constraints>
- Never delete from the target's bundle-managed paths. Files no longer in the bundle survive as `stale_in_target`; user removes them manually if desired.
- Never modify the target's project-local content under `.claude/` (anything not under skills/agents/commands/hooks).
- Outside the sentinel-bounded marker block, never modify the target's CLAUDE.md.
- Never run git operations — bootstrap is a filesystem-level change; commit cadence is the target's choice.
- Never write outside the target's project root.
- On detected sentinel-marker malformation (start or end count != 1, or end appears before start), FAIL the relevant step with `markers-malformed` diagnostic — do not attempt automatic recovery.
- If `<target>/.claude` is a symlink resolving to anywhere other than the configured bundle's `.claude` (including a broken symlink), FAIL Step 3 with `symlink-target-mismatch` — do not silently overwrite.
- If running inside the bundle source itself (basename match or git-config substring match per Step 2), FAIL Step 2 with `bundle-source-init-refused` — bundle development happens directly in the source tree.
</constraints>

<success_criteria>
- `<target>/.claude` is a real directory (not a symlink) containing copies of the bundle's `skills/`, `agents/`, `commands/`, `hooks/`.
- `<target>/.claude/.plan-foundry-bundle-version` exists with `sha=`, `tag=`, `synced=` lines.
- Workbench/ exists and contains a current-month LOG file.
- Retired/ exists.
- .gitignore contains entries for `Retired/`, `Workbench/.heartbeat/`, `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`, `.claude/.plan-foundry-bundle-version`, `.claude/_foundry_log.jsonl` — each on its own line.
- Target CLAUDE.md (created or existing) contains a single pair of `<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->` markers wrapping the current operating-rules.md content byte-for-byte.
- The human is shown a "RESTART Claude Code for project-local skills to register" notice.
- The skill returns a structured per-step report.
</success_criteria>
