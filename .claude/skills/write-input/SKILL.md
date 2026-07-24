---
name: write-input
description: Input transcription skill. Writes RESEARCH (data drops) and ADVICE (strategic notes) files into the Workbench directory, updates the monthly LOG's Context Inputs table, and clears any PLAN's blocked state that was waiting on this input. Trigger phrases: "write this research", "create research file", "write this advice", "paste advice", "record this input".
---

**Naming:** RESEARCH and ADVICE files use the `TYPE-NNN_slug.md` format. To compute the next ID, run:
- `python .claude/skills/write-plan/scripts/next_id.py ADVICE`
- `python .claude/skills/write-plan/scripts/next_id.py RESEARCH`

Construct the filename as `ADVICE-{NNN}_{slug}.md` or `RESEARCH-{NNN}_{slug}.md`. Never hand-count existing files — always use `scripts/next_id.py`.

### Grammar (forward-only, per PLAN-AF6 D1/D2)

NEW inputs MAY use the unified datetime grammar `TYPE-YYYYMMDD-hhmm-<slug>.md` (datetime agent-supplied at write time, colon-free, no numeric ID — e.g. `ADVICE-20260712-1430-restructure-mandate.md`). The legacy `TYPE-NNN_slug.md` grammar remains valid; `next_id.py` still serves the numeric path. Do NOT bulk-rename existing inputs. Both grammars coexist during transition. Reads use `encoding='utf-8', errors='replace'`.

<essential_principles>
Transcribe input content accurately. Do not interpret, summarise, or modify content.
RESEARCH and ADVICE are the same shape: context inputs that unblock PLANs. One skill handles both; the Type field distinguishes them.
Always check the input's `feeds_plan` (RESEARCH) or `advises_plan` (ADVICE) frontmatter — if that PLAN is `blocked` waiting on this input, clear the blocked state.
Always update the monthly LOG's Context Inputs table after writing an input file.
Report back: filename written, LOG updated, PLAN(s) unblocked if any.
ID assignment: call `scripts/next_id.py ADVICE` or `scripts/next_id.py RESEARCH` to get the next sequential number. Never reuse an ID.
</essential_principles>

<preconditions>
Before writing, confirm:
- Type is RESEARCH or ADVICE (exact uppercase)
- Content, target filename, and target plan (if any) have been provided
- Current month LOG exists (if not, create it via write-plan's Step 2 first)
</preconditions>

**Input writing procedure:** See [workflows/write-input.md](workflows/write-input.md)

<constraints>
- Never modify input content — transcribe exactly as provided
- Never flip a PLAN's status unless the input clearly resolves its blocked_by reason — if in doubt, leave status unchanged and flag to the human
- Never clear `blocked_by` without also flipping `status: blocked` → `ready` in the same edit
- Never write to Wiki/ — that is the Wiki skills' domain
- An input file's `integration_status` stays `pending` until it is integrated into a PLAN; this skill does not mark integration complete
</constraints>

<success_criteria>
- Input file exists at the correct path with valid frontmatter
- Monthly LOG Context Inputs table has the new row
- If the input resolved a PLAN block: that PLAN's `status` is `ready`, `blocked_by` is empty, and the input filename appears in its `linked_inputs`
- The human has been given the report including which PLAN (if any) was unblocked
</success_criteria>