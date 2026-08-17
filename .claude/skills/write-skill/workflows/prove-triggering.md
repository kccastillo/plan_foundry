# Prove the skill triggers

A description's firing behaviour is measured rather than argued.

The measurement needs a live session. Nothing here runs in CI, because the thing under
test is a model's selection decision and there is no model in CI. Run the procedure
before the skill ships.

## What you are testing

Two rates matter, and they fail in opposite directions.

**Trigger rate** is the fraction of `should_trigger` runs where the skill fired. A low
rate means the description is written in the author's vocabulary rather than the
invoker's.

**False-trigger rate** is the fraction of `should_not_trigger` runs where the skill
fired anyway. A high rate means the description is broad enough to capture work that
belongs elsewhere.

Tuning one moves the other. A description that fires on everything scores perfectly on
the first set, which is why the negative set is not optional and why that set passes
by not firing.

## Procedure

1. Read `evals.json` for the skill. Confirm both sets are non-empty and that the
   negative set contains at least one genuine near miss: a prompt that belongs to the
   neighbouring skill most confusable with the new skill. A negative set made of
   unrelated prompts tests nothing.

2. For each query in both sets, dispatch a fresh subagent with the query as its whole
   task. Use the cheapest tier that reproduces the selection behaviour. Run each query
   `runs_per_query` times, in separate dispatches, because the selection is stochastic
   and one run of one prompt is not a measurement.

3. Record, per run, whether the skill fired and, where another skill fired instead,
   which one. The substitute matters more than the miss, because the substitute names
   the collision.

4. Compute both rates against the thresholds in `evals.json`.

## Reading the result

**Both thresholds met.** Ship the skill. Report both rates to the person who asked.

**Trigger rate too low.** The description is missing the words a user types. Add the
concrete artefact or effect the skill produces, and the phrases in the invoker's
terms. Do not lengthen the description by adding synonyms, which costs listing budget
and rarely helps.

**False-trigger rate too high.** State the exclusion in the description itself, naming
the neighbouring skill the request should go to instead. This is more effective than
narrowing the positive language, which usually breaks the trigger rate.

**Both wrong at once.** The skill's boundary is wrong rather than its wording. Return
to the objective and settle what this skill is not for before changing the
description again.

## The cheap diagnostic, before the expensive one

Ask the model directly: "when would you use the `<name>` skill?"

Its answer is the description read back through the selection machinery, and the gap
between that answer and what you meant is the defect, stated in the model's own terms.
This costs one turn and usually locates the problem the rates only detect.

Use the diagnostic to tune rather than to certify. The answer tells you what the
description says, and whether the skill actually fires is measured only by the runs
above.

## Critique the assertions before the result

A passing rate on a weak eval set converts an unexamined question into recorded
evidence that the question was answered.

Before accepting a pass, ask what a bad description would have to do to fail this set.
If the answer is "almost nothing" - the positive prompts all name the skill, the
negative prompts are all unrelated - the eval set is the defect and the rate means
nothing. Fix the set and run the set again.

## Record it

The result goes back into `evals.json`, in a `measured` block beside the prompt sets
the runs used. Recording the block there rather than only in a plan or a commit
message lets the fixture be read later without the run's context:

```json
"measured": {
  "run_date": "2026-01-31",
  "runs_per_query": 3,
  "trigger_rate": 1.0,
  "false_trigger_rate": 0.0,
  "substitutes": ["neighbouring-skill"]
}
```

`run_date` is the day the runs were dispatched, `runs_per_query` is what actually ran
rather than what was intended, and `substitutes` names every skill that fired instead.
A rate with no run count and no date attached is not a measurement.

The block is the same shape wherever it is written. A consumer records the block in
the `evals.json` beside the skill the fixture measures. This repository holds no
acceptance copy yet: `check_eval_fixture.py` reads
`write-skill/scripts/fixtures/eval-fixture.json`, nothing has produced that file, and
the check therefore prints `check_eval_fixture: no fixture to check` and exits 0 in
every CI run. Passing `--require-measured` turns the same absence into a failure,
which is how a caller that genuinely requires the measurement asserts it. The check
never re-runs the measurement - the thing under test is a model's selection decision
and there is no model in CI - so what it asserts, once a fixture exists, is that the
recorded fixture parses and carries measured rates rather than asserted ones.

Write the block only from runs that happened. A fixture carrying rates nobody measured
is the assertion this whole procedure exists to replace.

**Confirm the skill loaded before trusting a low rate.** A skill the harness never
loaded and a skill described badly both measure zero, and the two are
indistinguishable from the rate alone. If the listing is over its aggregate budget the
harness drops descriptions, and a dropped description means the selection surface
cannot see the thing being measured. Check that the skill is in the listing with its
description intact, and where the description is missing, record no rate: fix the
loading and measure again.
