# audit-skills report - seeded ownership probe, bundle-managed branch

<!-- ascii-exempt (D18): this file is a captured audit-skills run, committed as evidence
     rather than authored as documentation. Model-generated prose carries punctuation the
     D18 map forbids, and rewriting it after the run - by hand or by --fix - would edit the
     evidence. The file is exempted instead. -->

Run date: 2026-08-04. Scope: one sandbox corpus, outside any repository, seeded to
exercise a single ownership branch. Measured against the skill standard in
`_shared/skill-standard.md` and the values registered in `_shared/harness-contract.md`.

The corpus root is a temp-directory sandbox. It carries an install receipt at
`.bundle-receipts/plan_foundry.files` recording the audited path in receipt-relative form as
`skills/aj8-probe-bundle/SKILL.md`, and it carries neither `scripts/promote.sh` nor
`scripts/prod-repo.txt`, so the foundry-source branch does not fire and the
determination proceeds to the receipt.

## aj8-probe-bundle

### Ownership

Verdict `bundle_managed`, on the signal `.bundle-receipts/plan_foundry.files records this
path`. Returned by `classify_skill_ownership` and transcribed here rather than
reasoned out. `may_propose_edit` is false and `raise_to` names the foundry request
channel.

This is the branch that decides everything below it. The defect found in the next
section is real and its repair is obvious, and it is still not proposed as an edit,
because an edit to a bundle-managed file in a consuming project is destroyed at the
next sync. Proposing one produces work that disappears and a reader who believes a
defect is closed.

### Standard conformance

**One defect, raised.** The SKILL.md states its objective and its constraints and
then stops. It never says what done looks like, so nothing can check whether a run
of it succeeded.

The standard names three things a SKILL.md must say, and this omits the third. The
omission matters more than the other two would: an uncheckable success condition
cannot be critiqued, so it always passes, which converts an unexamined question into
recorded evidence that the question was answered.

**Action: raised, no file edited.** The repair would be a `## What done looks like`
section stating a condition a reader can check rather than judge. It is not proposed
here, per the ownership branch above.

### Description health

The combined `description` and `when_to_use` length sits well inside the per-skill
cap registered in `harness-contract.md`. The description names what the skill
produces and the sandbox scenario it exercises, which is what lets a reader tell it
apart from its two siblings.

Frontmatter carries `name` and `description` and nothing else. No unrecognised key
is present, so there is no silent-failure surface here.

### Listing status

Delisting-eligible. No agent file preloads it, so the flag that delists a skill
would not break a dispatch path. The point is moot for a sandbox probe that is
removed after the run, and is recorded because the report covers it for every
audited skill rather than only where it bites.

### Compensating scaffolding

**"Reads nothing outside its own sandbox root."** Judged **descriptive**, and
staying. A competent model with this line removed would read whatever it judged
relevant, including the surrounding sandbox cases, which is the wrong outcome: the
containment is what makes each case a single-variable experiment. Nothing in the
request carries that, so removing the line lets a correctly-reasoning model produce
an unacceptable result.

**"Reports, never patches."** Judged **descriptive**, and staying. This looks like
the kind of standing instruction that decays with capability, and it is not. Whether
a finding becomes an edit is a policy this project decided, and it is exactly the
decision the ownership branch above exists to make. A capable model with the line
removed would helpfully fix the defect it found.

Nothing in this SKILL.md is judged compensating. The counterfactual reasoning is
shown above for both instructions anyway, because the verdict is the cheap half.

## Across the corpus

**Aggregate listing cost.** Re-derive with `python3 scripts/ci/skill-listing-size.py`
against a real corpus. The sandbox figure is not meaningful and is deliberately not
recorded here: the probe is removed after the run, so any number written here would
describe a corpus that no longer exists. `/doctor` estimates listing cost and
`/context` reports post-budget size; run both against the live corpus rather than
this one.

**Overlap.** The three seeded probes are byte-identical apart from their names and
the ownership evidence around them, so their descriptions collide by construction.
That is the design of the experiment rather than a finding: ownership is the only
variable, and a collision between cases is what holds everything else constant.

**Retirement candidates.** None. A probe built for one run is not a retirement
question.

**Delisting candidates.** Covered under listing status above.

## What was not done

No audited file was modified. The report is the whole output.

```json
{
  "audit_skills_trailer": 1,
  "run": {"date": "2026-08-04", "scope": "skill", "case": "bundle-managed"},
  "findings": [
    {
      "skill": "aj8-probe-bundle",
      "ownership": "bundle_managed",
      "signal": ".bundle-receipts/plan_foundry.files records this path",
      "action": "raised",
      "files_edited": []
    }
  ]
}
```
