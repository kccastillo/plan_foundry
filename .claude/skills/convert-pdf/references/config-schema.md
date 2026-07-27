---
asset_id: convert-pdf-config-schema
kind: reference
title: "convert-pdf Config Schema (.claude/convert-pdf.yaml)"
topic_tags: [convert-pdf, config, frontmatter, document-ingestion]
last_consulted: ""
consulted_by: []
---

# convert-pdf Config Schema

`convert-pdf` reads an optional project-local config file at `.claude/convert-pdf.yaml`. This file allows project owners to override frontmatter defaults applied by `reformat-md` during document reformatting.

The config file is **project-local** and **not bundle-managed**: it is created by the project owner in their target project's `.claude/` directory, and it survives `plan-foundry-sync` (the sync script does not overwrite files outside the bundle sentinel zone).

---

## File Location

```
<project-root>/.claude/convert-pdf.yaml
```

---

## Schema

The config file is a flat YAML document with a single top-level `fields:` key.

```yaml
fields:
  <field-name>: <override-value>
  ...
```

### Overridable Fields and Defaults

| Field | Default Value | Description |
|---|---|---|
| `version` | `"1.0"` | Document version stamped in frontmatter |
| `type` | `"source-document"` | Document type classification in frontmatter |
| `issuer` | `""` | Issuer/organisation from `document_provenance` |
| `date` | `""` | Document date from `document_provenance` (not the conversion date — the source document's publication date) |
| `document_version` | `""` | Version from `document_provenance` (the source document's version, not the frontmatter `version`) |

**Note:** The following frontmatter fields are always computed at conversion time and cannot be overridden via config:

| Field | Always Computed As |
|---|---|
| `slug` | Derived from segment filename |
| `date` (frontmatter top-level) | Today's date (the conversion date) |
| `title` | First `#` heading in the segment, or first non-blank line |
| `file_provenance.split_from` | Source file slug |
| `file_provenance.split_date` | Today's date |

---

## Merge Behaviour

When `.claude/convert-pdf.yaml` is present:

1. `reformat-md` reads the `fields:` block.
2. Each key in `fields:` overrides the corresponding default.
3. Keys not present in the config file use the defaults listed above.
4. Unknown keys in `fields:` are logged as warnings and ignored.

---

## Example `.claude/convert-pdf.yaml`

```yaml
# Project-local overrides for convert-pdf frontmatter defaults.
# Place this file at .claude/convert-pdf.yaml in your project root.

fields:
  # Stamp all ingested documents with version 2.0 rather than the default 1.0
  version: "2.0"

  # Classify documents as reference-document rather than source-document
  type: "reference-document"

  # Pre-fill the issuer for all documents from this source
  issuer: "Acme Corporation"
```

---

## v2 Extension (Future)

A future `extends:` key is reserved for inheriting from a base config file. It is not implemented in v1. Do not use `extends:` in v1 configs — it will be ignored with a warning.

```yaml
# Reserved for v2 — not functional in v1
extends: "../../shared/.claude/convert-pdf.yaml"

fields:
  type: "project-specific-document"
```
