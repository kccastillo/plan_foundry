# Ideate Critique Codes

Closed enum for self-critique findings. Namespace: `C001`–`C007` (named categories), `C999` (OTHER).

Every finding the self-critique phase emits **must** carry a code from this enum. If a finding does not fit any named category, use `C999` and include `[NEW CATEGORY NEEDED: <proposed category name>]` in the `message` field so the schema can be extended in a future version.

---

## Category Map

| Code | Category | Description |
|---|---|---|
| C001 | underspecified | Step lacks concrete file paths, command names, or verifiable assertions |
| C002 | missing-acceptance | Verification section has no `acceptance:` items |
| C003 | wrong-step-decomposition | Step combines multiple concerns; should be split |
| C004 | stale-reference | Step references code/config that no longer exists |
| C005 | design-issue | Architectural concern in the chosen approach |
| C006 | cross-spec-conflict | Conflicts with another in-flight PLAN |
| C007 | premature-optimization | Step adds complexity for hypothetical future requirements |
| C999 | other | Catch-all; message must include `[NEW CATEGORY NEEDED: <proposed>]` |

---

## C001 — underspecified

**Description:** A step or verification item lacks the concrete detail needed to execute it unambiguously. Common symptoms: missing file paths, missing command names, "etc." placeholders, or verification items that are not shell-runnable.

**When to use:** Step prose says "update the config" without naming the file; a verify item says `test -f some-file` without specifying the expected content; an acceptance check is described only in prose with no shell command.

**Example finding:**

```json
{
  "id": "C1",
  "code": "C001",
  "severity": "major",
  "category": "underspecified",
  "location": {"section_id": "Steps", "step_n": 4},
  "issue": "Step 4 says 'update the SKILL.md to add the new trigger phrases' but does not specify which phrases or where in the file they should appear. An executor cannot verify correctness without the exact strings.",
  "suggested_fix": "List the exact trigger phrases inline in the step prose, or reference a section in the linked ADVICE document where they are enumerated.",
  "fingerprint": ""
}
```

---

## C002 — missing-acceptance

**Description:** The Verification section contains only `verify:` (state-check) items and no `acceptance:` (behaviour-exercising) items. Per plan-safe requirements, at least one `acceptance:` item is required per PLAN.

**When to use:** Scanning the Verification section reveals only `verify:` or `verify: human` items and no `acceptance:` shell command that exercises the deliverable on a representative input.

**Example finding:**

```json
{
  "id": "C1",
  "code": "C002",
  "severity": "major",
  "category": "missing-acceptance",
  "location": {"section_id": "Verification"},
  "issue": "The Verification section has three `verify: test -f ...` items but no `acceptance:` command that actually runs the deliverable. The PLAN cannot pass plan-safety audit without at least one acceptance check.",
  "suggested_fix": "Add an `acceptance:` item that invokes the new script with a representative input and asserts the expected output. For example: `acceptance: python myscript.py && echo OK`",
  "fingerprint": ""
}
```

---

## C003 — wrong-step-decomposition

**Description:** A single step performs two or more logically independent operations that would be better separated. Steps that combine concerns are harder to verify, re-execute after failure, and review in git history.

**When to use:** Step N creates a file AND modifies an existing file AND runs a test; step description uses "and" or "also" to join distinct concerns; a step that would require multiple independent verification items.

**Example finding:**

```json
{
  "id": "C2",
  "code": "C003",
  "severity": "minor",
  "category": "wrong-step-decomposition",
  "location": {"section_id": "Steps", "step_n": 7},
  "issue": "Step 7 both creates render_critique.py and updates the existing render_prompts.py library. These are independent operations with different rollback implications and should be separate steps.",
  "suggested_fix": "Split into Step 7a (create render_critique.py) and Step 7b (update render_prompts.py if needed). Keep them sequential with explicit dependency noted.",
  "fingerprint": ""
}
```

---

## C004 — stale-reference

**Description:** A step or context section references a file, directory, function, config key, or API that no longer exists at the specified path, or has been renamed/moved without the PLAN being updated.

**When to use:** A step says `import from plugins/foo/lib/bar.py` but that file was moved; a context section references a PLAN that has since been retired; a step references a config file that has been superseded.

**Example finding:**

