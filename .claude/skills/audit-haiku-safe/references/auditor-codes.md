# Audit-Haiku-Safe Auditor Codes

Closed enum for plan-safety findings. Namespace: `H001`-`H499` (by category), `H999` (OTHER). The plan-safety auditor also emits four auxiliary code families (`SFV`, `PPV`, `PSZ`, `FAL`) from its Step 4a-4d mechanical checks - these are documented separately in the "Auxiliary code families" section below rather than folded into the `H###` category map.

Every finding the plan-safety auditor emits **must** carry a code from this enum. If a finding does not fit any category, use `H999` and include `[NEW CATEGORY NEEDED: <proposed category name>]` in the `message` field so the schema can be extended in a future version.

---

## Category Map

| Code Range | Category | Description |
|---|---|---|
| H001-H099 | concreteness | Steps that are vague, underspecified, or require interpretation to execute |
| H101-H199 | atomicity | Steps that are too coarse-grained, non-idempotent, or contain hidden ordering |
| H201-H299 | unambiguity | Steps with multiple valid interpretations - executor must guess |
| H301-H399 | safety | Steps that perform destructive, irreversible, or privileged operations without proper approval |
| H401-H499 | testability | Verification items that cannot be run by the executor or do not prove step delivery |
| H999 | OTHER | Finding that does not fit any category above; annotate with `[NEW CATEGORY NEEDED: ...]` |

---

## H001-H099 - Concreteness

Findings about steps that are vague, underspecified, or require interpretation. The executor must be able to execute the step without any additional judgement calls.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| H001 | step-vague | Step prose does not specify what file/path/value to operate on |
| H002 | implicit-tool | Step implies a tool or mechanism without naming it (e.g. "update the file" without specifying how) |
| H003 | missing-content | Step says "add a section" or "include field X" but does not specify the required content |
| H004 | no-success-criterion | Step has no clear definition of what "done" looks like for that step |

**Example finding:**

```json
{
  "code": "H001",
  "level": "error",
  "category": "concreteness",
  "location": "Step 4",
  "message": "Step 4 says 'update the SKILL.md with v2 schema instructions' but does not specify which section to replace, what existing text to remove, or the exact new content to add. The executor cannot proceed without guessing.",
  "suggested_fix": "Either inline the exact replacement text in Step 4 or reference a template file the executor can copy from."
}
```

---

## H101-H199 - Atomicity

Findings about steps that are too coarse-grained, combine multiple independent operations, or cannot be safely re-run after partial failure.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| H101 | multi-operation-step | A single step performs two or more independent operations that each need their own verify |
| H102 | non-idempotent | A step creates a resource without checking if it already exists; re-running after partial failure would error or corrupt state |
| H103 | no-checkpoint | A step processes multiple targets (files, records) in a loop with no intermediate checkpoint; full re-run required on any partial failure |
| H104 | implicit-dependency | Step N relies on the output of step M but this ordering is not stated in either step |

**Example finding:**

```json
{
  "code": "H101",
  "level": "error",
  "category": "atomicity",
  "location": "Step 6",
  "message": "Step 6 adds ten new frontmatter fields AND two nested blocks (audit_state, verification_state) to plan-template.md. These are structurally independent - failure while adding the nested blocks leaves the template half-updated with no way to distinguish from a complete run.",
  "suggested_fix": "Split into Step 6a (top-level fields) and Step 6b (nested blocks), each with its own verify check."
}
```

---

## H201-H299 - Unambiguity

Findings about steps with more than one valid interpretation - the executor would have to guess which is intended.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| H201 | ambiguous-scope | It is unclear which file(s), directory, or system the step applies to |
| H202 | ambiguous-action | The verb used ("update", "add", "modify") admits multiple implementations |
| H203 | ambiguous-content | A value or content block to be written could be interpreted multiple ways |
| H204 | conflicting-instructions | Two parts of the same step contradict each other |

**Example finding:**

```json
{
  "code": "H202",
  "level": "warning",
  "category": "unambiguity",
  "location": "Step 9",
  "message": "Step 9b says 'the orchestrator runs git rev-parse HEAD, captures the short SHA, and writes it to audit_state.last_audit_commit'. 'Short SHA' is ambiguous - `git rev-parse --short HEAD` defaults to 7 characters but the length can vary by repo. The dispatch.md update should specify the exact git flag.",
  "suggested_fix": "Specify `git rev-parse --short=8 HEAD` (8 characters) in the dispatch.md prose, matching the fingerprint format in the schema."
}
```

---

## H301-H399 - Safety

Findings about steps that perform destructive, irreversible, or privileged operations without proper authorisation or safeguards.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| H301 | destructive-without-approval | Step deletes, overwrites, or modifies a file that was not explicitly approved for modification in this PLAN |
| H302 | excluded-operation | Step asks the executor to invoke an excluded operation (retire, write-input, plan-pipeline, ideate, raw Bash) - executor capability boundary violation per plan-safe.md |
| H303 | irreversible-migration | Step performs a schema migration or data transformation with no rollback path |
| H304 | privileged-operation | Step requires elevated permissions not available to the executor in its normal sandbox |

**Example finding:**

