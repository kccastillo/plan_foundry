# rehydrate-input workflow

Idempotent four-step procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Step 1: Read and validate the input file

Read the file at `input_path`.
- **If absent / unreadable:** FAIL. Surface `<exception>input not found at <path></exception>`. Return.
- **If present but missing frontmatter or missing `integration_status` field:** FAIL. Surface diagnostic and return — caller should fix the input (or it's not a write-input-authored file).
- **If `integration_status: integrated` already:** SKIPPED. Surface "input <path> already integrated; no action." Skip to Step 4 with payload `prior_status=integrated, new_status=integrated, action=no-op`.
- **Otherwise:** PASS. Capture `lifecycle_mode` (default `input` if absent), `feeds_plan` / `advises_plan`, and the body content.

## Step 2: Surface input content

Present to the operator as a structured block:

```
== rehydrating input ==
Path: <input_path>
Type: <RESEARCH | ADVICE>
lifecycle_mode: <input | reference>
feeds_plan: <PLAN(s) | (none)>
integration_status: pending → ? (awaiting confirmation)

== content ==
<frontmatter block>
<body — first H2 section per heading>
...
```

If `lifecycle_mode: reference`, add a one-line note: "ℹ Reference-mode input — will NOT be auto-retired even when integrated."

## Step 3: Prompt for integration confirmation

Ask the operator: "Absorbed into <consuming_plan> (or which PLAN)? Flip `integration_status: integrated`? [y/N]"

- **If `y` (or operator confirms):** edit the input file's frontmatter — change `integration_status: pending` to `integration_status: integrated`. Single-field mutation; do NOT touch body content. PASS.
- **If `N` (or operator defers):** SKIPPED. Surface "integration_status left as pending; re-invoke when ready." No file mutation.

## Step 4: Emit pipeline-result

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` (always — no FAIL after Step 1 succeeds).
- `payload.input_path`: the input path.
- `payload.prior_status`: `pending` | `integrated`.
- `payload.new_status`: `integrated` (if Step 3 confirmed) | `pending` (if deferred).
- `payload.lifecycle_mode`: `input` | `reference`.
- `payload.feeds_plan`: list of PLANs that consume this input.
- `payload.will_auto_retire`: `true` if `lifecycle_mode != reference` AND `new_status == integrated` (semantic preview; actual auto-retire is plan-pipeline §4F's job at consuming-PLAN retire time).
- `diagnostics`: any per-step notes.

## Reporting

PASS / SKIPPED / FAIL per step. FAIL only on Step 1 read errors; Steps 2-4 always PASS or SKIPPED.
