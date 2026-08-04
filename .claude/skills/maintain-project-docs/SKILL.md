---
name: maintain-project-docs
description: Audit, add to, or prune the project's durable docs - CLAUDE.md, ARCHITECTURE.md, CONTEXT_CONSTITUTION.md and the _shared/*.md helpers. Output is a PLAN or a findings file, never a direct edit. Say "audit CLAUDE.md", "prune the docs".
---

# maintain-project-docs

## Objective

Keep the documents that are loaded into every session, or read by every agent, honest
about the codebase they describe. These rot silently: nothing fails when CLAUDE.md
names a skill that was renamed months ago, or when a helper describes a mechanism that
was removed.

Three modes, dispatched by phrasing:

- **audit** - "audit CLAUDE.md", "is CLAUDE.md still good", "review the helpers", or
  the monthly recurring trigger. Scans every in-scope file against the checklist and
  produces a punch list.
- **add** - "add X to CLAUDE.md", "should this go in the constitution". Proposes the
  addition with the exact diff, and flags placement, duplication risk and budget
  impact.
- **prune** - "prune CLAUDE.md", "remove the dead reference to X". Proposes specific
  removals.

If the phrasing does not settle the mode, ask once before producing anything.

## Files in scope

- `CLAUDE.md` - the always-loaded instruction file.
- `ARCHITECTURE.md` - design philosophy, strategic principles, the invariants register.
- `.claude/CONTEXT_CONSTITUTION.md` - present only on team-scoped projects.
- `.claude/skills/_shared/*.md` - the durable helpers every skill reads.

**Why the helpers are in scope.** Durable content migrates into `_shared/` by default
when a working file retires, so the directory accumulates content that outlives the
work that produced it, and it is read by skills rather than by people. Nothing else
owns it. That was survivable while it held only scripts and stopped being survivable
once prose started landing there.

**Absent-file semantics.** Each file is audited only if it exists. A file that does not
exist is silently skipped and is never reported as drift. This keeps the skill safe in
both a foundry-maintainer project, where all of them exist, and a consuming project,
where typically only CLAUDE.md does.

**Checklist applicability.** Sections A (size and budget), C (instruction weighting),
D (anti-patterns) and E (reference health) apply to every file in scope. Section B
(trinity present) is CLAUDE.md-specific and is skipped elsewhere.

**Helper-specific checks.** For `_shared/*.md`, add two the root docs do not need.
Check that no helper carries marginalia: commentary about itself, provenance, or a
parked question for the reader. Check that no helper references a working artefact -
a plan, an input, a handoff, a request, or anything under a working directory - since
those are deleted or moved and the helper is not.

## Bundle-managed content

When the audited CLAUDE.md carries a
`<!-- plan-foundry:init-plan-foundry:start -->` ... `<!-- plan-foundry:init-plan-foundry:end -->`
block, the content between the markers belongs to the bundle rather than to the
consumer.

- Skip sections A, C, D and E for the content between the markers. Auditing bundle
  content for line budget or instruction weighting reports drift the consumer cannot
  act on.
- Verify the marker pair is well formed: exactly one start, exactly one end, end after
  start. A malformed pair is a blocker finding labelled `marker-malformed`, with the
  repair named: re-run the bundle installer, or remove the malformed markers by hand
  and re-run it.
- Never propose a modification inside the markers. When the inlined content is stale,
  the consumer re-runs the installer to replace it from the current bundle.

The same rule holds for a `_shared/` helper in a consuming project. Those are bundle
files, so an edit there is destroyed at the next sync. Report the finding and raise it
rather than proposing a patch.

## Line-cap policy

- **Soft warn at 150 lines.** Above this the audit flags the file as approaching the
  cap and suggests prune mode.
- **Hard cap:** read the enforced value from `scripts/ci/run-all.sh`, which fails the
  build above it. Do not carry a second copy of that number here.
- Above the hard cap, block every add-mode proposal until a prune lands.

## Constraints

- Never edit an in-scope file directly. The output is always a file, so the human
  approves a change before it happens.
- Never write findings to chat only.
- Never audit `.claude/skills/*/references/*.md`. Those are progressive-disclosure
  targets and bulk is correct there. Do check that pointers into them resolve.
- Use the checklist verbatim. Do not invent a rule during an audit. Propose a new rule
  through an add-mode run against the checklist itself.

## Workflow

See [workflows/produce-plan.md](workflows/produce-plan.md).

Output mode depends on whether the planning bundle is installed. With it, the findings
are written as a Workbench PLAN. Without it, they are written as a markdown file in the
project root. `--output workbench` or `--output plain` overrides the detection.

## References

- [references/audit-checklist.md](references/audit-checklist.md) - the checks.
- [references/anti-patterns.md](references/anti-patterns.md) - what to flag and why.
- Templates: [audit](templates/audit-plan-template.md),
  [add](templates/add-plan-template.md), [prune](templates/prune-plan-template.md).

## What done looks like

- An output file exists: a Workbench PLAN with valid frontmatter, or a markdown
  findings file in the project root.
- Every finding names the file, the line range, the verdict and the recommended fix.
- No in-scope file was modified by this run.
- The human can hand the output straight to execution without further design.
