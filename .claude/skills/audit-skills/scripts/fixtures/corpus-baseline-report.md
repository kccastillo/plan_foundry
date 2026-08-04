# audit-skills corpus baseline report

<!-- ascii-exempt (D18): this file is a captured audit-skills run over the whole corpus,
     committed as evidence rather than authored as documentation. Model-generated prose
     carries punctuation the D18 map forbids, and rewriting it after the run - by hand or
     by --fix - would edit the evidence. The file is exempted instead. -->

Run date: **2026-08-04**, against commit `66d61d0`, with no `aj8-` directory present
under `.claude/skills/`. Measured against `_shared/skill-standard.md`, with harness
values read from `_shared/harness-contract.md`.

This report is the committed baseline `check_report_coverage.py` reads. It is evidence
of a run rather than a document to be edited: it is refreshed by re-running
`audit-skills` over the corpus out-of-CI, never by hand-editing this file. Adding or
retiring any skill reddens that check until the report is regenerated.

## Method, and one correction made during the run

A structural scan for the three required elements produced results that reading
contradicted, and the corrected reading is what is reported below.

The scan looked for headings named Objective, Constraints and a done-condition. The
corpus is split between XML-ish section tags and plain headings, and the standard
rules markup free, so a skill stating its objective as the first line of
`<essential_principles>` conforms while failing the scan. Checked by reading:
`write-plan` opens with "Transcribe plan content accurately", which is the objective;
`audit-sufficiency` opens by scoping itself against its two nearest neighbours, which
is the objective doing the harder half of its job. Both were scan failures and both
conform.

The scan was right about `retire`, which has an `<objective>` block and no constraints
section at all, and right that the deprecation shims state none of the three - which is
correct for a shim rather than a defect in one.

Recording this because the standard's "judge, do not lint" constraint is the reason
this skill is model-driven, and this run is a worked instance of a static rule being
confidently wrong in both directions.

## The corpus

Every skill installed under `.claude/skills/`, with its ownership verdict.

**Ownership is uniform and that fact is itself the finding.** Every skill below returns
`foundry_source` on the signal `scripts/promote.sh and scripts/prod-repo.txt both
present`, because this working tree is the bundle source rather than a project that
installed it. Fixes are proposed here rather than raised. The three consumer-facing
branches - bundle-managed, consumer-owned, undeterminable - are unreachable in this
repository by construction, which is why they are exercised against seeded sandbox
fixtures instead.

| Skill | Listing | Conformance | Notes |
|---|---|---|---|
| `audit-haiku-safe` | listed, pinned | states constraints and success criteria; objective carried in `<essential_principles>` | pinned by the plan-safety auditor agent |
| `audit-skills` | listed | conforms | this skill |
| `audit-sufficiency` | listed, pinned | conforms; objective scopes it against its two neighbours | pinned by the sufficiency auditor agent |
| `autonomous-loop` | delisted | states none of the three under a recognised heading | delisted, so its body loads only on explicit invocation |
| `convert-pdf` | listed | shim | deprecation ledger records the replacement |
| `doc-to-md` | listed | shim | deprecation ledger records the replacement |
| `execute-plan` | listed, pinned | states constraints and success criteria | pinned by all three executor agents |
| `foundry-research` | listed | shim | deprecation ledger records the replacement |
| `handoff-next-session` | listed | conforms | heaviest non-`ideate` description |
| `ideate` | listed | states constraints and success criteria | largest single listing cost in the corpus |
| `init-plan-foundry` | delisted | conforms | |
| `maintain-claude-md` | listed | shim | renamed; ledger records the successor |
| `maintain-project-docs` | listed | conforms | |
| `plan-foundry-check-current` | delisted | shim-shaped body, minimal | |
| `plan-foundry-sync` | delisted | conforms | |
| `plan-foundry-uninstall` | delisted | conforms | |
| `plan-pipeline` | listed | states constraints and success criteria | objective is carried by the frontmatter description rather than the body; see findings |
| `raise-foundry-request` | listed | conforms | |
| `reformat-md` | listed | shim | deprecation ledger records the replacement |
| `rehydrate-handoff` | listed | conforms | |
| `rehydrate-input` | listed | shim | deprecation ledger records the replacement |
| `retire` | listed, pinned | **no constraints section** | see findings |
| `segment-doc` | listed | shim | deprecation ledger records the replacement |
| `test-foundry` | delisted | states neither objective nor done-condition under a recognised heading | |
| `write-input` | listed | states constraints and success criteria | |
| `write-plan` | listed, pinned | conforms; objective is the first line of `<essential_principles>` | pinned by the plan-writer agent |
| `write-skill` | listed | conforms | |

