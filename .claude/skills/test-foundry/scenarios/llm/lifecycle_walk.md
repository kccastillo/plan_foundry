# lifecycle_walk

**Scenario ID:** `lifecycle_walk`

**Tier:** LLM (parent-session `Skill(...)` dispatches required)

## Goal

Walk a synthesised PLAN through every `pipeline_phase` value of the plan-pipeline state machine and assert that disk frontmatter reflects each phase transition.

## Fixture preparation (`prep_scenario`)

1. Create temp dir `<tmp>/Workbench/`.
2. Seed a minimal PLAN at `<tmp>/Workbench/PLAN-test-lifecycle-XX_walk.md` with `pipeline_phase: drafting`, `status: ready`, `schema_version: 2`, and one `## Steps` item plus one `## Verification` item that is trivially true.
3. Return `context = { "workbench": "<tmp>/Workbench", "target_plan": "PLAN-test-lifecycle-XX_walk.md" }`.

## Parent-session `Skill(...)` invocations

Issue, in order:

1. `Skill("plan-pipeline", "advance PLAN-test-lifecycle-XX_walk.md from drafting → drafted")` (or equivalent — the scenario driver dispatches whatever surface plan-pipeline currently exposes for phase advance).
2. `Skill("plan-pipeline", "advance PLAN-test-lifecycle-XX_walk.md from drafted → checked")`.
3. `Skill("plan-pipeline", "advance PLAN-test-lifecycle-XX_walk.md from checked → executing")`.
4. `Skill("plan-pipeline", "advance PLAN-test-lifecycle-XX_walk.md from executing → outcome-verifying")`.
5. `Skill("plan-pipeline", "advance PLAN-test-lifecycle-XX_walk.md from outcome-verifying → complete")`.

## Mechanical assertions

After each step above returns `outcome: success`, re-read the PLAN's frontmatter from disk and assert `pipeline_phase` equals the expected enum literal for that transition.

Expected assertion list (handed to `capture_assertions`):

```json
[
  { "path": "<workbench>/PLAN-test-lifecycle-XX_walk.md", "frontmatter_key": "pipeline_phase", "expected": "drafted", "after_step": 1 },
  { "path": "<workbench>/PLAN-test-lifecycle-XX_walk.md", "frontmatter_key": "pipeline_phase", "expected": "checked", "after_step": 2 },
  { "path": "<workbench>/PLAN-test-lifecycle-XX_walk.md", "frontmatter_key": "pipeline_phase", "expected": "executing", "after_step": 3 },
  { "path": "<workbench>/PLAN-test-lifecycle-XX_walk.md", "frontmatter_key": "pipeline_phase", "expected": "outcome-verifying", "after_step": 4 },
  { "path": "<workbench>/PLAN-test-lifecycle-XX_walk.md", "frontmatter_key": "pipeline_phase", "expected": "complete", "after_step": 5 }
]
```

**Pass condition:** all five assertions pass.
**Fail condition:** any assertion fails — capture the actual value vs expected.

## Cleanup

Remove `<tmp>/` entirely.
