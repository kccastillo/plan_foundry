# Gate B - Risk-Assess-Spec Workflow

Adversarial risk-assessment gate that fires after Spec-Draft (Phase 4), before Self-Critique (Phase 5). Catches specification construction errors - broken step sequences, unverifiable acceptance items, missing substrate, and dependency misordering - before the critique phase encodes them as "already reviewed" findings.

Part of the ideate cadence defined in `cadence-phases.md`. For the phase-transition table, see `references/phase-transitions.md`.

Gate output artefact lifecycle: `Workbench/.ideate-gate/<plan-id>-gate-b.json` is written on a clean pass and cleaned up after Self-Critique completes. See `cadence-phases.md section Gate B` for the authoritative lifecycle note.

---

## Trigger Condition

Gate B fires when `ideate_phase` transitions from `spec_draft` - immediately after Spec-Draft (Phase 4) completes and before Self-Critique (Phase 5) begins. The source key is `"spec_draft"`.

State transition on entry: `advance_phase(plan_path, 'spec_draft', 'risk_assess_spec')`.

---

## Standing Structural Checks (always run)

Four structural checks run at every Gate B invocation, regardless of plan content:

1. **step-completeness** - Is there a path from Step 1 to Verification that does not pass through an undescribed action? Check for implicit actions, missing intermediate steps, and steps that reference outputs never produced by prior steps.

2. **verification-gaming** - Do the `verify:` and `acceptance:` items attest what they claim, or can they pass on a broken implementation? Check for verification items that test the existence of a file rather than its content, or that can be satisfied by a stub.

3. **dependency-ordering** - Are Steps sequenced so that each one's inputs exist when it runs? Check for forward-references (a step uses a file or state not yet created), missing prerequisite steps, and parallel steps that must be serialised.

4. **substrate-fidelity** - Does any Step reference a file, function, or capability that does not exist in the substrate as described? Check the `substrate_files` frontmatter and the Context section for the ground-truth substrate, then verify each Step's references against it.

---

## Domain-Specific Lenses (derived at gate-time)

After the four standing checks, derive 1-3 additional domain-specific lenses from the PLAN's Objective. The derivation prompt to the orchestrator:

> "Given this PLAN's Objective and the written Steps + Verification, what are the 1-3 most likely spec-construction failure modes that the four standing checks would NOT catch? Name each as a short hyphenated label (e.g. `schema-mismatch`, `missing-rollback`) and a one-sentence description of the check."

These derived lenses are passed to the Workflow harness as additional items in `standing_checks`.

---

## Workflow Harness Call

```javascript
const result = await Workflow({
  scriptPath: ".claude/skills/ideate/workflows/risk-assess.workflow.js",
  args: {
    gate: "B",
    plan_content: "<full PLAN file content as string>",
    standing_checks: [
      "step-completeness: Is there a continuous path from Step 1 to Verification with no undescribed actions?",
      "verification-gaming: Do verify:/acceptance: items attest what they claim, or can they pass on a broken implementation?",
      "dependency-ordering: Are Steps sequenced so each one's inputs exist when it runs?",
      "substrate-fidelity: Does any Step reference a file, function, or capability absent from the substrate?",
      // ... plus 1-3 derived domain-specific checks
    ]
  }
});
// result: { show_stopper, show_stopper_description, mitigations }
```

---

## Output Routing

### Clean pass (`show_stopper: false`)

1. Write the synthesis mitigation list to `Workbench/.ideate-gate/<plan-id>-gate-b.json`:
   ```json
   {
     "gate": "B",
     "plan_id": "<plan-id>",
     "show_stopper": false,
     "show_stopper_description": null,
     "mitigations": [
       { "finding": "...", "mitigation": "...", "incorporated_into_phase": "self_critique" }
     ]
   }
   ```

2. The mitigation list folds silently into Self-Critique context. The orchestrator prepends the mitigations to the Self-Critique prompt so the critique phase can treat them as already-known candidates.

3. Advance phase: `advance_phase(plan_path, 'risk_assess_spec', 'self_critique')`.

4. Proceed to Phase 5 (Self-Critique). Do NOT surface the mitigation list to the human (per D4).

### Show-stopper detected (`show_stopper: true`)

**Check iteration counter first:**

```python
from state import read_ideate_state, MAX_RISK_ASSESS_SPEC_REVISIONS
s = read_ideate_state(plan_path)
attempts_spent = s["ideate_iteration_count"]["risk_assess_spec"]
```

**If `attempts_spent >= MAX_RISK_ASSESS_SPEC_REVISIONS` (attempt already spent):**

Skip the revision attempt. Go directly to surface and block:

1. Surface to the human with the show-stopper description. Format:

   > **Gate B - Risk-Assess-Spec: show-stopper (revision attempt spent)**
   >
   > `<show_stopper_description>`
   >
   > One autonomous revision was already attempted. The spec still has a show-stopper. Address the issue manually, then say `"resume ideate <plan-id>"` to re-run Gate B.

2. Set `ideate_phase: risk_assess_spec_blocked` via `advance_phase(plan_path, 'risk_assess_spec', 'risk_assess_spec_blocked')`.

3. Halt.

**If `attempts_spent == 0` (first encounter):**

Perform one autonomous revision attempt within the current `risk_assess_spec` occupancy:

1. Read the show-stopper description and the full mitigation list from the Workflow result.

2. Revise the PLAN's Steps and/or Verification sections to address the blockers. Write the updated PLAN file directly (no `ideate_phase` change - the revision stays within the same `risk_assess_spec` occupancy, per D7).

3. Persist the attempt count: `set_ideate_iteration_count(plan_path, 'risk_assess_spec', 1)`.

4. Re-run the Workflow harness with the updated PLAN content.

5. Evaluate the re-run result:
   - If `show_stopper: false` -> write the artefact and advance to `self_critique` (clean pass routing above).
   - If `show_stopper: true` -> surface to the human and set `risk_assess_spec_blocked` (spent-attempt path above).

---

## Blocked-Phase Resume

When `ideate` reads `ideate_phase: risk_assess_spec_blocked` on resume, the skill:

1. Surfaces the stored show-stopper from the gate artefact file (if it exists) or from the conversation history.
2. Explains the block and waits for the human to address the issue.
3. On `"resume ideate <plan-id>"` trigger: calls `advance_phase(plan_path, 'risk_assess_spec_blocked', 'risk_assess_spec')` and re-runs this workflow.

`risk_assess_spec_blocked` is NOT autonomously cleared - explicit human action required.

Note: `ideate_iteration_count.risk_assess_spec` tracks autonomous revision attempts (bound: `MAX_RISK_ASSESS_SPEC_REVISIONS = 1`). On resume after a human-addressed block, `attempts_spent` may already be at 1 from the prior autonomous attempt; the resume path re-runs Gate B (which will re-check `attempts_spent` and skip the autonomous revision on a second show-stopper).
