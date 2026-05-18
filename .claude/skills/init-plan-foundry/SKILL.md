---
name: init-plan-foundry
description: Bootstrap a target repository with the plan_foundry skill scaffold. Creates the coarse symlink `<target>/.claude → ~/.claude/plan_foundry/.claude`, scaffolds Workbench/ and Retired/, seeds the current-month LOG, updates .gitignore, and inlines operating-rules into the target's CLAUDE.md via paired sentinel markers. Idempotent — running twice produces no change unless the bundle's operating-rules.md changed. Trigger phrases — "initialise plan_foundry", "set up plan_foundry", "bootstrap plan_foundry", "init plan_foundry".
---

<objective>
Make a target project plan_foundry-aware after the bundle is cloned at ~/.claude/plan_foundry/. Three layers: (a) coarse `.claude` symlink into the bundle so the target inherits every skill, agent, and command; (b) create project state directories and files (Workbench/, Retired/, monthly LOG, .gitignore entries); (c) inline the bundle's operating-rules.md content into the target's CLAUDE.md between paired sentinel markers (`<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->`). Re-running the skill detects the markers and replaces content between them with the current operating-rules.md.
</objective>

<essential_principles>
Idempotent. Every operation checks-first-then-acts; running the skill twice over an unchanged bundle produces no diff.
Bundle retains content authority. The target's CLAUDE.md content between the sentinel markers is owned by the bundle; the skill replaces it from operating-rules.md on every run. Humans should not hand-edit between markers — edits are lost on re-run (warning is included in the inserted block).
Non-invasive elsewhere. Outside the sentinel-bounded block, the skill never modifies the target's CLAUDE.md.
Self-reporting. Return a per-step PASS / SKIPPED / FAIL report so the human sees exactly what changed.
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a target project (CWD is the project root).
- The plan_foundry bundle is cloned at `~/.claude/plan_foundry/` (the default). Override via the `PLAN_FOUNDRY_BUNDLE_PATH` environment variable if installed elsewhere.
- The bundle's `.claude/skills/init-plan-foundry/operating-rules.md` is reachable.
</preconditions>

<inputs>
None. The skill operates on the current working directory.
</inputs>

**Init procedure:** See [workflows/init-steps.md](workflows/init-steps.md) for the step-by-step bootstrap.

<constraints>
- Never overwrite an existing file. Only create files that are absent.
- Outside the sentinel-bounded marker block, never modify the target's CLAUDE.md.
- Never run git operations — bootstrap is a filesystem-level change; commit cadence is the target's choice.
- Never write to directories outside the target's project root, with one exception: the coarse `.claude` symlink whose target IS the bundle path.
- On detected sentinel-marker malformation (start or end count != 1, or end appears before start), FAIL the relevant step with `markers-malformed` diagnostic — do not attempt automatic recovery.
- If `<target>/.claude` already exists as a real directory (not a symlink) with content, surface a conflict and abort — do not destroy.
</constraints>

<success_criteria>
- `<target>/.claude` is a symlink to `~/.claude/plan_foundry/.claude` (or the resolved bundle path)
- Workbench/ exists and contains a current-month LOG file
- Retired/ exists
- .gitignore contains entries for Retired/ and Workbench/.heartbeat/ unconditionally, plus `.claude` when running in a target repo (per D10 — the target's .claude is a symlink into the home bundle, not target-tracked content). The `.claude` entry is suppressed when running inside the bundle source itself (`plan_foundry_dev` or `plan_foundry`), where `.claude/` is real tracked content.
- Target CLAUDE.md (created or existing) contains a single pair of `<!-- plan-foundry:init-plan-foundry:start -->` and `<!-- plan-foundry:init-plan-foundry:end -->` markers wrapping the current operating-rules.md content byte-for-byte
- The human is shown a "RESTART Claude Code for project-local skills to register" notice
- The skill returns a structured per-step report
</success_criteria>
