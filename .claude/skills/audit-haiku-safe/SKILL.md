---
name: audit-haiku-safe
description: 'Mechanical plan-safety audit (Opus-pinned). Reviews a PLAN file step by step against the shared plan-safe definition, checks that each step is concrete, atomic, unambiguous, safe and testable, and checks that Verification items use one of the four valid annotations (verify:, acceptance:, verify: orchestrator, verify: human) with at least one acceptance: per PLAN. Returns a structured review with a machine-readable Blockers count. Trigger phrases: "haiku-safe check this", "is this plan haiku-safe", "verify plan-safety", "audit-haiku-safe".'
---

**Plan-safe definition:** See [../_shared/plan-safe.md](../_shared/plan-safe.md) - single source of truth shared with execute-plan.

<essential_principles>
This audit is mechanical only and does not include conceptual review. Sufficiency is `audit-sufficiency`'s job.
Read each PLAN step, evaluate the step against the plan-safe criteria, and classify each finding as Blocker or Not-blocker.
Check cross-step coherence, covering ordering and line-number consistency after upstream edits.
Check the verification format: every item must have `verify:` / `acceptance:` / `verify: orchestrator` / `verify: human`, and every PLAN must have at least one `acceptance:` item. All four annotations are legal, and `verify: orchestrator` is never flagged under `H401`.
Output a machine-readable `Blockers: N` summary so the orchestrator can apply the gate.
Tier-relative sizing - audit each PLAN against the bar of **its assigned tier**, not always Haiku's. Read the PLAN's `size:` / `assigned_to:` frontmatter and hold the PLAN to that tier's bar (S=haiku, M=sonnet, L=opus). See [../_shared/plan-safe.md](../_shared/plan-safe.md) section Executor t-shirt sizing. "Not haiku-safe" is a **sizing outcome, not automatically a Blocker**: when a Step exceeds the assigned tier, pick a remedy and record which - **decompose** (keep S, emit decomposition Blocker) or **size up** (recommend M/L via a `note`-level re-size finding, not a Blocker). A PLAN with non-haiku-safe Steps and no recorded size/tier is incompletely sized - recommend a size rather than passing silently. A `size:` that disagrees with `assigned_to:` is a Blocker.
Do not fix the PLAN. Surface the findings, after which the Human revises and re-audits.
Wire format: end the response with a literal `<pipeline-result>` block containing a JSON code fence, per parent decision 23. Use no XML payload and no HTML escaping.
</essential_principles>

<preconditions>
Before starting:
- PLAN file path is provided as input.
- PLAN file exists and is readable.
- Shared plan-safe definition exists at `skills/_shared/plan-safe.md`.
- audit-sufficiency has run and returned `outcome: success` (there is no benefit to checking plan-safety on an insufficient plan). If not yet run, return `outcome: exception`.
</preconditions>

<inputs>
- `plan_path: string` - absolute or repo-relative path to the PLAN file under review.
</inputs>

<output_schema>
- `outcome: enum[success, revision_needed, exception]`
  - `success` -> Blockers: 0, the PLAN is mechanically executable, and the orchestrator advances `pipeline_phase: drafted -> checked`.
  - `revision_needed` -> Blockers: N>0, the PLAN has plan-safety issues, and the orchestrator surfaces the findings and awaits revision.
  - `exception` -> preconditions failed (e.g. invoked before sufficiency passed, PLAN unreadable, or shared plan-safe.md missing).
- `payload:`
  - `blockers_count: int`
  - `review_text: string` - formatted review per the CLAUDE.md "Reviews" rule.
- `diagnostics:` - always present and always carrying `findings`, on every outcome including `success`. The array is empty only when the audit produced no findings at all, and it carries every finding it did produce, blockers and not-blockers alike. `audit_loop.py` rewrites the outcome to `exception` when `diagnostics` carries no `findings` key, so an omitted array fails the audit rather than reading as a clean one. The findings array belongs here, as `diagnostics.findings`, and never under `payload`. The orchestrator reads the findings array from that location only, so an array placed anywhere else disables recurrence detection and acknowledgement-stripping without failing anything.

The agent's response message ends with a `<pipeline-result>` block (decision 23 of PLAN 202605011400):
```
<pipeline-result>
```json
{ "outcome": "...", "payload": { ... }, "diagnostics": { ... } }
```
</pipeline-result>
```

**Findings must use v3 schema.** Each finding is a JSON object with fields: `code` (from `references/auditor-codes.md`), `level` (`error`/`warning`/`note`), `category`, `location`, `message`, `suggested_fix` (optional). See [`../_shared/auditor-schema-v3.md`](../_shared/auditor-schema-v3.md) for the full schema.
</output_schema>

## Re-Audit Mode

When the orchestrator brief includes a prior findings table (iteration > 1), the auditor operates in Re-Audit Mode. The brief contains:
- The prior findings table (code, level, category, location, message, fingerprint)
- A list of findings the Human has acknowledged (fingerprints in `audit_acknowledgements`)
- A list of findings the Human has disputed (fingerprints in `audit_disputes`)
- A unified diff anchored at `audit_state.last_audit_commit` showing what changed since the last audit

**Re-Audit Mode obligations:**

