# Ideate Phase-Transition Routing Table

Eight-phase enum routing for the ideate cadence pipeline. `lib/state.py:advance_phase()` validates every `ideate_phase` state transition against this table.

---

## Phase Enum

The `ideate_phase` field accepts the following values:

| Value | Category |
|---|---|
| (empty / absent) | Pre-state: phases 1-3 are conversational and write no disk state |
| `clarify` | Phase 1 - conversational |
| `survey` | Phase 2 - conversational |
| `converge` | Phase 3 - conversational |
| `risk_assess_idea` | Gate A - pre-spec adversarial check (fires before Phase 4) |
| `risk_assess_idea_blocked` | Gate A - show-stopper detected, so automation waits on human action |
| `spec_draft` | Phase 4 - state goes to disk here (entered via Gate A / `risk_assess_idea`) |
| `risk_assess_spec` | Gate B - post-spec adversarial check (fires before Phase 5) |
| `risk_assess_spec_blocked` | Gate B - show-stopper detected after a revision attempt, so automation waits on human action |
| `self_critique` | Phase 5 - critique gate |
| `spec_refine` | Phase 6 - refinement |
| `cross_spec_reconcile` | Phase 7 - cross-plan check |
| `consolidate` | Phase 8 - terminal, hands off to plan-pipeline |
| `complete` | Terminal: plan-pipeline picks up (`pipeline_phase: drafted`) |
| `exited_early` | Terminal: PLAN preserved but pipeline does not pick up |

---

## Routing Table

| Current `ideate_phase` | Next on advance | Next on loop/revision | Next on early-exit |
|---|---|---|---|
| (none / empty) | `risk_assess_idea` (at Converge close - Gate A fires first) | `clarify` / `survey` / `converge` (in-conversation loops, no disk state) | Write an input and ideate ends. `exited_early` is also accepted by the routing table once a PLAN file with frontmatter exists |
| `clarify` | `spec_draft` (accepted by the routing table, and it reaches Phase 4 without passing Gate A) | `survey` | `exited_early` |
| `survey` | `spec_draft` (accepted by the routing table, and it reaches Phase 4 without passing Gate A) | `converge` / `clarify` | `exited_early` |
| `converge` | `spec_draft` (accepted by the routing table, and it reaches Phase 4 without passing Gate A) | (none) | `exited_early` |
| `risk_assess_idea` | `spec_draft` (clean pass) | (no loop; retry on `risk_assess_idea_blocked -> risk_assess_idea`) | `risk_assess_idea_blocked` (show-stopper) OR `exited_early` |
| `risk_assess_idea_blocked` | `risk_assess_idea` (on human resume) | (none) | `exited_early` |
| `spec_draft` | `risk_assess_spec` (Gate B fires - mandatory) | (always advances; no loop from spec_draft) | `exited_early` |
| `risk_assess_spec` | `self_critique` (clean pass) | (no loop; retry on `risk_assess_spec_blocked -> risk_assess_spec`) | `risk_assess_spec_blocked` (show-stopper after attempt spent) OR `exited_early` |
| `risk_assess_spec_blocked` | `risk_assess_spec` (on human resume) | (none) | `exited_early` |
| `self_critique` (n < 5) | `spec_refine` (if findings > 0) OR `consolidate` (zero-findings short-circuit) | `self_critique` (additional iteration; increment counter) | `exited_early` OR `discard_all` -> `consolidate` |
| `self_critique` (n == 5) | HALT - surface as exception | (none; counter exhausted) | `exited_early` |
| `spec_refine` | `cross_spec_reconcile` | `self_critique` (more critique requested by human) | `consolidate` (early-exit via "ship it") OR `exited_early` |
| `cross_spec_reconcile` | `consolidate` | `spec_refine` (conflict requires PLAN edit) | `exited_early`. The phase itself has no early-exit branch and always concludes by setting `ideate_reconcile_outcome`, so this edge exists in the routing table for an operator-driven abandon rather than for a workflow branch |
| `consolidate` | `complete` | (none; terminal transition) | (none) |
| `complete` | (terminal - plan-pipeline picks up) | (none) | (none) |
| `exited_early` | (terminal - PLAN ignored by plan-pipeline) | (none) | (none) |

**The three conversational rows, and what Gate A actually rests on.** `lib/state.py` lines 73 to 75 carry routing-table rows keyed `clarify`, `survey` and `converge`, and the three rows above transcribe those keys exactly. Every one of them accepts `-> spec_draft`, so the routing table does not itself make Gate A mandatory - a caller that supplied `clarify`, `survey` or `converge` as the source phase would enter Phase 4 with no Gate A record written. What makes Gate A mandatory in the shipped arc is that no caller supplies those keys. Every `advance_phase()` call site in the ideate workflows passes `""`, `risk_assess_idea`, `risk_assess_idea_blocked`, `spec_draft`, `risk_assess_spec` or `risk_assess_spec_blocked` as the source, `workflows/cadence-phases.md` line 127 directs Converge close to fire Gate A rather than call `advance_phase(plan_path, '', 'spec_draft')`, and `workflows/risk-assess-idea.md` line 13 records `converge` as a dead legacy key whose live equivalent is `""`. No workflow writes `ideate_phase: clarify`, `ideate_phase: survey` or `ideate_phase: converge` to a PLAN, so the pre-state at Converge close is always `""` or absent. Treat the three rows as reachable only by a caller written against them, and not as a supported route to Phase 4.

---

## Bounded-Iteration Rule

The `self_critique` phase has a hard iteration bound of **5**. `state.py:advance_phase()` enforces the bound by checking `ideate_iteration_count.self_critique` before allowing a loop transition.

