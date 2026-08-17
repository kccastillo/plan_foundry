# Audit-Sufficiency Procedure

This procedure is conceptual review rather than mechanical review. Each lens carries a concrete prompt, so apply all nine lenses, classify each finding as Blocker or Not-blocker, then compose the structured review.

## Step 1: Validate preconditions
- Read the PLAN file at `plan_path`.
  - Unreadable -> `outcome: exception` with diagnostics.
- Check structural completeness: Objective, Context, Steps, Verification sections all exist.
  - Missing -> `outcome: exception` with diagnostics.
- For each filename in PLAN frontmatter `linked_inputs:`, verify the file exists at `Workbench/<filename>`.
  - Missing -> `outcome: exception`.
- Scan the Steps section for cited source-file paths on a best-effort basis, and note any path that does not exist as a `freshness` lens finding rather than an exception.

## Step 2: Read the PLAN's referenced inputs
- Read each `linked_inputs:` file. An input either informs the Context or captures a decision you need to know about during sufficiency review.
- For source files cited in Steps (when paths look real): spot-check 2-3 of them. Do not read everything, because the goal is sampling rather than exhaustive context loading.

## Step 3: Apply the nine lenses

For each lens, use the prompt below. Generate findings, and classify each finding as Blocker or Not-blocker.

### Lens 1 - Assumptions
**Prompt:** What does this PLAN's design depend on that has not been confirmed in this Claude Code version, this codebase, this team's tooling, or this environment? Surface load-bearing assumptions before they become silent failures.

**Examples of blockers:** "Step 3 assumes feature X is supported but probe-1 did not verify", "Step 7 depends on Bash command Y being available - not in `.claude/settings.json` permissions", and "Decision N references behaviour that is not documented anywhere".

**Examples of not-blockers:** "Step 5 assumes a tool returns JSON, which the tool usually returns, although the format may vary".

### Lens 2 - Validation path
**Prompt:** When is this PLAN's design first tested? If testing comes late, what is at risk when a foundational assumption is wrong? Look for the gap between "we built it" and "we verified it works".

**Examples of blockers:** "PLAN builds 6 things and only validates at the very end via dogfood - if assumption X is wrong, we discover after building all 6", and "No smoke test exists for the orchestrator's re-entry pattern".

**Examples of not-blockers:** "Validation is at end-of-PLAN rather than per-step, but the steps are tightly coupled so per-step does not add much".

### Lens 3 - Test fidelity
**Prompt:** Does the dogfood / smoke test exercise real friction, or is the test a contrived synthetic that does not surface real-world issues?

**Examples of blockers:** "Dogfood target is `note-jot` - a synthetic skill with no real ideation surface, so building the skill does not prove the pipeline survives real planning friction", and "Test data is hand-crafted and will not trigger edge cases that real data would".

**Examples of not-blockers:** "Test target is small but exercises the critical path".

### Lens 4 - Edge cases at the orchestration layer
**Prompt:** What if a referenced artefact is missing, malformed, or fails? Does the PLAN handle these cases, or does the PLAN leave them silent?

**Examples of blockers:** "Orchestrator re-entry on a missing PLAN file is not specified, so the orchestrator would silently advance", "Loop has no max-iteration guard, so the loop could run away", and "If a subagent returns a malformed `<pipeline-result>` block, behaviour is undefined".

**Examples of not-blockers:** "Subagent dispatch error reporting could be more verbose".

### Lens 5 - Freshness
**Prompt:** Anything elsewhere in the codebase, memory, or docs that this design contradicts? Anything that will become misleading after this PLAN executes?

**Examples of blockers:** "Memory note says X always commits and pushes, but this PLAN decouples X from git without updating the memory", and "CLAUDE.md skill table will be stale after this PLAN, and no step updates the table".

**Examples of not-blockers:** "Workflow file has a typo from a previous edit, which is harmless but worth fixing".

### Lens 6 - Meta
**Prompt:** Is the design over-engineered? Could the design be smaller? What is the minimum viable version of this PLAN?

**Examples of blockers:** "PLAN has 14 decisions but only 3 are real choices - the others are mechanically forced, so the 14-decision header obscures the real design surface", and "Three steps could be one if we accept slightly less granular Verification".

