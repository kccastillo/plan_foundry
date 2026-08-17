# Ideate - Eight-Phase Cadence Workflow

Phases 4-8 of the ideate cadence are defined here. Phases 1-3 are defined in `ideate-arc.md` and appear below only as cross-references, so do not duplicate or contradict that document.

For the phase-transition routing table, see `references/phase-transitions.md`. For the critique JSON schema, see `references/critique-schema.md`. For critique codes, see `references/critique-codes.md`.

---

## Phase 1 - Clarify

**Cross-reference:** `workflows/ideate-arc.md` section Phase 1 - Clarify. All procedure is defined there, and this section only summarises that procedure.

**Purpose:** Establish the requirement before any mechanism is discussed. Reframe malformed questions. Surface implicit constraints.

**Input contract:** Trigger phrase from the human (any of the documented ideate triggers, including the phase-explicit ones the human uses to skip straight to a phase).

**Output contract:** A restated problem statement that the human has acknowledged ("yes, that's right" or an equivalent refinement).

**Boundary check:** The human explicitly acknowledges the stated requirement. The orchestrator never exits Phase 1 on its own.

**Human surface:** Open question(s) + "Is this the right framing? Confirm or correct me."

**Early-exit path:** When the human signals abandon, produce an input file if the clarification revealed a decision worth persisting, then end ideation.

**State:** Conversational. `ideate_phase` is absent/empty throughout. If the human wants durability, the `/checkpoint` command writes `Workbench/.ideate-checkpoint/<thread-id>.md` for the forensic record.

---

## Phase 2 - Survey

**Cross-reference:** `workflows/ideate-arc.md` section Phase 2 - Survey. All procedure is defined there.

**Purpose:** Generate the solution space with honest tradeoffs. State which you lean toward and explain why. Phase 2.A below enumerates at least 3 options per cluster internally wherever that many genuinely exist, and the floor for what reaches the Human is the at-least-2 bar set in `ideate-arc.md` section Phase 2 - Survey. Apply F2 expand-explode before presentation, F1 research-anchor between expansion and presentation, and the F7 triage column in all tables.

**Input contract:** Confirmed problem statement from Phase 1.

**Output contract:** Structured survey per Phase 2.A -> 2.B -> 2.C sequence (below). Human selects or proposes a refinement.

**Boundary check:** Human has explicitly selected an option (or explicitly combined options, or proposed a new option that re-enters survey).

**Human surface:** Per Phase 2.C format - headline summary per cluster + tradeoff table with triage column + invite for input.

**Early-exit path:** Produce an input file, whether the gap is missing data or a strategic decision worth persisting. Ideation pauses here until that input is written.

**State:** Conversational. `ideate_phase` remains empty. The `/checkpoint` command is available.

### Phase 2.A - F2 Expand-Explode (pre-presentation)

Before Survey is presented to the Human, the orchestrator runs an internal expand-explode pass:

1. **Enumerate >=3 options per cluster.** For each decision cluster, brainstorm at least 3 distinct approaches. If 3+ genuine alternatives exist, list them all. If fewer than 3 alternatives genuinely exist, proceed to the anti-option discipline.

2. **Anti-option discipline (always applies).** The orchestrator MUST name the "obvious anti-option" - the approach that would be wrong here and why - even when >=3 options already exist. Naming the anti-option forces the question "what would be wrong here" and makes implicit assumptions explicit. Every cluster carries at least one anti-option, with no exception.

3. **One-line reason per option.** For each option (including anti-options), write one line stating the reason for inclusion, rejection, or lean. This line makes the orchestrator's filtering pass visible to the Human and carries the lean signal itself.

4. **Output of 2.A:** an internal options-with-reasons list per cluster, classified per decision 15 (taxonomy: See `../../audit-sufficiency/workflows/audit-sufficiency-steps.md` - Step 4). Phase 2.B (research trigger) and Phase 2.C (presentation) both read this list.

### Phase 2.B - F1 Research-Anchor (between expand and presentation)

After Phase 2.A expansion, apply the research-anchor trigger:

1. **Count Real-judgement-call clusters** in the post-expand option space.