The pinned set is derived by reading `.claude/agents/*.md` at run time. Five skills are
preloaded by at least one agent: `execute-plan`, `retire`, `audit-haiku-safe`,
`write-plan`, `audit-sufficiency`. A pinned skill cannot be delisted, because the flag
that delists also blocks subagent preloading.

## Findings

### The corpus cites artefacts that do not outlive it

**The largest conformance finding, and it is corpus-wide.** The standard forbids a
skill carrying a reference to anything with a lifecycle that ends, and names the case
explicitly: citing a decision as "per D4 of PLAN-XX0" is the same defect as linking the
file, because the reader cannot resolve it once the plan retires and the sentence stops
meaning anything.

Measured by scanning every markdown file under each skill directory for a PLAN
identifier or a decision code cited as authority, and excluding directory names like
`Workbench/`, which are the operating surface of several skills rather than references
to ephemeral objects:

```
skills citing a PLAN identifier ......... 18
skills citing a decision code ........... 12
skills with at least one of either ...... 18
heaviest: plan-pipeline (28 PLAN-id sites), plan-foundry-sync (22), write-plan (20)
```

The visible half is that the pointers break. The worse half is that a rule justified by
a decision the reader cannot look up is a rule they cannot evaluate, so they follow it
blindly or ignore it. Several of the cited PLANs have already retired.

**Not proposed as a corpus-wide fix.** Enforcement of the standard is forward-only:
the corpus is measured against it and new skills are built to it. This is recorded with
its reasoning shown, and acting on it is separate work. The repair per site is to state
the rule and its reason in the skill, move long reasoning to a durable `_shared/`
helper, or drop the citation to the commit message.

### `retire` has no constraints section

The standard says a skill with no constraints section is either trivial or has not been
thought about. `retire` is neither - it moves files and has a post-condition check built
after a real data-loss incident. Three constraint-shaped lines exist in the body; none
sits under a constraints heading. **Proposed fix:** gather them under one, since what
`retire` must not do is the load-bearing half of it.

### `plan-pipeline` carries its objective only in frontmatter

Its body opens on architecture - orchestrator, organs, dispatched workers - rather than
on what the skill is for in the terms of someone invoking it. The frontmatter
description does that job, and the description is not the body. A reader who has
triggered the skill and is reading it has left the description behind. **Proposed fix:**
one opening sentence of objective before the architecture.

### Compensating versus descriptive

Applied per instruction to the skills carrying standing procedural rules. The
counterfactual test: an instruction is compensating if a competent model would do it
unprompted, descriptive if removing it lets a correctly-reasoning model still produce an
unacceptable outcome.

**Descriptive, staying.** `execute-plan`'s halt-on-ambiguity rule: a capable model with
it removed picks the most sensible reading and proceeds, which is wrong here, because
who owns an ambiguity is a decision this project made and nothing in the request carries
it. `execute-plan`'s division of frontmatter ownership between executor and
orchestrator: remove it and a capable executor writes the terminal status itself,
helpfully and wrongly. `audit-skills`'s report-never-patch constraint: whether a finding
becomes an edit is policy, and no capability tells a model what this project decided.
`plan-pipeline`'s idempotent-re-entry rule: a model cannot infer from the task that
double-dispatch is the failure mode being guarded.

**Compensating, recorded not removed.** `execute-plan`'s standing instruction to verify
each step before moving on. A competent model checks its work as it goes, and the
instruction converts that into a separate announced pass, which is the over-verification
shape the vendor guidance names. Where a specific step genuinely depends on the previous
one landing, that belongs at the step. The general form earns nothing.

