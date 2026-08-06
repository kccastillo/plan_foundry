---
title: Proportionality Gate
description: The rung menu presented when ideation is invoked. Decides how much of plan_foundry a piece of work needs, before any of it runs.
created: 2026-08-03
---

# Proportionality gate

Fires once, when ideation is invoked. Assess the work, present the menu, take the
Human's pick. Do not run any phase before the pick.

The full arc costs most of a day. That is the right price for a finicky, wide,
irreversible change. It is the wrong price for most work, and the model can do
much of that work unaided.

## The three questions

Ask these in order. Each one only rules the rung up, never down.

1. Is the requirement agreed, or does it still need shaping?
2. Is the mechanism forced, or is there a live design fork?
3. Is the change reversible, and how wide is its blast radius?

Shaping needed sends it to Full arc. A live fork sends it to Audit it or higher.
Irreversible, or wide, sends it to Full arc.

## The menu

Present all four rungs every time, with the recommendation named. The Human picks
by name.

| Rung | What runs | When it fits |
|---|---|---|
| **just do it** | The work. No PLAN file. | Mechanism forced, small radius, reversible. |
| **plan it** | PLAN written, executed, verified, retired. No ideate phases, no audit loop. | Requirement agreed, several steps, worth a durable record. |
| **audit it** | Plan it, plus the sufficiency and plan-safety auditors. | A live design fork, or work a second reader would catch something in. |
| **full arc** | Ideate phases 1-8, both risk gates, then the audit loop and the pipeline. | The requirement itself needs shaping, or the change is irreversible or wide. |

Say what the recommended rung costs and what it skips. A Human choosing `plan it`
is choosing to go without a second reader, and must be able to see that.

## Mechanism per rung

Once the Human picks a rung below `full arc`, this is exactly which skill call
the agent makes next.

- **`just do it`:** do the work directly in the current turn. Do not call
  `write-plan`. State the rung and the one-sentence reason in the reply (rule
  5, unchanged). No disk record is written for this rung, by design - the work
  stays off the record on purpose.

- **`plan it`:** gather Objective/Steps/Verification content directly in the
  conversation (no Clarify/Survey/Converge phases), then call
  `Skill("write-plan")` with no `target_phase` (leave `pipeline_phase` unset -
  do not hand-set `checked`). Once written, the parent session (the Human, or
  the agent acting under an active `send it` grant - never a subagent) runs
  `execute-plan` directly against the PLAN and does not invoke
  `plan-pipeline` - this is what "no audit loop" means mechanically.
  `execute-plan` itself still writes `last_executor_outcome` and Executor
  Notes, and syncs any `closes_thread`, `advances_thread` or
  `parent_plan_of_plans` linkage into `ROADMAP.md` - both run automatically
  because they are part of the `execute-plan` skill, not the orchestrator, so
  nothing extra is needed for either.

  Two things are orchestrator-only, with no substitute once no orchestrator
  runs. The parent session performs both by hand before retiring. First, set
  `status` to its terminal value (`done`, or `partially-complete` if steps
  were deferred) - `execute-plan`'s frontmatter forbidlist bars the executor
  from writing `status`. Second, if the PLAN carries `linked_inputs`, walk the
  same three-gate check `plan-pipeline`'s complete-phase retire dispatch runs
  (lifecycle_mode, integration_status, all-feeds-retired) and dispose of each
  input accordingly, rather than leaving it stranded at `pending`. If this
  PLAN's own `files_touched` matches a skill/command/CLAUDE.md/
  ARCHITECTURE.md path, also run `Skill("maintain-project-docs")` by hand
  before retiring - the doc-drift check is orchestrator-only, and
  `execute-plan` never runs the check itself. Then call `Skill("retire")`.

  If a later `plan-pipeline` invocation is ever pointed at this PLAN, the
  ad-hoc default reads its unset `pipeline_phase` as `drafted` and it enters
  the audit loop honestly at that point.

- **`audit it`:** gather the same content, call `Skill("write-plan")` with
  `target_phase: drafted`, then invoke `Skill("plan-pipeline")` against the
  written PLAN. The orchestrator's existing `drafted` audit loop, `checked`
  dispatch, and `outcome-verifying`/`complete` phases run unchanged from here -
  no new orchestrator behaviour, just the entry point.

## Rules

1. Present the menu. Do not pick silently.
2. Recommend one rung, and give the reason in one sentence.
3. Escalate on your own judgement. Never drop a rung silently.
4. If you recommend a rung below what the three questions indicate, say which
   question you are discounting and why.
5. Record the chosen rung in the PLAN's Context, or in the reply when no PLAN is
   written.
6. The rung binds the run. Reopen it only when the work turns out to be different
   from what was assessed, and say so when you do.

## This is not the autonomy grant

`send it` caps how much autonomy the agent takes. This caps how much ceremony the
work carries. They move independently. A high `send it` with a low rung is the
common case. Grammar for the grant:
[dispatch-authorisation.md](dispatch-authorisation.md).

## Presenting the menu

Follow [questioning-contract.md](questioning-contract.md). The menu is a choice
surface, so it carries each rung's consequence, the recommendation and its reason,
and a way to stop. `just do it` is the do-nothing-more option and is always on the
menu.
