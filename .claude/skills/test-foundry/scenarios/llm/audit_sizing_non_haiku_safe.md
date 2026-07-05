# audit_sizing_non_haiku_safe

**Scenario ID:** `audit_sizing_non_haiku_safe`

**Tier:** LLM (parent-session `Skill(...)` dispatch required)

## Goal

Verify the executor **t-shirt sizing** behaviour: a PLAN whose Step carries an
**irreducible** judgement call is **sized up** (a `note`-level re-size recommendation
naming `size: M`/`L` and the matching `assigned_to:`) rather than only hard-blocked —
while a PLAN whose non-haiku-safety is **reducible** still earns a decomposition Blocker.
Behavioural companion to the CI wiring test `audit-haiku-safe/lib/test_sizing_wiring.py`.

## Fixture preparation (`prep_scenario`)

1. Create temp dir `<tmp>/Workbench/` (fresh git repo).
2. Seed two schema-v2 PLANs, each with a `## Steps` and a `## Verification` section
   containing at least one `acceptance:` item, and `pipeline_phase: drafted`,
   `audit_state.last_stage: sufficiency`, `last_outcome: success` (so plan-safety may run):
   - `PLAN-test-SZ1_irreducible.md` — `assigned_to: haiku`, one Step that genuinely needs
     design-at-execution judgement that cannot be pre-specified (e.g. "choose the cleanest
     public API shape for module X given the trade-offs, then implement it"). This is an
     irreducible-judgement Step → the correct remedy is **size up**, not decompose.
   - `PLAN-test-SZ2_reducible.md` — `assigned_to: haiku`, one vague Step that CAN be made
     mechanical by splitting (e.g. "tidy up the imports" → enumerable edits). The correct
     remedy is **decompose** (a Blocker, keep S).
3. `git init && git add -A && git commit -m "seed"`.
4. Return `context = { "repo": "<tmp>" }`.

## Parent-session `Skill(...)` invocations

Dispatch, from cwd `<tmp>`:
- `Skill("audit-haiku-safe", "audit Workbench/PLAN-test-SZ1_irreducible.md")`
- `Skill("audit-haiku-safe", "audit Workbench/PLAN-test-SZ2_reducible.md")`

Capture each `<pipeline-result>` block and the review prose.

## Manual assertions (LLM-evaluated)

Unlike file-state scenarios, the signal here is the **auditor's returned review + the
`<pipeline-result>` block**, not an on-disk artefact — so the driving session evaluates
these against each captured return:

1. **SZ1 → size up, not hard-blocked.** The review for `PLAN-test-SZ1_irreducible.md`
   recommends a higher size/tier — it contains at least one of `size: M`, `size: L`,
   `re-size`, `size up`, `assigned_to: sonnet`, or `assigned_to: opus` — and surfaces the
   irreducible-judgement Step as a **`note`-level re-size recommendation**, NOT solely as an
   unresolved decomposition Blocker.
2. **SZ2 → decomposition Blocker.** The review for `PLAN-test-SZ2_reducible.md` emits at
   least one Blocker (`blockers_count >= 1` in its `<pipeline-result>`) whose remedy is
   decomposition, keeping the PLAN at size **S**.

**Pass condition:** both manual assertions hold — SZ1 is sized up (sizing outcome), SZ2 is
decomposition-blocked.
**Fail condition:** SZ1 is hard-blocked with no size recommendation (the pre-PR-#44
behaviour), or SZ2 passes without flagging its reducible vagueness.

> Note: these assertions are prose because the harness's `capture_assertions` inspects
> on-disk state, not a subagent's returned text. The `handoff_readiness_gate` scenario, by
> contrast, asserts against the written handoff file and uses the mechanical
> `file_substring` / `file_regex` kinds.

## Cleanup

Remove `<tmp>/` entirely.
