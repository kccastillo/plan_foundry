# Model-tiering policy for research fan-outs

This is the version-controlled source of truth for `foundry-research`'s per-role
model assignment. The executable copy is the `MODEL_BY_ROLE` constant in
`../workflows/foundry-research.workflow.js`; keep the two in step.

Origin: PLAN-AE5, integrating `Workbench/EXTERNAL_ADVICE-002` (strategic note),
`Workbench/EXTERNAL_RESEARCH-009` (the invocation trace + root cause), and the
budget-sizing half of `Workbench/ADVICE-013`.

## The defect this fixes

The native `deep-research` harness is a built-in Claude Code skill (no on-disk
`SKILL.md`, un-editable from this repo). Its auto-generated Workflow script calls
`agent()` **without `model:` on every call**, so every fan-out agent inherits the
main-loop (session) model. One observed run put **~104 agents on Fable 5**, spent
**~1.48M tokens**, stalled across two session-limit resets, and still returned a
degraded result (synthesis never ran). The operator's recorded
`deep-research-model-split` memory could not fix it, because a memory does not
bind a native skill's auto-generated script. The fix has to live in bundle code.

## Tier table (PLAN-AE5 decision D2 — "Granular 4-tier")

| Role | Model | Volume | Why this tier |
|---|---|---|---|
| **Scope** (decompose question → angles) | `sonnet` | 1 | Bounded decomposition. Real but light judgement — Sonnet copes; Opus is not needed and would cost more for no quality gain. |
| **Search** (one WebSearch per angle) | `haiku` | ~5 | Mechanical: run a search, rank results by relevance. No deep reasoning. |
| **Fetch + extract** (per source) | `sonnet` | ~12 | Fetch a page and extract falsifiable claims with supporting quotes — reading comprehension. Matches the operator's recorded "retrieval = sonnet" preference. |
| **Verify** (3 adversarial votes per claim) | `haiku` | ~60 | Boolean, schema-bounded "refute this claim" votes. The **highest-volume** role — putting it on Haiku is the single biggest cost win. |
| **Synthesize** (merge + cited report) | `opus` | 1 | The one place real judgement concentrates: dedup, group, weight confidence, write the answer. Matches the recorded "synthesis = opus" preference. |

**Two hard rules:**
- **Fable is used nowhere.** It is reserved for cases where it is absolutely necessary; ordinary research fan-out is not such a case.
- **Opus appears only at synthesis.** Every other role runs on Sonnet or Haiku.

### Effort caveat

The Workflow harness `agent()` options expose `model:` but **no effort knob**. The
recorded "sonnet/medium + opus/high" split is therefore honoured by model tier
only — effort cannot be set per-agent here. If a future harness version exposes
effort, set medium for retrieval roles and high for synthesis.

## Budget-aware fan-out sizing

The Workflow `budget` global carries the turn's token **target** (`budget.total`)
when the user set one; `null` otherwise. The workflow:

1. **Pre-flight:** scales the caps (`ANGLES_TARGET`, `MAX_FETCH`,
   `MAX_VERIFY_CLAIMS`) linearly around an ~800k-token reference run, clamped to a
   sane band. No target → conservative defaults.
2. **Mid-run guard:** before the verify barrier, if a target is in force, it trims
   the claim pool so `claims × votes` (on Haiku) plus a reserve for the Opus
   synthesis still fit `budget.remaining()`.

**Honest limitation (ADVICE-013):** the assistant **cannot read the live
plan-usage %** — that figure lives only in the human's client UI and no tool
exposes it. So sizing is to the *explicit* token target only; the skill cannot
auto-pause at "N% of the plan consumed". It can throttle at checkpoints and flag
before a wide/background dispatch — nothing more.

## Cross-cutting principle

The defect is **not** specific to research. Any role-homogeneous fan-out inherits
the session model unless something tiers it by role — the same session's
writers-room judge panel ran 11 `general-purpose` judges all on Fable 5
(EXTERNAL_ADVICE-002 §"Second instance"). Judge/verdict panels and review/
bughunter swarms are schema-bounded comparison work — small-model jobs — and
should pin `model:` per role exactly as this skill does. When building a new
fan-out harness, tier the models by role and size the fan-out to the budget.
