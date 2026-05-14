# Ideate — Eight-Phase Cadence Workflow

Detailed per-phase workflow for the enhanced ideate skill. This document extends `ideate-arc.md` (phases 1–3) with five new phases (4–8). Phases 1–3 are cross-referenced to `ideate-arc.md` — do not duplicate or contradict that document.

For the phase-transition routing table, see `references/phase-transitions.md`. For the critique JSON schema, see `references/critique-schema.md`. For critique codes, see `references/critique-codes.md`.

---

## Phase 1 — Clarify

**Cross-reference:** `workflows/ideate-arc.md` § Phase 1 — Clarify. All procedure defined there. This section is a summary only.

**Purpose:** Establish the requirement before any mechanism is discussed. Reframe malformed questions. Surface implicit constraints.

**Input contract:** Trigger phrase from human (any of the documented ideate triggers, including new phase-explicit ones if the human skips straight to a phase).

**Output contract:** Restated problem statement; human has acknowledged it ("yes, that's right" or equivalent refinement).

**Boundary check:** Human explicitly acknowledges the stated requirement. No auto-exit.

**Human surface:** Open question(s) + "Is this the right framing? Confirm or correct me."

**Early-exit path:** Human signals abandon. Optionally produce RESEARCH/ADVICE file if the clarification revealed a decision worth persisting. Ideate ends.

**State:** Conversational. `ideate_phase` is absent/empty throughout. Optional `/checkpoint` command writes `Workbench/.ideate-checkpoint/<thread-id>.md` for forensic record if the human wants durability.

---

## Phase 2 — Survey

**Cross-reference:** `workflows/ideate-arc.md` § Phase 2 — Survey. All procedure defined there.

**Purpose:** Generate the solution space — at least 2 options — with honest tradeoffs. State which you lean toward and explain why.

**Input contract:** Confirmed problem statement from Phase 1.

**Output contract:** Numbered options (3–5 typical) with per-option tradeoffs and a stated lean; human selects or proposes a refinement.

**Boundary check:** Human has explicitly selected an option (or explicitly combined options, or proposed a new option that re-enters survey).

**Human surface:** Numbered options + lean + invite for input.

**Early-exit path:** Produce RESEARCH file (need more data) or ADVICE file (strategic decision worth persisting). Ideate may pause here pending the input.

**State:** Conversational. `ideate_phase` remains empty. `/checkpoint` available.

---

## Phase 3 — Converge

**Cross-reference:** `workflows/ideate-arc.md` § Phase 3 — Converge. All procedure defined there.

**Purpose:** Sharpen the chosen approach to plan-ready specificity. Lock decisions. Classify them per decision 15.

**Input contract:** Human's chosen option from Phase 2.

**Output contract:** Decision classification (Already-locked / Mechanically-forced / Real-judgement-calls); concrete steps and acceptance criteria walked verbally; human signals readiness to proceed to spec.

**Boundary check:** Human signals readiness ("spec this out", "write the PLAN", "ready to plan it", or equivalent).

**Human surface:** Decision-triage table + "Shall we proceed to spec this out, or stop here as ADVICE only?"

**Early-exit path:** Produce ADVICE file (decisions recorded, no PLAN yet). Ideate ends at Phase 3.

**State:** Conversational. `ideate_phase` remains empty. The PLAN file MAY already exist (created at Phase 1 exit via plan-writer per ideate-arc.md) with `pipeline_phase: drafting` and partial content (Objective + Context). `/checkpoint` available.

**Transition to Phase 4:** When human confirms "spec this out" (or equivalent), dispatch plan-writer to ensure the PLAN file exists with Objective + Context populated, then proceed to Phase 4.

---

## Phase 4 — Spec-Draft

**State goes to disk here.** This is the first phase that sets `ideate_phase` to a non-empty value.

**Purpose:** Produce the first complete draft implementation spec — Steps and Verification sections — extending the existing PLAN file. This phase does NOT create the PLAN file; it extends a PLAN that already exists (created at Phase 1/3 exit per ideate-arc.md).

**Input contract:**
- Locked decisions from Phase 3.
- Existing PLAN file at `Workbench/<timestamp>_PLAN_<slug>.md` with `pipeline_phase: drafting` (created by plan-writer during Phase 1–3).
- The PLAN file has Objective + Context + Design Decisions Classification already populated.

**Output contract:**
- PLAN file extended with populated Steps section and Verification section (with at least one `acceptance:` item).
- PLAN frontmatter updated: `ideate_phase: spec_draft`.
- Commit written (parent session commits; executor defers to parent per harness contract).

**Boundary check:** PLAN file exists and parses; Steps and Verification sections are present and non-empty; `ideate_phase: spec_draft` is set in frontmatter.

**Human surface:** "PLAN draft written at `<path>`. Ready to run self-critique. Reply 'continue' to proceed or 'stop here' to exit early."