```json
{
  "id": "C3",
  "code": "C004",
  "severity": "major",
  "category": "stale-reference",
  "location": {"section_id": "Steps", "step_n": 6},
  "issue": "Step 6 imports from `plugins/plan-foundry-core/skills/plan-pipeline/lib/apply_actions.py` but the PLAN does not require creating or modifying that file, and the step's described logic does not call any function from it. The import is vestigial from an earlier design.",
  "suggested_fix": "Remove the apply_actions import from Step 6's prose. If apply_actions is genuinely needed, add a linked_input referencing it and document why.",
  "fingerprint": ""
}
```

---

## C005 — design-issue

**Description:** An architectural or structural concern with the chosen approach. The PLAN is internally consistent, but the design has a flaw that will make it brittle, hard to extend, or incorrect under realistic conditions.

**When to use:** Chosen approach creates a circular dependency; a module is given responsibilities that belong to a different layer; state is held in a way that won't survive restart; a file format assumes properties the implementation does not guarantee.

**Example finding:**

```json
{
  "id": "C4",
  "code": "C005",
  "severity": "major",
  "category": "design-issue",
  "location": {"section_id": "Context"},
  "issue": "The PLAN stores ideate_phase in PLAN frontmatter but the frontmatter parser in build_index.py skips indented lines, so any nested ideate_phase sub-key would be silently dropped. The proposed field is a flat top-level key, which is correct — but this should be stated explicitly to prevent future nesting.",
  "suggested_fix": "Add a note to the PLAN design decisions: ideate_phase is always a flat top-level YAML scalar, never nested. Document the build_index.py parser constraint.",
  "fingerprint": ""
}
```

---

## C006 — cross-spec-conflict

**Description:** A step or design decision in this PLAN conflicts with another in-flight PLAN that is modifying the same file, API, or shared contract. The two PLANs, if executed in order, would produce an inconsistent state.

**When to use:** Two PLANs both modify dispatch.md Step 3 in incompatible ways; one PLAN adds a frontmatter field that another PLAN assumes is absent; two PLANs rename the same function to different names.

**Example finding:**

```json
{
  "id": "C5",
  "code": "C006",
  "severity": "major",
  "category": "cross-spec-conflict",
  "location": {"section_id": "Steps", "step_n": 11},
  "issue": "Step 11 modifies build_index.py to add stuck_ideation alert. The in-flight PLAN 202605131200_PLAN_index-v2-alerts.md also modifies compute_alerts() to add a different alert. If both PLANs execute sequentially, the second will overwrite changes made by the first.",
  "suggested_fix": "Coordinate with 202605131200_PLAN_index-v2-alerts.md — either merge the alert additions into one PLAN, or add a cross-reference and explicit sequencing constraint between them.",
  "fingerprint": ""
}
```

---

## C007 — premature-optimization

**Description:** A step adds abstraction, configuration, or complexity that solves a hypothetical future requirement that is not stated in the current Objective or known constraints. YAGNI — You Aren't Gonna Need It.

**When to use:** Step adds a config file for a feature that will only be needed "if we scale"; step makes a function generic when the PLAN only needs one specific use; step adds a caching layer before any performance measurement exists.

**Example finding:**

```json
{
  "id": "C6",
  "code": "C007",
  "severity": "minor",
  "category": "premature-optimization",
  "location": {"section_id": "Steps", "step_n": 5},
  "issue": "Step 5 proposes a configurable context-window size via a YAML config file, but the PLAN's stated requirement is a single heuristic check. The PLAN text says 'best-effort, not exact' — adding file-based config before the heuristic is even validated adds complexity with no current payoff.",
  "suggested_fix": "Use the environment variable `IDEATE_CONTEXT_WINDOW` with a hardcoded default as stated in the implementation guidance. Add the config file in a follow-up PLAN if usage patterns show it is needed.",
  "fingerprint": ""
}
```

---

## C999 — other

**Description:** A finding that is clearly a self-critique concern but does not fit any of the seven named categories above.

**Requirement:** The `message` field **must** include `[NEW CATEGORY NEEDED: <proposed category name>]` so the enum can be extended in a future schema version.

**When to use:** Only when no existing category (C001–C007) adequately describes the concern.

**Example finding:**

```json
{
  "id": "C7",
  "code": "C999",
  "severity": "minor",
  "category": "other",
  "location": {"section_id": "Context"},
  "issue": "The PLAN does not state its target audience — whether this skill is intended for solo developers or team use. This affects several design choices that are currently ambiguous. [NEW CATEGORY NEEDED: audience-scope]",
  "suggested_fix": "Add a one-sentence audience statement to the Context section: 'This implementation targets single-developer harness use; team extensions tracked in CONTEXT_CONSTITUTION.md.'",
  "fingerprint": ""
}
```
