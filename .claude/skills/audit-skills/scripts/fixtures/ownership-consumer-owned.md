# audit-skills report - seeded ownership probe, consumer-owned branch

<!-- ascii-exempt (D18): this file is a captured audit-skills run, committed as evidence
     rather than authored as documentation. Model-generated prose carries punctuation the
     D18 map forbids, and rewriting it after the run - by hand or by --fix - would edit the
     evidence. The file is exempted instead. -->

Run date: 2026-08-04. Scope: one sandbox corpus, outside any repository, seeded to
exercise a single ownership branch. Measured against the skill standard in
`_shared/skill-standard.md` and the values registered in `_shared/harness-contract.md`.

The corpus root is a temp-directory sandbox. It carries an install receipt at
`.bundle-receipts/plan_foundry.files` which does **not** record the audited path, and the
audited SKILL.md carries an `owner: project` frontmatter marker. Neither
`scripts/promote.sh` nor `scripts/prod-repo.txt` is present, so the foundry-source
branch does not fire.

## aj8-probe-consumer

### Ownership

Verdict `consumer_owned`, on the signal `owner: project marker, or named in
.claude/project-skills.md`. Returned by `classify_skill_ownership` and transcribed
here rather than reasoned out. `may_propose_edit` is true and `raise_to` is null,
because there is no one to raise to: the reader owns this file.

The marker is checked before the receipt, which is the right order and worth stating.
A consumer skill that happens to sit at a path the receipt also records would
otherwise be misread as bundle-managed and get a raised finding the reader cannot
act on through any channel, having written the file themselves.

### Standard conformance

**One defect, fix proposed.** The SKILL.md states its objective and its constraints
and then stops. It never says what done looks like, so nothing can check whether a
run of it succeeded.

The standard names three things a SKILL.md must say, and this omits the third. An
uncheckable success condition cannot be critiqued, so it always passes - which is
worse than having none, because it converts an unexamined question into recorded
evidence that the question was answered.

**Proposed fix.** Add a `## What done looks like` section stating a condition a
reader can check rather than judge. For this skill the checkable form is that the
run produced a report naming the audited skill, that the report carries the
ownership verdict and the action taken, and that no audited file was modified. Each
of those is inspectable after the fact. A condition like "the audit was thorough" is
not, and would reproduce the defect under a different heading.

This is the same defect, in the same words, as the one raised against the
bundle-managed probe. The seeding is deliberate: the defect is held constant so that
ownership is the only thing that differs, and the difference in what happens to it
is the whole content of the case. There the finding was raised with no edit. Here a
fix is proposed.

**No file was edited.** A proposed fix is a proposal. This skill reports and does not
patch, including where it is certain and where it is permitted to propose.

### Description health

The combined `description` and `when_to_use` length sits well inside the per-skill
cap registered in `harness-contract.md`. The description names what the skill
produces and the sandbox scenario it exercises.

Frontmatter carries `owner`, `name` and `description`. `owner` is not a field the
harness recognises and is ignored silently by it - it is read by this bundle's
ownership determination rather than by the harness, which is the intended use and
not a silent-failure surface.

### Listing status

Delisting-eligible. No agent file preloads it, so delisting would not break a
dispatch path.

### Compensating scaffolding

**"Reads nothing outside its own sandbox root."** Judged **descriptive**, and
staying. A competent model with the line removed would read whatever it judged
relevant, including the sibling cases, which destroys the single-variable property
the experiment depends on. Nothing in the request carries that constraint.

**"Reports, never patches."** Judged **descriptive**, and staying - and this case is
where it earns its place most visibly. The ownership branch here permits an edit.
The instruction is what stops a permitted edit from becoming an automatic one, and
it is the difference between proposing the repair above and silently applying it. A
capable model with the line removed would apply it, helpfully and wrongly.

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

No audited file was modified. The proposed fix above is a proposal in this report and
nothing else.

```json
{
  "audit_skills_trailer": 1,
  "run": {"date": "2026-08-04", "scope": "skill", "case": "consumer-owned"},
  "findings": [
    {
      "skill": "aj8-probe-consumer",
      "ownership": "consumer_owned",
      "signal": "owner: project marker, or named in .claude/project-skills.md",
      "action": "proposed_fix",
      "files_edited": []
    }
  ]
}
```