**Early-exit path:** Human replies "stop here" or equivalent. Set `ideate_phase: exited_early`. PLAN file is preserved but `pipeline_phase` remains `drafting`; plan-pipeline will not pick it up. Ideate ends.

**State:**
- `ideate_phase: spec_draft` (written to PLAN frontmatter at phase entry)
- `pipeline_phase: drafting` (unchanged — ideate still in flight)
- No critique JSON yet.

**Core requirement:** Phase 4 requires `plan-foundry-core` (plan-writer skill). Without core, the cadence ends at Phase 3. Detection: at the Converge→Spec-Draft boundary, if `Skill("write-plan")` does not resolve, present the finalised decisions as plain markdown and notify the human that phases 4–8 are unavailable.

---

## Phase 5 — Self-Critique

**Purpose:** Structured self-critique gate. Produces a critique JSON against the Phase 4 spec. Presents findings to the human using the severity-surface pattern (via `lib/render_critique.py`).

**Input contract:**
- PLAN file with `ideate_phase: spec_draft` and fully populated Steps + Verification sections.
- `ideate_iteration_count.self_critique < 5`.

**Output contract:**
- Critique JSON at `Workbench/.ideate-critique/<plan-id>-<iter>.json` (committed). See `references/critique-schema.md` for schema.
- `ideate_phase: self_critique` set in PLAN frontmatter.
- `ideate_iteration_count.self_critique` incremented.
- Severity-surface prompt rendered and shown to human.

**Boundary check:** Critique JSON written and parseable; `ideate_phase: self_critique`; `ideate_iteration_count.self_critique` ≥ 1.

**Human surface:** Rendered by `lib/render_critique.py:render_critique_surface()`. Shows findings grouped by severity (major / minor). Action menu:
- `address C1` — will fix this finding in Spec-Refine
- `defer C2` — acknowledge but don't fix this iteration (carry forward)
- `dispute C3: <reason>` — critique finding is wrong; provide rationale
- `discard C4` — cancel this finding (no fix, no carry-forward)
- `discard_all` — discard all findings; short-circuit to Phase 8 (Consolidate)
- `details C1` — show full issue + suggested_fix text
- `?` — show this help

**Early-exit paths:**
- `discard_all` → advance directly to Phase 8 (Consolidate). Set `ideate_phase: consolidate`.
- `exited_early` → human signals abandon; PLAN preserved with current `ideate_phase`.

**Iteration bound:** If `ideate_iteration_count.self_critique == 5` at this phase entry, halt-and-surface. Do not dispatch a new critique. Human must take an explicit action (ship / exit / override) to break the halt.

**Zero-findings short-circuit:** If critique JSON has `findings: []`, advance directly to Phase 8 (Consolidate). Write the empty JSON to disk for forensic record. Notify human: "No critique findings. Advancing to Consolidate."

**State:**
- `ideate_phase: self_critique`
- `ideate_iteration_count.self_critique += 1`
- Critique JSON written to `Workbench/.ideate-critique/<plan-id>-<iter>.json`

---

## Phase 6 — Spec-Refine

**Purpose:** Produce the revised spec (v2, v3, …) addressing the `address`-tagged findings from Phase 5. Updating the PLAN in-place; recording addressed fingerprints.

**Input contract:**
- PLAN file with `ideate_phase: self_critique`.
- Most recent critique JSON from `Workbench/.ideate-critique/`.
- Human's action decisions parsed by `lib/render_critique.py:parse_critique_reply()` — specifically the list of `address`-tagged finding fingerprints.

**Output contract:**
- PLAN file updated (Steps / Verification sections revised to address the `address`-tagged findings).
- `ideate_phase: spec_refine` set in PLAN frontmatter.
- `ideate_critique_addressed` list in PLAN frontmatter extended with fingerprints of addressed findings (appended, not replaced — cumulative across iterations).
- `ideate_iteration_count.spec_refine` incremented.

**Boundary check:** PLAN file updated; `ideate_phase: spec_refine`; addressed fingerprints recorded in `ideate_critique_addressed`.

**Human surface:** "v{N} PLAN written. {K} findings addressed, {L} deferred, {M} disputed, {N} discarded. Ready for Cross-Spec Reconcile. Reply 'continue' or 'ship it' to skip reconcile."

**Early-exit path:** "ship it" → advance directly to Phase 8 (Consolidate). Set `ideate_phase: consolidate`. Skip Phases 7.

**Back-loop path:** Human may request additional critique before reconcile. Reply "critique again" → advance to Phase 5 (additional iteration). Check iteration bound first.

**State:**
- `ideate_phase: spec_refine`
- `ideate_iteration_count.spec_refine += 1`
- `ideate_critique_addressed` list appended

---

## Phase 7 — Cross-Spec-Reconcile

**Purpose:** Check for dependencies and conflicts with other in-flight PLANs. Single-shot phase: always concludes by writing `ideate_reconcile_outcome` (no loop, no unbounded retry).

**Input contract:**
- Refined PLAN file with `ideate_phase: spec_refine`.
- Scan of `Workbench/*.md` frontmatter for in-flight PLANs.

