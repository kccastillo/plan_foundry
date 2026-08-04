# Plan File Conventions

This file is the canonical source for Workbench/ file conventions. AGENT_RULES.md and CLAUDE.md should point here rather than duplicate.

## File Naming

`{YYYYMMDDHHMI}_{TYPE}_{slug}.md` - see `references/naming-convention.md` for full pattern, type tokens, and examples.

## PLAN Identity Policy (2026-05-16, per PLAN-AA0 plan-of-plans)

**D1 Active-Unique-LOG-History.** PLAN IDs are unique within the *currently active set only*. The LOG carries history. Slug is the durable cross-generation discriminator across ID re-uses.

**D2 AA0-ZZ9 active scheme.** New PLAN IDs are allocated in `PLAN-[A-Z][A-Z][0-9]` (6,760 lexicographic slots: AA0 -> AA9 -> AB0 -> ... -> ZZ9). Strict-sequential issuance per the AA1 allocator. Burned IDs leave permanent gaps; reissue is forbidden. At ZZ9 the scheme will need extension - that is the next generation's problem (>6,760 PLANs at the foundry's rate is decades away).

**D2a Burn-By-Tombstone.** An ID can be retired without ever owning a PLAN file - the work it named was reverted, or the ID was drawn and abandoned. Record the burn as a file, never as prose: `Retired/PLAN-<ID>_BURNED_<slug>.md`, carrying the reason and pointing at wherever the decision was made. The allocator derives its used set from filenames, so the tombstone is what enforces D2; a burn recorded only in prose is invisible to it and the ID gets handed out again. That happened on 2026-07-31, when `AI6` was offered after being burned the previous day, and was caught only because the operator recognised the number. `next_id.py --explain` labels a tombstoned ID `Burned` rather than `Retired`, so the table says why the ID is skipped.

**D3 Numeric-Historical-Frozen.** Old `PLAN-NNN` IDs in `Retired/` are historical-only and frozen. They are not migrated. Reference them exactly as historically recorded. When a `PLAN-NNN` collides with an AA-form ID's predecessor (e.g. PLAN-031 renamed to PLAN-AA9), reference the active PLAN by its AA-form ID and disambiguate by appending "(formerly PLAN-NNN)" in narrative prose.

**Inputs carry no allocated ID.** A new input is `INPUT-YYYYMMDD-hhmm-<slug>.md`, so there is nothing to allocate and nothing to collide. The grandfathered `ADVICE-NNN` and `RESEARCH-NNN` spaces stay numeric and stay readable; `next_id.py` keeps both tokens for that space alone (PLAN-AJ3 D5).

**Allocator.** `.claude/skills/write-plan/scripts/next_id.py` is the canonical allocator. Source of truth: the filesystem, and only the filesystem - Workbench/ + Retired/ (recursive) are authoritative for "used IDs". No cache. Read-only contract - not idempotent across calls. See PLAN-AA1's design lineage (research-validated leans across event-sourcing canonical pattern, Postgres `nextval` template, Jira/Linear/GitHub ID conventions).

**Anti-pattern (per AA4 TESTREPORT-002 finding).** "PLAN shipped inline in a PR but never walked through plan-pipeline" leaves the PLAN's `status: ready` while the deliverables are in tree. Future `audit-foundry.py` extensions may flag this by cross-checking `status: ready` PLANs' `files_touched` against recent commit changesets. The cure is to walk plan-pipeline against the PLAN retroactively (mark status: done, populate Executor Notes), then retire.

## Recurring PLAN Prefix

Slugs start with `RECUR-`. One persistent file per recurring task; each cycle appends to `## History`.

## File Types

`PLAN` | `INPUT`. `RESEARCH` and `ADVICE` are grandfathered read-only tokens.

## PLAN Status Lifecycle

Frontmatter `status` field:
```
ready -> in-progress -> done | partially-complete | blocked | needs-revision
```

