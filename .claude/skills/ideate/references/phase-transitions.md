# Ideate Phase-Transition Routing Table

Eight-phase enum routing for the ideate cadence pipeline. All `ideate_phase` state transitions are validated against this table by `lib/state.py:advance_phase()`.

---

## Phase Enum

The `ideate_phase` field accepts the following values:

| Value | Category |
|---|---|
| (empty / absent) | Pre-state: phases 1-3 are conversational; no disk state |
| `clarify` | Phase 1 - conversational |
| `survey` | Phase 2 - conversational |
| `converge` | Phase 3 - conversational |
| `risk_assess_idea` | Gate A - pre-spec adversarial check (fires before Phase 4) |
| `risk_assess_idea_blocked` | Gate A - show-stopper detected; awaiting human action |
| `spec_draft` | Phase 4 - state goes to disk here (entered via Gate A / `risk_assess_idea`) |
| `risk_assess_spec` | Gate B - post-spec adversarial check (fires before Phase 5) |
| `risk_assess_spec_blocked` | Gate B - show-stopper detected after revision attempt; awaiting human action |
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
| (none / empty) | `risk_assess_idea` (at Converge close - Gate A fires first) | `clarify` / `survey` / `converge` (in-conversation loops; no disk state) | Write an input; ideate ends |
| `risk_assess_idea` | `spec_draft` (clean pass) | (no loop; retry on `risk_assess_idea_blocked -> risk_assess_idea`) | `risk_assess_idea_blocked` (show-stopper) OR `exited_early` |
| `risk_assess_idea_blocked` | `risk_assess_idea` (on human resume) | (none) | `exited_early` |
| `spec_draft` | `risk_assess_spec` (Gate B fires - mandatory) | (always advances; no loop from spec_draft) | `exited_early` |
| `risk_assess_spec` | `self_critique` (clean pass) | (no loop; retry on `risk_assess_spec_blocked -> risk_assess_spec`) | `risk_assess_spec_blocked` (show-stopper after attempt spent) OR `exited_early` |
| `risk_assess_spec_blocked` | `risk_assess_spec` (on human resume) | (none) | `exited_early` |
| `self_critique` (n < 5) | `spec_refine` (if findings > 0) OR `consolidate` (zero-findings short-circuit) | `self_critique` (additional iteration; increment counter) | `exited_early` OR `discard_all` -> `consolidate` |
| `self_critique` (n == 5) | HALT - surface as exception | (none; counter exhausted) | `exited_early` |
| `spec_refine` | `cross_spec_reconcile` | `self_critique` (more critique requested by human) | `consolidate` (early-exit via "ship it") |
| `cross_spec_reconcile` | `consolidate` | `spec_refine` (conflict requires PLAN edit) | (no early-exit; always concludes by setting `ideate_reconcile_outcome`) |
| `consolidate` | `complete` | (none; terminal transition) | (none) |
| `complete` | (terminal - plan-pipeline picks up) | (none) | (none) |
| `exited_early` | (terminal - PLAN ignored by plan-pipeline) | (none) | (none) |

---

## Bounded-Iteration Rule

The `self_critique` phase has a hard iteration bound of **5**. The bound is enforced by `state.py:advance_phase()` which checks `ideate_iteration_count.self_critique` before allowing a loop transition.

- Iterations 1-4: `self_critique -> spec_refine -> (optionally back to self_critique)` loop is allowed.
- At iteration 5 (counter equals 5): no further loop is permitted. The orchestrator emits a halt-and-surface with exception type `max_critique_iterations`. The human must take an explicit action (ship, exit, or override) to break the halt.

The `spec_refine` counter (`ideate_iteration_count.spec_refine`) is incremented on each `spec_refine -> self_critique` back-edge. It is informational (no hard bound in v1; surfaced in INDEX for observability).

**Gate B (`risk_assess_spec`) autonomous revision bound:** `MAX_RISK_ASSESS_SPEC_REVISIONS = 1`. The Gate B workflow checks `ideate_iteration_count.risk_assess_spec` against this constant before starting an autonomous revision. If the counter is already at 1, the revision is skipped and the gate surfaces directly to the human with `risk_assess_spec_blocked`. `advance_phase()` does not enforce this bound - the bound is checked in the Gate B workflow step before the revision attempt. Tracking field: `ideate_iteration_count.risk_assess_spec` (persisted via `set_ideate_iteration_count()`).

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
| -> `spec_refine` | `ideate_phase: spec_refine`; `ideate_iteration_count.spec_refine += 1`; `ideate_critique_addressed` appended |
| -> `cross_spec_reconcile` | `ideate_phase: cross_spec_reconcile` |
| -> `consolidate` | `ideate_phase: consolidate`; `ideate_reconcile_outcome` written (if from cross_spec_reconcile) |
| -> `complete` | `ideate_phase: complete`; `pipeline_phase: drafted` |
| -> `exited_early` | `ideate_phase: exited_early` |
| `discard_all` shortcut | `ideate_phase: consolidate` (skips spec_refine and cross_spec_reconcile) |

---

## Relationship to pipeline_phase

The `ideate_phase` field is orthogonal to `pipeline_phase`. During ideate cadence phases 4-8, `pipeline_phase` remains `drafting`. The terminal handoff (Phase 8 -> complete) is the only moment `pipeline_phase` changes: it flips to `drafted`, signalling plan-pipeline to take over.

plan-pipeline's dispatch.md Step 3 checks `ideate_phase` before acting on `pipeline_phase: drafting` - see dispatch.md for the no-op branch definition.
