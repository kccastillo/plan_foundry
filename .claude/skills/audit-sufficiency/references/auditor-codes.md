# Audit-Sufficiency Auditor Codes

Closed enum for sufficiency findings. Namespace: `S001`-`S799` (by category), `S999` (OTHER).

Every finding the sufficiency auditor emits **must** carry a code from this enum. If a finding does not fit any category, use `S999` and include `[NEW CATEGORY NEEDED: <proposed category name>]` in the `message` field so the schema can be extended in a future version.

---

## Category Map

| Code Range | Category | Description |
|---|---|---|
| S001-S099 | assumptions | Unstated or invalid assumptions baked into the PLAN |
| S101-S199 | validation-path | Broken or missing verification chain |
| S201-S299 | test-fidelity | Test coverage gaps or superficial acceptance checks |
| S301-S399 | atomicity | Steps that combine concerns or are too coarse-grained |
| S401-S499 | freshness | Stale context, outdated references, or obsolete dependencies |
| S501-S599 | meta-design | Structural or architectural concerns about the PLAN itself |
| S601-S699 | spec-acceptance | Delivery does not match stated objective or success criteria |
| S701-S799 | audit-trail-durability | Decision-driving inputs (research-bot returns, ADVICE) not persisted as Workbench artefacts |
| S999 | OTHER | Finding that does not fit any category above; annotate with `[NEW CATEGORY NEEDED: ...]` |

---

## S001-S099 - Assumptions

Findings about unstated, unverified, or invalid assumptions baked into the PLAN's objective, context, or steps.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| S001 | missing-precondition | A step assumes a precondition (file exists, service running, permission granted) that is not verified or stated |
| S002 | invalid-assumption | An assumption is stated but is demonstrably false given available context |
| S003 | unresolved-ambiguity | The PLAN assumes a specific interpretation of an ambiguous requirement without documenting the choice |
| S004 | hidden-dependency | A step depends on an external system, file, or output that is not listed in `linked_inputs` and not explained |

**Example finding:**

```json
{
  "code": "S001",
  "level": "error",
  "category": "assumptions",
  "location": "Step 3",
  "message": "Step 3 assumes `Workbench/.audit/` already exists, but no prior step creates it and the PLAN does not state this as a precondition.",
  "suggested_fix": "Add a precondition check to Step 3 or add an earlier step that creates the directory with `mkdir -p`."
}
```

---

## S101-S199 - Validation Path

Findings about broken or missing verification chains - verify/acceptance items that don't actually prove delivery, are untestable, or are absent entirely.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| S101 | no-acceptance-check | PLAN has no `acceptance:` verification item (mechanically required per plan-safe; also a sufficiency concern if the objective is not exercised) |
| S102 | verify-does-not-prove-objective | A `verify:` check confirms a file exists but does not confirm the file does what the step claims |
| S103 | acceptance-too-shallow | An `acceptance:` command exercises the deliverable but does not check the output meaningfully (e.g. exits 0 on any input) |
| S104 | missing-failure-path-test | PLAN describes error-handling logic but no verification item exercises the error path |

**Example finding:**

```json
{
  "code": "S102",
  "level": "warning",
  "category": "validation-path",
  "location": "Verification / build_index.py exists",
  "message": "The verify check confirms `build_index.py` is present but does not confirm the script actually runs or produces valid JSON. The acceptance check on the same file is stronger and covers this - but the verify item alone is misleading.",
  "suggested_fix": "Either drop the redundant `verify:` item or note it is a fast pre-flight that is superseded by the `acceptance:` command below it."
}
```

---

## S201-S299 - Test Fidelity

Findings about test coverage gaps: important scenarios not covered, assertions checking structure not behaviour, or fixtures that do not represent realistic inputs.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| S201 | uncovered-scenario | A significant behaviour or edge case is not exercised by any verification item |
| S202 | fixture-not-realistic | A test fixture (fake file, stub, sample data) does not represent the real input the deliverable will receive |
| S203 | structure-not-behaviour | An assertion checks file structure (keys present) rather than computed behaviour (correct values) |
| S204 | missing-negative-test | PLAN adds new validation/gate logic but does not test the case where validation fails |

