---
name: write-input
description: 'Input transcription skill. Writes INPUT files (findings, data drops, strategic notes) into the Workbench directory, and clears any PLAN''s blocked state that was waiting on that input. Trigger phrases: "write this input", "create input file", "record this input", "write this research", "paste advice", "write this advice".'
---

**Naming:** an input is written as `INPUT-YYYYMMDD-hhmm-<slug>.md`. The agent supplies the datetime at write time, colon-free. There is no numeric ID and no allocator call.

### One kind, and the grandfathered forms

An input is one artefact kind. The `ADVICE` and `RESEARCH` kinds were collapsed into it on 2026-08-03 (PLAN-AJ3) because no skill ever branched on the difference.

Files already on disk under `ADVICE-*` or `RESEARCH-*`, in either the `TYPE-NNN_slug.md` or the `TYPE-YYYYMMDD-hhmm-<slug>.md` grammar, remain valid inputs. Read them, reference them in `linked_inputs`, and retire them normally. Do not bulk-rename them. Do not write a new file under either name. Reads use `encoding='utf-8', errors='replace'`.

<essential_principles>
Transcribe input content accurately. Do not interpret, summarise, or modify content.
An input is a context artefact that unblocks PLANs. The old split between a data drop and a strategic note was never acted on by any skill, so it is not recorded in the file.
Always check the input's `feeds_plan` frontmatter. If that PLAN is `blocked` waiting on this input, clear the blocked state.
Report back: filename written, PLAN(s) unblocked if any.
</essential_principles>

<preconditions>
Before writing, confirm:
- Content, target filename, and target plan (if any) have been provided
</preconditions>

**Input writing procedure:** See [workflows/write-input.md](workflows/write-input.md)

<constraints>
- Never modify input content - transcribe exactly as provided
- Never flip a PLAN's status unless the input clearly resolves its blocked_by reason - if in doubt, leave status unchanged and flag to the human
- Never clear `blocked_by` without also flipping `status: blocked` -> `ready` in the same edit
- Never write to Wiki/ - that is the Wiki skills' domain
- An input file's `integration_status` stays `pending` until it is integrated into a PLAN; this skill does not mark integration complete
</constraints>

<success_criteria>
- Input file exists at the correct path with valid frontmatter
- If the input resolved a PLAN block: that PLAN's `status` is `ready`, `blocked_by` is empty, and the input filename appears in its `linked_inputs`
- The human has been given the report including which PLAN (if any) was unblocked
</success_criteria>