**Auto-skip detection:**
The orchestrator scans `Workbench/*.md` for PLANs (other than the current PLAN) where:
```
pipeline_phase ∈ {drafting, drafted, checked, executing, outcome-verifying}
AND (ideate_phase ∉ {complete, exited_early} OR ideate_phase field absent)
```
Uses `lib/state.py:detect_in_flight_plans()`.

If zero such PLANs are found: auto-skip. Set `ideate_reconcile_outcome: passed`. Notify human: "No other in-flight PLANs. Cross-spec reconcile auto-skipped. Advancing to Consolidate."

**Output contract:**
- `ideate_phase: cross_spec_reconcile` set at phase entry.
- `ideate_reconcile_outcome` written (always, even on auto-skip):
  - `passed` — no conflicts or auto-skipped
  - `conflicts-resolved` — conflicts found and resolved
  - `conflicts-pending` — conflicts found; human accepted them as intentional

**Boundary check:** `ideate_phase: cross_spec_reconcile`; `ideate_reconcile_outcome` is non-empty.

**Human surface (when conflicts found):** Numbered list of conflicts + proposed resolutions. Human replies:
- `accept proposal` — accept the orchestrator's suggested resolution
- `modify: <alternative>` — accept with modification
- `dispute: <reason>` — conflicts are intentional; proceed with `conflicts-pending`

**Early-exit path:** None. Phase 7 always concludes by writing `ideate_reconcile_outcome`. If the human marks `conflicts-pending`, the PLAN still advances to Phase 8 (human has accepted responsibility for the pending conflicts).

**Back-loop path:** If a conflict requires editing the PLAN, human may request return to Phase 6 (spec-refine). Transition: `cross_spec_reconcile → spec_refine`. Increment `ideate_iteration_count.spec_refine`.

**State:**
- `ideate_phase: cross_spec_reconcile` (at phase entry)
- `ideate_reconcile_outcome: passed | conflicts-resolved | conflicts-pending` (written before phase exit)

---

## Phase 8 — Consolidate

**Purpose:** Finalise the spec. Produce the terminal state that hands off to plan-pipeline. This is the only phase that flips `pipeline_phase`.

**Input contract:**
- Refined (and reconciled) PLAN file with `ideate_phase` ∈ {`spec_refine`, `cross_spec_reconcile`} — or entering directly via discard_all shortcut.
- `ideate_reconcile_outcome` is non-empty (unless entered via discard_all shortcut, in which case it remains empty — acceptable).

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
- Commit exists (parent session commits; executor defers).

**Human surface:** "PLAN finalised. `pipeline_phase` flipped to `drafted`. Ideate complete. Plan-pipeline audit loop will start on next pipeline invocation. PLAN path: `<path>`."

**Early-exit path:** None. Phase 8 is terminal. If the human wants to abandon at this point, they set `ideate_phase: exited_early` directly (or invoke the exited_early transition explicitly).

**State:**
- `ideate_phase: complete`
- `pipeline_phase: drafted`
- Commit written.

**plan-pipeline handoff:** After Phase 8 completes, the next invocation of `plan-pipeline` sees `pipeline_phase: drafted` and begins the audit loop (sufficiency-auditor, then plan-safety-auditor). The `ideate_phase: complete` field is informational for the orchestrator — it confirms the PLAN was produced via the full cadence, not ad-hoc.

---

## Operating Notes

**Token budget at phase boundaries.** At each phase boundary (4→5, 5→6, 6→7, 7→8), the orchestrator estimates context budget consumed using `lib/state.py:estimate_token_budget_percent()`. If > 70% of the model's context window is consumed, a one-line warning is surfaced: "Token budget at ~{N}%. Consider `/checkpoint` before continuing." The human always decides whether to proceed; the orchestrator never halts on token budget alone.

**Core requirement.** Phases 4–8 require `plan-foundry-core` plugin. Without it, ideate behaves exactly as the three-phase arc (phases 1–3 only), terminating at Phase 3 with plain markdown or an ADVICE file. Detection at the Converge→Spec-Draft boundary.

**Resumption.** "resume ideate <plan-id>" reads `ideate_phase` from the PLAN frontmatter, loads the most recent critique JSON (if any), and loads the most recent checkpoint file from `Workbench/.ideate-checkpoint/` (if any) to restore conversation context. The arc resumes from the recorded `ideate_phase`.

**`/checkpoint` command.** Available during all phases. Writes `Workbench/.ideate-checkpoint/<thread-id>.md` with the current conversation summary, phase, open questions, and decisions captured so far. Committed to git. Useful for resumption across sessions.

**Backward compatibility.** The existing three-phase arc trigger phrases ("let's ideate", "ideate X", etc.) continue to work. They enter Phase 1 as before. The new cadence is additive: it activates when the human signals "spec this out" at Phase 3. PLANs created via the ad-hoc `write-plan` path bypass the ideate cadence entirely — their `ideate_phase` remains empty.