**Examples of not-blockers:** "PLAN is comfortable with bootstrap chicken-and-egg, which is fine because the cost is one-time".

### Lens 7 - Spec-acceptance fidelity (per parent decision 25)
**Prompt:** Does the PLAN's `acceptance:` sample(s) actually exercise what the Objective claims to deliver? Or are the samples incidental box-ticks that pass without the deliverable working?

**Examples of blockers:** "Objective says 'ship a working note-jot skill' but Verification only checks the SKILL.md file exists and never invokes the skill on a real input", and "PLAN has zero `acceptance:` items - only `verify:` state assertions".

**Examples of not-blockers:** "Acceptance check could be more thorough but covers the critical path".

### Lens 8 - Rigour heuristics applied (per PLAN-AB2)

**Prompt:** Were the Spec-Draft rigour heuristics (H2 capacity ceiling, H4 calling-convention checklist, H8 literal-heading discipline) applied correctly in this PLAN?

Apply the sub-checks below. Each missing item is a `warn`-severity finding rather than an `error`, because false-positives are likely and an `error` would over-alarm for specs that simply have no relevant deliverables.

Read the sub-checks yourself. This lens has no lint module. PLAN-AB2's Q4 chose a writer-template rule plus this eye-read check over a lint, and `../lib/rigour_heuristics.py` is a dormant module the executor built to hold that PLAN's specified test file. Nothing dispatches that module, and its `RGH###` codes appear in neither auditor-codes register, so do not run the module and do not emit its codes. Findings from this lens use the ordinary `S###` codes.

**H2 - Capacity-ceiling acknowledged:**
If the spec's deliverable count for any discrete unit type carrying a threshold in `.claude/skills/_shared/capacity-thresholds.md` exceeds 0.8x that threshold, check that the PLAN's Context section explicitly acknowledges the threshold brushing and notes that a research bot was dispatched. If the brushing is not acknowledged -> emit a `warn` finding: "capacity-threshold brushing unacknowledged: deliverable count N exceeds 0.8x threshold T but Context does not document it."

**H4 - Calling-convention checklist filled:**
Scan the Steps body for test-runner keywords (`pytest`, `unittest`, `async def`, `asyncio`), API client patterns, or platform-specific keywords (`posix`, `windows`, `subprocess`, `os.path`). If the scan finds any of them, check that the PLAN's Context section enumerates the relevant calling conventions (async/sync posture, fixture patterns, platform conventions). If keywords are present but no conventions are enumerated -> emit a `warn` finding: "calling-convention checklist absent: Steps contains test/API/platform keywords but Context does not enumerate conventions."

**H8 - Literal-heading discipline:**
Scan Step bodies for deliverable-section references that use ambiguous prose (patterns: "should have a .* section", "should include a .* section", "add a .* sub-section", "include a .* section") rather than literal heading syntax (`MUST include a \`## X\` heading`). Each ambiguous reference -> emit a `warn` finding: "literal-heading violation: Step N specifies deliverable section by ambiguous prose. Use 'MUST include a \`## X\` heading' syntax."

**Examples of blockers under this lens:** None - all H2/H4/H8 findings are warn-severity rather than blockers, because the heuristics are advisory checks rather than structural correctness gates.

**Examples of not-blockers:** "H2 threshold not approached (deliverable count is 12 tools, well under 0.8x 50 = 40 - no acknowledgement needed)", "H4 trigger not met - Steps has no test-runner keywords", and "H8 all named sections use literal-heading syntax."

### Lens 9 - Audit-trail durability (per PLAN-AB8)

Decision-driving inputs (research-bot returns, ADVICE) must be persisted as Workbench artefacts before PLAN sufficiency closes - otherwise the trail of *why* the PLAN's decisions were made is lost to memory compaction. Lens 5 freshness covers stale references, whereas this lens covers provenance durability.

