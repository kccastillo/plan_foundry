# Workflow: Update sources/INDEX.md

This workflow is invoked by `convert-pdf` Step 6 after `reformat-md` has produced one or more output files in `sources/`.

---

## Inputs

| Input | Description |
|---|---|
| `output_paths` | List of newly produced reformatted file paths (`sources/<slug>.md`) |

---

## INDEX.md Structure

`sources/INDEX.md` uses the following format:

```yaml
---
asset_id: sources-index
kind: index
title: "Sources Index"
created: <date of first run>
last_updated: <today>
---
```

```markdown
# Sources Index

Reformatted source documents produced by `convert-pdf`. Each entry is a clean, navigable Markdown file derived from a PDF, DOCX, or pre-converted MD original.

| Slug | Title | Type | Date | Source |
|---|---|---|---|---|
| <slug> | <title> | <type> | <date> | <split_from> |
```

---

## Update Logic

### 1. Check whether sources/INDEX.md exists

**If `sources/INDEX.md` does not exist:**

Create it from scratch. Use today's date for both `created` and `last_updated`. Write an empty table body, then proceed to Step 3 to add the new rows.

**If `sources/INDEX.md` exists:**

Read the existing file. Parse the table rows. Extract the set of slugs already listed.

### 2. Compute new rows

For each path in `output_paths`:

1. Read the file's YAML frontmatter to extract: `slug`, `title`, `type`, `date`, `file_provenance.split_from`.
2. Check whether the slug is already present in the existing table. If already listed, skip (idempotent).
3. If not listed, add a new row:
   ```
   | <slug> | <title> | <type> | <date> | <split_from> |
   ```

### 3. Sort rows

Sort all table rows by `date` descending (newest first). Where dates are equal, sort by slug alphabetically.

### 4. Write updated INDEX.md

Reconstruct the full `sources/INDEX.md` with:
- Updated `last_updated: <today>` in frontmatter
- Preserved `created:` date (do not change if file already existed)
- Full sorted table

Write via Write tool only. Do not echo content as agent text.

---

## Example sources/INDEX.md

```yaml
---
asset_id: sources-index
kind: index
title: "Sources Index"
created: 2026-07-23
last_updated: 2026-07-23
---
```

```markdown
# Sources Index

Reformatted source documents produced by `convert-pdf`. Each entry is a clean, navigable Markdown file derived from a PDF, DOCX, or pre-converted MD original.

| Slug | Title | Type | Date | Source |
|---|---|---|---|---|
| annual-report-2025-seg-02 | Financial Summary | source-document | 2026-07-23 | annual-report-2025-raw |
| annual-report-2025-seg-01 | Executive Overview | source-document | 2026-07-23 | annual-report-2025-raw |
```
