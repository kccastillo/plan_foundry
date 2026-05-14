# Plan File Conventions

This file is the canonical source for Workbench/ file conventions. AGENT_RULES.md and CLAUDE.md should point here rather than duplicate.

## File Naming

`{YYYYMMDDHHMI}_{TYPE}_{slug}.md` — see `references/naming-convention.md` for full pattern, type tokens, and examples.

## Monthly LOG Path

`Workbench/{YYYYMM}010000_LOG_{YYYYMM}.md` — first-of-month midnight timestamp regardless of when created.

## Recurring PLAN Prefix

Slugs start with `RECUR-`. One persistent file per recurring task; each cycle appends to `## History`.

## File Types

`LOG` | `PLAN` | `RESEARCH` | `ADVICE`.

## PLAN Status Lifecycle

Frontmatter `status` field:
```
ready → in-progress → done | partially-complete | blocked | needs-revision
```

- `ready` — transcribed, not yet started. Set on creation.
- `in-progress` — execute-plan skill has started. Set when execution begins.
- `done` — all verification criteria pass. Terminal.
- `partially-complete` — some steps done, others blocked or deferred. Terminal for this cycle.
- `blocked` — cannot proceed; `blocked_by` holds the reason. Cleared automatically by `write-input` when the resolving RESEARCH/ADVICE lands, or manually by the Human. Non-terminal until unblocked.
- `needs-revision` — plan itself is faulty; return to Sonnet. Non-terminal.

LOG Status Table "Status" column mirrors the plan's frontmatter `status` at end of day. Rollover treats `done`, `cancelled`, `closed` as complete; everything else rolls over.

## PLAN Pipeline Phase

Frontmatter `pipeline_phase` field, orthogonal to `status`. Tracks orchestration state for PLANs managed by the `plan-pipeline` skill.

```
drafting → drafted → checked → executing → complete
```

- `drafting` — ideation underway; PLAN being written/updated incrementally.
- `drafted` — ideation closed; PLAN written; awaiting sufficiency + plan-safety review.
- `checked` — review passed; ready to execute. Aligns with `status: ready`.
- `executing` — `plan-executor` subagent has been dispatched.
- `complete` — execution done; ready for retirement.

**Default for ad-hoc PLANs** (created directly via `write-plan` outside the pipeline): field absent or empty. When `plan-pipeline` is invoked against such a PLAN, it treats absent/empty as `drafted` (assume the PLAN is already written and ready for review), not `drafting` — to avoid re-ideating an already-authored plan.

## PLAN Input Linkage

Frontmatter `linked_inputs: []` contains one array of filenames — both RESEARCH and ADVICE. Type is recoverable from the `_RESEARCH_` / `_ADVICE_` token in each filename. No separate `linked_research` / `linked_advice` / `requires_opus` / `requires_research` fields — `status: blocked` + `blocked_by` carries the "needs input before running" signal.

## Roadmap Linkage

PLANs may reference items in `.claude/ROADMAP.md` via three optional frontmatter fields:

- `closes_thread: T{ID}` — this PLAN's successful execution fully closes the named thread. On PLAN closure (outcome=done), `execute-plan` Step 4.5 appends a closure bullet to the thread body and sets the thread's `Status` to `closed`. The thread stays in its pillar for historical context; grep for `Status:.*closed` to inventory closed work.
- `advances_thread: T{ID}` — this PLAN partially progresses the thread. On closure, `execute-plan` appends a progress note to the thread body but leaves the thread in its pillar.
- `parent_plan_of_plans: <path>` — this PLAN is part of a coordinated effort tracked by another file. On closure, `execute-plan` updates the parent plan-of-plans tracking section per that file's schema.

Set these on PLAN creation (in `write-plan`). Empty string means no linkage. A PLAN closes or advances at most one thread; for multi-thread work, decompose into multiple PLANs or introduce a plan-of-plans.

## Plan-of-plans authoring: sketch-first convention

When authoring a plan-of-plans (a PLAN that coordinates multiple child PLANs across linked threads, files, or plugins):

1. **When to use a plan-of-plans.** A plan-of-plans is appropriate when work spans multiple independent threads or coordinated effort across files/plugins — for example, plugin extraction (PLAN 1200) or a multi-phase infrastructure refactor. If work fits naturally into a single PLAN with sequential steps, use that instead.

2. **The placeholder convention.** You do not need to author all child PLANs before drafting the parent. Instead, declare child PLANs in the parent's `triggers_plans: []` field using placeholder syntax: `"[placeholder] <slug>"`, where `<slug>` is a short descriptive name for the child work. For example: `triggers_plans: ["[placeholder] plugin-extraction", "[placeholder] update-harness-templates"]`. This lets you sketch the coordinated effort's shape while child details are still being shaped.

3. **Transition to real IDs.** As each child PLAN is drafted, replace the corresponding placeholder entry with the actual PLAN filename (e.g. `"PLAN-010_plugin-extraction.md"`). This replacement should happen in the same commit that drafts the child, keeping the parent's tracking in sync.

4. **Parent update discipline.** When a child PLAN is drafted, update both the parent's `triggers_plans` array and any child-tracking table in the parent's Objective or Context section (if used). Do both edits in a single commit to maintain clarity.