The verdict is the cheap half in every case above; the counterfactual reasoning is what
was actually done.

## Aggregate listing cost

Re-derive with `python3 scripts/ci/skill-listing-size.py`. Run `/doctor` for the
harness's own listing estimate and `/context` for post-budget size; this skill does not
measure those itself.

Measured 2026-08-04, probe-absent:

```
TOTAL listed ................ 7749
recovered by delisting ...... 3602
largest single contributor .. ideate, 1070
```

No skill is over the per-skill cap registered in `harness-contract.md`; the caps check
passes. The figure above is a dated measurement of one run, not a standing total.

`ideate` is the largest contributor by a wide margin and the obvious first candidate if
the aggregate becomes a constraint. It is also the skill whose description does the most
disambiguation work, so trimming it trades listing cost against trigger accuracy, and
that trade needs measuring rather than assuming.

## Overlap

Pairs whose descriptions plausibly match the same request:

- `write-plan` and `plan-pipeline`. Already resolved in `plan-pipeline`'s description by
  a stated exclusion routing "create plan file" to `write-plan`. This is the pattern the
  standard prescribes for over-firing, and it is the corpus's only worked instance.
- `write-input` and `raise-foundry-request`. Both accept an observation from the
  operator. The boundary is real but is carried by `raise-foundry-request` alone.
- `rehydrate-handoff` and `handoff-next-session`. Read side and write side of one
  lifecycle, with adjacent vocabulary. No collision observed in practice.
- `maintain-project-docs` and `audit-skills`. Both audit and both report rather than
  patch. Different surfaces, adjacent phrasing.
- The seven deprecation shims retain descriptions that still describe the work they no
  longer do, each prefixed "Deprecated". They remain in the listing and continue to
  spend budget.

## Retirement candidates

The seven skills the deprecation ledger already records, all shim-only bodies:
`convert-pdf`, `doc-to-md`, `segment-doc`, `reformat-md`, `foundry-research`,
`rehydrate-input`, `maintain-claude-md`. The ledger names a replacement for each. They
are scheduled for removal at the next major and are retained deliberately so a consumer
invoking one gets a diagnostic rather than a missing-file error.

Their listing cost while retained is visible in the breakdown above. Delisting them
would recover it and still leave the diagnostic reachable by explicit invocation, which
is the disposition worth considering if the aggregate becomes pressing before the major
lands.

No skill outside the ledger is a retirement candidate on this evidence. Invocation
evidence is collected externally and re-derived; it is never a self-reported field, and
none is asserted here.

## Delisting candidates

Six skills are already delisted: `autonomous-loop`, `init-plan-foundry`,
`plan-foundry-sync`, `plan-foundry-uninstall`, `plan-foundry-check-current`,
`test-foundry`. Each retains explicit invocation and a slash command where one exists.

The seven ledger-recorded shims are the remaining candidates, per the section above.
Every other listed skill is either model-triggered by design or pinned by an agent.

## What was not done

No audited file was modified.

```json
{
  "audit_skills_trailer": 1,
  "run": {"date": "2026-08-04", "scope": "corpus", "case": null},
  "findings": [
    {"skill": "audit-haiku-safe", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "audit-skills", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "audit-sufficiency", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "autonomous-loop", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "convert-pdf", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "doc-to-md", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "execute-plan", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "foundry-research", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "handoff-next-session", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "ideate", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "init-plan-foundry", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "maintain-claude-md", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "maintain-project-docs", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "plan-foundry-check-current", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "plan-foundry-sync", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "plan-foundry-uninstall", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "plan-pipeline", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "raise-foundry-request", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "reformat-md", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "rehydrate-handoff", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "rehydrate-input", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "retire", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "segment-doc", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "test-foundry", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "write-input", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "write-plan", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []},
    {"skill": "write-skill", "ownership": "foundry_source", "signal": "scripts/promote.sh and scripts/prod-repo.txt both present", "action": "proposed_fix", "files_edited": []}
  ]
}
```
