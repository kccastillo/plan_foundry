# raise-foundry-request workflow

Idempotent procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Steps

### Step 1: Resolve origin, datetime, and gist slug

At write time, the agent supplies:
- `<origin>` from `git remote get-url origin` basename (e.g. `my-project` from `https://github.com/acme/my-project.git`). Fall back to the working-directory name when no remote is configured (per PLAN-AH0 D3 - Origin-From-Remote). The agent resolves this from shell context or conversation metadata. Normalise to lowercase-kebab (replace non-alphanumeric with hyphens, trim leading/trailing hyphens).
- `YYYYMMDD-hhmm` from the current session datetime (NOT a shell call; no colon - colon-free is required for Windows-path-safety). Example: `20260712-1430`.
- `<slug>` as a few-word lowercase-kebab summary of the request's headline content. The slug is a discovery aid - a reader listing `Workbench/` can triage without opening the file - and is never a substitute for the request body.

Compose the target filename: `Workbench/FOUNDRYREQ-<origin>-<YYYYMMDD>-<hhmm>-<slug>.md`.

**Post-condition - filename validation (PLAN-AH0 D5):** Call `.claude/skills/_shared/validate_artefact_filename.py::classify_artefact_filename(basename)` on the composed basename. If the result is not `"conforming"`, hard-fail: return `outcome: FAIL` with `diagnostics.reason: "composed filename classified as <class>: <reason>"`. This guard catches any colon-containing or slug-absent name before the file is written.

### Step 2: Write `Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md`

Write the file using the standard request frontmatter (ADVICE-shaped, reconciled against `write-input/templates/advice-template.md` as the SoT for `type: advice` inputs). Request frontmatter MUST include all of the following fields:

```yaml
---
title: "[Brief headline of the request]"
type: advice
kind: bug | feature | model-fit
created: YYYY-MM-DD
advises_plan: ""
from: ""
question_asked: ""
integration_status: pending
lifecycle_mode: input
---
```

Field guidance:
- `title` - a one-line headline for the request (e.g. "FOUNDRYREQ: handoff filenames lack date and gist slug").
- `type: advice` - requests are ADVICE-shaped and flow through the ADVICE lifecycle.
- `kind` - exactly one of `bug` (the bundle misbehaves against its own contract), `feature` (a capability gap or behaviour-change request), or `model-fit` (a model assignment or prompting convention in the bundle no longer matches observed model behaviour). Definitions and the raising bar are in [../SKILL.md](../SKILL.md) section Request kinds. Required on every new request; never added retroactively to a pre-existing one.
- `created` - the write date in ISO format (YYYY-MM-DD), agent-supplied (no shell).
- `advises_plan` - the PLAN filename this request advises (or `""` when no specific PLAN is identified yet).
- `from` - the origin identifier: the repo name, operator, session ID, or agent name that raised it. Typically the same as `<origin>` in the filename.
- `question_asked` - the trigger or question the request records (e.g. "Can the handoff skill support scoped thread handoffs?").
- `integration_status: pending` - always set to `pending` at creation; flipped to `integrated` by `plan-pipeline` section 4F when a PLAN listing this file in `linked_inputs` retires.
- `lifecycle_mode: input` - always `input` (not `reference`) so the request auto-retires when all consuming PLANs retire via plan-pipeline section 4F.

Body: write the request substance below the frontmatter block. At minimum include a `## Request` heading with the substantive content, and optionally `## Suggested action`, `## Evidence`, `## Related requests`.

**Additional body contract for `kind: model-fit`.** Before writing, check the request against the four discipline rules in [../SKILL.md](../SKILL.md) section Trigger discipline for `kind: model-fit`. If the finding does not clear all four, do not write the file - report to the operator which rule it fails and stop. If it clears them, `## Evidence` is mandatory (not optional) and must name:

- the skill, agent, or prompt surface concerned, and the model assigned to it;
- what it was asked to do, and what it actually produced;
- the direction of the mismatch - **under-tiered** (the assigned model could not do the work) or **over-tiered** (a cheaper model would have done it equally well);
- whether the mismatch was observed once or repeatedly, and if once, what it cost.

Reads use `encoding='utf-8', errors='replace'`; writes emit UTF-8. PASS.

### Step 3: Report to the operator

Return the written filename and confirmation:
```
Written:   Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md  (type: advice, kind: <kind>, integration_status: pending)
Next step: reference the request in a PLAN's `linked_inputs`. It is marked integrated and retired automatically when that PLAN retires.
```
