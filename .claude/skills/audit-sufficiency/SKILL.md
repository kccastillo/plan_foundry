---
name: audit-sufficiency
description: 'Conceptual audit of a PLAN (Opus-pinned). Interrogates assumptions, validation path, test fidelity, orchestration edge cases, freshness, meta-design, spec-acceptance fidelity, rigour-heuristics application, and audit-trail durability. Catches what mechanical review misses - "we can build it, but is it the right thing?". Returns a structured review with a machine-readable Blockers count. Runs first in the drafted-phase audit loop, because plan-safety-auditor runs only after sufficiency passes. Trigger phrases: "opus pass", "sufficiency audit", "course-correct check", "check sufficiency", "audit-sufficiency".'
---

**Plan-safe definition:** See [../_shared/plan-safe.md](../_shared/plan-safe.md).

**Worked exemplar:** See [`references/sufficiency-audit-exemplar.md`](references/sufficiency-audit-exemplar.md) - captures what an Opus-pass output looks like, generated from the parent PLAN of plan-pipeline itself. Authors and future iterators of this skill calibrate against this exemplar.

<essential_principles>
This skill applies a conceptual lens rather than a mechanical one. Per-step concreteness, atomicity, and exact-text checks belong to `audit-haiku-safe`, so do not duplicate them here. The focus is invariant violations across sections, which is distinct from Self-Critique (structural omissions) and from audit-haiku-safe (mechanical safety). See [_shared/audit-stages.md](../_shared/audit-stages.md) for the three-tier focus distinction.
Apply nine lenses in order: assumptions, validation path, test fidelity, orchestration edge cases, freshness, meta, spec-acceptance fidelity, rigour-heuristics-applied, audit-trail durability. Each lens carries a concrete prompt, and every finding is classified Blocker or Not-blocker.
Read the PLAN, its referenced inputs (`linked_inputs`), and any source files the PLAN cites, because sufficiency review needs context the PLAN itself cannot fully express.
The response ends with a machine-readable `Blockers: N` summary (parent decision 14). The gate itself reads `outcome` and `payload.blockers_count` out of the `<pipeline-result>` block rather than this line, so the line is the human-readable tally and must carry the same number as `payload.blockers_count`.
Apply decision-triage (parent decision 15) to any Human-input items: classify already_locked / mechanically_forced / real_judgement_call (snake_case closed enum) before surfacing.
Do not fix the PLAN. Surface the findings, and the Human revises the PLAN and re-audits.
Sufficiency must pass before plan-safety runs (parent decision 21 loop), because there is no benefit to checking Haiku-safety on an insufficient plan.
Wire format: end the response with a literal `<pipeline-result>` block containing a JSON code fence per parent decision 23, with no XML payload and no HTML escaping.
</essential_principles>

<preconditions>
Before starting:
- PLAN file path is provided as input.
- PLAN file exists and is readable.
- PLAN has the expected sections: Objective, Context, Steps, Verification.
- Any files referenced in PLAN's `linked_inputs:` exist and are readable.
- Any source files cited in PLAN's Context or Steps are accessible (best-effort - the orchestrator cannot verify all code paths upfront).
</preconditions>

<inputs>
- `plan_path: string` - absolute or repo-relative path to the PLAN file under review.
</inputs>

<output_schema>
- `outcome: enum[success, revision_needed, exception]`
  - `success` -> Blockers: 0. The PLAN is sufficient, so the orchestrator advances to dispatch `plan-safety-auditor`.
  - `revision_needed` -> Blockers: N>0. The PLAN has sufficiency issues, so the orchestrator surfaces the findings, awaits revision, and re-audits sufficiency on the next iteration.
  - `exception` -> preconditions failed (PLAN unreadable, malformed, linked_inputs missing), so the orchestrator pulls the kanban full-stop.
- `payload:`
  - `blockers_count: int`
  - `review_text: string` - formatted review per the CLAUDE.md "Reviews" rule, with each lens's findings.
  - `triaged_human_items: list` - Human-input items classified per decision 15. Each entry carries a `class` from the closed snake_case enum `already_locked` / `mechanically_forced` / `real_judgement_call`, plus the `code` and `location` of the finding it classifies.
- `diagnostics:` - always present and always carrying `findings`, on every outcome including `success`, where `findings` is an empty array. The findings array belongs here, as `diagnostics.findings`, and never under `payload`. `audit_loop.py` reads the array from that location alone and rewrites the outcome to `exception` when `diagnostics` carries no `findings` key, so an array placed anywhere else fails the audit rather than degrading quietly. An empty array is a clean audit, and an absent key is a malformed return.

