# raise-observation workflow

Idempotent procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Steps

### Step 1: Resolve datetime and gist slug

At write time, the agent supplies:
- `YYYYMMDD-hhmm` from the current session datetime (NOT a shell call; no colon — colon-free is required for Windows-path-safety). Example: `20260712-1430`.
- `<slug>` as a few-word lowercase-kebab summary of the observation's headline content. The slug is a discovery aid — a reader listing `Workbench/` can triage without opening the file — and is never a substitute for the observation body.

Compose the target filename: `Workbench/OBSERVATION-<YYYYMMDD>-<hhmm>-<slug>.md`.

### Step 2: Write `Workbench/OBSERVATION-<datetime>-<slug>.md`

Write the file using the standard observation frontmatter (ADVICE-shaped, reconciled against `write-input/templates/advice-template.md` as the SoT for `type: advice` inputs). Observation frontmatter MUST include all of the following fields:

```yaml
---
title: "[Brief headline of the observation]"
type: advice
created: YYYY-MM-DD
advises_plan: ""
from: ""
question_asked: ""
integration_status: pending
lifecycle_mode: input
---
```

Field guidance:
- `title` — a one-line headline for the observation (e.g. "Handoff filenames lack date and gist slug").
- `type: advice` — observations are ADVICE-shaped and flow through the ADVICE lifecycle.
- `created` — the write date in ISO format (YYYY-MM-DD), agent-supplied (no shell).
- `advises_plan` — the PLAN filename this observation advises (or `""` when no specific PLAN is identified yet).
- `from` — who raised the observation: the operator, session ID, or agent name that logged it.
- `question_asked` — the trigger or question the observation records (e.g. "Why do handoff filenames carry no date or gist summary?").
- `integration_status: pending` — always set to `pending` at creation; flipped to `integrated` by `rehydrate-input` on operator confirmation.
- `lifecycle_mode: input` — always `input` (not `reference`) so the observation auto-retires when all consuming PLANs retire via plan-pipeline §4F.

Body: write the observation substance below the frontmatter block. At minimum include a `## Observation` heading with the substantive content, and optionally `## Suggested action`, `## Evidence`, `## Related observations`.

Reads use `encoding='utf-8', errors='replace'`; writes emit UTF-8. PASS.

### Step 3: Report to the operator

Return the written filename and confirmation:
```
Written:   Workbench/OBSERVATION-<datetime>-<slug>.md  (type: advice, integration_status: pending)
Next step: Rehydrate and integrate via `rehydrate-input` when the observation is absorbed into a PLAN.
```
