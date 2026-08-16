---
description: Single-tier currency check. Reads this project's `.claude/.plan-foundry-bundle-version` pin and compares it to the remote bundle's HEAD via `git ls-remote https://github.com/kccastillo/plan_foundry`. If behind, surfaces `/plan-foundry-sync` as the next step. Network required (graceful failure if unreachable).
---

Read `.claude/skills/plan-foundry-check-current/SKILL.md`, follow the workflow it
describes, and report the result. Read the file directly rather than dispatching the
Skill tool: the skill carries `disable-model-invocation: true`, and whether that flag
blocks a Skill-tool call made from a command body is unsettled.

The skill runs `lib/check_current.py`, which:
1. Reads `<target>/.claude/.plan-foundry-bundle-version` (the project pin).
2. Runs `git ls-remote https://github.com/kccastillo/plan_foundry HEAD` (the remote HEAD).
3. Compares.

Status ∈ {`current`, `behind_or_diverged`, `not_initialised`, `legacy_symlink`, `remote_unreachable`, `unknown`, `sync_incomplete`}. Output is structured JSON with `status`, `project_sha`, `remote_sha`, `message`, `sync_incomplete`.

After invocation, report:
- `status` and human-readable `message`.
- If `behind_or_diverged`: surface "run /plan-foundry-sync".
- If `not_initialised`: surface "run /init-plan-foundry first".
- If `legacy_symlink`: surface "run /init-plan-foundry to migrate".
- If `remote_unreachable`: report current pin and the network error.
- If `sync_incomplete`: a previous sync started and did not finish - report the sha it was moving to (`sync_incomplete.target_sha`) and surface "run /plan-foundry-sync again to complete it". This is decided ahead of any network call, so it can fire even when the pin would otherwise compare as current.
