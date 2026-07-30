# Workflow: Write CLAUDE.md Sentinel Block

This workflow is invoked by `convert-pdf` Step 8. It writes (or updates) a sentinel-bounded pointer block in the target project's CLAUDE.md, recording that `sources/` and `originals/` exist and linking to their INDEX files.

---

## Sentinel Markers

```
<!-- convert-pdf:sources-start -->
<!-- convert-pdf:sources-end -->
```

---

## Block Content

The block written between the sentinel markers is:

```markdown
<!-- convert-pdf:sources-start -->
## Document Sources

This project uses `convert-pdf` to ingest and reformat PDF/DOCX documents.

- `sources/` - reformatted per-document Markdown files; see [`sources/INDEX.md`](sources/INDEX.md) for the full list
- `originals/` - original source files and raw conversion intermediates; see [`originals/INDEX.md`](originals/INDEX.md)

To process a new document: `Skill("convert-pdf")` with the file path.
<!-- convert-pdf:sources-end -->
```

---

## Logic

### Case 1 - CLAUDE.md does not exist

Create a new `CLAUDE.md` file containing only the sentinel block (as its entire content). Write via Write tool.

### Case 2 - CLAUDE.md exists, sentinel markers absent

Read `CLAUDE.md`. Determine the insertion point:

**Placement rule:**

- If the file contains the plan-foundry operating-rules sentinel closing marker (`<!-- plan-foundry:operating-rules-end -->`): insert the convert-pdf block **immediately after** that marker, not at the file's absolute end. Insert a blank line before the block for readability.
- Otherwise: append the block at the absolute end of the file, preceded by a blank line.

Write the updated file via the Write tool (full file rewrite) or the Edit tool (targeted insertion). Prefer Edit if the file is large (> 200 lines) to avoid re-writing unchanged content.

### Case 3 - CLAUDE.md exists, sentinel markers present

Read `CLAUDE.md`. Locate the existing `<!-- convert-pdf:sources-start -->` and `<!-- convert-pdf:sources-end -->` markers.

Replace the content between the markers (inclusive of the markers themselves) with the current block content. This is an idempotent update - running `convert-pdf` multiple times produces the same sentinel block.

Use the Edit tool to perform the replacement. Write the exact sentinel block content (start marker + body + end marker) as the replacement string.

---

## Constraint

This sentinel block is project-local and NOT bundle-managed. It survives `plan-foundry-sync` because it lives outside the bundle sentinel zone (`<!-- plan-foundry:operating-rules-start/end -->`). The plan-foundry sync skill must not overwrite content between `convert-pdf` sentinel markers.

---

## Error Handling

| Condition | Action |
|---|---|
| CLAUDE.md write fails | Log `[convert-pdf] WARNING: failed to write sentinel block to CLAUDE.md: <reason>`. Continue - this is non-fatal. |
| Sentinel markers are malformed (start without end, or vice versa) | Log `[convert-pdf] WARNING: malformed sentinel markers in CLAUDE.md; appending fresh block at end of file.` Append the block at end of file as Case 2. |
