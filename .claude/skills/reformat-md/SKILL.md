---
name: reformat-md
description: Reformat a raw segment Markdown file — normalise headings, strip PDF artefacts, fix definition terms, consolidate tables, characterise image placeholders via Claude vision (PDF source only; DOCX skips characterisation), apply YAML frontmatter — and write the clean output to sources/<slug>.md. All output via Write tool only; content is never echoed as agent text. Trigger phrases: "reformat segment", "clean up markdown", "apply frontmatter", "reformat document", "clean segment".
---

## Purpose

`reformat-md` transforms a raw segment Markdown file (produced by `segment-doc`) into a clean, formatted Markdown file with YAML frontmatter. It is the third stage of the `convert-pdf` pipeline and may also be invoked standalone.

This skill runs in the **parent session** only.

---

## Calling Convention (Two Positional Arguments)

`reformat-md` receives two positional arguments:

1. **`segment_path`** (required) — path to the raw segment Markdown file to reformat
2. **`source_path`** (optional) — path to the original source PDF or DOCX file, used for vision-based image characterisation. If omitted, image characterisation is skipped and placeholder text is emitted instead.

Example invocation from the orchestrator:
```
Skill("reformat-md", "<segment_path> <source_path>")
```

The two-argument calling convention must be documented explicitly at the top of this Body section so the orchestrator can wire the call correctly.

---

## Inputs

| Argument | Position | Type | Description |
|---|---|---|---|
| `segment_path` | 1 | string (required) | Path to the raw segment MD file |
| `source_path` | 2 | string (optional) | Path to the original source PDF/DOCX for vision lookup |

---

## Reformatting Actions

Apply the following actions in order. After all actions are applied, write the result via the Write tool. Do NOT echo the reformatted content as agent text output (D11).

### Action 1 — Heading Normalisation

1. Detect the document's heading hierarchy from the raw segment (the lowest heading level present is the "document title" level).
2. Remap headings so that:
   - The document title (or first `#` heading) becomes `#`
   - Top-level sections become `##`
   - Subsections become `###`, and so on recursively
3. Unwrap `## **Bold text**` patterns: if a heading contains only bolded text (e.g. `## **3.1 Overview**`), and a section number is present in the text (e.g. `3.1`), convert it to a plain heading at the appropriate level: `### 3.1 Overview`.

### Action 2 — PDF Artefact Removal

Apply the following cleanup passes in order:

1. **Trailing whitespace:** strip trailing whitespace from each line.
2. **Orphaned page numbers:** remove lines that contain only a digit or a "Page N of M" / "Page N" pattern (case-insensitive).
3. **Split TOC rows:** consolidate consecutive short lines (≤ 60 characters) that together form a single TOC entry — typically a section title fragment on one line and a page number on the next — into a single line.
4. **Running header/footer repetitions:** remove repeated occurrences of identified running header/footer boilerplate lines (as flagged by `segment-doc`'s detection pass). If the segment was not produced by `segment-doc`, skip this sub-pass.

### Action 3 — Definition Term Fix

Identify headings that function as definition terms: a heading followed immediately by a definition paragraph, with no sub-headings between them.

Convert these to bold paragraph text:
```
**Term**

Definition paragraph text.
```

Do not apply this transformation to headings that have sub-headings below them.

### Action 4 — Table Consolidation

Detect fragmented Markdown table rows: pipe-separated (`|`) lines that are broken across multiple physical lines, producing an incomplete table. Merge them into valid Markdown tables with a proper header row, separator row (`|---|---|`), and body rows.

If a table already has a valid separator row, leave it as-is.

### Action 5 — Image Placeholder Handling

Detect image placeholder patterns in the segment:
- Inline image syntax with an empty or generic (`image`, `img`, or similar) src attribute
- OCR gap markers such as `[IMAGE]`, `[FIGURE]`, `<image>`
- Explicit figure references: `[Figure N]`, `[Fig. N]`

For each placeholder detected:

#### PDF source (vision characterisation — D5)

1. Grep the surrounding segment text (±20 lines around the placeholder) for nearby headings and captions to estimate the figure's location (section name, caption text, approximate page position).
2. Read the source PDF at the estimated page range (±2 pages of the estimated page) using the Read tool for vision lookup.
3. Generate a prose description of the figure based on what the vision read reveals.
4. Replace the placeholder with:
   ```
   > **Figure N:** <prose description>
   ```
   Where N is the figure number if determinable from surrounding text, or a sequential counter if not.

#### DOCX source (no characterisation — D5)

Skip vision characterisation. Emit the following placeholder at the image location:
```
> **Figure N:** [image — characterisation not available for DOCX inputs]
```

DOCX inputs do not have readable page structure accessible via the Read tool; characterisation is not available (per D5).

#### Source path absent

If no `source_path` was provided, treat as DOCX source: emit the placeholder text without characterisation.

---

## Action 6 — Frontmatter Application

Compute and apply a YAML frontmatter block at the top of the output file.

### Frontmatter fields

| Field | Value |
|---|---|
| `slug` | Filename stem of the segment file, kebab-cased, without extension (e.g. `contract-raw-seg-01` → `contract-seg-01`, stripping `-raw`) |
| `date` | Today's date (ISO 8601, e.g. `2026-07-23`) |
| `version` | `"1.0"` (default; override from `.claude/convert-pdf.yaml` if present) |
| `type` | `"source-document"` |
| `title` | First `#` heading in the segment, or first non-blank line if no `#` heading |
| `file_provenance` | `{split_from: <source-slug>, split_date: <today>}` |
| `document_provenance` | `{document: <title>, issuer: "", date: "", version: ""}` — issuer/date/version left blank for human to fill if not detectable from the document body |

### Config override

If `.claude/convert-pdf.yaml` exists in the project root, read it and merge its `fields:` block over the defaults. Fields in `convert-pdf.yaml` take precedence over defaults; fields not present in the file use the defaults above.

Example `.claude/convert-pdf.yaml`:
```yaml
fields:
  version: "2.0"
  type: "reference-document"
```

---

## Output

- **Output file path:** `sources/<slug>.md`
  - `<slug>` is the computed slug from the frontmatter application step
- **Write constraint (D11):** write reformatted content via Write tool only. Never echo reformatted content as agent text.

---

## Return Value

The skill returns a single string: the path to the written output file (`sources/<slug>.md`).

---

## Error Handling

| Condition | Action |
|---|---|
| `segment_path` does not exist | Halt with `[reformat-md] ERROR: segment file not found: <path>` |
| Segment file is empty | Halt with `[reformat-md] ERROR: segment file is empty: <path>` |
| Vision read fails (PDF source) | Log warning, emit placeholder text, continue |
| `.claude/convert-pdf.yaml` is malformed | Log warning, use defaults, continue |
