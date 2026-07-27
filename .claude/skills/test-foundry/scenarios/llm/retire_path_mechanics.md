# retire_path_mechanics

**Scenario ID:** `retire_path_mechanics`

**Tier:** LLM (parent-session `Skill(...)` dispatches required)

## Goal

Verify the retire-skill post-condition: a PLAN passed to `retire` is **moved** (not deleted) to `Retired/`. Mirrors the §4F post-condition gate that caught the PLAN-AA2 retire-bug.

## Fixture preparation (`prep_scenario`)

1. Create temp dir `<tmp>/` with `Workbench/` and `Retired/` subdirs.
1b. Run `git init && git add -A && git commit -m seed` in `<tmp>/` to make the fixture directory a git worktree (required by retire-file.md Step 2's mandatory `git rev-parse --show-toplevel`). Follow the same pattern used by the four sibling LLM scenarios: `init_foundry_idempotency`, `handoff_readiness_gate`, `audit_revision_needed_loop`, `audit_sizing_non_haiku_safe`.
2. Seed a done PLAN at `<tmp>/Workbench/PLAN-test-retire-XX.md` with `status: done`, `pipeline_phase: complete`, valid schema-v2 frontmatter, and non-zero body content.
3. Return `context = { "repo": "<tmp>", "source_plan": "Workbench/PLAN-test-retire-XX.md", "expected_target": "Retired/PLAN-test-retire-XX.md" }`.

## Parent-session `Skill(...)` invocations

From cwd=`<tmp>`: `Skill("retire", "Workbench/PLAN-test-retire-XX.md")`.

## Mechanical assertions

```json
[
  {
    "kind": "path_absent",
    "path": "<repo>/Workbench/PLAN-test-retire-XX.md"
  },
  {
    "kind": "path_exists",
    "path": "<repo>/Retired/PLAN-test-retire-XX.md"
  },
  {
    "kind": "regular_file_nonzero",
    "path": "<repo>/Retired/PLAN-test-retire-XX.md",
    "requires": ["is_file", "size > 0"]
  },
  {
    "kind": "path_absent",
    "path": "<repo>/Workbench/Retired/"
  }
]
```

**Pass condition:** all four assertions hold (source absent, target present at root Retired/, target is a regular non-empty file, Workbench/Retired/ is absent).
**Fail condition:** any assertion fails. The "target absent" symptom specifically catches the PLAN-AA2 delete-not-move bug class. The "Workbench/Retired/ absent" assertion is the behavioural regression test for Bug A (misplaced destination).

## Cleanup

Remove `<tmp>/` entirely.
