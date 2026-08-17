# Write Input File to Workbench

## Process

Step 1: Receive input content:
  - Content (full body)
  - Target filename, as `INPUT-YYYYMMDD-hhmm-<slug>.md`
  - Target plan filename (if this input feeds a specific plan)
  - Frontmatter values: question_asked, from

Step 2: Write the input file.
  - Use templates/input-template.md
  - Fill all frontmatter exactly as provided
  - Set `integration_status: pending`
  - Set `lifecycle_mode: input` by default. Use `lifecycle_mode: reference` only when the input is durable knowledge that should NOT be auto-retired on consuming-PLAN retire (e.g. event-sourcing research, capacity thresholds doc). Reference-mode files still get `integration_status: integrated` flipped on consumption, and the only difference is the auto-retire exemption. Reference-mode inputs should carry a `review_by` ISO date (e.g. `review_by: "2027-01-01"`) so that reference mode is not immortal by default. No check reads that date and nothing fires on it, so it is a marker for whoever next reviews the Workbench rather than an automated trigger. Leave `review_by: ""` when no end-of-life review is planned.
  - Set `feeds_plan` to the target PLAN filename (or "" if none)
  - Delete any template section the input does not use
  - The agent supplies the datetime in the filename at write time, colon-free, and sets `created` to that same date in `YYYY-MM-DD` form. This skill makes no allocator call. Writes emit UTF-8, and reads use `encoding='utf-8', errors='replace'`.

Step 3: Unblock the target PLAN (if applicable).
  If `feeds_plan` is set:
    a. Open that PLAN file.
    b. Check if this input resolves the block:
       - PLAN's `status: blocked`, AND
       - the input's topic matches the PLAN's `blocked_by` reason (semantic match - the author already confirmed the intent when setting `feeds_plan` to point at this PLAN).
    c. If resolved:
       - Flip `status: blocked` -> `status: ready`
       - Clear `blocked_by: ""`
       - Add the new input's filename to `linked_inputs` if not already present
       - If `assigned_to: human` was set because of this block, flip back to `assigned_to: ""`
    d. If NOT resolved (PLAN blocked on a different input, or status is not blocked):
       - Still add the filename to `linked_inputs`
       - Do not change `status` or `blocked_by`
       - Note the unresolved block in the report to the Human

Step 4: Report to the Human:
  ```
  Written:     {input filename}
  Unblocked:   {PLAN filename} -> status: ready   (or "no PLAN unblocked")
  Ready for:   {next step - e.g. "integration of input and re-run of the PLAN"}
  ```

## Grandfathered files

A file already on disk under `ADVICE-*` or `RESEARCH-*` is a valid input. Read the file, reference the file, and retire the file as normal. The target PLAN may appear in `advises_plan` rather than `feeds_plan`, so read both fields on those files. Never write either field or either filename form on a new input.