- `ready` - transcribed, not yet started. Set on creation.
- `in-progress` - execute-plan skill has started. Set when execution begins.
- `done` - all verification criteria pass. Terminal.
- `partially-complete` - some steps done, others blocked or deferred. Terminal for this cycle.
- `blocked` - cannot proceed; `blocked_by` holds the reason. Cleared automatically by `write-input` when the resolving input lands, or manually by the Human. Non-terminal until unblocked.
- `needs-revision` - plan itself is faulty; return to Sonnet. Non-terminal.

PLAN frontmatter is the sole canonical surface for PLAN status.

## PLAN Pipeline Phase

Frontmatter `pipeline_phase` field, orthogonal to `status`. Tracks orchestration state for PLANs managed by the `plan-pipeline` skill.

```
drafting -> drafted -> checked -> executing -> complete
```

- `drafting` - ideation underway; PLAN being written/updated incrementally.
- `drafted` - ideation closed; PLAN written; awaiting sufficiency + plan-safety review.
- `checked` - review passed; ready to execute. Aligns with `status: ready`.
- `executing` - `plan-executor` subagent has been dispatched.
- `complete` - execution done; ready for retirement.

**Default for ad-hoc PLANs** (created directly via `write-plan` outside the pipeline): field absent or empty. When `plan-pipeline` is invoked against such a PLAN, it treats absent/empty as `drafted` (assume the PLAN is already written and ready for review), not `drafting` - to avoid re-ideating an already-authored plan.

## PLAN Input Linkage

Frontmatter `linked_inputs: []` contains one array of input filenames, live and grandfathered alike. No separate `linked_research` / `linked_advice` / `requires_opus` / `requires_research` fields - `status: blocked` + `blocked_by` carries the "needs input before running" signal.

## Roadmap Linkage

PLANs may reference items in `.claude/ROADMAP.md` via three optional frontmatter fields:

- `closes_thread: T{ID}` - this PLAN's successful execution fully closes the named thread. On PLAN closure (outcome=done), `execute-plan` Step 4.5 appends a closure bullet to the thread body and sets the thread's `Status` to `closed`. The thread stays in its pillar for historical context; grep for `Status:.*closed` to inventory closed work.
- `advances_thread: T{ID}` - this PLAN partially progresses the thread. On closure, `execute-plan` appends a progress note to the thread body but leaves the thread in its pillar.
- `parent_plan_of_plans: <path>` - this PLAN is part of a coordinated effort tracked by another file. On closure, `execute-plan` updates the parent plan-of-plans tracking section per that file's schema.

Set these on PLAN creation (in `write-plan`). Empty string means no linkage. A PLAN closes or advances at most one thread; for multi-thread work, decompose into multiple PLANs or introduce a plan-of-plans.

## Push Policy

**Optional frontmatter field: `push_policy: auto | manual`**

Controls whether the plan-pipeline orchestrator pushes to remote after each milestone commit, or commits locally and surfaces a `<push_status>` message for the operator to push manually.

```yaml
push_policy: manual   # or "auto"
```

**Resolution order (first match wins; simplified by PLAN-AC4 D6):**
1. PLAN frontmatter `push_policy` field - per-PLAN override.
2. Hard-coded default: `manual`.

**Values:**
- `auto` - push after every milestone commit (original behaviour).
- `manual` - commit only; emit `<push_status>commit landed locally; push manual per push_policy. Run \`git push\` when ready.</push_status>` to the operator.

**Project default:** `manual`. Set `push_policy: auto` per-PLAN for individual plans that need immediate remote propagation.

**Implementation:** `.claude/skills/_shared/push_policy.py` - function `get_push_policy(plan_path, repo_root=None) -> str`.

## Orchestrator-managed frontmatter fields

The following frontmatter fields are managed exclusively by the plan-pipeline orchestrator. Executors and subagents MUST NOT write them directly (per T14, 2026-05-13):

