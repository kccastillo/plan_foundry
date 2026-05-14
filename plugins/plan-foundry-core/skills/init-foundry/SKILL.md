---
name: init-foundry
description: Bootstrap plan-foundry into a consumer project. Creates project state (Workbench/, current-month LOG, Retired/, .gitignore entries) and makes the consumer's CLAUDE.md plan-foundry-aware by inlining the plugin's operating-rules content between paired sentinel markers. Idempotent — running twice produces no change unless the plugin's operating-rules.md changed. Trigger phrases: "initialise plan-foundry", "set up plan-foundry", "bootstrap plan-foundry", "init foundry".
---

<objective>
Make a consumer project plan-foundry-aware after plugin install. Two layers: (a) create project state directories and files; (b) inline the plugin's operating-rules.md content into the consumer's CLAUDE.md between paired sentinel markers (`<!-- plan-foundry:init-foundry:start -->` and `<!-- plan-foundry:init-foundry:end -->`). Re-running the skill detects the markers and replaces content between them with the current operating-rules.md.
</objective>

<essential_principles>
Idempotent. Every operation checks-first-then-acts; running the skill twice over an unchanged plugin produces no diff.
Plugin retains content authority. The consumer's CLAUDE.md content between the sentinel markers is owned by the plugin; the skill replaces it from the plugin's operating-rules.md on every run. Humans should not hand-edit between markers — edits are lost on re-run (warning is included in the inserted block and in the stub template).
Non-invasive elsewhere. Outside the sentinel-bounded block, the skill never modifies the consumer's CLAUDE.md.
Self-reporting. Return a per-step PASS / SKIPPED / FAIL report so the human sees exactly what changed.
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23.
</essential_principles>

<preconditions>
- Running in a Claude Code session inside a consumer project (CWD is the project root).
- The plan-foundry-core plugin is installed (this skill itself is being invoked, so the plugin is present).
</preconditions>

<inputs>
None. The skill operates on the current working directory.
</inputs>

**Init procedure:** See [workflows/init-steps.md](workflows/init-steps.md) for the step-by-step bootstrap.

<constraints>
- Never overwrite an existing file. Only create files that are absent.
- Outside the sentinel-bounded marker block, never modify the consumer's CLAUDE.md.
- Never run git operations — bootstrap is a filesystem-level change; commit cadence is the consumer's choice.
- Never write to directories outside the consumer's project root.
- On detected sentinel-marker malformation (start or end count != 1, or end appears before start), FAIL Step 6 with `markers-malformed` diagnostic — do not attempt automatic recovery.
</constraints>

<success_criteria>
- Workbench/ exists and contains a current-month LOG file
- Retired/ exists
- .gitignore contains entries for Retired/ and Workbench/.heartbeat/
- Consumer CLAUDE.md (created or existing) contains a single pair of `<!-- plan-foundry:init-foundry:start -->` and `<!-- plan-foundry:init-foundry:end -->` markers wrapping the current operating-rules.md content byte-for-byte (after stripping one leading and one trailing newline introduced by the wrapping)
- The skill returns a structured per-step report
</success_criteria>