**Example finding:**

```json
{
  "code": "S201",
  "level": "warning",
  "category": "test-fidelity",
  "location": "Verification / smoke test",
  "message": "The smoke test creates a PLAN with one audit finding but does not verify the INDEX alert is raised when the audit loop exceeds iteration 3 (the `stuck_audits` alert threshold). The alert code path is untested.",
  "suggested_fix": "Add a second fake audit JSON with iteration >= 3 to the smoke test and verify the `stuck_audits` alert appears in `.index.json`."
}
```

---

## S301-S399 - Atomicity

Findings about steps that are too coarse-grained, combine multiple concerns, or are structurally underdivided - making them hard to verify, roll back, or re-execute after failure.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| S301 | step-combines-concerns | A single step performs two logically independent operations that should be separate steps |
| S302 | non-idempotent-step | A step cannot be safely re-run if it fails partway through (side effects not reversible) |
| S303 | batch-without-checkpoint | Multiple files or records processed in one step with no intermediate commit or checkpoint |
| S304 | implicit-ordering | Steps have an implicit ordering dependency not stated in their prose (step N must succeed before step M, but this is undocumented) |

**Example finding:**

```json
{
  "code": "S301",
  "level": "error",
  "category": "atomicity",
  "location": "Step 9",
  "message": "Step 9 updates dispatch.md with four distinct concerns (brief construction, last-commit anchor, recurrence detection, acknowledgement stripping). Each concern could fail independently and would be easier to review and re-execute if split into steps 9a-9d.",
  "suggested_fix": "Split Step 9 into four sub-steps or four distinct verification items, one per concern. The PLAN already labels them (a)-(d); formalise the split."
}
```

---

## S401-S499 - Freshness

Findings about stale context: the PLAN references a file, API, schema, or convention that has since changed; decisions captured in Context are outdated; or the PLAN was authored against an older version of the codebase.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| S401 | stale-file-reference | A step references a file path that no longer exists or has moved |
| S402 | stale-schema | A schema or frontmatter structure described in the PLAN diverges from what is currently on disk |
| S403 | outdated-decision | A design decision in Context was superseded by a later decision not reflected here |
| S404 | version-mismatch | PLAN targets a version of a tool, library, or skill that is no longer current |

**Example finding:**

```json
{
  "code": "S401",
  "level": "error",
  "category": "freshness",
  "location": "Step 7, Context",
  "message": "Step 7 references `plugins/plan-foundry-core/skills/plan-pipeline/lib/` but that directory does not yet exist on disk. The step must create it - the current prose implies it pre-exists.",
  "suggested_fix": "Prepend 'Create the `lib/` directory if absent' to Step 7's prose, or add a separate step for directory creation."
}
```

---

## S501-S599 - Meta-Design

Structural or architectural concerns about the PLAN itself: scope creep, missing decomposition, unclear ownership boundaries, or a design that makes future iteration costly.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| S501 | scope-too-large | The PLAN spans multiple independent concerns that should be separate PLANs |
| S502 | missing-rollback-path | A risky or irreversible operation has no documented rollback or recovery path |
| S503 | ownership-unclear | A step involves a boundary (human vs orchestrator vs executor) that is not clearly assigned |
| S504 | anti-pattern | The PLAN's design introduces a known anti-pattern (e.g. hardcoded paths, in-memory-only state, skip-hooks) |

**Example finding:**

```json
{
  "code": "S503",
  "level": "warning",
  "category": "meta-design",
  "location": "Step 20",
  "message": "Step 20 says 'commit a checkpoint' but the plan-foundry harness contract assigns all git operations to the orchestrator/parent session, not the executor. The executor cannot and should not commit.",
  "suggested_fix": "Rewrite Step 20 as a note to the executor ('leave files staged; parent session commits') or remove the step entirely and note it in executor constraints."
}
```

---

## S601-S699 - Spec-Acceptance

