---
name: raise-foundry-request
description: 'Raise a plan_foundry bug report, feature request, or model-fit finding from a consumer repo. Writes `Workbench/FOUNDRYREQ-<origin>-YYYYMMDD-hhmm-<slug>.md` with standard ADVICE-shaped frontmatter (including `kind: bug|feature|model-fit`) so consumers never hand-edit bundle files. The `<origin>` is derived from the git remote basename (or working-directory name as fallback). Trigger phrases: "raise a foundry bug", "request a foundry feature", "file a foundry request", "raise a foundry request", "raise a plan-foundry observation", "log an observation", "raise observation", "record a foundry observation", "raise a model-fit finding", "wrong model for this skill", "this skill is on the wrong tier", "the model assignment is wrong", "record a model-fit observation".'
---

## Objective

Ship a bundle skill so host and consumer repos can raise bugs and feature requests against plan_foundry via a skill invocation rather than by hand-editing bundle files that `/plan-foundry-sync` would later overwrite. Per PLAN-AF6 D3 - Raise-Skill (consumer->foundry feedback channel); repurposed and renamed by PLAN-AH0 D2 - Foundry-Req-Rename to serve as the dedicated producer of `FOUNDRYREQ` artefacts.

Each request is an ADVICE-shaped input that enters the input lifecycle at `integration_status: pending`, advises a PLAN (or the empty string when no specific PLAN is identified yet), and eventually retires when all consuming PLANs retire (per plan-pipeline section 4F). Requests flow through the ADVICE lifecycle because their substance is strategic input that shapes future PLAN authoring.

**Filename grammar:** see [../handoff-next-session/references/handoff-naming.md](../handoff-next-session/references/handoff-naming.md) - the shared grammar single-source-of-truth for all datetime-stamped artefacts (HANDOFF, FOUNDRYREQ, and input files).

## Filename grammar

Target: `Workbench/FOUNDRYREQ-<origin>-<YYYYMMDD>-<hhmm>-<slug>.md`

- `<origin>` identifies the originating repo or workspace. Derived at write time from `git remote get-url origin` basename (e.g. `my-project` from `https://github.com/acme/my-project.git`), falling back to the working-directory name when no remote is configured (per PLAN-AH0 D3 - Origin-From-Remote). The agent supplies this from the shell context or conversation metadata; no colon - Windows-path-safe.
- `YYYYMMDD-hhmm` is the local write-time datetime supplied by the write-time agent from its own clock/context (NOT a shell call; no colon - Windows-path-safe and lexically sortable).
- `<slug>` is a lowercase-kebab gist summary of the request's headline content, authored at write time - e.g. `FOUNDRYREQ-my-project-20260712-1402-handoff-filenames-date-slug.md`.
- The grammar drops the `NNN` sequential counter (per PLAN-AH0 D4 - External-Only-NNN): consumer repos cannot reach this repo's `next_id.py` allocator, so origin + datetime + slug gives each request a globally unique, autonomous name.
- The grammar follows PLAN-AF6 D1 (Datetime-Grammar) exactly for the datetime component.

## Request kinds

Every request carries a `kind` frontmatter field classifying what sort of finding it is. All three kinds stay ADVICE-shaped (`type: advice`) and share one lifecycle - `kind` sub-classifies within the FOUNDRYREQ family so that findings can be routed to the right absorbing PLAN rather than triaged by reading every body.

| `kind` | What it records | Absorbed by |
|---|---|---|
| `bug` | The bundle does something other than what it says it does. A skill, script, hook, or contract misbehaves. | The PLAN that owns the broken surface. |
| `feature` | The bundle does what it says, and what it says is not enough. A capability gap or a behaviour change request. | A new or in-flight PLAN scoping the capability. |
| `model-fit` | A model assignment or prompting convention in the bundle no longer matches how the model behaves. Not a bug in the code - a drift between the harness's assumptions about a model and that model's actual behaviour. | The release-triggered model-drift review (in this repo, `PLAN-AD2` W2.2). |

