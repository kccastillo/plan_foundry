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
  - Set `lifecycle_mode: input` by default. Use `lifecycle_mode: reference` only when the input is durable knowledge that should NOT be auto-retired on consuming-PLAN retire (e.g. event-sourcing research, capacity thresholds doc). Reference-mode files still get `integration_status: integrated` flipped on consumption; the difference is auto-retire exemption. Reference-mode inputs SHOULD carry a `review_by` ISO date (e.g. `review_by: "2027-01-01"`) so they are not immortal-by-default - the `reference_review_due` INDEX alert fires on/after that date to prompt periodic review. Leave `review_by: ""` if no EOL review is planned (the alert will not fire).
  - Set `feeds_plan` to the target PLAN filename (or "" if none)
  - Delete any template section the input does not use
  - The agent supplies the datetime in the filename at write time, colon-free. There is no allocator call. Writes emit UTF-8; reads use `encoding='utf-8', errors='replace'`.

Step 3: Unblock the target PLAN (if applicable).
  If `feeds_plan` is set:
    a. Open that PLAN file.
    b. Check if this input resolves the block:
       - PLAN's `status: blocked`, AND
       - the input's topic matches the PLAN's `blocked_by` reason (semantic match - the intent was already confirmed when `feeds_plan` was set to point at this PLAN).
    c. If resolved:
       - Flip `status: blocked` -> `status: ready`
       - Clear `blocked_by: ""`
       - Add the new input's filename to `linked_inputs` if not already present
       - If `assigned_to: human` was set because of this block, flip back to `assigned_to: ""`
    d. If NOT resolved (PLAN blocked on a different input, or status is not blocked):
       - Still add the filename to `linked_inputs`
       - Do not change `status` or `blocked_by`
       - Note this in the report to the Human

Step 4: Report to the Human:
  ```
  Written:     {input filename}
  Unblocked:   {PLAN filename} -> status: ready   (or "no PLAN unblocked")
  Ready for:   {next step - e.g. "integration of input and re-run of the PLAN"}
  ```

## Grandfathered files

A file already on disk under `ADVICE-*` or `RESEARCH-*` is a valid input. Read it, reference it and retire it as normal. Its target PLAN may sit in `advises_plan` rather than `feeds_plan`, so read both fields on those files. Never write either field or either filename form on a new input.