Emit **S701** (severity: **blocker**, category: **audit-trail-durability**) when the PLAN's Context, Steps, or trace describes a research-bot dispatch - qualifying patterns: `"research bot"`, `"research-bot"`, `"expand-research"`, OR `subagent_type: general-purpose` co-occurring within ~10 lines with research-framing tokens (`"research"`, `"prior art"`, `"find evidence"`, `"investigate"`, `"survey"`) - AND the PLAN's `linked_inputs` frontmatter array contains no input file (no entry matching the live convention `INPUT-\d{8}-\d{4}-`, nor either grandfathered form `RESEARCH-\d+_` or `\d{12}_RESEARCH_`). Suggest the operator invoke `Skill("write-input")` per cluster and add the resulting filenames to `linked_inputs`.

## Step 4: Triage Human-input items (decision 15)

Across all lens findings, identify each Blocker and classify the Blocker using the **closed snake_case enum**: `already_locked` | `mechanically_forced` | `real_judgement_call`. Every Blocker (regardless of class) MUST appear in `triaged_human_items` in the Step 6 output with the correct snake_case `class` value - not only `real_judgement_call` items. Every entry in `triaged_human_items` MUST carry `code` and `location` fields equal to those of the finding the entry classifies. The orchestrator locates a blocker's repair by that pair rather than by matching prose. **Collision rule:** if the pair matches more than one finding in the round, every matching finding goes to the human surface and none of their patches are applied.

Classify each per parent PLAN 202605011400 decision 15:

