# Prove the skill triggers

A description's firing behaviour is measured, not argued. This is the procedure.

It needs a live session. Nothing here runs in CI, because the thing under test is a
model's selection decision and there is no model in CI. Run it before the skill ships.

## What you are testing

Two rates, and they fail in opposite directions.

**Trigger rate** is the fraction of `should_trigger` runs where the skill fired. A low
rate means the description is written in the author's vocabulary rather than the
invoker's.

**False-trigger rate** is the fraction of `should_not_trigger` runs where the skill
fired anyway. A high rate means the description is broad enough to capture work that
belongs elsewhere.

Tuning one moves the other. A description that fires on everything scores perfectly on
the first set, which is why the negative set is not optional and why it passes by not
firing.

## Procedure

1. Read `evals.json` for the skill. Confirm both sets are non-empty and that the
   negative set contains at least one genuine near miss: a prompt that belongs to the
   neighbouring skill this one is most confusable with. A negative set made of
   unrelated prompts tests nothing.

2. For each query in both sets, dispatch a fresh subagent with the query as its whole
   task. Use the cheapest tier that reproduces the selection behaviour. Run each query
   `runs_per_query` times, in separate dispatches, because the selection is stochastic
   and one run of one prompt is not a measurement.

3. Record, per run, whether the skill fired and which skill fired instead if one did.
   The substitute matters more than the miss: it names the collision.

4. Compute both rates against the thresholds in `evals.json`.

## Reading the result

**Both thresholds met.** Ship it. Report both rates to the person who asked.

**Trigger rate too low.** The description is missing the words a user types. Add the
concrete artefact or effect the skill produces, and the phrases in the invoker's
terms. Do not lengthen it by adding synonyms, which costs listing budget and rarely
helps.

**False-trigger rate too high.** Name the exclusion in the description itself, naming
the neighbouring skill the request should go to instead. This is more effective than
narrowing the positive language, which usually breaks the trigger rate.

**Both wrong at once.** The skill's boundary is wrong rather than its wording. Go back
to the objective and settle what this skill is not for before touching the
description again.

## The cheap diagnostic, before the expensive one

Ask the model directly: "when would you use the `<name>` skill?"

Its answer is the description read back through the selection machinery, and the gap
between that answer and what you meant is the defect, stated in the model's own terms.
This costs one turn and usually locates the problem the rates only detect.

Use it to tune, not to certify. It tells you what the description says. It does not
tell you whether the skill fires, and only the runs above do that.

## Critique the assertions before the result

A passing rate on a weak eval set records that the question was answered when it was
not.

Before accepting a pass, ask what a bad description would have to do to fail this set.
If the answer is "almost nothing" - the positive prompts all name the skill, the
negative prompts are all unrelated - the eval set is the defect and the rate means
nothing. Fix the set and run it again.

## Record it

The result goes back into `evals.json`, in a `measured` block alongside the two prompt
sets it was taken against. Keeping it there rather than only in a plan or a commit
message is what lets the fixture be read later without the run's context:

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

The block is the same shape wherever it is written. A consumer records it in the
`evals.json` sitting beside the skill it measures; this repository also keeps one
acceptance copy at `write-skill/scripts/fixtures/eval-fixture.json`, which
`check_eval_fixture.py --require-measured` reads to assert that a measured fixture was
produced at all. That check never re-runs the measurement - the thing under test is a
model's selection decision and there is no model in CI - so it asserts the recorded
fixture is present, parses, and carries measured rates rather than asserted ones.

Write the block only from runs that happened. A fixture carrying rates nobody measured
is the assertion this whole procedure exists to replace.

**Confirm the skill loaded before trusting a low rate.** A skill the harness never
picked up and a skill described badly both measure zero, and the two are
indistinguishable from the rate alone. If the listing is over its aggregate budget the
harness drops descriptions, and a dropped description means the selection surface
cannot see the thing being measured. Check that the skill is in the listing with its
description intact, and if it is not, record no rate: fix the pickup and measure again.
