# audit-skills report - seeded ownership probe, undeterminable branch

<!-- ascii-exempt (D18): this file is a captured audit-skills run, committed as evidence
     rather than authored as documentation. Model-generated prose carries punctuation the
     D18 map forbids, and rewriting it after the run - by hand or by --fix - would edit the
     evidence. The file is exempted instead. -->

Run date: 2026-08-04. Scope: one sandbox corpus, outside any repository, seeded to
exercise a single ownership branch. Measured against the skill standard in
`_shared/skill-standard.md` and the values registered in `_shared/harness-contract.md`.

The corpus root is a temp-directory sandbox carrying **no install receipt at all**.
The audited skill sits at `.claude/skills/aj8-probe-unknown/`, a path that does not
resolve anywhere in this repository and is not meant to - the probe was removed after
the run, and the unresolvable path is the content of this case rather than an
oversight in recording it. Neither `scripts/promote.sh` nor `scripts/prod-repo.txt`
is present, so the foundry-source branch does not fire, and with no receipt to read
the determination has nothing to attribute the path to.

## aj8-probe-unknown

### Ownership

Verdict `undeterminable`, on the signal `no install receipt, or the receipt did not
parse`. Returned by `classify_skill_ownership` and transcribed here rather than
reasoned out. `may_propose_edit` is false and `raise_to` names the foundry request
channel.

The determination attached a note to this verdict and it is the substance of the
case: *absent evidence is not evidence of consumer ownership, so this is raised
rather than fixed.* The branch fails closed.

That direction is the whole point. The permissive reading - no receipt, so nobody
claims it, so the reader may as well own it - is the one that produces silent harm,
because it proposes edits against files that turn out to be bundle-managed and are
destroyed at the next sync. The reader is then left believing a defect is closed. A
wrongly-raised request costs one request that gets declined, and the reader still
holds the file and can still fix it. The costs are not symmetric, and the branch is
built around which way it is safe to be wrong.

### Standard conformance

**One defect, raised.** The SKILL.md states its objective and its constraints and
then stops. It never says what done looks like, so nothing can check whether a run
of it succeeded.

The standard names three things a SKILL.md must say, and this omits the third. An
uncheckable success condition cannot be critiqued, so it always passes.

**Action: raised, no file edited.** This is the same defect, in the same words, as
the one carried by the other two probes. Holding it constant is what makes ownership
the only variable across the three cases, and the difference in what happens to it
is what each case records. Here it is raised for the same reason as the
bundle-managed case but on different evidence: there the receipt said the bundle
owns the path, here nothing said anything and the branch refused to guess.

### Description health

The combined `description` and `when_to_use` length sits well inside the per-skill
cap registered in `harness-contract.md`. The description names what the skill
produces and the sandbox scenario it exercises.

Frontmatter carries `name` and `description` and nothing else. No unrecognised key
is present.

### Listing status

Delisting-eligible. No agent file preloads it, so delisting would not break a
dispatch path.

### Compensating scaffolding

**"Reads nothing outside its own sandbox root."** Judged **descriptive**, and
staying. A competent model with the line removed would read whatever it judged
relevant, including the sibling cases, which destroys the single-variable property
the experiment depends on.

**"Reports, never patches."** Judged **descriptive**, and staying. Whether a finding
becomes an edit is a policy this project decided, and no amount of capability tells a
model what this project decided.

Nothing in this SKILL.md is judged compensating.

## Across the corpus

**Aggregate listing cost.** Re-derive with `python3 scripts/ci/skill-listing-size.py`
against a real corpus. No sandbox figure is recorded here: the probe is removed after
the run, so any number would describe a corpus that no longer exists. `/doctor` and
`/context` report listing and post-budget cost against the live corpus.

**Overlap.** The seeded probes are byte-identical apart from their names and the
ownership evidence around them, so their descriptions collide by construction. That
is the design of the experiment rather than a finding.

**Retirement candidates.** None.

**Delisting candidates.** Covered under listing status above.

## What was not done

No audited file was modified. The report is the whole output.

```json
{
  "audit_skills_trailer": 1,
  "run": {"date": "2026-08-04", "scope": "skill", "case": "undeterminable"},
  "findings": [
    {
      "skill": "aj8-probe-unknown",
      "ownership": "undeterminable",
      "signal": "no install receipt, or the receipt did not parse",
      "action": "raised",
      "files_edited": []
    }
  ]
}
```
