---
name: convert-pdf
description: 'Orchestrate full document-to-Markdown pipeline for a PDF, DOCX, or pre-converted MD file. Chains doc-to-md (raw conversion), segment-doc (boundary detection + user confirmation), and reformat-md (heading normalisation, artefact removal, image characterisation, frontmatter). Manages sources/ and originals/ directory structure, updates both INDEX files, and writes a session-memory sentinel block in the project CLAUDE.md. Parent-session-only. Trigger phrases: "convert PDF", "convert DOCX", "process document", "ingest document", "run convert-pdf".'
---

## Parent Session Only

**`convert-pdf` runs only in the parent session.** It requires interactive Human turn-taking (for `segment-doc` confirmation) and access to Bash, Write, Edit, and Read tools in the parent session context. Do not dispatch from a subagent.

---

## Purpose

`convert-pdf` is the end-to-end orchestrator that chains three sub-skills to transform a source document (PDF, DOCX, or pre-converted MD) into clean, navigable Markdown files. It manages the `sources/` and `originals/` directory structure, maintains both INDEX files, and writes a sentinel pointer block in the project CLAUDE.md.

---

## Input

| Argument | Type | Description |
|---|---|---|
| `source_path` | string (required) | Path to the source file (.pdf, .docx, or .md) |

---

## Orchestration Flow

### Step 1 - Prepare directories

Create `sources/` and `originals/` directories if they do not already exist:

```bash
mkdir -p sources originals
```

### Step 2 - Convert source to raw Markdown

Invoke `Skill("doc-to-md")` with `source_path`. Capture the returned path as `raw_md_path`.

- For `.pdf` inputs: `raw_md_path` = `originals/<basename>-raw.md`
- For `.docx` inputs: `raw_md_path` = `originals/<basename>-raw.md`
- For `.md` inputs: `raw_md_path` = `source_path` (pass-through, unchanged)

### Step 3 - Copy original source file to originals/

Copy (do not move) the original source file into `originals/` if it is not already there (per D14 - file preservation):

```bash
cp <source_path> originals/<source_filename>
```

The original file at `source_path` is preserved intact. The user may delete it manually after confirming the `originals/` copy is intact.

- Skip this copy step if `source_path` is already within `originals/`.
- For `.md` pass-through inputs where `source_path` is already the raw MD, skip the copy.

### Step 4 - Segment the raw Markdown

Invoke `Skill("segment-doc")` with `raw_md_path`. This skill presents the proposed segment list to the user and awaits confirmation before writing any files.

Capture the returned list of written segment file paths as `segment_paths`.

### Step 5 - Reformat each segment

For each `segment_path` in `segment_paths`:

Invoke `Skill("reformat-md")` with two positional arguments:
1. `segment_path` - the raw segment file
2. `source_path` - the original source path (for vision-based image characterisation)

Calling convention: `Skill("reformat-md", "<segment_path> <source_path>")`

Collect all returned output file paths into `output_paths`.

### Step 6 - Update sources/INDEX.md

Follow the workflow defined in `workflows/update-sources-index.md`.

Pass `output_paths` as the list of newly produced files to add to the index.

### Step 7 - Update originals/INDEX.md

Follow the workflow defined in `workflows/update-originals-index.md`.

Pass all files now present in `originals/` (original source file + raw MD + raw segment files) as the files to index.

### Step 8 - Write CLAUDE.md sentinel block

Follow the workflow defined in `workflows/update-claude-md-sentinel.md`.

---

## Config

If `.claude/convert-pdf.yaml` exists in the project root, `reformat-md` reads it during Step 5 to merge field overrides into the generated frontmatter. See `.claude/skills/convert-pdf/references/config-schema.md` for the full schema.

---

## Directory Structure

After a successful run, the project will contain:

```
sources/
  INDEX.md                    <- reformatted document index
  <slug>.md                   <- one file per confirmed segment (reformatted)
originals/
  INDEX.md                    <- originals index
  <source-filename>           <- copy of original PDF/DOCX
  <basename>-raw.md           <- raw converted Markdown (from doc-to-md)
  <basename>-raw-seg-01.md    <- raw segment 1 (from segment-doc)
  <basename>-raw-seg-02.md    <- raw segment 2
  ...
```

---

## Error Handling

| Condition | Action |
|---|---|
| `doc-to-md` halts (pandoc/pdftotext missing) | Surface the sub-skill's diagnostic to the user; halt the orchestrator |
| `segment-doc` returns "cancel" | Halt with no files written to `sources/`; leave `originals/` as-is |
| `reformat-md` fails for a segment | Log the failure, continue with remaining segments, report failed paths in the summary |
| `sources/INDEX.md` write fails | Log warning; continue |
| `originals/INDEX.md` write fails | Log warning; continue |
| CLAUDE.md sentinel write fails | Log warning; continue |

---

## Summary Report

After Step 8, emit a summary to the user:

```
convert-pdf complete.
  Source: <source_path>
  Segments: <N> produced
  Reformatted files:
    - sources/<slug-1>.md
    - sources/<slug-2>.md
    ...
  Originals: originals/ (see originals/INDEX.md)
  Sources: sources/ (see sources/INDEX.md)
  CLAUDE.md: sentinel block written/updated
```