- `pipeline_phase` - current phase in the execution lifecycle.
- `audit_state` - durable audit loop state; includes `sufficiency_iterations`, `plan_safety_iterations`, `last_stage`, `last_outcome`, `last_audit_commit`, `preferred_model_override`.
- `last_executor_outcome` - written by the executor on completion; read-only for the orchestrator.
- `verification_state` - outcome-verifying phase state.
- `total_loop_attempts` - cross-session IAL guard (PLAN-AH1 D1/FM2). Integer, default 0. Incremented by the Routine on every non-deferred firing. Ceiling: 10. NOT zeroed on `drafted`-revert - its purpose spans resets to maintain the guard across auto-fix cycles. Managed by the autonomous-loop Routine; the orchestrator reads it but does not reset it on audit-state resets.
- `step_remaps` - a list of `{iteration, map}` entries recording every ordinal remap applied to this PLAN's `## Steps` (PLAN-AJ1). Appended by the orchestrator when the patch-application procedure (dispatch.md section 4B) renumbers a patched block; never hand-edited, and never reset.

## Substrate Files Declaration

**Optional frontmatter field: `substrate_files: []`**

An opt-in declaration of file paths that plan-writer MUST `Read` as ground truth before authoring any Steps that emit SQL DDL/queries, ORM operations, Python imports from existing modules, or string-literal values of constrained-type (enum) fields.

```yaml
substrate_files:
  - path/to/schema.py
  - path/to/enums.py
```

**Purpose:** prevents hallucinated column names, enum values, and private API attributes - the H5/H9/H11 hiccup class (2026-05-16 retrospective). When `substrate_files` is non-empty, plan-writer reads each listed path before any Write/Edit that touches a substrate-grammar construct; the read must appear in the writer's reasoning trace. audit-haiku-safe lints substrate fidelity post-hoc (grep-based) and emits `error`-severity findings for any named entity in Steps that has zero matches across the declared substrate files.

**When to set:** any PLAN whose Steps reference SQL table/column names, Python symbols imported from existing modules, enum string-literal values, or third-party API attributes. Leave empty (`substrate_files: []`) for PLANs with no such references - the lint heuristic-detects them and emits a `warn`-severity advisory if it finds substrate-grammar constructs despite the empty declaration.

**Fidelity lint scope (four failure classes from H5/H9/H11):**
1. SQL column refs (`table.column` pattern)
2. Python imports (`from X import Y`)
3. Enum string-literal values (string literal adjacent to a `*.kind`, `*.status`, or `Enum` class reference)
4. Public-API surface attributes (`_`-prefixed attribute on a third-party module signals private access)

See `.claude/skills/audit-haiku-safe/workflows/audit-haiku-safe-steps.md` (Step 4a: Substrate fidelity check) and `.claude/skills/write-plan/workflows/write-plan.md` (Step 0: Substrate-verification preflight) for the enforcement sites.

## Platform portability (per PLAN-AB3)

Every `verify:` and `acceptance:` item in a PLAN's Verification section MUST be portable across the foundry's CI baseline (Ubuntu Linux + Python 3.11 + pytest + pyyaml + git + gh + POSIX shell with bash-isms allowed) unless explicitly annotated.

**Default expectation:** write portable commands (Python one-liners, `python -m pytest`, `git`, `gh`). A command that only works on Linux or only on Windows is a platform-portability violation unless annotated.

**Annotation syntax:** add a trailing comment on the same line when portability is genuinely impossible:
- `verify: <cmd> # platform: posix` - POSIX-specific; skipped by portability lint.
- `verify: <cmd> # platform: windows` - Windows-specific; skipped by portability lint.

**Forbidden patterns (when unannotated):** `/tmp/`, `/dev/null`, `bash -c`, `test -[a-zA-Z]`, `> /dev/`, `2>/dev/null`, `&&` in compound commands. See `.claude/skills/_shared/plan-safe.md` "Platform portability" section for the full list with rationale and portable alternatives.

**Audit enforcement:** `audit-haiku-safe` Step 4b runs the platform-portability lint (`lib/platform_portability.py`) and emits `warn`-severity findings for unannotated forbidden patterns. These are non-blockers by default (CI baseline is POSIX) but surface as advisory items for Windows consumers.

## Preliminary holding-PLAN pattern

A **preliminary holding-PLAN** (also called a holding-PLAN) is a PLAN file created before ideation has begun - used to park inputs and frame the open questions that ideation will eventually answer.

