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
