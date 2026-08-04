# init_foundry_idempotency

**Scenario ID:** `init_foundry_idempotency`

**Tier:** LLM (parent-session `Skill(...)` dispatches required)

## Goal

Verify that `init-foundry` is idempotent: running it twice in a fresh git repo produces the same on-disk state. Captured via `git status --porcelain` after each run.

## Fixture preparation (`prep_scenario`)

1. Create temp dir `<tmp>/` and run `git init` inside it.
2. Return `context = { "repo": "<tmp>" }`.

## Parent-session invocations

`init-plan-foundry` carries `disable-model-invocation: true`, so this scenario reads
its SKILL.md and follows it rather than dispatching the Skill tool. The scenario tests
the idempotency of the install workflow, not the dispatch mechanism, so the change of
entry point does not change what is under test.

1. From cwd=`<tmp>`: read `.claude/skills/init-plan-foundry/SKILL.md` and run the
   workflow it describes.
2. Capture `git status --porcelain` output into variable `first_status`.
3. From cwd=`<tmp>`: run that workflow again (second run).
4. Capture `git status --porcelain` output into variable `second_status`.

## Mechanical assertions

```json
[
  {
    "kind": "string_equality",
    "lhs_source": "first_status",
    "rhs_source": "second_status",
    "comparison": "byte_identical",
    "diff_tool": "GNU diff against captured strings (not a directory-tree diff)"
  }
]
```

**Pass condition:** `first_status` is byte-identical to `second_status` (GNU `diff` returns exit 0).
**Fail condition:** `diff` reports any delta; capture the delta as a symptom.

## Cleanup

Remove `<tmp>/` entirely.