Findings about delivery that does not match the stated Objective or success criteria - the PLAN is internally consistent but builds the wrong thing, or the Verification section does not test what the Objective promises.

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| S601 | objective-not-verified | The stated Objective names an outcome but no Verification item checks for it |
| S602 | scope-gap | A requirement stated in the Objective is not addressed by any Step |
| S603 | contradictory-spec | Two Steps or one Step and the Verification section specify contradictory behaviour |
| S604 | delivers-different-thing | The Steps collectively produce a different artefact than the Objective describes |

**Example finding:**

```json
{
  "code": "S602",
  "level": "error",
  "category": "spec-acceptance",
  "location": "Objective / Verification",
  "message": "The Objective mentions 'diff truncation at 3000 tokens with a suffix flag' but no Verification item exercises the truncation path to confirm the suffix is appended.",
  "suggested_fix": "Add an acceptance check that calls build_brief.py with a PLAN whose diff exceeds 3000 tokens and asserts '[... DIFF TRUNCATED ...]' appears in the output."
}
```

---

## S701-S799 - Audit-trail Durability

Findings about decision-driving artefacts (research-bot returns, ADVICE inputs) that are not persisted as Workbench files before downstream decisions are locked. Distinct from S400-series freshness (stale references) - this category is about *provenance durability* (the artefact must exist on disk so a future reader can reconstruct why the PLAN's decisions were made, after memory compaction).

**Codes in use:**

| Code | Name | When to use |
|---|---|---|
| S701 | research-bot-dispatch-without-RESEARCH | PLAN's Context, Steps, or trace describes a research-bot dispatch (qualifying patterns: `"research bot"`, `"research-bot"`, `"expand-research"`, OR `subagent_type: general-purpose` co-occurring within ~10 lines with research-framing tokens `"research"` / `"prior art"` / `"find evidence"` / `"investigate"` / `"survey"`) AND `linked_inputs` contains no RESEARCH file (no entry matching either the new-convention regex `RESEARCH-\d+_` OR the legacy timestamp-prefix regex `\d{12}_RESEARCH_` - both forms are equally valid for the lint) |

**Example finding:**

```json
{
  "code": "S701",
  "level": "error",
  "category": "audit-trail-durability",
  "location": "Context, linked_inputs",
  "message": "PLAN's Context describes dispatching 3 general-purpose research bots for cluster-level expansion, but `linked_inputs` does not reference any RESEARCH file. Findings will be lost to memory compaction. Per PLAN-AB8 the procedural ideate cadence (cadence-phases.md Phase 2.B step 7) mandates write-input before phase advance; this PLAN bypassed that step.",
  "suggested_fix": "Invoke `Skill(\"write-input\")` for each research-bot return (or one combined file per logical cluster of bots). Add the resulting filename(s) to `linked_inputs`. Reference exemplar: `Workbench/RESEARCH-002_ab6-clarify-expand-research.md`."
}
```

---

## S999 - OTHER

Use `S999` when a finding is clearly a sufficiency concern but does not fit any category above. You **must** include `[NEW CATEGORY NEEDED: <proposed category name>]` in the `message` field so the enum can be extended in a future schema version.

**Example finding:**

```json
{
  "code": "S999",
  "level": "note",
  "category": "OTHER",
  "location": "Context",
  "message": "The PLAN does not state whether the INDEX projection should be gitignored or committed. [NEW CATEGORY NEEDED: commit-policy]",
  "suggested_fix": "Add a sentence to Context clarifying whether Workbench/INDEX.md and Workbench/.index.json are committed or gitignored."
}
```

---

## Related auxiliary families

The plan-safety auditor (`audit-haiku-safe`) also emits four auxiliary code families - `SFV###` (substrate-fidelity), `PPV###` (platform-portability), `PSZ001` (plan-sizing), and `FAL001-a`..`FAL001-f` (falsifiability) - from its mechanical Steps 4a-4d checks. These are plan-safety-only; the sufficiency auditor does not emit them. See [`../../audit-haiku-safe/references/auditor-codes.md`](../../audit-haiku-safe/references/auditor-codes.md) "Auxiliary code families" section for the full table.