```json
{
  "code": "H302",
  "level": "error",
  "category": "safety",
  "location": "Step 20",
  "message": "Step 20 instructs the executor to 'stage all new and modified files; commit' - committing is an excluded operation for the executor. The harness contract assigns all git operations to the orchestrator/parent session (decision 13).",
  "suggested_fix": "Remove Step 20 from executor scope. Note in constraints that the parent session handles the commit. The executor should leave files in place for the parent to stage and commit."
}
```

---

## H401-H499 - Testability

Findings about verification items that cannot be run mechanically by the executor, are incorrectly formatted, or do not actually prove the step was completed correctly.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| H401 | verify-format-invalid | A verification item does not use `verify:`, `acceptance:`, `verify: orchestrator`, or `verify: human` format |
| H402 | no-acceptance-item | The PLAN has zero `acceptance:` items - at least one is required per plan-safe.md |
| H403 | shell-command-broken | A `verify:` or `acceptance:` shell command contains a syntax error or references a non-existent tool |
| H404 | verify-does-not-test-step | A `verify:` item is listed under a step but checks a different file or condition than the step created/modified |
| H405 | requires-human-for-mechanical-check | A `verify:` item (not `verify: human`) requires subjective judgement that only a human can provide - however, see guidance below: if the item needs INDEPENDENCE (not authority), prescribe `verify: orchestrator` instead |

**Guidance on verify-tier selection for H401/H405:**

`verify: orchestrator` is a valid, non-flagged annotation. Auditors MUST NOT flag `verify: orchestrator` under H401.

When prescribing a verification tier for a fidelity property, auditors should apply the following decision rule:
- Does the property require **authority** - a decision only the operator may make (scope amendment, stakeholder-facing framing, risk acceptance, political judgement)? -> Prescribe `verify: human`.
- Does the property require **independence** - the executor must not self-certify it, but any non-executor agent can check it? -> Prescribe `verify: orchestrator`.
- Is it mechanically shell-checkable without independence concerns? -> Prescribe `verify:` (shell command) or `acceptance:`.

H405 (`requires-human-for-mechanical-check`) retains its original intent: it fires when a `verify:` shell item (NOT `verify: human` or `verify: orchestrator`) requires subjective judgement. When a property's substance is machine-checkable but the executor must not self-certify it, the correct prescription is `verify: orchestrator` - NOT `verify: human`. Audit findings should reflect this: if an item is authored as `verify: human` but its substance is a fidelity check with no authority dimension, the auditor should recommend downgrading it to `verify: orchestrator`.

**Example finding:**

```json
{
  "code": "H402",
  "level": "error",
  "category": "testability",
  "location": "Verification",
  "message": "The PLAN's Verification section contains only `verify:` shell commands and `verify: human` items. There is no `acceptance:` item. At least one acceptance check is required to exercise the deliverable's behaviour per plan-safe.md.",
  "suggested_fix": "Add an `acceptance:` item that runs the primary deliverable (e.g. the Python script) against a representative input and checks its output."
}
```

---

## H999 - OTHER

Use `H999` when a finding is clearly a plan-safety concern but does not fit any category above. You **must** include `[NEW CATEGORY NEEDED: <proposed category name>]` in the `message` field so the enum can be extended in a future schema version.

**Example finding:**

```json
{
  "code": "H999",
  "level": "note",
  "category": "OTHER",
  "location": "Step 12",
  "message": "Step 12 produces a Python file with a `if __name__ == '__main__':` CLI block, but there is no mention of whether the file should be marked executable (chmod +x). [NEW CATEGORY NEEDED: file-permissions]",
  "suggested_fix": "Add a sub-step or note clarifying whether the file requires execute permission, or explicitly state it is invoked via `python <script>` only."
}
```

---

## Auxiliary code families (SFV / PPV / PSZ / FAL)

These four families are emitted by the plan-safety auditor's mechanical checks (Steps 4a-4d in [`../workflows/audit-haiku-safe-steps.md`](../workflows/audit-haiku-safe-steps.md)), separately from the `H###` category map above. They are admitted by the widened `findings[].code` pattern in [`../../_shared/auditor-schema-v3.md`](../../_shared/auditor-schema-v3.md).

| Code | Level | Category | Emit-site |
|---|---|---|---|
| SFV001 | error | substrate-fidelity | Step 4a - named entity in Steps not found in any declared substrate file |
| SFV002 | error | substrate-fidelity | Step 4a - `_`-prefixed (private) attribute authored against a third-party module |
| SFV003 | warning | substrate-fidelity | Step 4a - substrate-grammar constructs detected but `substrate_files` not declared |
| PPV001-PPV007 | warning | platform-portability | Step 4b - forbidden non-portable shell pattern in an unannotated `verify:`/`acceptance:` line (`/tmp/`, `/dev/null`, `bash -c`, POSIX `test`, `/dev/` redirect, `2>/dev/null`, `&&` compounds) |
| PSZ001 | warning | plan-sizing | Step 4d - PLAN has more than 12 top-level Steps and `PSZ001` is not in `audit_acknowledgements` |
| FAL001-a .. FAL001-f | warning | falsifiability | Step 4c - a `verify:`/`acceptance:` assertion matches a vacuous-pattern blocklist entry (`or callable(...)`, `or True`, `and True`, `hasattr(...) or <non-eq-expr>`, `any(... True ...)`, `or <x> is not None and True`) |

`FAL` codes carry an optional trailing lowercase-letter sub-code (`-a` through `-f`) identifying which vacuous pattern matched; all other families are the bare `<PREFIX><3-digit>` form.