`kind: model-fit` exists because model-behaviour drift arrives continuously and from consumers, while the review that acts on it is periodic and central. Without a manual channel, the findings are only ever noticed by whoever happened to hit them, and are gone by the time the review runs.

**Back-compatibility:** requests written before `kind` existed have no such field. Absent `kind` is *unclassified*, not invalid - never fail, never rewrite a historical request to add one. Only new requests are required to set it.

Every request also carries `transfer_scope` (`upstream` | `project-local`), distinct from `kind`: `kind` classifies what the finding is, `transfer_scope` classifies whether the request is meant for this bundle at all. `upstream` (the default for new requests) means the request belongs in plan_foundry itself; `project-local` flags a finding that is genuinely specific to the raising repo and never meant to travel further. Per PLAN-AK7 D5, this pass is documentation only - no bundle code reads or enforces `transfer_scope` yet.

**Back-compatibility:** requests written before `transfer_scope` existed have no such field. Absent `transfer_scope` is *unclassified*, not invalid - never fail, never retrofit a historical request to add one.

### Trigger discipline for `kind: model-fit`

The value of this channel is entirely a function of its signal-to-noise ratio, so the bar to raise one is deliberately high. Raise a `model-fit` request only when **all** of these hold:

1. **The finding is observed, not predicted.** There was a real run. Name the skill or agent, the model it was assigned, what it was asked to do, and what it actually produced. A reasoned expectation that a tier "is probably wrong now" is not a finding.
2. **The mismatch is structural or expensive.** Either it is repeatable (the same assignment fails or wastes the same way across runs), or a single occurrence cost enough to matter - a halted pipeline, destroyed state, a wrong result that was acted on. A one-off poor answer that a retry fixed is model variance, not model fit.
3. **The shortfall is named.** State which direction the mismatch runs: under-tiered (the assigned model could not do the work) or over-tiered (a cheaper model would have done it equally well). "The output was bad" does not distinguish these, and they have opposite fixes.
4. **One finding per request.** Do not bundle several assignments into one file; they will be absorbed at different times.

Prompting-convention inversions count as `model-fit`: a documented instruction in the bundle that a newer model makes counterproductive rather than merely redundant is exactly this kind of drift.

**Do not raise a `model-fit` request** for a model release on its own. A new frontier model triggers a scheduled, central re-assessment of every assignment - it is not something each consumer files a request about. The channel is for behaviour observed in use, not for release news.

## Essential principles

- Write-time datetime is agent-supplied (no shell call; colon-free; e.g. `1430`, not `14:30`).
- `<origin>` is derived from `git remote get-url origin` basename; fall back to working-directory name when no remote is configured. The agent resolves this from shell context or conversation metadata.
- Requests are ADVICE-shaped inputs - they share the ADVICE template's full frontmatter key set (including `from` and `question_asked`), flow through the same `integration_status` lifecycle, and retire via the same section 4F path.
- Do NOT wire any git operation into the skill - the caller (plan-pipeline or the human) commits and pushes.
- Reads use `encoding='utf-8', errors='replace'`; writes emit UTF-8.

**Foundry request writing procedure:** See [workflows/write-foundry-request.md](workflows/write-foundry-request.md) for the step-by-step.

<constraints>
- Only write to `Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md`. Never write to bundle skill directories.
- Never modify input content after transcription.
- Never start a git operation.
- `integration_status` is always `pending` at creation.
- `kind` is exactly one of `bug`, `feature`, `model-fit` on every newly written request. Never invent a fourth value - if a finding fits none of the three, it is a `feature` request against the taxonomy itself.
- Never add a `kind` field to a pre-existing request that lacks one.
</constraints>

<success_criteria>
- A new `Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md` exists with valid ADVICE-shaped frontmatter.
- `integration_status: pending` and `lifecycle_mode: input` are set.
- `kind` is set to one of `bug`, `feature`, `model-fit`.
- For `kind: model-fit`, the body names the skill/agent, the assigned model, the observed behaviour, and the direction of the mismatch (under-tiered or over-tiered).
- The operator has been given the written path.
- The composed filename classified as `conforming` by the shared validator (PLAN-AH0 D5).
</success_criteria>
