---
name: raise-observation
description: Raise a plan-foundry observation log. Writes `Workbench/OBSERVATION-<YYYYMMDD>-<hhmm>-<slug>.md` with standard ADVICE-shaped observation frontmatter so consumers never hand-edit bundle files. Trigger phrases: "raise a plan-foundry observation", "log an observation", "raise observation", "record a foundry observation".
---

## Objective

Ship a bundle skill so host and consumer repos can raise observation logs via a skill invocation rather than by hand-editing bundle files that `/plan-foundry-sync` would later overwrite. Per PLAN-AF6 D3 — Raise-Skill.

Each observation is an ADVICE-shaped input that enters the input lifecycle at `integration_status: pending`, advises a PLAN (or the empty string when no specific PLAN is identified yet), and eventually retires when all consuming PLANs retire (per plan-pipeline §4F). Observations flow through the ADVICE lifecycle because their substance is strategic input that shapes future PLAN authoring.

**Filename grammar:** see [../handoff-next-session/references/handoff-naming.md](../handoff-next-session/references/handoff-naming.md) — the shared grammar single-source-of-truth for all datetime-stamped artefacts (HANDOFF, OBSERVATION, and input files).

## Filename grammar

Target: `Workbench/OBSERVATION-<YYYYMMDD>-<hhmm>-<slug>.md`

- `YYYYMMDD-hhmm` is the local write-time datetime supplied by the write-time agent from its own clock/context (NOT a shell call; no colon — Windows-path-safe and lexically sortable).
- `<slug>` is a lowercase-kebab gist summary of the observation's headline content, authored at write time — e.g. `OBSERVATION-20260712-1402-handoff-filenames-date-slug.md`.
- The grammar follows PLAN-AF6 D1 (Datetime-Grammar) exactly.

## Essential principles

- Write-time datetime is agent-supplied (no shell call; colon-free; e.g. `1430`, not `14:30`).
- Observations are ADVICE-shaped inputs — they share the ADVICE template's full frontmatter key set (including `from` and `question_asked`), flow through the same `integration_status` lifecycle, and retire via the same §4F path.
- Do NOT wire any git operation into the skill — the caller (plan-pipeline or the human) commits and pushes.
- Reads use `encoding='utf-8', errors='replace'`; writes emit UTF-8.

**Observation writing procedure:** See [workflows/write-observation.md](workflows/write-observation.md) for the step-by-step.

<constraints>
- Only write to `Workbench/OBSERVATION-<datetime>-<slug>.md`. Never write to bundle skill directories.
- Never modify input content after transcription.
- Never start a git operation.
- `integration_status` is always `pending` at creation.
</constraints>

<success_criteria>
- A new `Workbench/OBSERVATION-<datetime>-<slug>.md` exists with valid ADVICE-shaped frontmatter.
- `integration_status: pending` and `lifecycle_mode: input` are set.
- The operator has been given the written path.
</success_criteria>
