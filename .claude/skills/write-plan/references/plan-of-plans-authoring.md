---
title: Plan-of-Plans Authoring
description: Authoring discipline for a plan-of-plans - the sketch-first placeholder convention and parent-update rules.
created: 2026-08-17
---

# Plan-of-plans authoring: sketch-first convention

When authoring a plan-of-plans (a PLAN that coordinates multiple child PLANs across linked threads, files, or subsystems):

1. **When to use a plan-of-plans.** A plan-of-plans applies when work spans multiple independent threads or coordinated effort across files and subsystems - for example, harness extraction or a multi-phase infrastructure refactor. If the work fits naturally into a single PLAN with sequential steps, write a single PLAN instead.

2. **The placeholder convention.** You do not need to author all child PLANs before drafting the parent. Instead, declare child PLANs in the parent's `triggers_plans: []` field using placeholder syntax: `"[placeholder] <slug>"`, where `<slug>` is a short descriptive name for the child work. For example: `triggers_plans: ["[placeholder] harness-extraction", "[placeholder] update-harness-templates"]`. Declaring placeholders records the coordinated effort's shape before the child details are settled.

3. **Transition to real IDs.** As each child PLAN is drafted, replace the corresponding placeholder entry with the actual PLAN filename (e.g. `"PLAN-AB0_harness-extraction.md"`). Make that replacement in the same commit that drafts the child, so the parent's tracking stays in step with the children.

4. **Parent update discipline.** When a child PLAN is drafted, update both the parent's `triggers_plans` array and any child-tracking table in the parent's Objective or Context section (if used). Make both edits in a single commit.

5. **What a placeholder does not do.** A placeholder is an authoring-time marker and nothing reads it. `plan-pipeline`'s children gate, defined in `.claude/skills/plan-pipeline/workflows/dispatch.md` under Step 3, resolves each `triggers_plans` entry to a child PLAN file and reads that file's `status`, blocking the parent while any child is non-terminal. A `"[placeholder] <slug>"` entry names no file, so the gate has no `status` to read for it and the entry cannot hold the parent back on its own. Replace every placeholder with a real child filename before relying on the gate to sequence the parent behind its children.
