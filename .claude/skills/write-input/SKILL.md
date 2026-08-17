---
name: write-input
description: 'Input transcription skill. Writes INPUT files (findings, data drops, strategic notes) into the Workbench directory, and clears any PLAN''s blocked state that was waiting on that input. Trigger phrases: "write this input", "create input file", "record this input", "write this research", "paste advice", "write this advice".'
---

**Naming:** an input is written as `INPUT-YYYYMMDD-hhmm-<slug>.md`. The agent supplies the datetime at write time, colon-free. An input carries no numeric ID, and this skill makes no allocator call.

### One kind, and the grandfathered forms

An input is one artefact kind. The `ADVICE` and `RESEARCH` kinds were collapsed into the input kind on 2026-08-03 because no skill ever branched on the difference.

Files already on disk under `ADVICE-*` or `RESEARCH-*`, in either the `TYPE-NNN_slug.md` or the `TYPE-YYYYMMDD-hhmm-<slug>.md` grammar, remain valid inputs. Read them, reference them in `linked_inputs`, and retire them normally. Do not bulk-rename those files, and do not write a new file under either name. Reads use `encoding='utf-8', errors='replace'`.

<essential_principles>
Transcribe input content accurately. Do not interpret, summarise, or modify content.
An input is a context artefact that unblocks PLANs. No skill ever acted on the old split between a data drop and a strategic note, so the file does not record that split.
Always check the input's `feeds_plan` frontmatter. If that PLAN is `blocked` waiting on this input, clear the blocked state.
Report back the filename written and any PLANs unblocked.
</essential_principles>

<preconditions>
Before writing, confirm:
- Content, target filename, and target plan (if any) have been provided
</preconditions>

**Input writing procedure:** See [workflows/write-input.md](workflows/write-input.md)

<constraints>
- Never modify input content - transcribe the content exactly as provided
- Never flip a PLAN's status unless the input clearly resolves that PLAN's blocked_by reason - if in doubt, leave the status unchanged and flag the doubt to the human
- Never clear `blocked_by` without also flipping `status: blocked` -> `ready` in the same edit
- Never write to Wiki/ - that directory is the Wiki skills' domain
- An input file's `integration_status` stays `pending` until the input is integrated into a PLAN, and this skill never marks integration complete
</constraints>

<success_criteria>
- The input file exists at the correct path with valid frontmatter
- If the input resolved a PLAN block: that PLAN's `status` is `ready`, `blocked_by` is empty, and the input filename appears in that PLAN's `linked_inputs`
- The human has received the report, including which PLAN (if any) was unblocked
</success_criteria>
