---
name: write-plan
description: 'Plan transcription skill. Writes PLAN files (and updates monthly LOG, rollover files) at any point in a plan''s lifecycle - including incremental in-flight writes during ideation, draft updates, and final transcription. Overwrites of existing PLAN files with revised content are permitted. Trigger phrases: "write this plan", "create plan file", "update the plan", "update the log", "write plan file", "create the log".'
---

**Plan file conventions:** See [references/plan-conventions.md](references/plan-conventions.md) - canonical source for naming, status lifecycle, and input linkage.

**Naming:** See [references/naming-convention.md](references/naming-convention.md) - `TYPE-NNN_slug.md` format. To compute the next ID for a type, run: `python .claude/skills/write-plan/scripts/next_id.py PLAN` (or ADVICE / RESEARCH). LOG files retain the timestamp convention.

<essential_principles>
Transcribe plan content accurately. Do not invent, summarise, or modify content.
Always check if the current month LOG exists before writing any PLAN file. Create it first if missing.
After writing any PLAN file, regenerate the INDEX projection. The monthly LOG has carried no Status Table since 2026-06-01 (AB9 D3) - correct PLAN frontmatter is the status update.
For recurring PLAN files: append to the existing file's History table - do not create a new file.
Report back: filename written, LOG updated, ready for next step.
Overwriting an existing PLAN file with updated content is permitted during the drafting/ideation phase - preserve frontmatter `created`, `created_month`, and `created_by`; refresh body content and any `last_updated`-style fields.
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23. No XML payload, no HTML escaping.
ID assignment: call `scripts/next_id.py PLAN` to get the next sequential number; construct filename as `PLAN-{NNN}_{slug}.md`. For RECUR- plans: `PLAN-{NNN}_RECUR-{slug}.md`. Never reuse an ID. Never hand-count existing files - always use the script.
</essential_principles>

**Plan writing procedure:** See [workflows/write-plan.md](workflows/write-plan.md)

<inputs>
- `plan_content: string` - the body content to write (Objective, Context, Steps, Verification, etc.).
- `target_filename: string` - the PLAN file basename or path under `Workbench/`. Use `TYPE-NNN_slug.md` format; call `scripts/next_id.py` to get NNN.
- `mode: enum[create, update]` - whether the file is new or being overwritten in-flight.
- `target_phase: string (optional)` - when supplied, plan-writer writes the supplied `pipeline_phase` frontmatter value in the same file write as the body content, making content-write + phase-flip atomic. When omitted, `pipeline_phase` is left untouched.
</inputs>

<constraints>
- Never modify plan content - transcribe exactly as specified
- Never create a new RECUR- PLAN file if one already exists for that slug
- Always create the monthly LOG before writing the first PLAN of a month
- When creating a new monthly LOG, always run rollover (Step 2a) against the prior month's LOG before writing any new PLAN
- Never add a Status Table to a monthly LOG, and never backfill rows into a historical one. INDEX is the canonical status surface (AB9 D3); regenerate it after every PLAN file write
- The created_month field is set once and never changed - rollover updates log_month and rollover_count only
- Never move or rename PLAN files on rollover
- Rollover selects PLANs from `Workbench/.index.json` by `log_month` and `status`, never by reading a prior LOG's Status Table
</constraints>

<success_criteria>
- PLAN file exists at the correct path with valid frontmatter
- `Workbench/INDEX.md` lists the new PLAN with its frontmatter status
- Recurring tasks appear in Recurring Task Tracker
- RECUR- files have a ## History table
- On month rollover: prior LOG is closed; the new LOG's Rollover table lists all incomplete plans; each rolled plan's frontmatter has log_month updated and rollover_count incremented
- The human has been given the PLAN filename for next-step handoff
- No Status Table was created or modified in any monthly LOG.
</success_criteria>
