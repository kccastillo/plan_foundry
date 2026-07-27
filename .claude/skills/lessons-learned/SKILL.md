---
name: lessons-learned
description: 'Maintain a lean Lessons Learned section in the monthly LOG. Two modes - `jot` appends a single tagged bullet for a lesson learned now; `curate-forward` is invoked by write-plan at month rollover and triages prior-month lessons (forward what is still architecturally load-bearing, drop episode-specific or already-codified). Trigger phrases: "jot a lesson", "save this lesson", "log this learning", "lessons learned", "curate lessons forward".'
---

<essential_principles>

**Lean.** One bullet per lesson. No prose paragraphs, no nested structure, no quoting context that won't matter next month.

**Curation, not accumulation.** At rollover, the prior month's lessons are triaged - not all of them forward. The Lessons Learned section must never metastasise into a memory cancer. If unsure whether a lesson still applies, drop it; a lesson worth keeping resurfaces as a fresh observation.

**Source-tagged.** Every lesson carries the PLAN ID (or short context slug) where it was learned. Future curators use this to check whether the lesson has been codified into a permanent doc.

**Codification beats memory.** If a lesson has been captured in a skill or CLAUDE.md, it does NOT forward - the doc is now authoritative. One-month grace cross-reference is allowed; longer is hoarding.

**Wire format.** End the response with a literal `<pipeline-result>` JSON code fence per parent decision 23. No XML payload, no HTML escaping.

</essential_principles>

<lesson_format>

Each lesson is a single markdown bullet under the LOG's `## Lessons Learned` heading, in this exact shape:

```
- [<category>] (src: <source>; recurrences: <N>) - Lesson text in one or two lines.
```

**Category** - exactly one of:
- `architectural` - design truths about how the harness/skills compose
- `process` - how work flows; what catches problems early
- `user-preference` - the human's recurring preferences (only those that apply across PLANs)
- `convention` - agreed naming, format, or wire-protocol rules

**Source** - PLAN ID (e.g. `202605020000`). If learned outside a PLAN context, use a short slug (e.g. `f14-closeout`, `dogfood-1440`). When a lesson is forwarded for the second-or-later month, append `-> <YYYYMM>` to the source tag so multi-month survivors are visible: `(src: 202605020000 -> 202606; recurrences: 1)`.

**Recurrences** - non-negative integer; defaults to `1` on first jot. Counts how many times the same lesson has been independently observed. Bumped via `jot` mode `increment` when the caller recognises the new observation as the same pattern as an existing lesson (same source, same category). Stable across month rollover - `curate-forward` preserves the counter unchanged. Two thresholds drive curation:

- **Promotion candidate:** `recurrences >= 3` - the lesson has been observed enough times that it warrants codification into a permanent doc (skill SKILL.md, CLAUDE.md, or ARCHITECTURE.md's invariants register). `curate-forward` surfaces these in the rollover report; `maintain-claude-md` consumes the same signal in its monthly audit and surfaces it as a "consider codifying" finding.
- **Eviction candidate:** `recurrences == 1` AND the source-tag arrow chain shows 2+ months of forwards without re-observation - the lesson was a one-shot that hasn't recurred. `curate-forward` surfaces these for drop consideration.

**Legacy bullets without the `recurrences:` field** are tolerated and treated as `recurrences: 1` by parsers - backwards compatible.

</lesson_format>

<intake>

What would you like to do?

1. Jot a lesson into the current month's LOG
2. Curate prior-month lessons forward (rollover)

**Wait for response before proceeding.** When invoked by another skill (e.g. write-plan calling at rollover), the caller supplies `mode` directly and intake is skipped.

</intake>

<routing>

| Response | Mode | Workflow |
|---|---|---|
| 1, "jot", "save", "log this" | jot | `workflows/jot.md` |
| 2, "curate", "rollover", "forward" | curate-forward | `workflows/curate-forward.md` |
| `mode=jot` (programmatic) | jot | `workflows/jot.md` |
| `mode=curate-forward` (programmatic) | curate-forward | `workflows/curate-forward.md` |

**After reading the workflow, follow it exactly.**

</routing>

<integration>

**Called by `write-plan` at month rollover.** Step 2a of `write-plan/workflows/write-plan.md` must include a sub-step:

> 2a.e - After the rollover Status Table rows are written, invoke `Skill("lessons-learned", mode=curate-forward, prior_log_path=..., new_log_path=...)` to populate the new LOG's `## Lessons Learned` section.

**LOG template contract.** `write-plan/templates/log-template.md` must include a `## Lessons Learned` section (placed immediately before `## Month Summary`). When the section is empty, it carries the placeholder line `_(none carried forward)_`.

**Direct user invocation.**
- `Skill("lessons-learned", mode=jot, lesson_text="...", category=architectural, source=202605020000)`
- `Skill("lessons-learned", mode=curate-forward, prior_log_path="Workbench/202604010000_LOG_202604.md", new_log_path="Workbench/202605010000_LOG_202605.md")`

</integration>

<workflows_index>

| Workflow | Purpose |
|---|---|
| `workflows/jot.md` | Append one tagged bullet to the current LOG's Lessons Learned section |
| `workflows/curate-forward.md` | Triage prior-month lessons; forward survivors into the new LOG |

</workflows_index>

<success_criteria>

A correctly-built Lessons Learned section:
- Contains only single-line bullets in the prescribed format
- Has every bullet tagged with category and source
- Is materially smaller than the prior month's after curate-forward (unless every prior lesson genuinely still applies)
- Never accumulates lessons that have been codified into permanent docs beyond the one-month grace cross-reference window
- Carries a placeholder line when empty rather than removing the heading

</success_criteria>
