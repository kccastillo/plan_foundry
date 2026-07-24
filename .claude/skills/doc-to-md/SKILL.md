---
name: doc-to-md
description: Convert a PDF, DOCX, or already-converted MD file to raw Markdown. For PDFs, uses pdftotext (poppler-utils) as the primary path (file→file, no token ceiling); falls back to Claude native PDF reader with a documented page-count ceiling warning if pdftotext is absent. For DOCX, requires pandoc on PATH and halts with a diagnostic if absent. MD inputs are passed through unchanged. Output written to originals/<source-basename>-raw.md via the Write tool only — content is never echoed as agent text. Trigger phrases: "convert PDF", "convert DOCX", "doc to markdown", "ingest PDF", "ingest document".
---

## Purpose

`doc-to-md` converts a single source file (PDF, DOCX, or pre-converted MD) into a raw Markdown file suitable for segmentation by `segment-doc`. It is the first stage of the `convert-pdf` pipeline and may also be invoked standalone.

This skill runs in the **parent session** only. It requires interactive tool access (Bash for pandoc/pdftotext checks; Write tool for output).

---

## Inputs

| Argument | Type | Description |
|---|---|---|
| `source_path` | string (required) | Absolute or relative path to the source file (.pdf, .docx, or .md) |

---

## Format Detection

Format is determined by file extension (case-insensitive):

| Extension | Action |
|---|---|
| `.pdf` | PDF conversion path (pdftotext primary, Claude native fallback) |
| `.docx` | DOCX conversion via pandoc |
| `.md` | Pass-through — return source path unchanged, no conversion |

---

## PDF Conversion Path

### Primary path — pdftotext (D15)

1. Check that `pdftotext` is available: `which pdftotext` via Bash.
2. If present: run `pdftotext -layout <source_path> <output_path>` (file→file conversion). This avoids the model output-token ceiling entirely.
3. If `pdftotext` is absent from PATH: emit the warning below and fall back to the Claude native reader path.

**Fallback warning (emit verbatim when pdftotext is absent):**
```
[doc-to-md] WARNING: pdftotext not found. Falling back to Claude native PDF reader.
PDFs >50 pages may exceed the Write tool output ceiling. Install poppler-utils
(e.g. `brew install poppler` / `apt install poppler-utils`) to lift this ceiling.
```

### Fallback path — Claude native PDF reader

1. Use the Read tool with the PDF file path to ingest the document content.
2. Write the resulting content to the output path via the Write tool.
3. Do NOT echo the document content as agent text — pass directly from Read output to Write input.

---

## DOCX Conversion Path

### pandoc PATH check

Before attempting DOCX conversion, verify pandoc is available:

```bash
which pandoc
```

If pandoc is not found, halt immediately with the following diagnostic (do not attempt conversion):

```
[doc-to-md] ERROR: pandoc not found on PATH. Install pandoc
(https://pandoc.org/installing.html) and retry.
```

### Conversion command

```bash
pandoc -f docx -t markdown --wrap=none -o <output_path> <source_path>
```

Run via Bash tool. The `--wrap=none` flag prevents pandoc from hard-wrapping long lines.

---

## MD Pass-Through

When the input file has a `.md` extension:
- Return the source path unchanged.
- Do not copy, move, or modify the file.
- The orchestrator (or caller) passes this path directly to `segment-doc`.

---

## Output

- **Output file path:** `originals/<source-basename>-raw.md`
  - `<source-basename>` is the source filename without extension. Example: `contract.pdf` → `originals/contract-raw.md`.
  - For MD pass-through: no output file is written; return the source path as-is.
- **Write constraint (D11):** write raw MD content via Write tool only. Never echo document body as agent text output.

---

## Return Value

The skill returns a single string: the output file path (absolute or relative, matching what was written). For MD pass-through, this is the original source path unchanged.

---

## Error Handling

| Condition | Action |
|---|---|
| pandoc absent (DOCX input) | Halt with `[doc-to-md] ERROR: pandoc not found on PATH` diagnostic; do not write any output |
| pdftotext absent (PDF input) | Emit WARNING and fall back to Claude native reader |
| Source file does not exist | Halt with `[doc-to-md] ERROR: source file not found: <path>` |
| Conversion produces empty output | Halt with `[doc-to-md] ERROR: conversion produced empty output for <path>` |
| Unsupported file extension | Halt with `[doc-to-md] ERROR: unsupported file type '<ext>'. Supported: .pdf, .docx, .md` |
