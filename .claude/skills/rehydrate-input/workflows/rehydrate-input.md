# rehydrate-input workflow

Idempotent five-step procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Step 1: Read and validate the input file

Read the file at `input_path`.
- **If absent / unreadable:** FAIL. Surface `<exception>input not found at <path></exception>`. Return.
- **If frontmatter is missing:** FAIL. Surface diagnostic and return.

**Mode detection (AC2c D1c).** Call `detect_mode(frontmatter)` from `lib/mode_detect.py`:
- If `detect_mode` raises `ValueError` (ambiguous or unrecognised frontmatter): FAIL. Surface the error diagnostic and return.
- If mode is `"asset"`: route to **Step 1.a-asset** below.
- If mode is `"input"`: continue with input-mode validation below.

**Input mode validation (existing path):**
- **If missing `integration_status` field:** FAIL. Surface diagnostic and return — caller should fix the input (or it's not a write-input-authored file).
- **Legacy normalisation:** if `integration_status: open` is encountered (predates the `pending`/`integrated` convention), treat as equivalent to `pending` for the rest of the procedure. Log one diagnostic: "normalised legacy `integration_status: open` → `pending` for processing." Do not mutate the file at this step — Step 3 will rewrite the field via the confirm-and-flip path.
- **If `integration_status: integrated` already:** SKIPPED for the flip; jump to Step 4 (late-auto-retire) — the input may still be eligible for retire if it was integrated before all consuming PLANs were retired.
- **Otherwise:** PASS. Capture `lifecycle_mode` (default `input` if absent), `feeds_plan` / `advises_plan`, and the body content.

### Step 1.a-asset (asset mode)

Entered when `detect_mode(frontmatter) == "asset"`. Replaces Steps 2–5 for asset-mode invocations; the original input-mode Steps 2–5 are NOT executed.

**A1. Validate asset frontmatter.**

Required fields: `asset_id`, `kind` (must be one of `reference`, `helper`), `last_consulted` (may be empty string), `consulted_by` (list). If any required field is missing or `kind` has an unrecognised value: surface diagnostic and return `outcome: exception`.

Assert `consuming_plan` argument was supplied; if not, surface diagnostic ("asset mode requires consuming_plan; supply via skill argument") and return `outcome: exception`.

**A2. Surface asset content** in this shape:

```
== rehydrating asset ==
Path: <input_path>
Kind: <reference | helper>
asset_id: <id>
topic_tags: <list>
last_consulted: <date or "(never)">
consulted_by: <list> (last 20)

== content ==
<frontmatter block>
<body -- first H2 section per heading, if .md; or module docstring if .py>
```

**A3. Prompt for consumption confirmation.**

Ask: "Mark consulted by <consuming_plan>? [y/N]"

- **On confirmation (y):** PASS -- proceed to A4.
- **On deferral (N):** SKIPPED -- emit pipeline-result with `outcome: success`, `outcome_subtype: deferred`; no file mutation; return.

**A4. Write per-asset memory file FIRST (S4 atomicity ordering).**

Resolve memory directory: `os.environ.get("CLAUDE_PROJECT_MEMORY_DIR", os.path.expanduser("~/.claude/projects/D--projects-plan-foundry-dev/memory"))`.

- **If memory dir is reachable:** write `reference_<asset_id>.md` at that path containing:

  ```
  # <asset title> (<asset_id>)
  Path: <asset path relative to repo root>
  Kind: <reference | helper>
  Topic tags: <comma-joined tags>
  Last consulted: <ISO date>
  Consulted by (last 20): <comma-joined PLAN-ids>

  ---

  Description: <one-sentence description from frontmatter>
  ```

  Idempotent overwrite on re-consumption (replaces with fresh timestamp + updated `consulted_by`).

- **If memory dir is unreachable (does not exist):** surface one-line warning -- "memory dir <path> unreachable -- skipping memory write per S2; frontmatter stamp committed regardless". Set `memory_write_skipped: true` in the pipeline-result payload. Continue to A5. (This is the S2 degraded path -- normal during CI runs.)

- **If memory-file write raises (IOError, permission error, etc.):** HALT before A5. The asset frontmatter is left untouched (S4 clean-retry property). Return `outcome: exception` with `diagnostics_summary` describing the IOError. Do NOT proceed to A5.

**A5. Stamp asset frontmatter.**

Update `last_consulted` to today's ISO date (YYYY-MM-DD). Append `consuming_plan` to `consulted_by` with idempotency rule: skip the append if `consuming_plan` is already the most recent (last) entry of the list -- otherwise append. If `consulted_by` length > 20 after append, drop the OLDEST entry (index 0, FIFO per D6c). Set `consulted_by_evicted_oldest: true` in the pipeline-result payload if eviction occurred. Write back via in-place YAML edit (frontmatter only; body unchanged).

**A6. Commit ownership note.**

`rehydrate-input` does NOT run `git commit` in asset mode. The commit is the calling session's responsibility (plan-pipeline §4F commit phase if dispatched from an active PLAN execution; the operator if invoked standalone). The commit message when the caller commits is:

```
rehydrate-input: asset <asset_id> consulted by <consuming_plan> + memory pointer written
```

Proceed to Step 5-asset (emit pipeline-result).

## Step 2: Surface input content

Present to the operator as a structured block:

```
== rehydrating input ==
Path: <input_path>
Type: <RESEARCH | ADVICE>
lifecycle_mode: <input | reference>
feeds_plan: <PLAN(s) | (none)>
integration_status: <prior> → ? (awaiting confirmation)

== content ==
<frontmatter block>
<body — first H2 section per heading>
...
```

If `lifecycle_mode: reference`, add a one-line note: "ℹ Reference-mode input — will NOT be auto-retired even when integrated."

If every PLAN in `feeds_plan` / `advises_plan` is already located under `Retired/**`, add a one-line note: "ℹ All consuming PLANs already retired — confirming integration will trigger late auto-retire of this input."

If `feeds_plan` and `advises_plan` are both empty / unset, add a one-line warning: "⚠ Input has no `feeds_plan` / `advises_plan` wired — late-auto-retire gate cannot fire. Either wire the consuming PLAN(s) or invoke `Skill('retire', '<path>')` manually after integration."

## Step 3: Prompt for integration confirmation

Ask the operator: "Absorbed into <consuming_plan> (or which PLAN)? Flip `integration_status: integrated`? [y/N]"

- **If `y` (or operator confirms):** edit the input file's frontmatter — change `integration_status: <prior>` to `integration_status: integrated`. Single-field mutation; do NOT touch body content. PASS.
- **If `N` (or operator defers):** SKIPPED for the flip; jump to Step 5 (no late-auto-retire on a still-pending input). Surface "integration_status left as pending; re-invoke when ready." No file mutation.

## Step 4: Late auto-retire gate

Runs only if `integration_status` is `integrated` after Step 3 (whether just-flipped or already-integrated from Step 1).

Three gates (mirrors plan-pipeline §4F step 7 — keep aligned):

- **Gate 1 — lifecycle_mode:** if `lifecycle_mode: reference`, SKIP. Surface "Input retained: lifecycle_mode=reference." Note: reference-mode inputs are surfaced for periodic review by the `reference_review_due` INDEX alert when their `review_by` date passes — that is the EOL surface for reference-mode inputs, not this auto-retire gate.
- **Gate 2 — feeds_plan / advises_plan wired:** if both fields are empty / unset, SKIP. Surface "Input retained: no consuming PLAN wired; invoke `Skill('retire')` manually if appropriate."
- **Gate 3 — all-feeds-retired:** for each PLAN in `feeds_plan` (RESEARCH) or `advises_plan` (ADVICE), check whether the file exists under `Retired/**` (basename match suffices — `Retired/<basename>` or `Retired/202605/<basename>` or any subdirectory). If ANY consuming PLAN is still in `Workbench/`, SKIP. Surface "Input retained: PLAN <other-plan> still active."

**All gates pass → auto-retire immediately:**
1. `git mv Workbench/<input-basename> Retired/<input-basename>` (orchestrator runs in parent context).
2. Post-condition verification (AA2 defence-in-depth pattern): assert source absent; destination exists, readable, non-zero size. If any check fails, return `outcome: exception` with diagnostic.
3. Commit: `rehydrate-input: late auto-retired <input-basename> (consuming PLAN(s) already retired; integration_status: integrated)`. Push subject to push_policy.
4. PASS.

If Gate 3 surfaces SKIP due to active consuming PLAN(s), the input will be auto-retired later by plan-pipeline §4F when those PLANs retire — no operator action needed.

## Step 5: Emit pipeline-result

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` (always — no FAIL after Step 1 succeeds, except Step 4 post-condition violation).
- `payload.input_path`: the input path (or new `Retired/...` path if Step 4 auto-retired).
- `payload.prior_status`: `pending` | `open` (legacy) | `integrated`.
- `payload.new_status`: `integrated` (if Step 3 confirmed) | `pending` (if deferred).
- `payload.lifecycle_mode`: `input` | `reference`.
- `payload.feeds_plan`: list of PLANs that consume this input.
- `payload.late_auto_retired`: `true` if Step 4 retired the file; otherwise `false`.
- `payload.retired_path`: `Retired/<input-basename>` (if Step 4 retired) or `null`.
- `payload.will_auto_retire_at_4F`: `true` if `lifecycle_mode != reference` AND `new_status == integrated` AND Step 4 SKIPPED on Gate 3 (consuming PLAN(s) still active); `false` otherwise.
- `diagnostics`: any per-step notes (including legacy `open` normalisation).

## Reporting

PASS / SKIPPED / FAIL per step. FAIL on Step 1 read errors and Step 4 post-condition violations. Steps 2, 3, 5 always PASS or SKIPPED.

---

### Step 5-asset (asset-mode pipeline-result payload spec)

Asset mode emits a pipeline-result distinct from input mode. Required payload fields:

```json
{
  "outcome": "success",
  "payload": {
    "outcome_subtype": "consumed | deferred | warned-skip",
    "asset_id": "<asset_id>",
    "asset_path": "<path>",
    "prior_last_consulted": "<ISO date or empty string>",
    "new_last_consulted": "<ISO date or null if deferred/warned-skip-no-stamp>",
    "consulted_by_appended": true,
    "consulted_by_evicted_oldest": false,
    "memory_file_path": "<absolute path or null>",
    "memory_write_skipped": false,
    "executor_notes": "<one-line summary>",
    "files_modified": ["<asset path>"]
  },
  "diagnostics": {}
}
```

Outcome semantics:

- **`consumed`** -- operator confirmed (A3 PASS); frontmatter stamped AND memory file written. `new_last_consulted` = today; `consulted_by_appended` reflects idempotency check; `memory_write_skipped: false`.
- **`deferred`** -- operator declined at A3. No frontmatter mutation; no memory write. `new_last_consulted: null`; `consulted_by_appended: false`; `memory_write_skipped: false`; `files_modified: []`.
- **`warned-skip`** -- operator confirmed but memory dir unreachable at A4 (S2 degraded path). Frontmatter stamped at A5; memory file NOT written. `memory_write_skipped: true`; `memory_file_path: null`; `consulted_by_appended` reflects A5 result.

`outcome: exception` is reserved for true failures (frontmatter validation error, missing `consuming_plan` in asset mode, atomic-write IOError, YAML parse failure).
