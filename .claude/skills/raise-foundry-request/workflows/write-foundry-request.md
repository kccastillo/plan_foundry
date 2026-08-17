# raise-foundry-request workflow

This procedure is idempotent. Each step reports PASS, SKIPPED, or FAIL.

## Steps

### Step 1: Resolve origin, datetime, and gist slug

At write time, the agent supplies:
- `<origin>` from `git remote get-url origin` basename (e.g. `my-project` from `https://github.com/acme/my-project.git`). Fall back to the working-directory name when no remote is configured (per PLAN-AH0 D3 - Origin-From-Remote). The agent resolves this from shell context or conversation metadata. Normalise to lowercase-kebab (replace non-alphanumeric with hyphens, trim leading/trailing hyphens).
- `YYYYMMDD-hhmm` from the current session datetime (NOT a shell call, and no colon, because colon-free is required for Windows-path-safety). Example: `20260712-1430`.
- `<slug>` as a few-word lowercase-kebab summary of the request's headline content. The slug is a discovery aid - a reader listing `Workbench/` can triage without opening the file - and is never a substitute for the request body.

Compose the target filename: `Workbench/FOUNDRYREQ-<origin>-<YYYYMMDD>-<hhmm>-<slug>.md`.

**Post-condition - filename validation (PLAN-AH0 D5):** Call `.claude/skills/_shared/validate_artefact_filename.py::classify_artefact_filename(basename)` on the composed basename. If the result is not `"conforming"`, hard-fail: return `outcome: FAIL` with `diagnostics.reason: "composed filename classified as <class>: <reason>"`. This guard rejects any colon-containing or slug-absent name before the file is written.

### Step 2: Write `Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md`

Write the file using the standard request frontmatter set out below. There is no separate advice template to reconcile against: the `ADVICE` and `RESEARCH` kinds were collapsed into the input kind on 2026-08-03, `write-input/templates/input-template.md` writes `type: input` with `feeds_plan`, and `write-input` is forbidden from writing `advises_plan` or an `ADVICE-*` filename on a new file. This block is therefore the source of truth for a `type: advice` request. It carries the input template's key set, with `advises_plan` in place of `feeds_plan`, plus `kind` and `transfer_scope`. Request frontmatter MUST include all of the following fields:

```yaml
---
title: "[Brief headline of the request]"
type: advice
kind: bug | feature | model-fit
transfer_scope: upstream | project-local
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
- `kind` - exactly one of `bug` (the bundle misbehaves against its own contract), `feature` (a capability gap or behaviour-change request), or `model-fit` (a model assignment or prompting convention in the bundle no longer matches observed model behaviour). Definitions and the raising bar are in [../SKILL.md](../SKILL.md) section Request kinds. Required on every new request, and never added retroactively to a pre-existing one.
- `transfer_scope` - exactly one of `upstream` (the request belongs in plan_foundry itself - the default) or `project-local` (the finding is specific to the raising repo and is never meant to travel further). Distinct from `kind`: `kind` classifies what the finding is, `transfer_scope` classifies whether the finding is meant for this bundle at all. Per PLAN-AK7 D5, no bundle code reads or enforces this field yet. An absent value on a pre-existing request means unclassified, and is never retrofitted.
- `created` - the write date in ISO format (YYYY-MM-DD), agent-supplied (no shell).
- `advises_plan` - the PLAN filename this request advises (or `""` when no specific PLAN is identified yet).
- `from` - the origin identifier: the repo name, operator, session ID, or agent name that raised the request. This value is typically the same as `<origin>` in the filename.
- `question_asked` - the trigger or question the request records (e.g. "Can the handoff skill support scoped thread handoffs?").
- `integration_status: pending` - always set to `pending` at creation, and flipped to `integrated` by `plan-pipeline` section 4F when a PLAN listing this file in `linked_inputs` retires.
- `lifecycle_mode: input` - always `input` (not `reference`) so the request auto-retires when all consuming PLANs retire via plan-pipeline section 4F.

Body: write the request substance below the frontmatter block. At minimum include a `## Request` heading with the substantive content, and optionally `## Suggested action`, `## Evidence`, `## Related requests`.

**Additional body contract for `kind: model-fit`.** Before writing, check the request against the discipline rules in [../SKILL.md](../SKILL.md) section Trigger discipline for `kind: model-fit`. If the finding does not clear every rule, do not write the file - report to the operator which rule the finding fails, then stop. If the finding clears them, `## Evidence` is mandatory (not optional) and must name:

- the skill, agent, or prompt surface concerned, and the model assigned to that surface
- what the surface was asked to do, and what the surface actually produced
- the direction of the mismatch - **under-tiered** (the assigned model could not do the work) or **over-tiered** (a cheaper model would have done the work equally well)
- whether the mismatch was observed once or repeatedly, and, when it was observed once, what that occurrence cost

Reads use `encoding='utf-8', errors='replace'`, and writes emit UTF-8. PASS.

### Step 3: Report to the operator

Return the written filename and confirmation:
```
Written:   Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md  (type: advice, kind: <kind>, integration_status: pending)
Next step: reference the request in a PLAN's `linked_inputs`. It is marked integrated and retired automatically when that PLAN retires.
```
