# Write Plan File to Workbench

## Process

Step 0: Substrate-verification preflight.
  Before any Write or Edit call that emits SQL DDL/queries, ORM operations, Python imports from existing modules, or string-literal values of constrained-type (enum) fields:

  a. **Declared substrate (preferred path):** If the target PLAN's frontmatter `substrate_files: [...]` is non-empty, the writer MUST `Read` each listed path. This `Read` must appear in the writer's reasoning trace BEFORE any Write/Edit that emits substrate-grammar constructs. There is no exception - authoring against substrate not yet read is a violation.

  b. **Heuristic detection (fallback when `substrate_files` is empty or absent):** Scan the brief's Steps section for substrate signals:
     - SQL keywords: `CREATE TABLE`, `INSERT INTO`, `SELECT ... FROM`, `ALTER TABLE`, `column_name.`
     - Python imports from existing modules: `from <module> import <symbol>` where `<module>` is not a stdlib module
     - String-literal values adjacent to enum-typed variables or `Enum` class references (e.g. `kind="..."`, `status="..."`, `EventKind.<value>`)
     - Third-party API attribute access (any `obj.<attr>` where the module is an installed package)

     If any signals are found: surface a "detected substrate" list to the Human for confirmation before authoring. Example message: "Detected substrate signals in Steps: [list of signals]. Please confirm which files I should Read as substrate ground truth, or acknowledge that no substrate verification is needed."

     If no signals are found: no preflight required; proceed to Step 1.

  c. **Violation outcome:** If plan-writer emits a Write/Edit with substrate-grammar constructs but has not Read the relevant substrate file(s) in its trace -> set `outcome: exception` with `diagnostics.reason = "substrate-verification preflight violation: <entity-name> referenced without reading <suspected-substrate>"`.

Step 1: Receive plan content:
  - Plan content (frontmatter values + body sections)
  - Target filename (Sonnet generates this)

Step 2: Write the PLAN file.
  Use templates/plan-template.md as structure.
  Fill all frontmatter fields from Sonnet's content exactly.
  Set created_month = current YYYYMM (this field is immutable, set once and never changed).
  Set log_month = current YYYYMM.

  Set bundle_version_at_creation (PLAN-AH8, provenance only - not a
  guarantee-2 mechanism; guarantee 2 is delivered by sync's pre-flight, not
  by this stamp). Call `bundle_copy.bundle_version_string(target_claude)`
  (in `.claude/skills/_shared/bundle_copy.py`, `target_claude` = the host
  project's `.claude/` directory) and write its return value into the
  field. Leave the field empty ("") when the call returns "" (no version
  pin exists yet, e.g. a bootstrap PLAN authored before `/init-plan-foundry`
  has run). Additive: existing PLANs written before this field existed have
  no such key and remain valid; do not backfill them.

  Special case - recurring PLAN (slug starts with RECUR-):
  - Check if a PLAN file with this RECUR- slug already exists.
  - If it exists: do NOT create a new file. Instead append a new row to the ## History table.
  - If it does not exist: create the file normally, then add a blank ## History table at the bottom.

Step 3: Report to the Human:
  ```
  Written: [filename]
  Ready for: [next step - e.g. 'hand to orchestrator for execution']
  ```