---
name: audit-haiku-safe
description: Mechanical plan-safety audit (Sonnet-pinned). Reviews a PLAN file step-by-step against the shared plan-safe definition; checks each step is concrete, atomic, unambiguous, safe, testable; checks Verification items have valid verify:/acceptance:/human format with at least one acceptance: per PLAN. Returns structured review with machine-readable Blockers count. Trigger phrases: "haiku-safe check this", "is this plan haiku-safe", "verify plan-safety", "audit-haiku-safe".
---

**Plan-safe definition:** See [../_shared/plan-safe.md](../_shared/plan-safe.md) — single source of truth shared with execute-plan.

<essential_principles>
Mechanical only — no conceptual review. Sufficiency is `audit-sufficiency`'s job.
Read each PLAN step. Evaluate against the five plan-safe criteria. Classify as Blocker or Not-blocker.
Cross-step coherence: ordering, line-number consistency after upstream edits.
Verification format: every item must have `verify:` / `acceptance:` / `verify: human`. At least one `acceptance:` per PLAN.
Output a machine-readable `Blockers: N` summary so the orchestrator can apply the gate.
Do not fix the PLAN. Surface findings; the Human revises and re-audits.
Wire format: end response with literal `<pipeline-result>` containing JSON code fence per parent decision 23. No XML payload, no HTML escaping.
</essential_principles>

<preconditions>
Before starting:
- PLAN file path is provided as input.
- PLAN file exists and is readable.
- Shared plan-safe definition exists at `skills/_shared/plan-safe.md`.
- audit-sufficiency has run and returned `outcome: success` (no point haiku-safety-checking an insufficient plan). If not yet run, return `outcome: exception`.
</preconditions>

<inputs>
- `plan_path: string` — absolute or repo-relative path to the PLAN file under review.
</inputs>

<output_schema>
- `outcome: enum[success, revision_needed, exception]`
  - `success` → Blockers: 0; PLAN is mechanically executable; orchestrator advances `pipeline_phase: drafted → checked`.
  - `revision_needed` → Blockers: N>0; PLAN has plan-safety issues; orchestrator surfaces findings, awaits revision.
  - `exception` → preconditions failed (e.g. invoked before sufficiency passed; PLAN unreadable; shared plan-safe.md missing).
- `payload:`
  - `blockers_count: int`
  - `review_text: string` — formatted review per the CLAUDE.md "Reviews" rule.
- `diagnostics:` — populated when outcome != success; otherwise empty.

The agent's response message ends with a `<pipeline-result>` block (decision 23 of PLAN 202605011400):
```
<pipeline-result>
```json
{ "outcome": "...", "payload": { ... }, "diagnostics": { ... } }
```
</pipeline-result>
```

**Findings must use v2 schema.** Each finding is a JSON object with fields: `code` (from `references/auditor-codes.md`), `level` (`error`/`warning`/`note`), `category`, `location`, `message`, `suggested_fix` (optional). See [`../_shared/auditor-schema-v2.md`](../_shared/auditor-schema-v2.md) for the full schema.
</output_schema>

## Re-Audit Mode

When the orchestrator brief includes a prior findings table (iteration > 1), the auditor operates in Re-Audit Mode. The brief contains:
- The prior findings table (code, level, category, location, message, fingerprint)
- A list of findings the Human has acknowledged (fingerprints in `audit_acknowledgements`)
- A list of findings the Human has disputed (fingerprints in `audit_disputes`)
- A unified diff anchored at `audit_state.last_audit_commit` showing what changed since the last audit

**Re-Audit Mode obligations:**

1. **Status each prior finding** — for every finding from the prior iteration, classify it as one of:
   - `resolved` — the revision fixed the issue
   - `still-present` — the issue remains unchanged
   - `disputed-and-reaffirmed` — the Human disputed this but the auditor still considers it valid after reviewing the dispute rationale
   - `disputed-and-dropped` — the Human's dispute was accepted; this finding is withdrawn

2. **Identify new findings** — apply all five plan-safety criteria to the revised PLAN step by step. New findings carry `status: new`.

