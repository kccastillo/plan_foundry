---
title: Plan-of-Plans Authoring
description: Authoring discipline for a plan-of-plans - the sketch-first placeholder convention and parent-update rules.
created: 2026-08-17
---

# Plan-of-plans authoring: sketch-first convention

When authoring a plan-of-plans (a PLAN that coordinates multiple child PLANs across linked threads, files, or subsystems):

1. **When to use a plan-of-plans.** A plan-of-plans is appropriate when work spans multiple independent threads or coordinated effort across files/subsystems - for example, harness extraction or a multi-phase infrastructure refactor. If work fits naturally into a single PLAN with sequential steps, use that instead.

2. **The placeholder convention.** You do not need to author all child PLANs before drafting the parent. Instead, declare child PLANs in the parent's `triggers_plans: []` field using placeholder syntax: `"[placeholder] <slug>"`, where `<slug>` is a short descriptive name for the child work. For example: `triggers_plans: ["[placeholder] harness-extraction", "[placeholder] update-harness-templates"]`. This lets you sketch the coordinated effort's shape while child details are still being shaped.

3. **Transition to real IDs.** As each child PLAN is drafted, replace the corresponding placeholder entry with the actual PLAN filename (e.g. `"PLAN-AB0_harness-extraction.md"`). This replacement should happen in the same commit that drafts the child, keeping the parent's tracking in sync.

4. **Parent update discipline.** When a child PLAN is drafted, update both the parent's `triggers_plans` array and any child-tracking table in the parent's Objective or Context section (if used). Do both edits in a single commit to maintain clarity.
