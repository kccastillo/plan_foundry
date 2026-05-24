# rehydrate-input workflow

Idempotent five-step procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Step 1: Read and validate the input file

Read the file at `input_path`.
- **If absent / unreadable:** FAIL. Surface `<exception>input not found at <path></exception>`. Return.
- **If present but missing frontmatter or missing `integration_status` field:** FAIL. Surface diagnostic and return — caller should fix the input (or it's not a write-input-authored file).
- **Legacy normalisation:** if `integration_status: open` is encountered (predates the `pending`/`integrated` convention), treat as equivalent to `pending` for the rest of the procedure. Log one diagnostic: "normalised legacy `integration_status: open` → `pending` for processing." Do not mutate the file at this step — Step 3 will rewrite the field via the confirm-and-flip path.
- **If `integration_status: integrated` already:** SKIPPED for the flip; jump to Step 4 (late-auto-retire) — the input may still be eligible for retire if it was integrated before all consuming PLANs were retired.
- **Otherwise:** PASS. Capture `lifecycle_mode` (default `input` if absent), `feeds_plan` / `advises_plan`, and the body content.

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

- **Gate 1 — lifecycle_mode:** if `lifecycle_mode: reference`, SKIP. Surface "Input retained: lifecycle_mode=reference."
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
