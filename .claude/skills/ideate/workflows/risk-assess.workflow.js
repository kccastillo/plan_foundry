export const meta = {
  name: 'risk-assess',
  description: 'Adversarial risk-assessment gate harness for the ideate cadence. Runs parallel Haiku checks against a PLAN (Gate A: pre-spec; Gate B: post-spec), then synthesises findings with Opus. Returns {show_stopper, show_stopper_description, mitigations}.',
  whenToUse: 'Called by risk-assess-idea.md (Gate A) and risk-assess-spec.md (Gate B) during the ideate cadence. Not invoked directly. args must be an object: {gate: "A"|"B", plan_content: string, standing_checks: string[]}.',
  phases: [
    { title: 'Adversarial checks', detail: 'One Haiku agent per check lens (parallel fan-out)', model: 'haiku' },
    { title: 'Synthesis', detail: 'Opus merges findings, judges severity, produces mitigation list', model: 'opus' },
  ],
}

// ─────────────────────────────────────────────────────────────────────────────
// risk-assess - adversarial gate harness for the ideate cadence (PLAN-AH3).
//
// MODEL TIER POLICY (cheapest capable per role, per _shared/dispatch-authorisation.md):
//   adversarial_check -> haiku  : boolean-output schema-bounded checks (high volume, cheap)
//   synthesis         -> opus   : merge findings, judge severity, produce mitigations
//
// SCHEMAS:
//   FINDING_SCHEMA:   { triggered, severity, finding, suggested_mitigation }
//   MITIGATION_SCHEMA:{ show_stopper, show_stopper_description, mitigations[] }
// ─────────────────────────────────────────────────────────────────────────────

const FINDING_SCHEMA = {
  type: "object",
  required: ["triggered", "severity", "finding", "suggested_mitigation"],
  properties: {
    triggered: { type: "boolean" },
    severity: { enum: ["blocker", "revision", "info"] },
    finding: { type: "string" },
    suggested_mitigation: { type: "string" },
  },
}

const MITIGATION_SCHEMA = {
  type: "object",
  required: ["show_stopper", "show_stopper_description", "mitigations"],
  properties: {
    show_stopper: { type: "boolean" },
    show_stopper_description: { type: ["string", "null"] },
    mitigations: {
      type: "array",
      items: {
        type: "object",
        required: ["finding", "mitigation", "incorporated_into_phase"],
        properties: {
          finding: { type: "string" },
          mitigation: { type: "string" },
          incorporated_into_phase: { type: "string" },
        },
      },
    },
  },
}

// ─── Validate args ────────────────────────────────────────────────────────────
const argsObj = (typeof args === "object" && args !== null && !Array.isArray(args)) ? args : null
if (!argsObj) {
  return {
    show_stopper: true,
    show_stopper_description: "risk-assess.workflow.js: args must be an object {gate, plan_content, standing_checks}. Received: " + JSON.stringify(args),
    mitigations: [],
  }
}
const GATE = argsObj.gate || "A"
const PLAN_CONTENT = argsObj.plan_content || ""
const STANDING_CHECKS = Array.isArray(argsObj.standing_checks) ? argsObj.standing_checks : []

if (!PLAN_CONTENT) {
  return {
    show_stopper: true,
    show_stopper_description: "risk-assess.workflow.js: plan_content is required but was empty.",
    mitigations: [],
  }
}
if (STANDING_CHECKS.length === 0) {
  return {
    show_stopper: true,
    show_stopper_description: "risk-assess.workflow.js: standing_checks array is required and must have at least one entry.",
    mitigations: [],
  }
}

const NEXT_PHASE = GATE === "A" ? "spec_draft" : "self_critique"

log("Gate " + GATE + ": running " + STANDING_CHECKS.length + " adversarial checks (haiku) -> opus synthesis")

// ─── Phase 1: Adversarial checks (HAIKU, parallel) ───────────────────────────
phase("Adversarial checks")

const ADVERSARIAL_PROMPT = (checkLabel) => {
  const parts = checkLabel.split(":")
  const label = parts[0].trim()
  const description = parts.slice(1).join(":").trim()
  return (
    "## Adversarial Risk Assessor - Gate " + GATE + ": " + label + "\n\n" +
    "You are an adversarial reviewer examining a PLAN before it is handed off to the next phase. " +
    "Your role is to be a skeptic - look for failure modes the plan author missed.\n\n" +
    "## Check: " + label + "\n" +
    (description ? description + "\n\n" : "\n") +
    "## PLAN content\n\n" + PLAN_CONTENT + "\n\n" +
    "## Task\n" +
    "Apply the check above to the PLAN content. Determine whether this check is triggered (a genuine issue found).\n\n" +
    "Severity rules:\n" +
    "- **blocker**: the plan cannot succeed as written without addressing this issue first\n" +
    "- **revision**: the plan has a significant weakness but may succeed with attention; worth surfacing\n" +
    "- **info**: minor observation; no action required\n\n" +
    "If not triggered: set triggered=false, severity='info', finding='No issue found for this check.', suggested_mitigation='None required.'\n" +
    "If triggered: set triggered=true, write a one-sentence finding and a concrete suggested_mitigation.\n\n" +
    "Structured output only. Be specific - vague findings are unhelpful."
  )
}

