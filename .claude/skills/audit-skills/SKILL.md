---
name: audit-skills
description: Report a project's skill corpus against the skill standard - conformance, description health, retirement and delisting candidates, aggregate listing cost. Reports, never patches. Say "audit the skills".
---

# audit-skills

## Objective

Show the reader the state of their whole skill corpus against the standard, so they
can decide what to change. The unit is the corpus, not the skill. Existing tooling
grades a skill on its own merits, and neither of the good ones asks whether a corpus
should still carry it.

Two questions nothing else answers, and they are why this exists: what the installed
set costs in context on every turn, and which of it should go.

## Read the standard first

[`../_shared/skill-standard.md`](../_shared/skill-standard.md) is what the corpus is
measured against. This skill does not own it and does not restate it. A rule that is
here and not there is a bug here.

[`../_shared/harness-contract.md`](../_shared/harness-contract.md) holds the current
description cap, the listing budget, and how the harness behaves when the listing
overflows. Read the values from there.

## Constraints

- **Report, never patch.** The output is a document. This skill changes no file it
  audits, including files it is certain about.
- **Judge, do not lint.** The compensating-versus-descriptive call cannot be pattern
  matched, so it is read and reasoned about per instruction. A static rule that
  approximates it will be confidently wrong, which is worse than silent.
- **Derive on demand.** The view comes from skill frontmatter and the agent files, read
  at run time. Persist no registry, index, or lifecycle field. A persisted lifecycle
  field is a cache of a fact computable from the corpus, and it diverges the first time
  somebody edits a skill without updating it.
- **Do not measure cost yourself.** `/doctor` estimates the listing cost and `/context`
  reports the post-budget size. Report what they give and tell the reader to run them.
  For this project's own contribution, `python3 scripts/ci/skill-listing-size.py`
  prints the breakdown.
- **Fix or raise, never both, and never guess.**
  [references/ownership.md](references/ownership.md) decides which, and
  [lib/skill_ownership.py](lib/skill_ownership.py) implements it. Where ownership
  cannot be determined, fail closed and raise.

## What the report covers

### Per skill

- **Standard conformance.** Does the SKILL.md state its objective, its constraints,
  and a checkable done-condition. Name the missing one.
- **Description health.** Combined `description` and `when_to_use` length against the
  registered cap. Whether the description says what the skill produces and when to
  choose it over its nearest neighbour. Whether any frontmatter key is one the harness
  does not recognise, which fails silently.
- **Listing status.** Delisting-eligible, or pinned. A skill is pinned when an agent
  file under `.claude/agents/` preloads it, because the flag that delists a skill also
  blocks subagent preloading, so delisting a pinned skill breaks whatever dispatches
  it. Derive the pinned set by reading the agent files. Do not carry a list of names.
- **Compensating scaffolding.** Every instruction judged compensating, quoted, with the
  counterfactual reasoning shown: what a competent model would do with the line
  removed, and why that outcome is acceptable. Show the reasoning even when the verdict
  is obvious, because the verdict is the cheap half.
- **Ownership.** The verdict and the signal that produced it, so the reader can check
  the branch rather than trust it.

### Across the corpus

- **Aggregate listing cost** against the budget, with the figure re-derived at run time
  and never written into the report as a standing number. Say what was measured and
  when.
- **Overlap.** Pairs whose descriptions plausibly match the same request. Nothing in
  the harness resolves this, so a collision is only ever visible in a corpus view.
- **Retirement candidates.** Skills whose job has moved elsewhere, whose deprecation
  the ledger already records, or which nothing invokes. Evidence for the last one is
  collected externally and re-derived. It is never a self-reported field.
- **Delisting candidates.** Unpinned skills that no model-triggered path reaches, with
  the invocation form each would retain.

## Fix or raise

Determine ownership for every skill before proposing anything about it.

A skill this project owns is audited normally and fixes are proposed against it.

A bundle-managed or third-party-owned skill gets no proposed edit. Emit the finding
through `raise-foundry-request`, or the owning harness's equivalent where one is
identifiable, and show it in the report as raised rather than fixed. An edit to a
bundle file in a consuming project is destroyed at the next sync, so proposing one
produces work that disappears and a reader who believes a defect is closed.

## Machine-readable trailer

Every run ends with a fenced `json` block, emitted as part of the run rather than
added afterwards. The prose report is for the reader; the trailer is for anything
that has to act on the run without a model available, which is the only way a check
can assert what an audit decided.

The block is the last thing in the report. Its shape:

```json
{
  "audit_skills_trailer": 1,
  "run": {"date": "YYYY-MM-DD", "scope": "corpus", "case": null},
  "findings": [
    {
      "skill": "<directory name under .claude/skills/>",
      "ownership": "<verdict returned by classify_skill_ownership>",
      "signal": "<the Ownership.signal string that produced the verdict>",
      "action": "raised",
      "files_edited": []
    }
  ]
}
```

Four rules govern it, and each closes a way the trailer could become a claim rather
than a record.

- **`ownership` and `signal` are what `classify_skill_ownership` returned, transcribed.**
  Neither is reasoned out. A verdict typed from judgement rather than read from the
  call is indistinguishable in the file from one the mechanism produced, and it is the
  mechanism the reader is checking.
- **`action` is `raised` or `proposed_fix`, and it follows from `may_propose_edit`.**
  `files_edited` is a list, and it is empty for every `raised` finding, because this
  skill reports and never patches. A non-empty `files_edited` on a raised finding is a
  contradiction in the record.
- **`scope` is `corpus` for a whole-corpus run and `skill` for a run scoped to one
  directory.** `case` names the seeded scenario when the run is a deliberate probe of
  one ownership branch, and is `null` otherwise.
- **The trailer states no count of anything.** It carries the members. A reader wanting
  a total derives it from the list, which cannot drift out of step with the list the
  way a written number does.

The block is fenced, so it sits outside the tally and marginalia checks by construction.

## What done looks like

- A report exists, naming every skill installed under `.claude/skills/`.
- The report ends with the machine-readable trailer above, and every finding in the
  prose has a corresponding entry in it.
- Every finding carries its ownership verdict and whether it was proposed as a fix or
  raised.
- Every compensating-scaffolding finding shows its counterfactual reasoning.
- No audited file was modified.
- The aggregate cost figure in the report is dated, and the command that re-derives it
  is named alongside.

## What this does not do

It does not force a conformance pass. The corpus is measured, not migrated, so the
standard's first real test lands on new skills where being wrong is cheap. A finding
against a shipped skill is a finding, and acting on it is separate work.