**Frontmatter signature:**
- `pipeline_phase: drafting` - ideation not yet started; plan-pipeline will not auto-advance past drafting until explicitly invoked.
- `ideate_phase: not-started` - distinguishes a holding-PLAN from a PLAN whose ideation is in-flight.
- `linked_inputs: [...]` - pre-populated with the input files that motivated the holding-PLAN. These are the primary inputs ideation will consume.

**Body structure (minimal):**
- **Objective** - one paragraph stating what decision or work the holding-PLAN is meant to produce.
- **Context** *(optional)* - background for the reader; include when the motivation is not self-evident from the linked inputs.
- **Key Questions** - the open questions that Phase 1 (Clarify) will treat as its agenda when plan-pipeline runs against this PLAN.
- **Re-prosecution Checklist** *(optional)* - a checklist of prior art, anti-patterns, or commitments the spec-author must check before locking any answer.

**Lifecycle:** When `plan-pipeline` is invoked against a holding-PLAN, it detects `pipeline_phase: drafting` and `ideate_phase: not-started` and enters Phase 1 (Clarify) of the ideate cadence, using the Key Questions section as the Clarify agenda. No dedicated entry point or separate skill is needed - existing `write-plan` and plan-pipeline handle holding-PLANs implicitly.

**Use case:** surfaces a durable, version-controlled destination for inputs that are not yet ready to walk the full ideate cadence. Allows a batch of inputs to be triaged into action-ready holding-PLANs before committing to spec work on any one of them.


**Note on schema enforcement:** holding-PLANs vary in shape. The pattern is documented here but audit-haiku-safe does not reject deviations - the pattern is a convention, not a schema rule.

## Spec-Draft rigour (per PLAN-AB2)

Three heuristics that plan-writer applies during Spec-Draft before declaring the spec complete. All three are also checked by audit-sufficiency (Lens 8 - Rigour heuristics applied, warn-severity).

### H2 - Capacity ceiling check

If any discrete deliverable count (MCP tools, schema tables, context-window slices) exceeds **0.8x** a threshold in `.claude/skills/_shared/capacity-thresholds.md`, the PLAN's Context section MUST acknowledge the brushing and note that a research bot was dispatched to confirm the threshold's current relevance.

**Origin:** Plan B initially specced 49 tools against a ~50-tool MCP degradation threshold; the brushing was caught only by a self-critique research bot, not pre-empted by the spec itself (2026-05-16 hiccup log section H2).

### H4 - Calling-convention checklist (conditional)

**Trigger:** Steps body contains test-runner keywords (`pytest`, `unittest`, `async def`, `asyncio`), API client patterns, or platform-specific behaviour keywords.

When triggered, the PLAN's Context section MUST enumerate: test-runner async/sync posture, fixture patterns (e.g. `tmp_path` vs `tmpdir`), and any relevant platform conventions - before the Step body is authored. Cheap when not triggered; skip the enumeration entirely if no trigger keywords are present.

**Origin:** Plan B's spec stated "tests are sync" without documenting the async/sync boundary; the executor had to make a judgement call that the spec should have pre-empted (2026-05-16 hiccup log section H4).

### H8 - Literal-heading discipline

When a Step body specifies that a deliverable must include a named section, the prose MUST use literal heading syntax, not ambiguous prose.

- **Correct:** "The output MUST include a `## Notes` heading."
- **Incorrect:** "The output should have a Notes sub-section." (executor interprets as "content appears somewhere").

**Origin:** Plan A's executor produced an ADVICE doc with L-tier notes integrated inline rather than under a dedicated `## Notes` heading, because the spec said "should have a Notes sub-section" rather than specifying the heading literally (2026-05-16 hiccup log section H8).

## Ideate Cadence Requirements (per PLAN-AA9, 2026-05-17)

Four retrospective findings (F1, F2, F7, F8) from the 2026-05-16 plan-foundry retrospective are now formally embedded in the ideate cadence. These are enforced in the workflow files; this section is a pointer for cross-referencing.