2. **Auto-dispatch threshold (>=2 Real-judgement-call clusters):** If 2 or more Real-judgement-call clusters were identified, the orchestrator auto-dispatches one `survey-researcher` subagent per cluster (`subagent_type: survey-researcher`). Because the dispatch is concurrent Sonnet fan-out, run it under `.claude/skills/_shared/thin-orchestration.md` (bounded reply, one seed if clusters share premises, each dispatch's writable set is its own input file only). The `survey-researcher` agent carries the Sonnet model pin, so dispatching by name enforces the tier rather than relying on the session model. Each agent:
   - Model: sonnet (pinned via the `survey-researcher` agent definition at `.claude/agents/survey-researcher.md`)
   - Mode: foreground or parallel-background (orchestrator's discretion based on urgency)
   - Output cap: 400 words maximum
   - Citations required: each finding must cite at least one source (URL or canonical reference)
   - Focus: prior art in adjacent communities rather than theory from scratch

3. **Below-floor discretion (0-1 Real-judgement-call clusters):** The orchestrator decides whether to dispatch. If prior art likely exists in adjacent communities, dispatch. If the decision is internal to the spec and no external ground truth exists, skip.

4. **Human opt-out / opt-in:** The Human can always say "skip research" to suppress dispatch, or "dispatch more" to request additional research on specific clusters.

5. **Research-prompt template:** Before every dispatch, the orchestrator reads `.claude/skills/_shared/research-prompt-template.md` for the mandatory sub-questions (public-API surface, prior-art citations, lean-reversibility, verdict line). The orchestrator includes these sub-questions verbatim in every research-bot prompt.

6. **Research output destinations (both, always):**
   - Input file on disk via `Skill("write-input")` - reusable across PLANs, persistent, referenced in `linked_inputs`.
   - Inline summary appended to the Converge close - orchestrator's working context at decision time.

7. **Mandatory write-input before phase advance (per PLAN-AB8, applies to any phase that dispatches research bots - Clarify expand-research, Survey 2.B, Self-Critique research dispatch, Cross-Spec-Reconcile research dispatch):** before advancing past the dispatching phase, the orchestrator MUST persist each research-bot return (or each logical cluster of returns) as a Workbench input file via `Skill("write-input")`. The PLAN's `linked_inputs` frontmatter array MUST reference the new input filename(s). Memory-file synthesis, inline Converge summaries, and conversation-transcript references do not substitute for the on-disk Workbench artefact, because compaction breaks the audit trail. Naming: `INPUT-YYYYMMDD-hhmm-<slug>.md`. File content: verbatim bot returns + <=200-word synthesis at the top. Forensic backstop: audit-sufficiency S701 catches dispatch-without-input when this procedural step is bypassed.

8. **Reversal handling:** If a research-bot's verdict reverses the orchestrator's pre-research lean on an option, the orchestrator re-opens that specific cluster in Survey (rebuilds the row with the new lean + cites the reversal source) before proceeding to Converge. Surface explicitly: "Research returned X and the original lean was Y, so this cluster returns to Survey."

### Phase 2.C - F7 Triage Column + F8 Inverted-Pyramid (presentation format)

Survey output presented to the Human follows inverted-pyramid format:

1. **Headline summary first (F8).** Every cluster carries a 1-2 sentence summary above its table, so the most important signal appears before any prose.

2. **Tradeoff table with triage column (F7).** One row per option per cluster. Required columns:

   | Option | One-liner | Decision-tier | Lean/Reject/Defer | Reason |
   |---|---|---|---|---|

   - **Option:** short name for the approach.
   - **One-liner:** what it does, in one sentence.
   - **Decision-tier:** `locked` / `forced` / `judgement` (per decision 15, taxonomy definitions: See `../../audit-sufficiency/workflows/audit-sufficiency-steps.md` - Step 4).
   - **Lean/Reject/Defer:** orchestrator's recommendation signal.
   - **Reason:** one sentence giving the lean or rejection rationale.

3. **Prose on demand (F8).** For `judgement`-tier or novel options, the orchestrator may include a prose body after the table. For `locked` or `forced` options, the table row is enough, so add no prose. The Human can always request "expand on [option]."

4. **Anti-options in the table.** Anti-options appear as rows with `Lean/Reject/Defer: Reject` and a one-line reason. These rows make the option-pruning pass visible to the Human.

---

## Phase 3 - Converge

**Cross-reference:** `workflows/ideate-arc.md` section Phase 3 - Converge. All procedure is defined there.

**Purpose:** Sharpen the chosen approach to plan-ready specificity, then lock the decisions and classify them per decision 15.

**Input contract:** Human's chosen option from Phase 2.

**Output contract:** Decision classification per decision 15 (taxonomy: See `../../audit-sufficiency/workflows/audit-sufficiency-steps.md` - Step 4). Concrete steps and acceptance criteria are walked verbally, after which the human signals readiness to proceed to spec.

**Boundary check:** Human signals readiness ("spec this out", "write the PLAN", "ready to plan it", or equivalent).

**Human surface:** Decision-triage table + "Shall we proceed to spec this out, or stop here and record the decisions as an input?"

**Early-exit path:** Produce an input file that records the decisions without a PLAN, then end ideation at Phase 3.

**State:** Conversational. `ideate_phase` remains empty. The PLAN file MAY already exist (created at Phase 1 exit via plan-writer per ideate-arc.md) with `pipeline_phase: drafting` and partial content (Objective + Context). The `/checkpoint` command is available.

**Transition to Gate A:** When the human confirms "spec this out" (or equivalent), dispatch plan-writer to ensure the PLAN file exists with Objective + Context populated, then fire Gate A (`risk-assess-idea.md`). Do not call `advance_phase(plan_path, '', 'spec_draft')` directly, because Gate A makes its own `advance_phase` call after its checks pass. The source `ideate_phase` at that moment is `""` or absent.

---

## Gate A - Risk-Assess-Idea

**Purpose:** Adversarial pre-spec gate. Gate A runs immediately after PLAN-file creation at Converge close, before Spec-Draft. Gate A catches intent misconstrual, scope errors, invisible assumptions, and executor-capability mismatches while the idea is locked and the spec is not yet written.

**Trigger condition:** Source `ideate_phase` is `""` (empty string) or absent, which is the live state at Converge close. The dead `"converge"` key does not trigger the gate. The PLAN file must exist on disk with frontmatter before Gate A runs.

**Workflow file:** `risk-assess-idea.md`, which states the full standing-check list, domain-lens derivation, harness call, and output routing.

**`ideate_phase` values involved:** `risk_assess_idea` (gate running or passed), `risk_assess_idea_blocked` (show-stopper detected, awaiting human action).

**Output -> next-phase routing:**
- `show_stopper: false` -> write `Workbench/.ideate-gate/<plan-id>-gate-a.json` (mitigations folded silently into Spec-Draft context), advance to `spec_draft`.
- `show_stopper: true` -> surface show-stopper to human, set `ideate_phase: risk_assess_idea_blocked`, halt.

**D9 lifecycle owner:** Gate A artefact (`Workbench/.ideate-gate/<plan-id>-gate-a.json`) is cleaned up after Spec-Draft completes. Gate B artefact is cleaned up after Self-Critique completes. This note is the authoritative lifecycle instruction, and `risk-assess-idea.md` and `risk-assess-spec.md` cross-reference this note.

**Blocked-phase resume contract:** When `ideate` reads `ideate_phase: risk_assess_idea_blocked`, the skill surfaces the stored show-stopper from the gate artefact file, explains the block, and waits for the human to address the issue. On `"resume ideate <plan-id>"`, the skill calls `advance_phase(plan_path, 'risk_assess_idea_blocked', 'risk_assess_idea')` and re-runs Gate A. The `*_blocked` phase is never cleared autonomously, because clearing it requires explicit human action.

---

## Phase 4 - Spec-Draft

**State goes to disk here (first substantive phase).** Gate A precedes Phase 4 and sets `ideate_phase: risk_assess_idea` before this phase begins, although Phase 4 remains the first phase to write substantive PLAN content (Steps, Verification sections). Phase 4 is entered by calling `advance_phase(plan_path, 'risk_assess_idea', 'spec_draft')`.

**Purpose:** Produce the first complete draft implementation spec - Steps and Verification sections - in the existing PLAN file. Phase 4 does not create the PLAN file, because the PLAN already exists (created at Phase 1/3 exit per ideate-arc.md). Phase 4 extends that file.

**Input contract:**
- Locked decisions from Phase 3.
- Existing PLAN file at `Workbench/PLAN-<ID>_<slug>.md` with `pipeline_phase: drafting` (created by plan-writer during Phase 1-3).
- The PLAN file has Objective + Context + Design Decisions Classification already populated.

**Output contract:**
- PLAN file extended with populated Steps section and Verification section (with at least one `acceptance:` item).
- PLAN frontmatter updated: `ideate_phase: spec_draft` (entered from `risk_assess_idea`).
- Commit written (the parent session commits, because the executor defers to the parent per the harness contract).

**Boundary check:** The PLAN file exists and parses, the Steps and Verification sections are present and non-empty, and `ideate_phase: spec_draft` is set in frontmatter.

**Human surface:** "PLAN draft written at `<path>`. Ready to run self-critique. Reply 'continue' to proceed or 'stop here' to exit early."

**Early-exit path:** If the human replies "stop here" or equivalent, set `ideate_phase: exited_early`. The PLAN file is preserved with `pipeline_phase` still `drafting`, so plan-pipeline never advances that PLAN into the audit loop. Ideation ends.

**State:**
- `ideate_phase: spec_draft` (written to PLAN frontmatter at phase entry)
- `pipeline_phase: drafting` (unchanged - ideate still in flight)
- No critique JSON yet.

**Core requirement:** Phase 4 requires the plan_foundry bundle (the `write-plan` skill). Without the bundle, the cadence ends at Phase 3. Detection: at the Converge->Spec-Draft boundary, if `Skill("write-plan")` does not resolve, present the finalised decisions as plain markdown and notify the human that phases 4-8 are unavailable.

---

## Gate B - Risk-Assess-Spec

**Purpose:** Adversarial post-spec gate. Gate B runs after Spec-Draft (Phase 4) and before Self-Critique (Phase 5). Gate B catches specification construction errors - broken step sequences, unverifiable acceptance items, missing substrate references, and dependency misordering.

**Trigger condition:** Source `ideate_phase` is `"spec_draft"`. Gate B fires when Spec-Draft completes and before Self-Critique begins. Phase 5 is entered by calling `advance_phase(plan_path, 'risk_assess_spec', 'self_critique')`.

**Workflow file:** `risk-assess-spec.md`, which states the full standing-check list, domain-lens derivation, harness call, and output routing including the autonomous revision attempt logic.

**`ideate_phase` values involved:** `risk_assess_spec` (gate running or passed), `risk_assess_spec_blocked` (show-stopper detected after the revision attempt is exhausted, awaiting human action).

**Output -> next-phase routing:**
- `show_stopper: false` -> write `Workbench/.ideate-gate/<plan-id>-gate-b.json` (mitigations folded silently into Self-Critique context), advance to `self_critique`.
- `show_stopper: true` (first encounter) -> perform one autonomous spec revision, persist attempt via `set_ideate_iteration_count(plan_path, 'risk_assess_spec', 1)`, re-run Gate B.
- `show_stopper: true` (attempt spent) -> surface show-stopper to human, set `ideate_phase: risk_assess_spec_blocked`, halt.

**D9 lifecycle owner:** Gate B artefact (`Workbench/.ideate-gate/<plan-id>-gate-b.json`) is cleaned up after Self-Critique completes. Gate A artefact is cleaned up after Spec-Draft completes. This note is the authoritative lifecycle instruction, and `risk-assess-idea.md` and `risk-assess-spec.md` cross-reference this note.

**Blocked-phase resume contract:** When `ideate` reads `ideate_phase: risk_assess_spec_blocked`, the skill surfaces the stored show-stopper from the gate artefact file, explains the block, and waits for the human to address the issue. On `"resume ideate <plan-id>"`, the skill calls `advance_phase(plan_path, 'risk_assess_spec_blocked', 'risk_assess_spec')` and re-runs Gate B. The `*_blocked` phase is never cleared autonomously, because clearing it requires explicit human action.

---

## Phase 5 - Self-Critique

**Purpose:** Structured self-critique gate. The orchestrator produces a critique JSON against the Phase 4 spec, then presents the findings to the human using the severity-surface pattern (via `lib/render_critique.py`). Self-Critique focuses on **structural omissions** - missing sections, missing details, internal inconsistency - and is distinct from audit-sufficiency (invariant violations) and audit-haiku-safe (mechanical safety). See [`_shared/audit-stages.md`](../../_shared/audit-stages.md) for how the focus of each audit stage differs.

**Input contract:**
- PLAN file with `ideate_phase: risk_assess_spec` and fully populated Steps + Verification sections.
- `ideate_iteration_count.self_critique < 5`.

**Output contract:**
- Critique JSON at `Workbench/.ideate-critique/<plan-id>-<iter>.json` (committed). See `references/critique-schema.md` for schema.
- `ideate_phase: self_critique` set in PLAN frontmatter.
- `ideate_iteration_count.self_critique` incremented.
- Severity-surface prompt rendered and shown to human per F7/F8 format below.

**Boundary check:** The critique JSON is written and parseable, `ideate_phase` is `self_critique`, and `ideate_iteration_count.self_critique` is >= 1.

### Phase 5 Output Format - F7 Triage Column + F8 Inverted-Pyramid

Self-Critique output presented to the Human follows inverted-pyramid format:

1. **Headline summary first (F8).** 1-2 sentences summarising the overall critique picture before any table. Example: "Two major structural omissions and no blocking design issues. The spec is otherwise sound."

2. **Findings table with triage column (F7).** Required columns:

   | Code | Severity | Finding | Decision-tier | Suggested-fix-shape |
   |---|---|---|---|---|

   - **Code:** finding ID (C1, C2, ...).
   - **Severity:** `major` / `minor`.
   - **Finding:** one-sentence description of the structural omission.
   - **Decision-tier:** `locked` / `forced` / `judgement` - how much Human attention this finding requires. The Human decides the `judgement` findings, a `forced` finding has one obvious fix, and a `locked` finding has already been addressed in the spec. Taxonomy definitions: See `../../audit-sufficiency/workflows/audit-sufficiency-steps.md` - Step 4.
   - **Suggested-fix-shape:** one sentence indicating the fix direction (not the fix itself).

3. **Prose only for `judgement`-tier or novel findings (F8).** Mechanical or forced findings appear as a table row only, with no prose. The Human can always request "details C1."

**Human surface:** Rendered by `lib/render_critique.py:render_critique_surface()`. Shows findings grouped by severity (major / minor) in the table format above. Action menu:
- `address C1` - fix this finding in Spec-Refine
- `defer C2` - acknowledge the finding without fixing it this iteration (carry forward)
- `dispute C3: <reason>` - the critique finding is wrong, and the reply gives the rationale
- `discard C4` - cancel this finding (no fix, no carry-forward)
- `discard_all` - discard all findings and short-circuit to Phase 8 (Consolidate)
- `details C1` - show full issue + suggested_fix text
- `?` - show this help

**Early-exit paths:**
- `discard_all` -> advance directly to Phase 8 (Consolidate). Set `ideate_phase: consolidate`.
- `exited_early` -> the human signals abandon, and the PLAN is preserved with its current `ideate_phase`.

**Iteration bound:** If `ideate_iteration_count.self_critique == 5` at this phase entry, halt-and-surface. Do not dispatch a new critique. The Human must take an explicit action (ship / exit / override) to break the halt.

**Zero-findings short-circuit:** If the critique JSON carries `findings: []`, advance directly to Phase 8 (Consolidate). Write the empty JSON to disk for the forensic record. Notify the human: "No critique findings. Advancing to Consolidate."

**State:**
- `ideate_phase: self_critique`
- `ideate_iteration_count.self_critique += 1`
- Critique JSON written to `Workbench/.ideate-critique/<plan-id>-<iter>.json`

---

## Phase 6 - Spec-Refine

**Purpose:** Produce the revised spec (v2, v3, ...) that addresses the `address`-tagged findings from Phase 5. Update the PLAN in place and record the addressed fingerprints.

**Input contract:**
- PLAN file with `ideate_phase: self_critique`.
- Most recent critique JSON from `Workbench/.ideate-critique/`.
- Human's action decisions parsed by `lib/render_critique.py:parse_critique_reply()` - specifically the list of `address`-tagged finding fingerprints.

**Output contract:**
- PLAN file updated (Steps / Verification sections revised to address the `address`-tagged findings).
- `ideate_phase: spec_refine` set in PLAN frontmatter.
- `ideate_critique_addressed` list in PLAN frontmatter extended with fingerprints of addressed findings (appended, not replaced - cumulative across iterations).
- `ideate_iteration_count.spec_refine` incremented.

**Boundary check:** The PLAN file is updated, `ideate_phase` is `spec_refine`, and the addressed fingerprints are recorded in `ideate_critique_addressed`.

**Human surface:** "v{V} PLAN written. {K} findings addressed, {L} deferred, {M} disputed, {N} discarded. Ready for Cross-Spec-Reconcile. Reply 'continue' or 'ship it' to skip reconcile."

**Early-exit path:** "ship it" -> advance directly to Phase 8 (Consolidate). Set `ideate_phase: consolidate`. Skip Phase 7.

**Back-loop path:** The Human may request an additional critique before reconcile. On the reply "critique again", check the iteration bound first, then advance to Phase 5 for a further iteration.

**State:**
- `ideate_phase: spec_refine`
- `ideate_iteration_count.spec_refine += 1`
- `ideate_critique_addressed` list appended

---

## Phase 7 - Cross-Spec-Reconcile

**Purpose:** Check for dependencies and conflicts with other in-flight PLANs. Phase 7 runs once and always concludes by writing `ideate_reconcile_outcome`, with no loop and no unbounded retry.

**Input contract:**
- Refined PLAN file with `ideate_phase: spec_refine`.
- Scan of `Workbench/*.md` frontmatter for in-flight PLANs.

**Auto-skip detection:**
The orchestrator scans `Workbench/*.md` for PLANs (other than the current PLAN) where:
```
pipeline_phase ∈ {drafting, drafted, checked, executing, outcome-verifying}
AND (ideate_phase ∉ {complete, exited_early} OR ideate_phase field absent)
```
The scan uses `lib/state.py:detect_in_flight_plans()`.

If the scan finds no such PLANs, skip the phase automatically and set `ideate_reconcile_outcome: passed`. Notify the human: "No other in-flight PLANs. Cross-spec reconcile auto-skipped. Advancing to Consolidate."

**Output contract:**
- `ideate_phase: cross_spec_reconcile` set at phase entry.
- `ideate_reconcile_outcome` written (always, even on auto-skip):
  - `passed` - no conflicts or auto-skipped
  - `conflicts-resolved` - conflicts found and resolved
  - `conflicts-pending` - conflicts found, and the human accepted them as intentional

**Boundary check:** `ideate_phase` is `cross_spec_reconcile` and `ideate_reconcile_outcome` is non-empty.

**Human surface (when conflicts found):** Per F7/F8 format below - headline summary + conflict table with triage column + proposed resolutions. Human replies:
- `accept proposal` - accept the orchestrator's suggested resolution
- `modify: <alternative>` - accept with modification
- `dispute: <reason>` - the conflicts are intentional, so proceed with `conflicts-pending`

### Phase 7 Output Format - F7 Triage Column + F8 Inverted-Pyramid

Cross-Spec-Reconcile output (when conflicts are found) follows inverted-pyramid format:

1. **Headline summary first (F8).** 1-2 sentences summarising the reconcile picture before any table. Example: "Two conflicts with PLAN-AB0 on vocabulary. A shared interface forces the first, and the second requires a Human decision."

2. **Conflict table with triage column (F7).** Required columns:

   | # | Conflict description | Sibling PLAN | Decision-tier | Proposed resolution |
   |---|---|---|---|---|

   - **#:** conflict number.
   - **Conflict description:** one-sentence description of the conflict or dependency.
   - **Sibling PLAN:** the other in-flight PLAN involved.
   - **Decision-tier:** `locked` / `forced` / `judgement`. A `forced` conflict has one obvious fix that the orchestrator applies without prompting, while a `judgement` conflict requires Human input, so the orchestrator surfaces only `judgement`-tier conflicts to the Human. Taxonomy definitions: See `../../audit-sufficiency/workflows/audit-sufficiency-steps.md` - Step 4.
   - **Proposed resolution:** one sentence describing the recommended fix.

3. **Prose only for `judgement`-tier conflicts (F8).** A `forced` conflict appears as a table row only. The Human can request "details on conflict 2" for elaboration.

**Holding-PLAN reconcile note:** When reconciling against a sibling PLAN that is in preliminary-holding state (`pipeline_phase: drafting` with `ideate_phase` empty or absent, which is the pre-state named in `references/phase-transitions.md`), also walk that PLAN's `linked_inputs`, because the reconcile evidence is in the input files rather than the PLAN body. A holding-PLAN body contains only Key Questions and optional context, and the substantive design content is in its linked input files.

**Early-exit path:** None. Phase 7 always concludes by writing `ideate_reconcile_outcome`. If the human marks `conflicts-pending`, the PLAN still advances to Phase 8 (human has accepted responsibility for the pending conflicts).

**Back-loop path:** If a conflict requires editing the PLAN, human may request return to Phase 6 (spec-refine). Transition: `cross_spec_reconcile -> spec_refine`. Increment `ideate_iteration_count.spec_refine`.

**State:**
- `ideate_phase: cross_spec_reconcile` (at phase entry)
- `ideate_reconcile_outcome: passed | conflicts-resolved | conflicts-pending` (written before phase exit)

---

## Phase 8 - Consolidate

**Purpose:** Finalise the spec and produce the terminal state that hands off to plan-pipeline. Phase 8 is the only phase that flips `pipeline_phase`.

**Input contract:**
- Refined (and reconciled) PLAN file with `ideate_phase` ∈ {`spec_refine`, `cross_spec_reconcile`}, or a PLAN entering directly via the `discard_all` shortcut.
- `ideate_reconcile_outcome` is non-empty, unless the PLAN entered via the `discard_all` shortcut, in which case the field remains empty and that is acceptable.

**Output contract:**
- PLAN file committed with:
  - `pipeline_phase: drafted` (flipped from `drafting`)
  - `ideate_phase: complete`
- All sections (Objective, Context, Design Decisions Classification, Steps, Verification) present and non-empty.
- At least one `acceptance:` item in Verification.

**Boundary check:**
- `pipeline_phase: drafted` in PLAN frontmatter.
- `ideate_phase: complete` in PLAN frontmatter.
- PLAN file parses correctly.
- Commit exists (the parent session commits, because the executor defers).

**Human surface:** "PLAN finalised. `pipeline_phase` flipped to `drafted`. Ideate complete. Plan-pipeline audit loop will start on next pipeline invocation. PLAN path: `<path>`."

**Early-exit path:** None. Phase 8 is terminal. If the human wants to abandon at this point, they set `ideate_phase: exited_early` directly (or invoke the exited_early transition explicitly).

**State:**
- `ideate_phase: complete`
- `pipeline_phase: drafted`
- Commit written.

**plan-pipeline handoff:** After Phase 8 completes, the next invocation of `plan-pipeline` reads `pipeline_phase: drafted` and begins the audit loop (sufficiency-auditor, then plan-safety-auditor). The `ideate_phase: complete` field is informational for the orchestrator, because the field confirms that the full cadence produced the PLAN rather than the ad-hoc `write-plan` path.

---

## Operating Notes

**Token budget at phase boundaries.** At each phase boundary (4->5, 5->6, 6->7, 7->8), the orchestrator estimates context budget consumed using `lib/state.py:estimate_token_budget_percent()`. If > 70% of the model's context window is consumed, the orchestrator surfaces a one-line warning: "Token budget at ~{N}%. Consider `/checkpoint` before continuing." The human always decides whether to proceed, and the orchestrator never halts on token budget alone.

**Core requirement.** Phases 4-8 require the plan_foundry bundle (Workbench/, write-plan, plan-pipeline). Without the bundle, ideate behaves exactly as the phases 1-3 arc and terminates at Phase 3 with plain markdown or an input file. Detection happens at the Converge->Gate A->Spec-Draft boundary.

**Resumption.** "resume ideate <plan-id>" reads `ideate_phase` from the PLAN frontmatter, loads the most recent critique JSON (if any), and loads the most recent checkpoint file from `Workbench/.ideate-checkpoint/` (if any) to restore conversation context. The arc resumes from the recorded `ideate_phase`. Exception: when `ideate_phase` is `risk_assess_idea_blocked` or `risk_assess_spec_blocked`, the arc does not resume into the blocked phase. Instead the skill calls `advance_phase()` on the appropriate back-edge (`risk_assess_idea_blocked -> risk_assess_idea` or `risk_assess_spec_blocked -> risk_assess_spec`) and re-runs the corresponding gate. See the blocked-phase resume contracts in section Gate A and section Gate B above.

**`/checkpoint` command.** The command is available during all phases and writes `Workbench/.ideate-checkpoint/<thread-id>.md` with the current conversation summary, phase, open questions, and decisions captured so far. The checkpoint file is committed to git, so a later session can resume from that file.

**Backward compatibility.** The trigger phrases for phases 1-3 ("let's ideate", "ideate X", etc.) continue to work and enter Phase 1 as before. Phases 4-8 are additive and activate when the human signals "spec this out" at Phase 3. PLANs created via the ad-hoc `write-plan` path bypass the ideate cadence entirely, so their `ideate_phase` remains empty.
