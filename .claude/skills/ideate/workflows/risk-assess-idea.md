# Gate A - Risk-Assess-Idea Workflow

Adversarial risk-assessment gate that fires immediately after PLAN-file creation at Converge close, before Spec-Draft. Catches intent misconstrual, scope errors, and capability mismatches while the idea is still locked but the spec is not yet written.

Part of the ideate cadence defined in `cadence-phases.md`. For the phase-transition table, see `references/phase-transitions.md`.

Gate output artefact lifecycle: `Workbench/.ideate-gate/<plan-id>-gate-a.json` is written on a clean pass and cleaned up after Spec-Draft completes. See `cadence-phases.md section Gate A` for the authoritative lifecycle note.

---

## Trigger Condition

Gate A fires when `ideate_phase` is `""` (empty string) or absent - the live source at Converge close after plan-writer has created the PLAN file on disk. The source key is NOT `"converge"` (that key is a dead legacy entry in `VALID_TRANSITIONS`). The PLAN file must exist on disk with frontmatter before Gate A runs.

State transition on entry: `advance_phase(plan_path, '', 'risk_assess_idea')`.

---

## Standing Structural Checks (always run)

Four structural checks run at every Gate A invocation, regardless of plan content:

1. **intent-drift** - Does the locked Converge design still match the original Clarify requirement, or has the solution drifted? Check whether the design answers the problem as stated, or has shifted to answer a related-but-different problem.

2. **scope-capture** - Is there a simpler version that satisfies the requirement, or is the design over-engineered? Is there a harder version the human actually wanted? Check both directions of scope error.

3. **invisible-assumption** - What must be true about the environment or prior state for this design to work, that is not stated in the PLAN's Context? Surface implicit environmental dependencies, ordering assumptions, and prerequisite state.

4. **executor-capability** - Can the designated executor (haiku/sonnet/opus, no Bash) actually perform the work implied by the locked design? Check for shell-execution requirements, external API dependencies, or filesystem operations that exceed executor permission bounds.

---

## Domain-Specific Lenses (derived at gate-time)

After the four standing checks, derive 1-3 additional domain-specific lenses from the PLAN's Objective and Context. The derivation prompt to the orchestrator:

> "Given this PLAN's Objective and Context, what are the 1-3 most likely failure modes that the four standing checks would NOT catch? Name each as a short hyphenated label (e.g. `migration-ordering`, `api-rate-limit`) and a one-sentence description of the check."

These derived lenses are passed to the Workflow harness as additional items in `standing_checks`.

---

## Workflow Harness Call

```javascript
const result = await Workflow({
  scriptPath: ".claude/skills/ideate/workflows/risk-assess.workflow.js",
  args: {
    gate: "A",
    plan_content: "<full PLAN file content as string>",
    standing_checks: [
      "intent-drift: Does the locked Converge design still match the original Clarify requirement?",
      "scope-capture: Is the scope right - not over-engineered, not under-specified?",
      "invisible-assumption: What must be true about environment or prior state that is not stated?",
      "executor-capability: Can the designated executor (no Bash) perform the work as designed?",
      // ... plus 1-3 derived domain-specific checks
    ]
  }
});
// result: { show_stopper, show_stopper_description, mitigations }
```

---

## Output Routing

### Clean pass (`show_stopper: false`)

1. Write the synthesis mitigation list to `Workbench/.ideate-gate/<plan-id>-gate-a.json`:
   ```json
   {
     "gate": "A",
     "plan_id": "<plan-id>",
     "show_stopper": false,
     "show_stopper_description": null,
     "mitigations": [
       { "finding": "...", "mitigation": "...", "incorporated_into_phase": "spec_draft" }
     ]
   }
   ```

2. Pass the mitigation list as additional context into Spec-Draft. The orchestrator prepends the mitigations to the Spec-Draft prompt so the spec author can address them without a separate surface.

3. Advance phase: `advance_phase(plan_path, 'risk_assess_idea', 'spec_draft')`.

4. Proceed to Phase 4 (Spec-Draft). Do NOT surface the mitigation list to the human - findings fold silently into Spec-Draft context unless a show-stopper is detected (per D4).

### Show-stopper detected (`show_stopper: true`)

1. Surface to the human with the show-stopper description. Format:

   > **Gate A - Risk-Assess-Idea: show-stopper detected**
   >
   > `<show_stopper_description>`
   >
   > The ideation arc is halted. Address the show-stopper, then say `"resume ideate <plan-id>"` to re-run Gate A.

2. Set `ideate_phase: risk_assess_idea_blocked` via `advance_phase(plan_path, 'risk_assess_idea', 'risk_assess_idea_blocked')`.

3. Halt. Do NOT write the gate artefact on a blocked pass (no `show_stopper: true` artefact written).

---

## Blocked-Phase Resume

When `ideate` reads `ideate_phase: risk_assess_idea_blocked` on resume, the skill:

1. Surfaces the stored show-stopper from the gate artefact file (if it exists) or from the conversation history.
2. Explains the block and waits for the human to address the issue.
3. On `"resume ideate <plan-id>"` trigger: calls `advance_phase(plan_path, 'risk_assess_idea_blocked', 'risk_assess_idea')` and re-runs this workflow.

`risk_assess_idea_blocked` is NOT autonomously cleared - explicit human action required.

The `ideate_iteration_count.risk_assess_idea` counter is incremented by `advance_phase()` when transitioning `risk_assess_idea_blocked -> risk_assess_idea` (human-initiated re-runs). First-entry (`"" -> risk_assess_idea`) does NOT increment the counter.