- Iterations 1-4: `self_critique -> spec_refine -> (optionally back to self_critique)` loop is allowed.
- At iteration 5 (counter equals 5): no further loop is permitted. `advance_phase()` raises a bare `ValueError` (`state.py` lines 323 to 326) whose message reads `self_critique iteration bound exceeded (<n>/5). Surface as exception - human must take explicit action (ship / exit / override).` There is no named exception type and no exception subclass, so a caller that wants to distinguish this failure from an invalid-transition `ValueError` must match on the message. The human must take an explicit action (ship, exit, or override) to break the halt.

The `spec_refine` counter (`ideate_iteration_count.spec_refine`) is incremented on each `spec_refine -> self_critique` back-edge. That counter is informational and carries no hard bound in v1. It is readable from PLAN frontmatter via `read_ideate_state()` (`state.py` line 280) and is not projected anywhere else - the Workbench INDEX projection that once surfaced it was deleted with the `update-workbench-index` skill and `build_index.py` on 2026-07-31 under PLAN-AI9.

**Gate B (`risk_assess_spec`) autonomous revision bound:** `MAX_RISK_ASSESS_SPEC_REVISIONS = 1`. The Gate B workflow checks `ideate_iteration_count.risk_assess_spec` against this constant before starting an autonomous revision. If the counter is already at 1, the workflow skips the revision and surfaces directly to the human with `risk_assess_spec_blocked`. `advance_phase()` does not enforce this bound, because the Gate B workflow step checks the bound before the revision attempt. Tracking field: `ideate_iteration_count.risk_assess_spec` (persisted via `set_ideate_iteration_count()`).

---

## Transition Diagram

```
Conversational (no disk state)
  ┌──────────────────────────────────────────────────────────┐
  │  TRIGGER -> [Clarify] -> [Survey] -> [Converge]             │
  │    ↑ loops within conversation                            │
  │    -> early-exit: write an input, ideate ends       │
  └──────────────────────────────────────────────────────────┘
                     ↓ "spec this out" (Converge close)
                     ↓ Gate A fires first (not spec_draft directly)

[risk_assess_idea]  ->  [spec_draft]  ->  [risk_assess_spec]  ->  [self_critique]  ->  [spec_refine]  ->  [cross_spec_reconcile]  ->  [consolidate]  ->  [complete]
        ↓                                       ↓                      ↓ ↑ loop             ↓ ↑ back-loop        ↓
[risk_assess_idea_blocked]          [risk_assess_spec_blocked]       exited_early or      consolidate          (no exit -
  (human must resolve)                (human must resolve)           discard_all->          ("ship it")          always concludes)
                                                                     consolidate
                                                                     HALT at n==5

[complete] -> plan-pipeline picks up (pipeline_phase: drafted)
[exited_early] -> PLAN archived; plan-pipeline ignores
```

---

## State Mutations at Each Transition

| Transition | Frontmatter mutations |
|---|---|
| -> `risk_assess_idea` (first entry from `""`) | `ideate_phase: risk_assess_idea` |
| -> `risk_assess_idea` (re-entry from `risk_assess_idea_blocked`) | `ideate_phase: risk_assess_idea`; `ideate_iteration_count.risk_assess_idea += 1` |
| -> `risk_assess_idea_blocked` | `ideate_phase: risk_assess_idea_blocked` |
| -> `spec_draft` | `ideate_phase: spec_draft` |
| -> `risk_assess_spec` | `ideate_phase: risk_assess_spec` |
| -> `risk_assess_spec_blocked` | `ideate_phase: risk_assess_spec_blocked` |
| -> `self_critique` (new iteration) | `ideate_phase: self_critique`; `ideate_iteration_count.self_critique += 1` |
| -> `spec_refine` | `ideate_phase: spec_refine`; `ideate_iteration_count.spec_refine += 1`. `ideate_critique_addressed` is appended by the Phase 6 workflow, not by `advance_phase()` - see the note below the table |
| -> `cross_spec_reconcile` | `ideate_phase: cross_spec_reconcile` |
| -> `consolidate` | `ideate_phase: consolidate`; `ideate_reconcile_outcome` written (if from cross_spec_reconcile) |
| -> `complete` | `ideate_phase: complete`; `pipeline_phase: drafted` |
| -> `exited_early` | `ideate_phase: exited_early` |
| `discard_all` shortcut | `ideate_phase: consolidate` (skips spec_refine and cross_spec_reconcile) |

**Who performs each mutation.** `advance_phase()` writes `ideate_phase`, the `self_critique`, `spec_refine` and `risk_assess_idea` counters, and `pipeline_phase: drafted` on the transition to `complete`. It writes nothing else. In particular it never touches `ideate_critique_addressed`: `state.py` defines `_append_to_list_field()` at line 215 and no code path calls it. The fingerprints of addressed findings are appended to `ideate_critique_addressed` by the Phase 6 workflow, from the state mutations `render_critique.py` produces - see `workflows/cadence-phases.md` line 274. The `ideate_reconcile_outcome` value on the transition to `consolidate` is likewise written by the Phase 7 workflow rather than by `advance_phase()`.

---

## Relationship to pipeline_phase

The `ideate_phase` field is orthogonal to `pipeline_phase`. During ideate cadence phases 4-8, `pipeline_phase` remains `drafting`. The terminal handoff (Phase 8 -> complete) is the only moment `pipeline_phase` changes, and at that moment `advance_phase()` sets `pipeline_phase` to `drafted`, which is the signal for plan-pipeline to take over.

plan-pipeline's dispatch.md Step 3 checks `ideate_phase` before acting on `pipeline_phase: drafting` - see dispatch.md for the no-op branch definition.