const findings = (await parallel(
  STANDING_CHECKS.map(checkLabel => () =>
    agent(ADVERSARIAL_PROMPT(checkLabel), {
      label: "check:" + checkLabel.split(":")[0].trim().slice(0, 40),
      phase: "Adversarial checks",
      schema: FINDING_SCHEMA,
      model: "haiku",
    }).then(result => {
      if (!result) {
        log("check returned null: " + checkLabel.slice(0, 60))
        return null
      }
      log(checkLabel.split(":")[0].trim() + ": triggered=" + result.triggered + " severity=" + result.severity)
      return { check: checkLabel.split(":")[0].trim(), ...result }
    }).catch(e => {
      log("check failed: " + checkLabel.slice(0, 60) + " - " + (e.message || e))
      return null
    })
  )
)).filter(Boolean)

const triggeredFindings = findings.filter(f => f.triggered)
log("Adversarial checks done: " + findings.length + " run, " + triggeredFindings.length + " triggered")

// ─── Phase 2: Synthesis (OPUS) ────────────────────────────────────────────────
phase("Synthesis")

const findingsBlock = triggeredFindings.length > 0
  ? triggeredFindings.map((f, i) =>
      "### Finding " + (i + 1) + " [" + f.severity + "]: " + f.check + "\n" +
      f.finding + "\n" +
      "Suggested mitigation: " + f.suggested_mitigation
    ).join("\n\n")
  : "(No triggered findings - all checks passed.)"

const allFindingsBlock = findings.length > 0
  ? findings.map((f, i) =>
      "- [" + (f.triggered ? f.severity.toUpperCase() : "PASS") + "] " + f.check + ": " + f.finding
    ).join("\n")
  : "(No findings recorded.)"

const SYNTHESIS_PROMPT =
  "## Gate " + GATE + " Risk-Assessment Synthesis\n\n" +
  "You are synthesising the output of " + STANDING_CHECKS.length + " adversarial checks against a PLAN. " +
  "Your task is to determine whether the checks found a show-stopper (an issue so severe the plan cannot proceed to the next phase without correction) and to produce a mitigation list for all triggered findings.\n\n" +
  "## All check outcomes\n" + allFindingsBlock + "\n\n" +
  "## Triggered findings (for synthesis)\n" + findingsBlock + "\n\n" +
  "## Next phase\n" +
  "If the plan passes (no show-stopper): mitigations are folded silently into '" + NEXT_PHASE + "' context.\n" +
  "If show-stopper found: the ideate arc is halted and the human is surfaced with the show_stopper_description.\n\n" +
  "## Task\n" +
  "1. Determine show_stopper: true only when >=1 finding has severity='blocker'. A collection of 'revision' findings does NOT constitute a show-stopper - they are addressed in the next phase.\n" +
  "2. If show_stopper=true: write a one-paragraph show_stopper_description that names the specific blocker, explains why it prevents proceeding, and states what the human must address before rerunning the gate.\n" +
  "3. If show_stopper=false: set show_stopper_description=null.\n" +
  "4. Produce the mitigations list: one entry per triggered finding (triggered=true). For each entry, write a concrete mitigation and set incorporated_into_phase to '" + NEXT_PHASE + "'. Omit non-triggered findings.\n" +
  "5. If no triggered findings: mitigations=[], show_stopper=false, show_stopper_description=null.\n\n" +
  "Structured output only."

const synthesis = await agent(SYNTHESIS_PROMPT, {
  label: "synthesize",
  phase: "Synthesis",
  schema: MITIGATION_SCHEMA,
  model: "opus",
})

if (!synthesis) {
  log("Synthesis returned null - returning safe default (show_stopper=false, no mitigations)")
  return {
    show_stopper: false,
    show_stopper_description: null,
    mitigations: triggeredFindings.map(f => ({
      finding: f.finding,
      mitigation: f.suggested_mitigation,
      incorporated_into_phase: NEXT_PHASE,
    })),
  }
}

log("Synthesis done: show_stopper=" + synthesis.show_stopper + " mitigations=" + synthesis.mitigations.length)

return {
  show_stopper: synthesis.show_stopper,
  show_stopper_description: synthesis.show_stopper_description,
  mitigations: synthesis.mitigations,
}