The agent's response message ends with a `<pipeline-result>` block (parent decision 23):
```
<pipeline-result>
```json
{ "outcome": "...", "payload": { ... }, "diagnostics": { ... } }
```
</pipeline-result>
```

**Findings must use v3 schema.** Each finding is a JSON object with fields: `code` (from `references/auditor-codes.md`), `level` (`error`/`warning`/`note`), `category`, `location`, `message`, `suggested_fix` (optional), `patch` (optional, and required for a `mechanically_forced` blocker). See [`../_shared/auditor-schema-v3.md`](../_shared/auditor-schema-v3.md) for the full schema.
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
   - `disputed-and-reaffirmed` - the Human disputed this finding, but the auditor still considers the finding valid after reviewing the dispute rationale
   - `disputed-and-dropped` - the Human's dispute was accepted, so the finding is withdrawn

2. **Identify new findings** - apply all nine lenses to the revised PLAN. New findings carry `status: new`.

3. **Do not re-emit acknowledged findings** - if a finding's fingerprint is in `audit_acknowledgements`, do not include that finding in the returned findings array. The orchestrator strips acknowledged findings defensively after parsing, but the auditor should not re-emit them in the first place.

4. **Focus on the diff** - use the unified diff to understand what changed, and give priority attention to the changed sections. Re-examine unchanged sections only when prior findings in those sections were marked `still-present`.

**Re-Audit Mode output:** the same v3 JSON schema, with `iteration` incremented and `status` fields populated on each finding.

<exception_conditions>
- PLAN file unreadable.
- PLAN structurally malformed (no Steps section, no Verification section, no Objective).
- One or more `linked_inputs:` files missing on disk.
- Source files cited in Steps reference paths that do not exist (best-effort, and not a strict precondition - flag in diagnostics rather than always halting).
</exception_conditions>

**Audit procedure:** See [workflows/audit-sufficiency-steps.md](workflows/audit-sufficiency-steps.md) for the nine-lens procedure.

<output_format>
Per the CLAUDE.md "Reviews" rule:
1. **Verification preamble** - what files were inspected (PLAN, linked_inputs, source files cited). Be specific: "Reviewed PLAN against [files A, B, C]" not "reviewed against project files".
2. **One-line overall verdict** - "Sufficient and ready for plan-safety audit" / "N sufficiency blockers - revise before re-auditing" / "Pre-condition violation - see diagnostics".
3. **Lens-by-lens findings**, each lens has its own subsection with:
   - `**Blockers**` (numbered, priority-ordered): the finding + the lens that surfaced the finding + the suggested fix shape, sketched rather than authored.
   - `**Not blockers**` (nits): brief list.
4. **Triaged Human-input items** (decision 15): if any blocker requires Human input, classify Already-locked / Mechanically-forced / Real-judgement-call. Only Real-judgement-call items become questions for the Human.
5. **Net verdict** - "ready to advance to plan-safety" / "revise the N blockers and re-audit".
6. **Machine-readable summary** - `Blockers: N` on its own line (e.g. `Blockers: 0`, `Blockers: 3`).

**Definition of "blocker"** (parent decision 14): any finding that would cause downstream work to halt, error, or be forced into a judgement call. Operator-procedural recommendations are nits.
</output_format>

<constraints>
- Never modify the PLAN under review.
- Never run any of the PLAN's `verify:`/`acceptance:` commands at this phase - running those commands belongs to the orchestrator's outcome-verification phase rather than to this audit.
- Never make mechanical observations (line numbers, exact-text matching, per-step concreteness). Those observations are `audit-haiku-safe`'s job.
- Always include the machine-readable `Blockers: N` line.
- Subagent context: invoked via the `sufficiency-auditor` agent, which preloads this skill via `skills:` frontmatter (decision 17). Do not assume access to the parent's wider skill registry.
- Sequencing: this skill runs first in the audit loop. Invoking this skill after `audit-haiku-safe` has already passed does no harm, because runs are idempotent, but the natural order is sufficiency -> plan-safety.
</constraints>

<success_criteria>
- Review prose follows CLAUDE.md "Reviews" rule format.
- All nine lenses were applied with at least one observation each (or explicit "no findings under this lens").
- Findings classified Blocker or Not-blocker.
- Decision-15 triage applied to any Human-input items.
- Output ends with `Blockers: N` machine-readable summary.
- Output ends with a `<pipeline-result>` block (decision 23).
- Verification preamble names the specific files inspected, not just "the PLAN".
- For Blockers, the suggested fix shape is sketched rather than authored, and the sketch gives the Human enough to know what direction the revision should take.
</success_criteria>
