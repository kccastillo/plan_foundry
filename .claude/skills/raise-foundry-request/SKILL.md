---
name: raise-foundry-request
description: Raise a plan_foundry bug report or feature request from a consumer repo. Writes `Workbench/FOUNDRYREQ-<origin>-YYYYMMDD-hhmm-<slug>.md` with standard ADVICE-shaped frontmatter so consumers never hand-edit bundle files. The `<origin>` is derived from the git remote basename (or working-directory name as fallback). Trigger phrases: "raise a foundry bug", "request a foundry feature", "file a foundry request", "raise a foundry request", "raise a plan-foundry observation", "log an observation", "raise observation", "record a foundry observation".
---

## Objective

Ship a bundle skill so host and consumer repos can raise bugs and feature requests against plan_foundry via a skill invocation rather than by hand-editing bundle files that `/plan-foundry-sync` would later overwrite. Per PLAN-AF6 D3 — Raise-Skill (consumer→foundry feedback channel); repurposed and renamed by PLAN-AH0 D2 — Foundry-Req-Rename to serve as the dedicated producer of `FOUNDRYREQ` artefacts.

Each request is an ADVICE-shaped input that enters the input lifecycle at `integration_status: pending`, advises a PLAN (or the empty string when no specific PLAN is identified yet), and eventually retires when all consuming PLANs retire (per plan-pipeline §4F). Requests flow through the ADVICE lifecycle because their substance is strategic input that shapes future PLAN authoring.

**Filename grammar:** see [../handoff-next-session/references/handoff-naming.md](../handoff-next-session/references/handoff-naming.md) — the shared grammar single-source-of-truth for all datetime-stamped artefacts (HANDOFF, FOUNDRYREQ, and input files).

## Filename grammar

Target: `Workbench/FOUNDRYREQ-<origin>-<YYYYMMDD>-<hhmm>-<slug>.md`

- `<origin>` identifies the originating repo or workspace. Derived at write time from `git remote get-url origin` basename (e.g. `my-project` from `https://github.com/acme/my-project.git`), falling back to the working-directory name when no remote is configured (per PLAN-AH0 D3 — Origin-From-Remote). The agent supplies this from the shell context or conversation metadata; no colon — Windows-path-safe.
- `YYYYMMDD-hhmm` is the local write-time datetime supplied by the write-time agent from its own clock/context (NOT a shell call; no colon — Windows-path-safe and lexically sortable).
- `<slug>` is a lowercase-kebab gist summary of the request's headline content, authored at write time — e.g. `FOUNDRYREQ-my-project-20260712-1402-handoff-filenames-date-slug.md`.
- The grammar drops the `NNN` sequential counter (per PLAN-AH0 D4 — External-Only-NNN): consumer repos cannot reach this repo's `next_id.py` allocator, so origin + datetime + slug gives each request a globally unique, autonomous name.
- The grammar follows PLAN-AF6 D1 (Datetime-Grammar) exactly for the datetime component.

## Essential principles

- Write-time datetime is agent-supplied (no shell call; colon-free; e.g. `1430`, not `14:30`).
- `<origin>` is derived from `git remote get-url origin` basename; fall back to working-directory name when no remote is configured. The agent resolves this from shell context or conversation metadata.
- Requests are ADVICE-shaped inputs — they share the ADVICE template's full frontmatter key set (including `from` and `question_asked`), flow through the same `integration_status` lifecycle, and retire via the same §4F path.
- Do NOT wire any git operation into the skill — the caller (plan-pipeline or the human) commits and pushes.
- Reads use `encoding='utf-8', errors='replace'`; writes emit UTF-8.

**Foundry request writing procedure:** See [workflows/write-foundry-request.md](workflows/write-foundry-request.md) for the step-by-step.

<constraints>
- Only write to `Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md`. Never write to bundle skill directories.
- Never modify input content after transcription.
- Never start a git operation.
- `integration_status` is always `pending` at creation.
</constraints>

<success_criteria>
- A new `Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md` exists with valid ADVICE-shaped frontmatter.
- `integration_status: pending` and `lifecycle_mode: input` are set.
- The operator has been given the written path.
- The composed filename classified as `conforming` by the shared validator (PLAN-AH0 D5).
</success_criteria>
