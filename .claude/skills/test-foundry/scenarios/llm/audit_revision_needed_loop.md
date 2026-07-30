# audit_revision_needed_loop

**Scenario ID:** `audit_revision_needed_loop`

**Tier:** LLM (parent-session `Skill(...)` dispatches required)

## Goal

Verify that a deliberately-flawed PLAN cannot escape `audit-sufficiency` / `audit-haiku-safe` revisions - that after `MAX_ITERATIONS=5` sufficiency cycles the pipeline halts and the orchestrator emits a `WIP:` halt commit.

## Fixture preparation (`prep_scenario`)

1. Create temp dir `<tmp>/Workbench/` (within a fresh git repo, since the assertion inspects `git log`).
2. Seed a deliberately-flawed PLAN at `<tmp>/Workbench/PLAN-test-flawed-XX_audit-loop.md` with `pipeline_phase: drafting`, schema-v2 frontmatter, **but no `## Steps` section** (this guarantees sufficiency-audit failure).
3. `git init && git add -A && git commit -m "seed"` inside `<tmp>`.
4. Return `context = { "repo": "<tmp>", "target_plan": "PLAN-test-flawed-XX_audit-loop.md" }`.

## Parent-session `Skill(...)` invocations

Dispatch `Skill("plan-pipeline", "advance PLAN-test-flawed-XX_audit-loop.md")` (or equivalent) repeatedly - up to `MAX_ITERATIONS=5` - and let plan-pipeline run its sufficiency-audit loop. The scenario does NOT intervene to "fix" the PLAN; the deliberate flaw must persist.

## Mechanical assertions

After `MAX_ITERATIONS=5` cycles have elapsed (or the orchestrator self-halts earlier):

```json
[
  {
    "path": "<repo>/Workbench/PLAN-test-flawed-XX_audit-loop.md",
    "frontmatter_key": "audit_state.last_outcome",
    "expected": "exception"
  },
  {
    "kind": "git_log_substring",
    "cwd": "<repo>",
    "command": "git log --oneline -1",
    "expected_substring": "WIP: pipeline halted at drafted"
  }
]
```

**Pass condition:** both assertions hold.
**Fail condition:** either assertion fails.

## Cleanup

Remove `<tmp>/` entirely.
