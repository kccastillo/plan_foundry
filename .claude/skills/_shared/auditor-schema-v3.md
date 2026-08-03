# Auditor Schema v3

Full JSON Schema for the v3 audit payload. Both auditor skills (`audit-sufficiency` and `audit-haiku-safe`) emit this format. The orchestrator parses, validates, and stores these payloads as sibling JSON files in `Workbench/.audit/`.

---

## Storage

Audit results are stored as:

```
Workbench/.audit/<plan-id>-<stage>-<iter>.json
```

Where:
- `<plan-id>` = the PLAN filename without the `.md` extension (e.g. `PLAN-022_audit-and-index-v2`)
- `<stage>` = `sufficiency` or `plan_safety`
- `<iter>` = the integer iteration number (e.g. `1`, `2`, `3`)

Files are committed (not gitignored). Separate commit per audit write.

---

## Fingerprint generation

Fingerprints are computed **by the orchestrator**, not the auditor. The auditor emits findings without fingerprints; the orchestrator generates them after parsing the return.

Formula:
```python
import hashlib
fingerprint = hashlib.sha256(
    f"{finding['code']}|{finding['level']}|{finding['category']}|{finding.get('location', '')}".encode()
).hexdigest()[:8]
```

`suggested_fix` is excluded from fingerprint inputs so that fix-refinements across iterations maintain the recurrence chain. `patch` is likewise excluded from fingerprint inputs, for the same reason.

`location` is concatenated verbatim with no normalisation - whitespace, case, and ordinal all move the fingerprint. When a Step insertion shifts a bare-ordinal `location` (e.g. `'Step 7'`), the orchestrator remaps the affected fingerprint-keyed records as part of applying the renumber (PLAN-AJ1), so an auditor should keep emitting the ordinal form the worked example below shows rather than inventing a stable identifier of its own.

---

## JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12",
  "title": "AuditResultV2",
  "type": "object",
  "required": ["schema_version", "auditor", "plan_id", "iteration", "findings", "summary"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {
      "type": "integer",
      "const": 3,
      "description": "Schema version. Always 3 for this format."
    },
    "auditor": {
      "type": "string",
      "enum": ["sufficiency", "plan_safety"],
      "description": "Which auditor produced this result."
    },
    "plan_id": {
      "type": "string",
      "description": "PLAN filename without .md extension (e.g. 'PLAN-022_audit-and-index-v2')."
    },
    "iteration": {
      "type": "integer",
      "minimum": 1,
      "description": "Audit iteration number for this auditor on this PLAN. Starts at 1."
    },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["code", "level", "category", "location", "message"],
        "additionalProperties": false,
        "properties": {
          "code": {
            "type": "string",
            "pattern": "^([SH]\\d{3}|SFV\\d{3}|PPV\\d{3}|PSZ\\d{3}|FAL\\d{3}(-[a-z])?)$",
            "description": "Finding code from an auditor's closed enum. Admitted families: sufficiency S### / plan-safety H### (with S999/H999 for OTHER); substrate-fidelity SFV###; platform-portability PPV###; plan-sizing PSZ###; falsifiability FAL### with an optional -a..-f sub-letter suffix (e.g. 'S001', 'H302', 'SFV001', 'PPV003', 'PSZ001', 'FAL001-a')."
          },
          "level": {
            "type": "string",
            "enum": ["error", "warning", "note"],
            "description": "Severity per RFC-2119 / SARIF alignment. error = MUST fix; warning = SHOULD fix; note = FYI."
          },
          "category": {
            "type": "string",
            "description": "Category name matching the code range (e.g. 'assumptions', 'concreteness', 'safety'). Must be 'OTHER' when code is S999/H999."
          },
          "location": {
            "type": "string",
            "description": "Free-text pointer to where the finding occurs (e.g. 'Step 7', 'Verification / acceptance check 3', 'Context paragraph 2')."
          },
          "message": {
            "type": "string",
            "description": "Human-readable description of the finding. For S999/H999, must include '[NEW CATEGORY NEEDED: <proposed>]'."
          },
          "suggested_fix": {
            "type": "string",
            "description": "Optional. Sketch of fix direction. NOT included in fingerprint inputs."
          },
          "patch": {
            "type": "object",
            "additionalProperties": false,
            "required": ["old_string", "new_string"],
            "properties": {
              "old_string": {
                "type": "string",
                "description": "Exact anchor text to locate in the target file."
              },
              "new_string": {
                "type": "string",
                "description": "Exact replacement text."
              },
              "occurrence": {
                "type": "integer",
                "minimum": 1,
                "default": 1,
                "description": "Expected count of old_string in the target file. old_string must occur in the target file exactly occurrence times for the patch to apply. Applied verbatim by the orchestrator and never modified."
              }
            },
            "description": "Optional. Literal string-replacement repair for this finding, required when the finding backs a mechanically_forced triaged item. See Patch semantics below."
          },
          "fingerprint": {
            "type": "string",
            "pattern": "^[0-9a-f]{8}$",
            "description": "8-character hex SHA-256 digest computed by orchestrator after parsing. Auditor omits this field; orchestrator populates it before writing to disk."
          },
          "status": {
            "type": "string",
            "enum": ["new", "resolved", "still-present", "disputed-and-reaffirmed", "disputed-and-dropped"],
            "description": "Optional. Populated only in re-audit iterations (iteration > 1). Describes this finding's status relative to the prior iteration."
          }
        }
      }
    },
    "summary": {
      "type": "object",
      "required": ["error_count", "warning_count", "note_count"],
      "additionalProperties": false,
      "properties": {
        "error_count": {
          "type": "integer",
          "minimum": 0,
          "description": "Count of findings with level: error."
        },
        "warning_count": {
          "type": "integer",
          "minimum": 0,
          "description": "Count of findings with level: warning."
        },
        "note_count": {
          "type": "integer",
          "minimum": 0,
          "description": "Count of findings with level: note."
        }
      }
    }
  }
}
```

---

## Patch semantics

A patch's target file is always the PLAN under audit. A patch MUST NOT be aimed at any other file, including a source file the finding cites.

A finding whose corresponding `triaged_human_items` entry classifies `mechanically_forced` requires a patch. If the repair cannot be expressed as an exact string replacement, the item is not mechanically forced and MUST be classified `real_judgement_call` instead.

A patch that does not apply - its anchor is absent, or occurs a different number of times than `occurrence` expects - demotes that one finding to the human surface without retry or re-derivation, while the rest of the round still applies. An anchor invalidated by an earlier patch in the same array is a demotion for the same reason, not an error.

A `code` plus `location` pair matching more than one finding in the round demotes every finding it matches, and no patch from that group is applied.

## Three severity levels

| Level | RFC-2119 | When to use | Orchestrator action |
|---|---|---|---|
| `error` | MUST fix | The finding would cause downstream work to halt, error, or produce incorrect output. | Pipeline advances only when error_count == 0. |
| `warning` | SHOULD fix | The finding is a real concern but would not block correct execution if ignored. | Human may acknowledge; orchestrator strips on next audit if fingerprint is in `audit_acknowledgements`. |
| `note` | FYI | Informational; no fix required. | Displayed to human; no gate logic. |

---

## Re-audit findings table

In re-audit iterations (iteration > 1), the auditor receives a brief that includes the prior findings table. The auditor must classify each prior finding:

| Status | Meaning |
|---|---|
| `resolved` | The Human's revision fixed the issue; finding no longer applies. |
| `still-present` | The issue remains unchanged in the revised PLAN. |
| `disputed-and-reaffirmed` | The Human disputed this finding but the auditor still considers it valid. |
| `disputed-and-dropped` | The Human disputed this finding and the auditor agrees it was incorrect or no longer applies. |

New findings discovered during re-audit carry `status: new` (or omit the field).

---

## Example audit file

`Workbench/.audit/202605121430_PLAN_audit-and-index-v2-1.json`:

```json
{
  "schema_version": 3,
  "auditor": "sufficiency",
  "plan_id": "PLAN-022_audit-and-index-v2",
  "iteration": 1,
  "findings": [
    {
      "code": "S001",
      "level": "warning",
      "category": "assumptions",
      "location": "Step 7",
      "message": "Step 7 references the lib/ directory but does not create it. The executor may fail if the directory does not exist.",
      "suggested_fix": "Prepend directory creation to Step 7 or add an earlier step.",
      "fingerprint": "a3f7c2d1"
    }
  ],
  "summary": {
    "error_count": 0,
    "warning_count": 1,
    "note_count": 0
  }
}
```

---

## References

- Sufficiency auditor codes: [`../audit-sufficiency/references/auditor-codes.md`](../audit-sufficiency/references/auditor-codes.md)
- Plan-safety auditor codes: [`../audit-haiku-safe/references/auditor-codes.md`](../audit-haiku-safe/references/auditor-codes.md)
- Human override fields (`audit_acknowledgements`, `audit_disputes`, `audit_overrides`): PLAN template frontmatter in `write-plan/templates/plan-template.md`
