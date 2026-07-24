---
name: segment-doc
description: Detect document boundaries in a raw Markdown file, propose a numbered segment list (with boundary signals) for user confirmation, then write per-document segment files to originals/. Does not write any files before the user confirms the segmentation. Handles yes/edit/cancel responses. Trigger phrases: "segment document", "split document", "detect segments", "divide document into sections".
---

## Purpose

`segment-doc` analyses a raw Markdown file, detects natural document boundaries, presents a proposed segment list to the user for confirmation, and writes per-segment Markdown files to `originals/` only after the user approves. It is the second stage of the `convert-pdf` pipeline and may also be invoked standalone.

This skill runs in the **parent session** only. It requires Human turn-taking for the confirmation step.

---

## Inputs

| Argument | Type | Description |
|---|---|---|
| `raw_md_path` | string (required) | Path to the raw Markdown file produced by `doc-to-md` (or any raw MD file) |
| `output_dir` | string (optional, default: `originals/`) | Directory to write segment files into |

---

## Detection Pass

Read the raw Markdown file in full. Scan for boundary signals in the following priority order:

### Signal 1 — TOC block (highest priority)

Detect a heading containing "contents" or "table of contents" (case-insensitive) followed by a list of numbered or linked entries. Each entry in the TOC is a candidate segment name. A TOC-detected segment spans from the start of the section named in the TOC entry to the start of the next TOC-listed section (or end of file for the last entry).

### Signal 2 — Level-1 headings

Detect `# Title` headings (ATX style) that do NOT appear within the TOC block itself. Each such heading marks the start of a new segment. Where a TOC is present, TOC entries take precedence over bare `#` headings that the TOC already names.

### Signal 3 — Repeating page header/footer boilerplate

Detect short lines (≤ 10 words) that appear at intervals of 30–80 lines with near-identical text (allowing minor variation such as page numbers). These are running headers or footers. Where they appear at regular intervals, use them as supplementary boundary markers rather than primary segment dividers — they indicate page boundaries within a section, not section boundaries.

### Signal 4 — Explicit page-break markers (lowest priority)

Detect lines containing only `---`, `\f` (backslash-f escape), or the Unicode form-feed character (U+000C). These are explicit page-break markers and serve as fallback segment boundaries when no higher-priority signals are present.

---

## Proposed Segment List

After the detection pass, produce a numbered proposed segment list in the following format. Present it to the user as an assistant message:

```
Proposed segments (N total):
1. <Segment Name> — lines <start>–<end> [boundary: <signal type>]
2. <Segment Name> — lines <start>–<end> [boundary: <signal type>]
...

Confirm segmentation? (yes / edit / cancel)
```

Where `<signal type>` is one of: `toc-entry`, `level-1-heading`, `page-header-footer`, `page-break-marker`.

Do NOT write any segment files before the user confirms. Await the user's reply.

---

## User Confirmation Flow

### "yes"

Write each segment to:
```
originals/<source-slug>-raw-seg-<N>.md
```

Where:
- `<source-slug>` is the raw MD filename stem, kebab-cased (e.g. `contract-raw`)
- `<N>` is the 1-based segment number, zero-padded to at least 2 digits (e.g. `01`, `02`, `10`)

Write each segment file via the Write tool only. Do not echo segment content as agent text.

Before writing, check whether the `originals/` directory (or the specified `output_dir`) exists. If it does not exist, create it via Bash `mkdir -p <output_dir>`.

Return the list of written segment file paths.

### "edit"

Accept revised segment boundaries from the user. The user may:
- Merge segments (e.g. "merge segments 3 and 4")
- Split a segment (e.g. "split segment 2 at line 145")
- Rename a segment (e.g. "rename segment 1 to 'Introduction'")
- Adjust start/end lines

Re-display the revised proposed segment list in the same format. Ask "Confirm segmentation? (yes / edit / cancel)" again. Repeat until the user confirms or cancels.

### "cancel"

Halt immediately. Do not write any files. Emit:
```
[segment-doc] Segmentation cancelled. No files written.
```

---

## Output

- **Written files:** `originals/<source-slug>-raw-seg-<N>.md` for each confirmed segment
- **Return value:** a list of written segment file paths (one per segment), in order

---

## Constraints

- Do NOT write any files before the user confirms (D3).
- All segment file writes use the Write tool only — never echo segment content as agent output.
- If the detection pass finds no boundary signals, propose treating the entire document as a single segment (segment 1, lines 1–EOF, boundary: none-detected) and present this to the user for confirmation.