- **`already_locked`** - the Human proposed or affirmed the item earlier in the conversation or the PLAN history. List for transparency without asking a question.
- **`mechanically_forced`** - only one alternative exists, either as a downstream consequence of locked decisions or as a scope-internal mechanism choice that the agent can resolve via best judgement per CLAUDE.md autonomous-execution rule (and record in the PLAN's Design Decisions Classification with a one-line rationale). List for transparency without asking a question. An auditor classifying a blocker `mechanically_forced` MUST supply a patch on the corresponding finding. If the repair cannot be expressed as an exact string replacement, the item MUST be classified `real_judgement_call` instead. An insertion is expressed by anchoring on the line preceding the insertion point and repeating that line at the head of `new_string`.
- **`real_judgement_call`** - surface as a question. **Narrowed criterion (T15, 2026-05-13):** only items that are architectural, irreversible, or shape-defining qualify. CLAUDE.md's "Autonomous execution" rule (CLAUDE.md:139-142) names two escalation categories: *"true blockers, where work cannot continue without their input"* and *"major architectural decisions, such as framework changes, schema migrations, data deletion, or choices between fundamentally different designs"*. CLAUDE.md:144 then names this `real_judgement_call` classification as the authoritative definition of both categories, so the T15 bar above is the source rather than a restatement of CLAUDE.md. CLAUDE.md itself does not use the words "irreversible" or "shape-defining", and the T15 narrowing adds them.

**Not real-judgement-calls - resolve autonomously and classify as Mechanically-forced:**
- Mechanism choices between near-equivalent alternatives (e.g. HTML-comment sentinel vs YAML-frontmatter sentinel vs custom-string sentinel - pick one, record rationale)
- Naming / phrasing / wording within the PLAN's scope
- Multi-match / multi-result handling policies (e.g. silent-pick vs fail-loud - pick per ecosystem precedent, record rationale)
- Test-coverage tradeoffs (e.g. state-only vs behavioural acceptance - pick per cost/value balance, record rationale)
- Path portability assumptions, glob patterns, file-extension choices
- Whether to inline a value or reference it indirectly
- Step decomposition / ordering (granularity of Steps within an already-scoped PLAN)
- Verification item phrasing and shell-command construction

When in doubt, prefer Mechanically-forced classification and record the rationale, because the human can always re-open the item via revision. Over-surfacing breaks the autonomous-execution contract in CLAUDE.md's "Autonomous execution" rule (CLAUDE.md:144): *"Use best judgement for routine decisions such as naming, phrasing, ordering, formatting, and scope-internal trade-offs. Record those decisions in the PLAN's Executor Notes."*

Only Real-judgement-call items appear as questions in the surfaced review.

## Step 5: Compose review output

Format per CLAUDE.md "Reviews" rule:

```markdown
## Verification preamble
Reviewed PLAN [filename] against:
- [list of inspected files: linked_inputs, source files]
- Cross-checked decisions [list] against [files where they're documented]

## Verdict
[One line]

## Sufficiency findings

### Lens 1 - Assumptions
**Blockers**
1. [Finding] - suggested fix shape: [direction, not full text]

**Not blockers**
- [Nit]

### Lens 2 - Validation path
[same shape]

[... repeat for all 9 lenses ...]

## Triaged Human-input items
**Already locked** (transparency only):
- [item]

**Mechanically forced** (transparency only):
- [item]

**Real judgement calls** (Human input requested):
- [question]

## Net verdict
[ready to advance / revise the N blockers and re-audit]

Blockers: N
```

## Step 6: Emit the pipeline-result block

End the agent's response with:
```
<pipeline-result>
```json
{
  "outcome": "success" | "revision_needed" | "exception",
  "payload": {
    "blockers_count": <int>,
    "review_text": "<the formatted review>",
    "triaged_human_items": [
      { "class": "real_judgement_call", "item": "...", "code": "S002", "location": "Step 3" },
      { "class": "mechanically_forced", "item": "...", "code": "S001", "location": "Step 7" },
      { "class": "already_locked", "item": "...", "code": "S003", "location": "Context paragraph 2" }
    ]
  },
  "diagnostics": {
    "findings": [
      {
        "code": "S001",
        "level": "error",
        "category": "assumptions",
        "location": "Step 7",
        "message": "<what is wrong>",
        "patch": {
          "old_string": "<exact anchor text>",
          "new_string": "<exact replacement text>",
          "occurrence": 1
        }
      }
    ]
  }
}
```
</pipeline-result>
```

**`diagnostics.findings` is mandatory and is emitted on every return, including
`outcome: success` (where it is an empty array).** The array carries one entry per
finding, blockers and not-blockers alike. Field shapes are defined in
[../../_shared/auditor-schema-v3.md](../../_shared/auditor-schema-v3.md).

The orchestrator fingerprints this array. `audit_loop.py` hashes
`code|level|category|location` to detect a finding recurring across iterations,
and `build_brief.py` renders the prior round's findings into the next round's
brief so the auditor can reconcile the prior round's findings against the current
round. Omitting the array is a malformed return rather than a quiet success:
`audit_loop.py` tests for the `findings` key inside `diagnostics` and rewrites
the outcome to `exception` when the key is absent, which halts the pipeline
through dispatch.md's existing exception routing. Before that guard, omission
silently disabled recurrence detection, emptied the prior-findings table, and
stopped the `[STUCK xN]` badge from ever firing. Every audit written before
2026-07-29 omitted the array, so the loop ran blind to its own repetition for
that entire stretch.

Keep `location` stable across iterations for a finding that has not moved. The
fingerprint depends on `location`, and a finding relocated by an edit reads as a
new finding rather than a recurring one.

The orchestrator parses this block to drive the audit-loop state machine (parent decision 21).

## Operating notes

- **The exemplar (`../references/sufficiency-audit-exemplar.md`) is the calibration target.** If your review is shallower than the exemplar, you missed lenses or did not read referenced files. If your review is heavier, check whether you have ventured into mechanical territory, and refactor those findings out because they belong to `audit-haiku-safe`.
- **Token economy:** sufficiency audit is the most expensive phase per dispatch (Opus reading PLAN + multiple inputs + sampled source files). Aim for one pass per loop iteration, and do not redo work the previous iteration already covered unless the revision actually invalidates prior findings.
- **Stay conceptual.** If you find yourself counting commas in a step, you are in the wrong skill. Stop and refactor that finding out.
- **The exemplar records 6 issues across 6 lenses** from a single Opus pass. Do not expect findings at every lens every time, because sometimes the correct output records "no findings" under a lens.

**`blockers_count` is a handoff value, never a stored source of truth.** The value travels in the live `<pipeline-result>` for this dispatch and is persisted only as part of the audit record. Nothing reads the value back off disk, and nothing should start. `diagnostics.findings` is the list, and any later reader wanting a blocker count derives the count from that array. A count read back from a file is a claim about findings the reader has never examined.
