# retire_no_git_walkup

**Scenario ID:** `retire_no_git_walkup`

**Tier:** LLM (parent-session `Skill(...)` dispatches required)

## Goal

Verify the walk-up fallback: `retire` and the `rehydrate-handoff` explicit-override
retire path must not hard-halt when `git rev-parse --show-toplevel` fails. Inside
a directory tree that has `.claude/` and `CLAUDE.md` but no `.git`, both must
anchor on that ancestor and land the file under `<anchor>/Retired/` with
`outcome: success`, instead of returning `outcome: exception`.

## Fixture preparation (`prep_scenario`)

1. Create temp dir `<tmp>/` with `Workbench/`, `Retired/`, and `.claude/`
   subdirs, and an empty `CLAUDE.md` at `<tmp>/CLAUDE.md`. Do **not** run
   `git init` - the whole point of this scenario is the absence of a `.git`
   worktree.
2. Seed a done PLAN at `<tmp>/Workbench/PLAN-test-retire-nogit.md` with
   `status: done`, `pipeline_phase: complete`, valid schema-v2 frontmatter,
   and non-zero body content.
3. Seed a handoff at `<tmp>/Workbench/HANDOFF-test-nogit.md` with a minimal
   valid frontmatter and non-zero body.
4. Return `context = { "repo": "<tmp>", "source_plan": "Workbench/PLAN-test-retire-nogit.md", "expected_plan_target": "Retired/PLAN-test-retire-nogit.md", "source_handoff": "Workbench/HANDOFF-test-nogit.md", "expected_handoff_target_glob": "Retired/HANDOFF-test-nogit-*.md" }`.

## Parent-session `Skill(...)` invocations

From cwd=`<tmp>` (no `.git` present):

1. `Skill("retire", "Workbench/PLAN-test-retire-nogit.md")`.
2. `Skill("rehydrate-handoff")`, select the seeded handoff, then explicitly
   request "retire this handoff now" to exercise the Step 3 override path.

## Mechanical assertions

The `retire` call has a deterministic destination filename, so it is checked
mechanically:

```json
[
  {
    "kind": "path_absent",
    "path": "<repo>/Workbench/PLAN-test-retire-nogit.md"
  },
  {
    "kind": "path_exists",
    "path": "<repo>/Retired/PLAN-test-retire-nogit.md"
  },
  {
    "kind": "regular_file_nonzero",
    "path": "<repo>/Retired/PLAN-test-retire-nogit.md",
    "requires": ["is_file", "size > 0"]
  },
  {
    "kind": "path_absent",
    "path": "<repo>/Workbench/HANDOFF-test-nogit.md"
  }
]
```

The `rehydrate-handoff` explicit-override destination carries a `{YYYYMMDDHHMI}`
timestamp per `read-handoff.md` Step 3, so it has no fixed filename to assert
against mechanically (the same limitation the harness's assertion-kind set has
for every timestamped destination elsewhere in this corpus). Verify it by
narrative: the skill's own returned report must state `outcome: success` (not
`exception`) and a destination path beginning `Retired/HANDOFF-test-nogit-`,
and `<repo>/Workbench/HANDOFF-test-nogit.md` must be gone per the mechanical
assertion above.

**Pass condition:** the `retire` mechanical assertions all hold, and the
`rehydrate-handoff` narrative check confirms `outcome: success` with a
`Retired/HANDOFF-test-nogit-*` destination. Neither skill halts on the
missing `.git`.

**Fail condition:** either skill returns `outcome: exception` for a missing
`.git` worktree, or either file is left under `Workbench/` or landed at a
path not anchored at `<repo>/Retired/`.

## Control case (unchanged)

`retire_path_mechanics` and `handoff_readiness_gate` already cover the
git-present fast path and must keep passing unchanged - this scenario only
adds the no-git branch, it does not replace either existing one.

## Cleanup

Remove `<tmp>/` entirely.
