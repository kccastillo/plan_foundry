# Self-Critique JSON Schema v1

JSON schema for self-critique outputs produced during Phase 5 (Self-Critique) of the eight-phase ideate cadence.

Stored at: `Workbench/.ideate-critique/<plan-id>-<iter>.json`

---

## Schema

```json
{
  "schema_version": 1,
  "phase": "self_critique",
  "iteration": 1,
  "plan_path": "Workbench/PLAN-AA0_slug.md",
  "findings": [
    {
      "id": "C1",
      "code": "C001",
      "severity": "major",
      "category": "underspecified",
      "location": {
        "section_id": "Steps",
        "step_n": 3
      },
      "issue": "<one-paragraph description of the problem>",
      "suggested_fix": "<actionable suggestion for how to address the finding>",
      "fingerprint": "<8-char SHA computed by ideate orchestrator>"
    }
  ],
  "summary": {
    "major_count": 0,
    "minor_count": 0,
    "discarded_count": 0
  }
}
```

---

## Field Definitions

### Top-level fields

| Field | Type | Constraint | Description |
|---|---|---|---|
| `schema_version` | integer | const `1` | Schema version; always 1 for this revision |
| `phase` | string | const `"self_critique"` | Phase identifier; always `self_critique` |
| `iteration` | integer | >= 1 | Iteration number (1-based); bounded at 5 per PLAN |
| `plan_path` | string | non-empty | Relative path to the PLAN file being critiqued |
| `findings` | array | may be empty | List of finding objects (see below) |
| `summary` | object | required | Counts of major, minor, and discarded findings |

### findings[] entry fields

| Field | Type | Constraint | Description |
|---|---|---|---|
| `id` | string | e.g. `"C1"`, `"C2"` | Human-readable sequential ID for the critique session |
| `code` | string | enum (see below) | Critique code from the closed enum in critique-codes.md |
| `severity` | string | `"major"` or `"minor"` | Severity classification (NOT `error/warning/note` - those are audit schema terms) |
| `category` | string | enum (see below) | Category name matching the code's category |
| `location` | object | required | Free-text locator; preferred fields: `section_id`, `step_n` |
| `issue` | string | non-empty | One-paragraph description of the problem |
| `suggested_fix` | string | non-empty | Actionable suggestion for how to address the finding |
| `fingerprint` | string | 8-char hex | SHA-256 digest computed by `compute_fingerprint()` in `lib/state.py` |

### severity enum

| Value | Meaning |
|---|---|
| `major` | Correctness-affecting; must be addressed or explicitly deferred/disputed before the PLAN advances |
| `minor` | Quality/clarity concern; should be addressed; may be deferred with rationale |

Note: this is distinct from the audit schema's `error/warning/note`. Translation occurs in `render_critique.py`: `major -> error`, `minor -> warning`.

### code enum

See `references/critique-codes.md` for the full closed enum. Quick reference:

| Code | Category |
|---|---|
| C001 | underspecified |
| C002 | missing-acceptance |
| C003 | wrong-step-decomposition |
| C004 | stale-reference |
| C005 | design-issue |
| C006 | cross-spec-conflict |
| C007 | premature-optimization |
| C999 | other |

### category enum

`underspecified` | `missing-acceptance` | `wrong-step-decomposition` | `stale-reference` | `design-issue` | `cross-spec-conflict` | `premature-optimization` | `other`

### location object

`location` is free-text to maximise flexibility. Preferred fields:

| Field | Type | Description |
|---|---|---|
| `section_id` | string | Section heading: `"Objective"`, `"Context"`, `"Steps"`, `"Verification"`, `"Design Decisions Classification"` |
| `step_n` | integer | Step number (when `section_id == "Steps"`) |

Additional fields are permitted (e.g. `"line_hint": 42`). No strict enum on `section_id` - use the literal heading text from the PLAN.

### summary object

| Field | Type | Description |
|---|---|---|
| `major_count` | integer | Count of findings with `severity: major` in this iteration |
| `minor_count` | integer | Count of findings with `severity: minor` in this iteration |
| `discarded_count` | integer | Count of findings discarded in prior iterations (not re-emitted) |

---

## Storage convention

- **Path pattern:** `Workbench/.ideate-critique/<plan-id>-<iter>.json`
  - `<plan-id>` is the PLAN file's stem (without `.md`), e.g. `PLAN-025_ideate-cadence-pipeline`
  - `<iter>` is the 1-based iteration number, zero-padded to 2 digits: `01`, `02`, ... `05`
  - Example: `Workbench/.ideate-critique/PLAN-AA0_ideate-cadence-pipeline-01.json`

- **Committed:** critique JSONs are committed to the repository (not gitignored). They provide a forensic trace of the critique arc, parallel to `.audit/` files for the audit arc.

- **Iteration bound:** `iteration` <= 5 per PLAN. Exceeding the bound causes a halt-and-surface (see `phase-transitions.md`).

---

## Zero-findings short-circuit

If Phase 5 produces a critique JSON with `findings: []` (or `major_count == 0 AND minor_count == 0`), the self-critique phase immediately advances to Phase 8 (Consolidate), bypassing Phases 6 and 7. The JSON is still written to disk for forensic record.

---

## Fingerprint computation

The `fingerprint` field is computed by the ideate orchestrator (not the critique producer) via `state.py:compute_fingerprint()`:

```python
sha256(code + severity + category + json.dumps(location, sort_keys=True))[:8]
```

This is analogous to the audit fingerprint formula (`sha256(code + level + category + location)[:8]`) with `severity` mapping to `level`. The fingerprint is stable across iterations provided the finding's code, severity, category, and location do not change - enabling cross-iteration recurrence detection.
