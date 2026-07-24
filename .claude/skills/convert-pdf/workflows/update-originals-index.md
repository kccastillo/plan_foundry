# Workflow: Update originals/INDEX.md

This workflow is invoked by `convert-pdf` Step 7 after all segment files and the original source file have been written to `originals/`.

---

## Inputs

| Input | Description |
|---|---|
| `originals_dir` | Path to the originals directory (default: `originals/`) |
| `new_files` | List of files written to `originals/` in this run (original source + raw MD + raw segment files) |
| `output_paths` | List of reformatted file paths in `sources/` that were derived from these originals |

---

## INDEX.md Structure

`originals/INDEX.md` uses the following format:

```yaml
---
asset_id: originals-index
kind: index
title: "Originals Index"
created: <date of first run>
last_updated: <today>
---
```

```markdown
# Originals Index

Original source files and raw conversion intermediates produced by `convert-pdf`.

| Filename | Kind | Date | Derived Files |
|---|---|---|---|
| <filename> | <kind> | <date> | <comma-separated slugs in sources/> |
```

---

## File Kind Classification

Classify each file in `originals/` by its kind:

| Pattern | Kind |
|---|---|
| `.pdf` extension | `original-pdf` |
| `.docx` extension | `original-docx` |
| `-raw.md` suffix | `raw-md` |
| `-raw-seg-<N>.md` suffix | `raw-segment` |

---

## Update Logic

### 1. Check whether originals/INDEX.md exists

**If `originals/INDEX.md` does not exist:**

Create it from scratch. Use today's date for both `created` and `last_updated`. Write an empty table body, then proceed to add rows for all new files.

**If `originals/INDEX.md` exists:**

Read the existing file. Parse the table rows. Extract the set of filenames already listed.

### 2. Compute new rows

For each file in `new_files`:

1. Classify the file by kind (see table above).
2. Use today's date as the `Date` value.
3. Determine `Derived Files`: for `original-pdf`, `original-docx`, and `raw-md` entries, list the slugs of all reformatted files in `sources/` derived from this source (from `output_paths`, read the frontmatter `file_provenance.split_from` to match). For `raw-segment` entries, list the slug of the single reformatted file it produced.
4. Check whether the filename is already present in the existing table. If already listed, update the `Derived Files` column if new derived files have been added. Otherwise skip.
5. If not listed, add a new row.

### 3. Sort rows

Sort all table rows by kind first (original-pdf, original-docx, raw-md, raw-segment), then by filename alphabetically within each kind.

### 4. Write updated INDEX.md

Reconstruct the full `originals/INDEX.md` with:
- Updated `last_updated: <today>` in frontmatter
- Preserved `created:` date (do not change if file already existed)
- Full sorted table

Write via Write tool only. Do not echo content as agent text.

---

## Example originals/INDEX.md

```yaml
---
asset_id: originals-index
kind: index
title: "Originals Index"
created: 2026-07-23
last_updated: 2026-07-23
---
```

```markdown
# Originals Index

Original source files and raw conversion intermediates produced by `convert-pdf`.

| Filename | Kind | Date | Derived Files |
|---|---|---|---|
| annual-report-2025.pdf | original-pdf | 2026-07-23 | annual-report-2025-seg-01, annual-report-2025-seg-02 |
| annual-report-2025-raw.md | raw-md | 2026-07-23 | annual-report-2025-seg-01, annual-report-2025-seg-02 |
| annual-report-2025-raw-seg-01.md | raw-segment | 2026-07-23 | annual-report-2025-seg-01 |
| annual-report-2025-raw-seg-02.md | raw-segment | 2026-07-23 | annual-report-2025-seg-02 |
```
