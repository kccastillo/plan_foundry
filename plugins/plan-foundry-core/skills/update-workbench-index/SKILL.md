---
name: update-workbench-index
description: Regenerate Workbench/INDEX.md and Workbench/.index.json from PLAN frontmatter and .audit/ files. Pure projection; idempotent; deterministic.
model: haiku
---

## Purpose

Regenerate the Workbench INDEX — a deterministic kanban projection of all PLAN files in `Workbench/`. Reads PLAN frontmatter and `.audit/` sibling files. Produces two output files committed separately from the triggering phase-transition commit:

- `Workbench/INDEX.md` — human-readable kanban view
- `Workbench/.index.json` — machine-readable projection for tooling

Both files are committed (not gitignored). Both are regenerated in full on every invocation (no incremental updates in v1).

---

## Invocation

The orchestrator dispatches this skill **after every commit-worthy phase transition**. Skill failure (exception outcome) is logged but does NOT halt the pipeline — INDEX regen is auxiliary.

The `/index` slash command invokes this skill on demand from the parent session.

---

## Procedure

1. Locate `Workbench/` — use the `workbenchDir` from `.claude/plan-foundry.config` if present, otherwise default to `Workbench/` relative to repo root.

2. Run the build script:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT:-plugins/plan-foundry-core}/skills/update-workbench-index/scripts/build_index.py" [workbench_dir]
   ```
   The script writes `Workbench/INDEX.md` and `Workbench/.index.json` directly.

3. Confirm both output files exist and `Workbench/.index.json` is valid JSON with `schema_version: 1`.

4. Return `<pipeline-result>` v2 with:
   - `outcome: success` if both files were written and JSON validates
   - `outcome: exception` with diagnostics if the script errored or output is missing/malformed

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

- Never modifies any PLAN file — read-only access to `Workbench/*.md` and `Workbench/.audit/*.json`.
- Full rebuild on every regen (no incremental updates in v1).
- INDEX regen failure does NOT halt the pipeline (auxiliary operation).
- The orchestrator commits the INDEX outputs in a separate commit: `plan-pipeline: update-workbench-index`.
