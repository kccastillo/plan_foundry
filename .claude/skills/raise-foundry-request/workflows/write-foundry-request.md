# raise-foundry-request workflow

Idempotent procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Steps

### Step 1: Resolve origin, datetime, and gist slug

At write time, the agent supplies:
- `<origin>` from `git remote get-url origin` basename (e.g. `my-project` from `https://github.com/acme/my-project.git`). Fall back to the working-directory name when no remote is configured (per PLAN-AH0 D3 — Origin-From-Remote). The agent resolves this from shell context or conversation metadata. Normalise to lowercase-kebab (replace non-alphanumeric with hyphens, trim leading/trailing hyphens).
- `YYYYMMDD-hhmm` from the current session datetime (NOT a shell call; no colon — colon-free is required for Windows-path-safety). Example: `20260712-1430`.
- `<slug>` as a few-word lowercase-kebab summary of the request's headline content. The slug is a discovery aid — a reader listing `Workbench/` can triage without opening the file — and is never a substitute for the request body.

Compose the target filename: `Workbench/FOUNDRYREQ-<origin>-<YYYYMMDD>-<hhmm>-<slug>.md`.

**Post-condition — filename validation (PLAN-AH0 D5):** Call `.claude/skills/_shared/validate_artefact_filename.py::classify_artefact_filename(basename)` on the composed basename. If the result is not `"conforming"`, hard-fail: return `outcome: FAIL` with `diagnostics.reason: "composed filename classified as <class>: <reason>"`. This guard catches any colon-containing or slug-absent name before the file is written.

### Step 2: Write `Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md`

Write the file using the standard request frontmatter (ADVICE-shaped, reconciled against `write-input/templates/advice-template.md` as the SoT for `type: advice` inputs). Request frontmatter MUST include all of the following fields:

```yaml
---
title: "[Brief headline of the request]"
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
- `title` — a one-line headline for the request (e.g. "FOUNDRYREQ: handoff filenames lack date and gist slug").
- `type: advice` — requests are ADVICE-shaped and flow through the ADVICE lifecycle.
- `created` — the write date in ISO format (YYYY-MM-DD), agent-supplied (no shell).
- `advises_plan` — the PLAN filename this request advises (or `""` when no specific PLAN is identified yet).
- `from` — the origin identifier: the repo name, operator, session ID, or agent name that raised it. Typically the same as `<origin>` in the filename.
- `question_asked` — the trigger or question the request records (e.g. "Can the handoff skill support scoped thread handoffs?").
- `integration_status: pending` — always set to `pending` at creation; flipped to `integrated` by `rehydrate-input` on operator confirmation.
- `lifecycle_mode: input` — always `input` (not `reference`) so the request auto-retires when all consuming PLANs retire via plan-pipeline §4F.

Body: write the request substance below the frontmatter block. At minimum include a `## Request` heading with the substantive content, and optionally `## Suggested action`, `## Evidence`, `## Related requests`.

Reads use `encoding='utf-8', errors='replace'`; writes emit UTF-8. PASS.

### Step 3: Report to the operator

Return the written filename and confirmation:
```
Written:   Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md  (type: advice, integration_status: pending)
Next step: Rehydrate and integrate via `rehydrate-input` when the request is absorbed into a PLAN.
```
