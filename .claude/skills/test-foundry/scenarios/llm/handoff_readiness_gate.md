# handoff_readiness_gate

**Scenario ID:** `handoff_readiness_gate`

**Tier:** LLM (parent-session `Skill(...)` dispatch required)

## Goal

Verify that `handoff-next-session` emits the **mandatory Audit & Execution-Readiness
Gate** and that its per-PLAN verdicts are correct — a PLAN at `pipeline_phase: checked`
reads **READY**, and every other phase reads **NOT-READY**. Behavioural companion to the
CI wiring test `handoff-next-session/lib/test_readiness_gate_wiring.py` (which only
proves the section exists, not that the verdicts are right).

## Fixture preparation (`prep_scenario`)

1. Create temp dir `<tmp>/Workbench/` (inside a fresh git repo).
2. Seed three schema-v2 PLANs:
   - `PLAN-test-RD1_checked.md` — `pipeline_phase: checked`, `audit_state.last_stage: plan_safety`, `last_outcome: success`, `assigned_to: haiku`.
   - `PLAN-test-RD2_drafted.md` — `pipeline_phase: drafted`, fresh `audit_state`, `assigned_to: sonnet`.
   - `PLAN-test-RD3_drafting.md` — `pipeline_phase: drafting`, `ideate_phase: survey`, `assigned_to: opus`.
3. `git init && git add -A && git commit -m "seed"` inside `<tmp>`.
4. Return `context = { "repo": "<tmp>" }`.

## Parent-session `Skill(...)` invocations

From a session whose cwd is `<tmp>`, dispatch `Skill("handoff-next-session")` (unscoped).
Let it run its full workflow, including Step 2.5 (compute the gate). Do NOT hand-edit the
resulting file.

## Mechanical assertions

Against the written `<repo>/Workbench/HANDOFF-NEXT-SESSION.md`:

```json
[
  { "kind": "file_substring", "path": "<repo>/Workbench/HANDOFF-NEXT-SESSION.md", "expected_substring": "## Audit & execution-readiness gate" },
  { "kind": "file_regex", "path": "<repo>/Workbench/HANDOFF-NEXT-SESSION.md", "expected_regex": "RD1.*(READY|✅)" },
  { "kind": "file_regex", "path": "<repo>/Workbench/HANDOFF-NEXT-SESSION.md", "expected_regex": "RD2.*(NOT-READY|🚫)" },
  { "kind": "file_regex", "path": "<repo>/Workbench/HANDOFF-NEXT-SESSION.md", "expected_regex": "RD3.*(NOT-READY|🚫)" },
  { "kind": "file_substring", "path": "<repo>/Workbench/HANDOFF-NEXT-SESSION.md", "expected_substring": "S (haiku)" }
]
```

**Pass condition:** the gate section is present, RD1 is the only PLAN marked READY, RD2 and
RD3 are NOT-READY, and sizes are rendered from `assigned_to`.
**Fail condition:** any NOT-READY plan reads as READY, the checked plan is missed, or the gate
section is absent.

## Cleanup

Remove `<tmp>/` entirely.