1. **Status each prior finding** - for every finding from the prior iteration, classify the finding as one of:
   - `resolved` - the revision fixed the issue
   - `still-present` - the issue remains unchanged
   - `disputed-and-reaffirmed` - the Human disputed this finding, and the auditor still considers the finding valid after reviewing the dispute rationale
   - `disputed-and-dropped` - the Human's dispute was accepted, so this finding is withdrawn

2. **Identify new findings** - apply all plan-safety criteria to the revised PLAN step by step. New findings carry `status: new`.

3. **Do not re-emit acknowledged findings** - if a finding's fingerprint is in `audit_acknowledgements`, do not include the finding in the returned findings array. The orchestrator strips acknowledged findings defensively after parsing, but the auditor should not re-emit them in the first place.

4. **Focus on the diff** - use the unified diff to understand what changed. Give priority attention to changed steps and verification items. Re-examine unchanged steps only when prior findings on those steps were marked `still-present`.

**Plan-safety H codes apply here.** All findings use codes from `H001`-`H499` (or `H999` for OTHER). See [`references/auditor-codes.md`](references/auditor-codes.md) for the full enum.

**Re-Audit Mode output:** the same v3 JSON schema, with `iteration` incremented and `status` fields populated on each finding.

<exception_conditions>
- PLAN file unreadable.
- audit-sufficiency has not yet returned `outcome: success` (precondition violation).
- Shared `_shared/plan-safe.md` reference missing.
- PLAN structurally malformed (no Steps section, no Verification section).
</exception_conditions>

**Review procedure:** See [workflows/audit-haiku-safe-steps.md](workflows/audit-haiku-safe-steps.md).

<output_format>
Brief verification preamble (what was checked against - files, not just the PLAN under review)
-> one-line overall verdict
-> for the single Plan-safety section:
   - **Blockers** subgroup (each item: prose + the criterion violated + suggested fix shape)
   - **Not blockers** subgroup
-> Net verdict
-> Machine-readable summary line: `Blockers: N` (e.g. `Blockers: 0` or `Blockers: 3`).

**Definition of "blocker"** (per PLAN 202605011400 decision 14, extended by the tier-relative rule): any finding that would cause the PLAN's **assigned tier** (not always Haiku) to halt, error, or be forced into a judgement call above its remit mid-execution. Operator-procedural recommendations are nits, not blockers. A Step exceeding the assigned tier is a Blocker only when the remedy is decomposition. When the remedy is a legitimate re-size (the job is irreducible), emit a `note`-level re-size recommendation naming the correct `size:`/`assigned_to:` rather than a Blocker.

**Decision-triage of any Human-input items** (per parent decision 15): if a finding requires Human input, classify the finding as `already_locked` / `mechanically_forced` / `real_judgement_call` before surfacing. Only `real_judgement_call` items become questions.
</output_format>

<constraints>
- Never modify the PLAN under review.
- Never run any of the PLAN's verify:/acceptance: commands at this phase - those commands run in the orchestrator's outcome-verification phase rather than in this audit.
- Never recommend conceptual changes (sufficiency lens). Stay mechanical.
- Always include the machine-readable `Blockers: N` line.
- Subagent context: the `plan-safety-auditor` agent invokes this audit and preloads this skill through that agent's `skills:` frontmatter (decision 17). Do not assume access to the parent's wider skill registry.
</constraints>

<success_criteria>
- Review prose follows CLAUDE.md "Reviews" rule format.
- Every PLAN step has been classified Blocker or Not-blocker.
- Verification items have been checked for a legal annotation (verify: / acceptance: / verify: orchestrator / verify: human) and for at least one acceptance: per PLAN.
- Output ends with `Blockers: N` machine-readable summary.
- Output ends with a `<pipeline-result>` block (decision 23).
- Decision-triage applied to any Human-input items.
</success_criteria>

<regression_examples>
**Executor capability-boundary regression (PLAN-009).** A PLAN whose Step directs the executor to perform an excluded operation MUST be flagged. Worked example:

> Step 1. Invoke `Skill('retire')` from inside plan-executor on `tmp/audit-smoke-target.md`.

Expected audit-haiku-safe behaviour: `outcome: revision_needed`, with at least one Blocker citing the "Executor capability boundaries" section of `_shared/executor-capability-boundary.md`, sub-clause (b) - `retire` is orchestrator-owned (decision 3) and also requires Bash (denied to executor by F1 Option C). Suggested fix shape: "Re-author Step 1 as 'orchestrator retires `tmp/audit-smoke-target.md`' - move the operation to parent session."

The same blocker shape applies to Steps that name `write-input`, `plan-pipeline`, `ideate`, or raw `bash`/`sh` invocation inside Step bodies. (Verification-section shell commands run in parent context and are not subject to this rule.)

As of PLAN-AK1, Step 4e checks this boundary mechanically (lib/capability_boundary.py, code EBV001), and the auditing model also reads the Step under H302.

Before PLAN-009, both audits passed such a PLAN (observed in F/14 closeout PLAN 202605012200, 2026-05-01: 8 retire moves became silent no-ops because `Skill()` from inside subagents fails without raising). The `_shared/executor-capability-boundary.md` "Executor capability boundaries" section closes the audit gate, and the executor agents' updated `Exception conditions` clause is the runtime safety net.
</regression_examples>