3. **Do not re-emit acknowledged findings** — if a finding's fingerprint is in `audit_acknowledgements`, do not include it in the returned findings array. The orchestrator strips acknowledged findings defensively after parsing, but the auditor should not re-emit them in the first place.

4. **Focus on the diff** — use the unified diff to understand what changed. Give priority attention to changed steps and verification items. Re-examine unchanged steps only when prior findings on those steps were marked `still-present`.

**Plan-safety H codes apply here.** All findings use codes from `H001`–`H499` (or `H999` for OTHER). See [`references/auditor-codes.md`](references/auditor-codes.md) for the full enum.

**Re-Audit Mode output:** the same v2 JSON schema, with `iteration` incremented and `status` fields populated on each finding.

<exception_conditions>
- PLAN file unreadable.
- audit-sufficiency has not yet returned `outcome: success` (precondition violation).
- Shared `_shared/plan-safe.md` reference missing.
- PLAN structurally malformed (no Steps section, no Verification section).
</exception_conditions>

**Review procedure:** See [workflows/audit-haiku-safe-steps.md](workflows/audit-haiku-safe-steps.md).

<output_format>
Brief verification preamble (what was checked against — files, not just the PLAN under review)
→ one-line overall verdict
→ for the single Plan-safety section:
   - **Blockers** subgroup (each item: prose + the criterion violated + suggested fix shape)
   - **Not blockers** subgroup
→ Net verdict
→ Machine-readable summary line: `Blockers: N` (e.g. `Blockers: 0` or `Blockers: 3`).

**Definition of "blocker"** (per PLAN 202605011400 decision 14): any finding that would cause Haiku to halt, error, or be forced into a judgement call mid-execution. Operator-procedural recommendations are nits, not blockers.

**Decision-triage of any Human-input items** (per parent decision 15): if a finding requires Human input, classify as Already-locked / Mechanically-forced / Real-judgement-call before surfacing. Only Real-judgement-call items become questions.
</output_format>

<constraints>
- Never modify the PLAN under review.
- Never run any of the PLAN's verify:/acceptance: commands at this phase — that's the orchestrator's outcome-verification phase, not this audit.
- Never recommend conceptual changes (sufficiency lens). Stay mechanical.
- Always include the machine-readable `Blockers: N` line.
- Subagent context: invoked via the `plan-safety-auditor` agent, which preloads this skill via `skills:` frontmatter (decision 17). Do not assume access to the parent's wider skill registry.
</constraints>

<success_criteria>
- Review prose follows CLAUDE.md "Reviews" rule format.
- Every PLAN step has been classified Blocker or Not-blocker.
- Verification items have been checked for shell-runnable format (verify: / acceptance: / verify: human) AND at least one acceptance: per PLAN.
- Output ends with `Blockers: N` machine-readable summary.
- Output ends with a `<pipeline-result>` block (decision 23).
- Decision-triage applied to any Human-input items.
</success_criteria>

<regression_examples>
**Executor capability-boundary regression (PLAN-009).** A PLAN whose Step asks the executor to perform an excluded operation MUST be flagged. Worked example:

> Step 1. Invoke `Skill('retire')` from inside plan-executor on `tmp/audit-smoke-target.md`.

Expected audit-haiku-safe behaviour: `outcome: revision_needed`, with at least one Blocker citing the "Executor capability boundaries" section of `_shared/plan-safe.md`, sub-clause (b) — `retire` is orchestrator-owned (decision 3) and additionally requires Bash (denied to executor by F1 Option C). Suggested fix shape: "Re-author Step 1 as 'orchestrator retires `tmp/audit-smoke-target.md`' — move the operation to parent session."

The same blocker shape applies to Steps that name `write-input`, `plan-pipeline`, `ideate`, or raw `bash`/`sh` invocation inside Step bodies. (Verification-section shell commands run in parent context and are not subject to this rule.)

This regression existed pre-fix: prior to PLAN-009, both audits passed such a PLAN (observed in F/14 closeout PLAN 202605012200, 2026-05-01: 8 retire moves silent-no-op'd because `Skill()` from inside subagents fails without raising). The new `_shared/plan-safe.md` "Executor capability boundaries" section closes the audit gate; the executor agents' updated `Exception conditions` clause is the runtime safety net.
</regression_examples>
