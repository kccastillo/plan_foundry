---
name: update-workbench-index
description: 'Regenerate Workbench/INDEX.md and Workbench/.index.json from PLAN frontmatter and .audit/ files. Pure projection; idempotent; deterministic. Trigger phrases - "regenerate INDEX", "update workbench INDEX", "rebuild workbench index", "/index". Also auto-fires from plan-pipeline after every commit-worthy phase transition (auxiliary; failure does not halt the pipeline).'
model: haiku
---

## Purpose

Regenerate the Workbench INDEX - a deterministic kanban projection of all PLAN files in `Workbench/`. Reads PLAN frontmatter and `.audit/` sibling files. Produces two output files committed separately from the triggering phase-transition commit:

- `Workbench/INDEX.md` - human-readable kanban view
- `Workbench/.index.json` - machine-readable projection for tooling

Both files are committed (not gitignored). Both are regenerated in full on every invocation (no incremental updates in v1).

---

## Invocation

The orchestrator dispatches this skill **after every commit-worthy phase transition**. Skill failure (exception outcome) is logged but does NOT halt the pipeline - INDEX regen is auxiliary.

The `/index` slash command invokes this skill on demand from the parent session.

---

## Procedure

1. Locate `Workbench/` - use the `workbenchDir` from `.claude/plan-foundry.config` if present, otherwise default to `Workbench/` relative to repo root.

2. Run the build script:
   ```bash
   python .claude/skills/update-workbench-index/scripts/build_index.py [workbench_dir]
   ```
   The script writes `Workbench/INDEX.md` and `Workbench/.index.json` directly.

3. Confirm both output files exist and `Workbench/.index.json` is valid JSON with `schema_version: 1`.

4. Return `<pipeline-result>` v2 with:
   - `outcome: success` if both files were written and JSON validates
   - `outcome: exception` with diagnostics if the script errored or output is missing/malformed

### Single regeneration entrypoint (INDEX + Context Inputs)

For pre-PR discipline and routine state-keeping, use the combined entrypoint
instead of running `build_index.py` and the LOG update separately:

```bash
python .claude/skills/update-workbench-index/scripts/regenerate_state.py [workbench_dir] [--write]
```

This runs two steps in sequence:

1. Regenerates `INDEX.md` + `.index.json` (always a write; idempotent; delegates to `build_index.py`).
2. Checks - or reconciles - the monthly LOG's `## Context Inputs This Month` table
   via `scripts/project_context_inputs.py`.

**Default behaviour (`--check`, D3 Option A):** The entrypoint reports dangling
rows (in the table but no file on disk) and missing rows (in-month on-disk input
file not in the table), then exits non-zero if drift is detected.  The LOG is
NOT modified - a human reviews the report and decides whether to reconcile.

**Opt-in reconciliation (`--write`):** Adds `--write` to reconcile the LOG's
Context Inputs table in place.  Surviving rows keep both their authored Advises
and Notes cells verbatim (these are routing narrative, not raw frontmatter
values).  Dangling rows are dropped.  Missing rows are appended with the
`advises_plan` / `feeds_plan` frontmatter value seeding the Advises cell (or
`-` when that field is empty).

Cross-reference: `scripts/project_context_inputs.py` is the projector
implementation and can also be invoked directly with `--check` or `--write`
and an optional `--log-path` override (useful for testing against a specific
LOG fixture).

---

## Output schema

```json
{
  "outcome": "success | exception",
  "payload": {
    "outcome_subtype": "done | blocked",
    "executor_notes": "string",
    "files_modified": ["Workbench/INDEX.md", "Workbench/.index.json"]
  },
  "diagnostics": {}
}
```

---

## References

- Build script: [`scripts/build_index.py`](scripts/build_index.py)
- Index JSON schema: [`references/index-schema.md`](references/index-schema.md)
- Alert definitions: [`references/alerts-spec.md`](references/alerts-spec.md)
- INDEX.md template: [`references/markdown-template.md`](references/markdown-template.md)

---

## Constraints

- Never modifies any PLAN file - read-only access to `Workbench/*.md` and `Workbench/.audit/*.json`.
- Full rebuild on every regen (no incremental updates in v1).
- INDEX regen failure does NOT halt the pipeline (auxiliary operation).
- The orchestrator commits the INDEX outputs in a separate commit: `plan-pipeline: update-workbench-index`.