- **F1 - Research-anchor:** Survey Phase 2.B auto-dispatches one research bot per Real-judgement-call cluster when >=2 such clusters exist. Each bot uses the sub-questions in `.claude/skills/_shared/research-prompt-template.md`.
- **F2 - Expand-explode:** Survey Phase 2.A brainstorms >=3 options per cluster plus an explicit "obvious anti-option" before any option is presented to the Human.
- **F7 - Decision-tier triage everywhere:** Survey, Self-Critique, and Cross-Spec-Reconcile all include a `decision-tier` column (`locked` / `forced` / `judgement`) in their findings tables. `forced` items are resolved by the orchestrator autonomously; `judgement` items are surfaced to the Human.
- **F8 - Inverted-pyramid output:** All three of those surfaces lead with a 1-2 sentence headline summary, then a tradeoff table with the triage column, then prose only for `judgement`-tier or novel items.

**Source of truth:** `.claude/skills/ideate/workflows/cadence-phases.md` section Phase 2 (Survey), section Phase 5 (Self-Critique), section Phase 7 (Cross-Spec-Reconcile).
**Structural tests:** `.claude/skills/ideate/lib/test_cadence_structure.py` (run via `python -m pytest`).
**Scope:** ideate phases 2, 5, 7 only. `audit-sufficiency` is unchanged (it already implements decision-15 triage from PLAN-035 and was explicitly out-of-scope per Q8 γ).

## PLAN sizing

A single PLAN MUST NOT exceed **12 top-level Steps** (D1 - Step-count ceiling, PLAN-AC7).

**Rationale (ADVICE-004 gap G1):** The agentic-failure literature's strongest, best-supported
result is that per-step errors compound and context degradation accumulates as run length grows.
plan_foundry's natural mitigation - decompose work into smaller PLANs - was previously only an
unwritten judgement. This ceiling makes it explicit.

**What counts:** A top-level Step is any line matching `^\d+\.\s+` (one or more digits, period,
whitespace, content) between the `## Steps` heading and the next `## ` heading. Sub-items
(lines starting with leading whitespace before the digit, or letter-prefixed items like `a.`)
do not count.

**When exceeded:** A PLAN with more than 12 top-level Steps must be decomposed into either:
- A **plan-of-plans** (a coordinating PLAN that `triggers_plans:` its children), or
- **Sequential PLANs** (each scoped to a coherent phase of the larger work).

**Exception path:** If a PLAN genuinely cannot be decomposed (all steps are tightly atomic and
forming a plan-of-plans would add overhead without benefit), the author may record an
acknowledgement in frontmatter:

```yaml
audit_acknowledgements:
  - PSZ001
```

This suppresses the `PSZ001` advisory from `audit-haiku-safe` without changing the ceiling's
intent. The acknowledgement must be recorded with a rationale in the PLAN's Context section.

## Plan-of-plans authoring: sketch-first convention

When authoring a plan-of-plans (a PLAN that coordinates multiple child PLANs across linked threads, files, or subsystems):

1. **When to use a plan-of-plans.** A plan-of-plans is appropriate when work spans multiple independent threads or coordinated effort across files/subsystems - for example, harness extraction or a multi-phase infrastructure refactor. If work fits naturally into a single PLAN with sequential steps, use that instead.

2. **The placeholder convention.** You do not need to author all child PLANs before drafting the parent. Instead, declare child PLANs in the parent's `triggers_plans: []` field using placeholder syntax: `"[placeholder] <slug>"`, where `<slug>` is a short descriptive name for the child work. For example: `triggers_plans: ["[placeholder] harness-extraction", "[placeholder] update-harness-templates"]`. This lets you sketch the coordinated effort's shape while child details are still being shaped.

3. **Transition to real IDs.** As each child PLAN is drafted, replace the corresponding placeholder entry with the actual PLAN filename (e.g. `"PLAN-AB0_harness-extraction.md"`). This replacement should happen in the same commit that drafts the child, keeping the parent's tracking in sync.

4. **Parent update discipline.** When a child PLAN is drafted, update both the parent's `triggers_plans` array and any child-tracking table in the parent's Objective or Context section (if used). Do both edits in a single commit to maintain clarity.
