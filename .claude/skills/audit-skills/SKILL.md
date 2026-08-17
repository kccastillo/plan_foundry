---
name: audit-skills
description: Report a project's skill corpus against the skill standard - conformance, description health, retirement and delisting candidates, aggregate listing cost. Reports, never patches. Say "audit the skills".
---

# audit-skills

## Objective

Show the reader the state of their whole skill corpus against the standard, so they
can decide what to change. The unit of the report is the corpus rather than the
individual skill. Existing tooling grades a skill on its own merits, and none of that
tooling reports whether a corpus should still carry the skill.

This skill exists to answer questions nothing else answers: what the installed set
costs in context on every turn, and which skills should go.

## Read the standard first

The corpus is measured against
[`../_shared/skill-standard.md`](../_shared/skill-standard.md). This skill does not own
the standard and does not restate its rules. A rule stated in this file and absent from
the standard is a defect in this file.

[`../_shared/harness-contract.md`](../_shared/harness-contract.md) holds the current
description cap, the listing budget, and how the harness behaves when the listing
overflows. Read the values from there.

## Constraints

- **Report, never patch.** The output is a document. This skill changes no file it
  audits, even where the defect is certain.
- **Judge, do not lint.** The compensating-versus-descriptive call cannot be pattern
  matched, so each instruction is read and judged on its own. A static rule that
  approximates the call will be confidently wrong, which does more damage than
  reporting nothing.
- **Derive on demand.** The report is derived from skill frontmatter and the agent
  files, read at run time. Persist no registry, index, or lifecycle field. A persisted
  lifecycle field is a cache of a fact computable from the corpus, and the cache
  diverges the first time somebody edits a skill without updating the field.
- **Do not measure cost yourself.** `/doctor` estimates the listing cost and `/context`
  reports the post-budget size. Report what those commands print and tell the reader to
  run them. For this project's own contribution,
  `python3 scripts/ci/skill-listing-size.py` prints the breakdown.
- **Fix or raise, never both, and never guess.**
  [references/ownership.md](references/ownership.md) states which branch applies, and
  [lib/skill_ownership.py](lib/skill_ownership.py) implements that policy. Where
  ownership cannot be determined, fail closed and raise.

## What the report covers

### Per skill

- **Standard conformance.** Does the SKILL.md state its objective, its constraints,
  and a checkable done-condition. Name the missing one.
- **Description health.** Combined `description` and `when_to_use` length against the
  registered cap. Whether the description says what the skill produces and when to
  choose it over its nearest neighbour. Whether any frontmatter key is one the harness
  does not recognise, which fails silently.
- **Listing status.** Delisting-eligible, or pinned. A skill is pinned when an agent
  file under `.claude/agents/` preloads it. The reason is registered rather than
  restated: the harness contract's "disable-model-invocation: subagent preloading"
  entry assumes the flag that delists a skill also blocks subagent preloading, at a
  `documented` status rather than a first-hand observation, so treat a pinned skill as
  unsafe to delist and read that entry for the current confidence before reporting on
  one. Derive the pinned set by reading the agent files. Do not carry a list of names.
- **Compensating scaffolding.** Every instruction judged compensating, quoted, with the
  counterfactual reasoning shown: what a competent model would do with the line
  removed, and why that outcome is acceptable. Show the reasoning even when the verdict
  is obvious, because the verdict is the cheap half.
- **Ownership.** The verdict and the signal that produced it, so the reader can check
  the branch rather than trusting the verdict.

### Across the corpus

- **Aggregate listing cost** against the budget, with the figure re-derived at run time
  and never written into the report as a standing number. Say what was measured and
  when.
- **Overlap.** Pairs whose descriptions plausibly match the same request. Nothing in
  the harness resolves this, so a collision is only ever visible in a corpus view.
- **Retirement candidates.** Skills whose job has moved elsewhere, whose deprecation
  the deprecation ledger already records, or which nothing invokes. Evidence for the
  last one is collected externally and re-derived. That evidence is never a
  self-reported field.
- **Delisting candidates.** Unpinned skills that no model-triggered path reaches, with
  the invocation form each would retain.

## Fix or raise

Determine ownership for every skill before proposing any change to that skill.

A skill this project owns is audited normally and fixes are proposed against that
skill.

A bundle-managed or third-party-owned skill receives no proposed edit. Emit the finding
through `raise-foundry-request`, or the owning harness's equivalent where one is
identifiable, and record the finding in the report as raised rather than fixed. An edit
to a bundle file in a consuming project is destroyed at the next sync, so proposing one
produces work that disappears and a reader who believes a defect is closed.

## Machine-readable trailer

Every run ends with a fenced `json` block, emitted as part of the run rather than
added afterwards. The prose report is for the reader, while the trailer is for anything
that has to act on the run without a model available, and the trailer is the only way a
check can assert what the auditor recorded.

The block is the last thing in the report, and it takes this shape:

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

These rules govern the trailer, and each one closes a way the trailer could become a
claim rather than a record.

- **`ownership` and `signal` are what `classify_skill_ownership` returned, transcribed.**
  Neither is reasoned out. A verdict typed from judgement rather than read from the
  call is indistinguishable in the file from one the mechanism produced, and the
  mechanism is what the reader is checking.
- **`action` is `raised` or `proposed_fix`, and it follows from `may_propose_edit`.**
  `files_edited` is a list, and that list is empty for every `raised` finding, because
  this skill reports and never patches. A non-empty `files_edited` on a raised finding
  is a contradiction in the record.
- **`scope` is `corpus` for a whole-corpus run and `skill` for a run scoped to one
  directory.** `case` names the seeded scenario when the run is a deliberate probe of
  one ownership branch, and is `null` otherwise.
- **The trailer states no count of anything.** The trailer carries the members instead.
  A reader wanting a total derives that total from the list, and a derived total cannot
  drift out of step with the members the way a written number does.

The block is fenced, so the tally and marginalia checks exclude it by construction.

## What done looks like

- A report exists, naming every skill installed under `.claude/skills/`.
- The report ends with the machine-readable trailer above, and every finding in the
  prose has a corresponding entry in the trailer.
- Every finding carries its ownership verdict and whether it was proposed as a fix or
  raised.
- Every compensating-scaffolding finding shows its counterfactual reasoning.
- No audited file was modified.
- The aggregate cost figure in the report is dated, and the command that re-derives it
  is named alongside.

## What this does not do

This skill does not force a conformance pass. The corpus is measured rather than
migrated, so the standard's first real test applies to new skills, where being wrong is
cheap. A finding against a shipped skill is recorded, and acting on that finding is
separate work.
