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
  - Any LOG updates needed

Step 2: Check if current month LOG exists.
  Path: Workbench/{YYYYMM}010000_LOG_{YYYYMM}.md
  If it does not exist: create it from templates/log-template.md, then perform rollover (Step 2a) before proceeding.

Step 2a: Rollover from prior month (only when creating a new LOG).
  a. Find the most recent prior LOG in Workbench/ (largest YYYYMM filename < current month). If none exists, skip rollover.
  b. Identify the PLANs to roll over. Read `Workbench/.index.json` (regenerate it first via `update-workbench-index` if stale) and select every PLAN whose `log_month` equals the prior month and whose `status` is NOT one of {done, cancelled, closed}. **Do not read the prior LOG's Status Table** - slim LOGs (`log_month >= 202606`, per AB9 D3) have none, and INDEX is the canonical projection of PLAN status. For each selected PLAN:
     - Add a row to the NEW LOG's "Rollover from Prior Month" table:
       | [plan filename] | [created_month from plan frontmatter] | [new rollover_count] | [one-line reason - e.g. "not started", "in progress", "blocked on X"] |
     - Open the plan file and update its frontmatter:
       * log_month = current YYYYMM  (this field always moves to the active LOG)
       * rollover_count = previous rollover_count + 1
       * created_month = UNCHANGED (immutable - never edit on rollover)
  c. Do NOT move or rename plan files. Plans stay at their original path; only the frontmatter and LOG references update.
  d. Close out the prior LOG: set its frontmatter status to "closed" and last_updated to today. Do not edit any table it carries - a fat LOG (`log_month <= 202605`) reflects end-of-month state and is a frozen historical record.
  e. Curate lessons forward. Invoke `Skill("lessons-learned", mode=curate-forward, prior_log_path=<prior LOG path>, new_log_path=<new LOG path>)` to populate the new LOG's `## Lessons Learned` section from the prior LOG via judgement-based triage. Do not copy lessons forward verbatim - that is the failure mode the skill exists to prevent.

Step 3: Write the PLAN file.
  Use templates/plan-template.md as structure.
  Fill all frontmatter fields from Sonnet's content exactly.
  Set created_month = current YYYYMM (this field is immutable - never change it on rollover).
  Set log_month = current YYYYMM (this changes on rollover).

  Special case - recurring PLAN (slug starts with RECUR-):
  - Check if a PLAN file with this RECUR- slug already exists.
  - If it exists: do NOT create a new file. Instead append a new row to the ## History table.
  - If it does not exist: create the file normally, then add a blank ## History table at the bottom.

Step 4: Update the monthly LOG.
  **There is no Status Table row to add.** The Status Table was removed from the
  monthly LOG on 2026-06-01 (AB9 D3) and `Workbench/INDEX.md` is now the sole
  canonical answer to "what is the status of PLAN X?", projected from PLAN
  frontmatter. Writing the PLAN file with correct frontmatter *is* the status
  update. Do not create a Status Table in a slim LOG, and do not backfill rows
  into a historical fat one.

  If this is a recurring task: add or update a row in the Recurring Task Tracker,
  which the slim LOG does still carry:
  | [task name] | [RECUR- slug] | [cadence] | [last done or -] | [next due] | [ACTIVE if applicable] |

  Then regenerate the projection: `Skill("update-workbench-index")`.

Step 5: Report to the Human:
  ```
  Written: [filename]
  LOG updated: [LOG filename]
  Ready for: [next step - e.g. 'hand to orchestrator for execution']
  ```