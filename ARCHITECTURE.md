# plan_foundry Architecture

This document is the maintainer-facing reference for plan_foundry. It covers the design philosophy, the strategic principles, the enforcement mechanisms, the invariants register, the doc landscape, and the bootstrap mechanism.

**Audience.** The reader is a maintainer or new contributor working on the harness itself, not an end user installing it. End-user documentation, including install commands and skill descriptions, lives in `README.md`. Agent-facing operating rules live in `CLAUDE.md`, which is always loaded. The load-bearing meta-policy was consolidated into `CLAUDE.md` when `AGENT_RULES.md` was dissolved (Option Y, 2026-05-14).

## Design Philosophy

plan_foundry exists to solve structural problems common to ad-hoc agent workflows.

**Deterministic triggering.** The next action should be determined by state, not by reconstructing intent from conversation history. Skills declare explicit trigger phrases. A phase state machine on disk determines which agent runs next. The orchestrator reads PLAN frontmatter and routes by enum. Whether to run the audit is never a judgement call, because the PLAN state answers that question.

**No race conditions.** Parallel actors should not be able to advance the same piece of work independently. There is a single conversational re-entry point: the background executor's completion message. All other subagent dispatch is foreground and synchronous. Audit gates run sequentially rather than in parallel. PLAN state lives in frontmatter on disk, so re-entry is idempotent, and re-running with no new outcome is a no-op rather than a duplicate dispatch.

**Small agents with explicit boundaries.** Agents should receive only the context, capabilities, and model tier their task requires. Each skill pins its model tier: Opus for design judgement, Sonnet for work that needs judgement, and Haiku for mechanical tasks. Subagents declare their skill registry explicitly and do not inherit the parent's.

### Architectural Scaffold, Not a Harness Helper

plan_foundry is a **scaffold**. The distinction matters because it sits between two approaches for which it is often mistaken.

- **Context engineering and harness helpers.** Prompt packs, operating rules, and skill collections that improve behaviour by instructing an agent to behave well. The guidance may be sound, but compliance remains probabilistic. The model can follow the instruction or ignore it, and there is no structural backstop when it does not.
- **Harness engineering.** Building a new runtime with its own execution loop, tool layer, state management, and control flow. This provides strong guarantees, but at the cost of building and maintaining a complete harness.

plan_foundry is neither. It is a scaffold built on top of an existing harness. It adds deterministic state transitions, audit gates, capability boundaries, and independent verification while remaining entirely file and skill based. The goal is to obtain many of the benefits of harness engineering without building a runtime. State determines what runs next. Gates block unsafe work. Verification runs in a trusted context. These guarantees are implemented mechanically rather than through instructions to the model.

The distinction carries design weight. When choosing between a behavioural instruction and a mechanical constraint, prefer the mechanical constraint. A change that adds another "please behave this way" rule where a deterministic gate is possible moves the system toward the harness-helper model.

## Strategic Principles

Every design decision is evaluated against the five principles below. They are design constraints, not stylistic preferences. When a PLAN references `[P3]`, it refers to principle 3 below. The principles register is deliberately stable. Refine or replace principles when necessary, but do not add new ones lightly.

1. **Context rot minimisation.** Keep `CLAUDE.md` and the skill registry lean. Route findings through `raise-foundry-request` rather than accumulating logs. Prevent drift through regular maintenance rather than periodic clean-ups.
2. **Just-in-time skill loading.** Load skills when they are needed. Resist always-on additions to the skill registry. Every always-loaded line is paid for on every interaction.
3. **Tool and model-tier selection.** Match capability to the work. Opus for design judgement. Sonnet for work that needs judgement. Haiku for mechanical tasks. Decision-15 triage (`already_locked`, `mechanically_forced`, `real_judgement_call`) prevents escalation creep; canonical definitions live in `.claude/skills/audit-sufficiency/workflows/audit-sufficiency-steps.md` Step 4.
4. **Codification over accumulation.** Recurring lessons become rules, skills, workflows, or documentation. Do not accumulate operational knowledge as memory or historical records when it can be codified.
5. **Robust subagent orchestration.** Wire formats are typed. Failure modes are explicit. Capability boundaries are enforced at audit time and at runtime. Partial success must never be silent.

## How plan_foundry Works

This section explains the enforcement mechanisms behind the harness. It sits between the high-level overview in `README.md` and the maintainer-focused detail in the Invariants Register. Each mechanism entry states what the mechanism does, what enforces it, and what breaks if it is removed.

### (a) PLAN Lifecycle State Machine

Every piece of work is represented by a PLAN file in `Workbench/`. Each PLAN carries a `pipeline_phase` frontmatter field, an enum whose valid values are:

`drafting` -> `drafted` -> `checked` -> `executing` -> `outcome-verifying` -> `complete`

The `plan-pipeline` orchestrator reads `pipeline_phase` on every invocation and dispatches the appropriate sub-skill. The orchestrator does not infer the phase from conversation history or from the PLAN body.

**Enforcement.** The transition table is defined in `.claude/skills/plan-pipeline/references/phase-state-machine.md`. Each transition writes the new phase to frontmatter before dispatching the next sub-skill, so a crash or interruption leaves the PLAN in a known state.

**If removed.** Re-entry would depend on reconstructing state from conversation history, which is lossy, session-scoped, and model-dependent. The result would be silent state drift, where different runs infer different phases from the same PLAN. The state machine exists so that the current phase is recorded in the PLAN rather than remembered by the model.

### (b) Audit Gates

A PLAN cannot advance from `drafted` to `checked` until it passes both independent audits. Each audit runs in a separate model invocation with no prior conversational context. The auditor reads the PLAN file directly and returns structured findings.

- **`audit-sufficiency`** (Opus) is the conceptual audit. It checks acceptance criteria, risk identification, and whether verification is realistic. Findings at `error` severity block advancement.
- **`audit-haiku-safe`** (Sonnet) is the mechanical audit. It checks substrate fidelity, destructive-action scope, and executor suitability. Its checks include:

  - substrate-fidelity checks (`SFV001` / `SFV002`), which require named entities in PLAN steps to exist in declared substrate files
  - capability-boundary checks (`EBV001` / `EBV002`), which prevent a PLAN from requesting capabilities the nominated executor does not have

Audit findings are blocking. If an audit returns `revision_needed`, `plan-pipeline` returns the PLAN to `pipeline_phase: drafted` and surfaces the findings. There is no advisory-only path.

**Enforcement.** `audit-sufficiency` and `audit-haiku-safe` write their outcomes to the PLAN's `audit_state` frontmatter block. Before advancing a PLAN, `plan-pipeline` reads `audit_state` and applies the phase-transition rules defined by the audit result. The enforcement logic lives in the audit skills and in `plan-pipeline`.

**If removed.** Quality assurance would collapse into self-review. The author and reviewer would be the same model operating from the same context, so findings that became normalised during authoring would no longer receive an independent review. The value of the audit system comes from independent evaluation, because a fresh invocation can recognise issues that the authoring context has stopped noticing.

**Productive audit failure.** The audit pipeline exists because each stage catches failures the others miss. A result of `revision_needed` after Self-Critique has passed is evidence that the process is working. The expected path is Spec -> Audit -> Refine -> Re-audit. Treat audit findings as inputs to the next revision, not as defects to hide and not as evidence of a poor author. A PLAN that passes every audit stage on its first iteration with no findings is the unusual case. Normalise productive audit failure. The purpose of the audit process is to find issues before execution, not to prove that none exist.

### (c) Verification in a Fresh Context

After execution, the `outcome-verifying` phase re-runs every `verify:` and `acceptance:` assertion. The assertions are re-run in the orchestrator's context, not the executor's context and not in the same turn that performed the work.

**Enforcement.** The executor agents (`plan-executor` and its variants) declare `Bash`, `WebFetch`, and `WebSearch` in `disallowedTools`, so an executor cannot run the assertions itself. The full declaration and its platform rationale are recorded under the Subagent Permission Inheritance invariant.

**If removed.** Verification would rest on the executor's own report of its outcome. The No Party Grades Its Own Constraint invariant records why the orchestrator re-runs verification rather than trusting executor-reported outcomes.

### (d) Bundle Propagation by Copy, Not Symlink

Installation copies the bundle into the target's `.claude/` rather than cloning it globally or symlinking it. The mechanism, its enforcement, and its consumer-boundary consequences are recorded once, in the Portable Bundle invariant below.

## Invariants Register

This register names the invariants the harness depends on. Each is a load-bearing promise that, if violated, would break correctness or surprise a maintainer. They are listed here so a tidy-up of any one enforcement site does not silently drop the underlying constraint.

**What qualifies as an invariant.** An invariant is a load-bearing fact about the harness or its environment that the code, skills, or agent files structurally depend on. Three tests:

1. **Codified somewhere structurally.** The invariant is enforced or relied on by a piece of code, an agent's `disallowedTools`, a skill's preconditions, or similar - not just a documented preference.
2. **Silent-break risk.** Removing or contradicting the invariant breaks correctness in a way that may not surface until later. If a violation is loudly caught at audit or runtime, it does not need to be an invariant - the enforcement site already documents it.
3. **Non-obvious to a future maintainer.** If a future contributor looking at the enforcement site would naturally re-derive the constraint, the invariant lives implicitly. The register exists for facts that a tidy-up could plausibly remove without realising the consequence.

Add to this register when a fact passes all three tests. Each entry names the invariant, states the constraint, cites evidence, lists the consequences, and explains why it is named here rather than left as commentary.

### Invariant: plan_foundry Doc-Set Integrity

The root document set is a key part of the repository design, and is organised by audience. When content could fit in more than one document, the audience determines the home, not author convenience.

The following documents must exist at the repository root:

| Doc                 | Audience                     | Owns                                                                                                                                        | Maintenance trigger                                                                                                          |
| ------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `CLAUDE.md`       | Always-loaded agent context  | Project overview, operating rules, working style, skill registry pointers, environment boundaries, CI references, and agent-facing caveats. | Changes to`.claude/skills/`, `.claude/commands/`, or `CLAUDE.md`.                                                      |
| `ARCHITECTURE.md` | Maintainers and contributors | Design philosophy, strategic principles, invariants, document boundaries, and bootstrap design.                                             | Changes to`.claude/skills/_shared/`, agent definitions, or any SKILL that introduces, removes, or depends on an invariant. |
| `README.md`       | Installers and end users     | Installation, update workflows, capability overview, and consumer-facing guidance.                                                          | Manual review.                                                                                                               |

Removing any of them breaks the information architecture of the project.

`CHANGELOG.md` also lives at the repository root and holds versioned migration and cleanup notes; it is not part of the CI-enforced presence set above.

This is a repository-level invariant, not a generic project rule. Consumer projects may have different root-document structures, so skills such as `maintain-project-docs` cannot enforce it universally. The invariant is recorded here so that future refactoring of individual documentation workflows does not silently remove the underlying requirement.

**Verified by:** `scripts/ci/check-invariants.py`, which asserts that all required root documents are present.

### Invariant: Single Canonical Home

Every fact the harness depends on has one canonical home. A fact is a rule, definition, enum, schema, or convention that the code, skills, agents, or documents rely on. Where the same fact appears in more than one place, the home holds the full statement and every other occurrence is either a pointer to the home or a managed inline copy. One test decides which: whether that occurrence's reader can open the home at runtime.

- A **pointer-eligible** site has a reader that reaches the home with a filesystem tool. The parent session reads any file it needs. A dispatched subagent reads the references and workflows its skill loads while it runs. Both can chase a pointer, so the duplicate is reduced to a one-line pointer naming the home, carrying no content of its own.
- A **dispatch-facing** site has a reader that receives the fact as pre-loaded text it cannot expand. Four kinds of site are dispatch-facing: an `.claude/agents/*.md` body, which the harness injects verbatim as a subagent's system prompt; the artefact-register block spliced into those bodies; a template copied into every PLAN; and `init-plan-foundry/operating-rules.md` together with the sentinel block it injects into a consumer's `CLAUDE.md`, where this repository's `_shared/` directory is not present. None of these readers can open the home, so the fact stays inline as managed duplication. Wording and spelling are aligned to the home to bound drift; the content stays.

Reducing a dispatch-facing site to a pointer is a defect. The dispatched agent or the consumer loses the fact with no error, because the pointer resolves to a file the reader cannot open.

**Why this is an invariant**

The break is silent. An agent body whose capability-boundary or rigour-heuristics text has been replaced by "see `_shared/...`" still parses, still loads, and still runs; the absence of the rule shows up only when the agent produces work the rule would have caught. A future contributor tidying what looks like duplication would naturally reduce an agent body to a pointer, the same edit they would safely make to a reference file, without knowing that the body is a system prompt with no filesystem behind it. The register records the distinction so that a tidy-up does not quietly turn managed duplication into a dangling pointer.

**Consequences**

- The home is chosen by separation of concerns. For the root documents the choice is recorded in the Doc-Set Integrity invariant; for the helper and reference corpus it is recorded in the corpus ownership index (`_shared/corpus-ownership.md`).
- A pointer-eligible duplicate carries a one-line pointer and no restated content.
- A dispatch-facing duplicate carries the full content; only its wording is aligned to the home.
- Code restates a fact only as behaviour. Checking logic, compiled patterns, emitted runtime strings, and typed schema declarations stay in place. A docstring or comment that restates a rule in prose is reduced to a one-line citation of the home.
- `dispatch-authorisation.md` is a separate case. The harness classifier blocks agent edits to it, so an agent never points content out of it; any change to that file is made by a human, whatever the reader.

**Verified by:** the structural half of this invariant - the bijection between corpus files and rows, the pointer and sync links, the freshness of the generated view, and the sync of each managed inline copy - is machine-checked by the corpus ownership index's drift-check, `scripts/ci/sync-corpus-ownership.py --check`, wired into `run-all.sh`. The semantic half, that a given occurrence really restates the same fact, is not mechanically reducible and is maintained by `maintain-project-docs` on its existing `_shared/` trigger, in the same spirit as the `No Party Grades Its Own Constraint` invariant.

### Invariant: Portable Bundle

plan_foundry ships as a bundle fetched from a public repository [github.com/kccastillo/plan_foundry.git](https://github.com/kccastillo/plan_foundry.git) into the target project itself. Every install, sync, and currency-check operation fetches directly from the source repository. There is no machine-global clone and no shared local installation. The target repository is the entire execution environment, and installation and update workflows may not depend on paths outside it.

`init-plan-foundry` and `plan-foundry-sync` clone the bundle into `.plan-foundry-tmp/`, copy the bundle-managed content into the target's `.claude/` directory, refresh the version pin, and remove the temporary clone. `plan-foundry-check-current` compares the local version pin with the remote repository. `plan-foundry-uninstall` is local-only and does not require network access.

**Why this is an invariant**

The portable-bundle model and the machine-global-clone model are mutually exclusive. Reintroducing references to a global installation path breaks sandboxed Claude Code environments - mobile, web, and restricted desktop sessions - where the target repository is the only writable filesystem surface. The design assumes every required file lives inside the target repository. The current clone-into-target model exists because the earlier global-clone approach failed in those environments.

**Consequences**

- Skills, agents, commands, and hooks live in `.claude/<kind>/<name>` within both the bundle source and consumer repositories. Installation copies them into place. No symlink mirror or plugin namespace exists.
- Bundle-managed paths are regenerable from the source bundle and are therefore gitignored. Project-local files remain part of the consumer repository's own history.
- Network access is required for install, sync, and currency-check operations. Uninstall remains offline and idempotent.
- Promotion from the development repository to the consumer-facing repository occurs through `scripts/promote.sh`. The shipped surface is defined by the script's allowlist rather than by documentation.
- Mobile, web, and other sandboxed Claude Code environments are supported because all required paths remain inside the target repository.
- New installations bootstrap from the public repository and execute entirely within the target repository.
- Consumer projects treat bundle-managed files as installed code, not local extension points. The four bundle-managed directories may be overwritten by `/plan-foundry-sync`, so a consumer records observations as INPUTs rather than editing those files in place. The reporting procedure and the full path list are in `init-plan-foundry/operating-rules.md`.
- Skills are invoked by bare name (for example, `Skill("plan-pipeline")`), never through a namespace; there are no namespaced skill identifiers.
- Projects are pinned to a specific bundle version through `.claude/.plan-foundry-bundle-version`.

The primary trade-off is that installation and updates require network access. This is accepted in exchange for sandbox compatibility.

**Verified by:** `scripts/ci/check-invariants.py`, which asserts that install, sync, and currency-check workflows contain no references to a machine-global clone path.

### Invariant: Bundle Namespace Ownership

`.claude/skills/_shared/` is plan_foundry's namespace. No plan_foundry code path may trust helpers loaded from an installed `_shared/` directory without first verifying that the directory belongs to plan_foundry.

Bundle identity is declared in `.claude/skills/_shared/bundle-contract.json` under the top-level `bundle` key. Entry points that load helpers from an installed `_shared/` directory must read and verify that identity before importing from it.

**Why this is an invariant**

A sibling bundle can share the same directory layout and install into the same consumer repository. In that situation, whichever bundle syncs last becomes the visible implementation at `_shared/`. Without an ownership check, a plan_foundry entry point can import compatible-looking helper code from a different bundle and continue running without any obvious failure. The result is silent execution of the wrong logic.

This is a namespace-ownership problem, not a `paper_trail` problem. One sibling bundle moving away from `_shared/` resolves a specific collision but does not eliminate the class of failure.

**Consequences**

- Ownership verification must happen before importing helpers from an installed `_shared/` directory.
- The ownership check cannot itself live in `_shared/`, because it is the mechanism that decides whether `_shared/` is trustworthy. The duplicated identity-reading logic is therefore intentional.
- A contract that names a different bundle diverts execution down the foreign-bundle path. A contract with no `bundle` key is treated as a legacy installation and remains trusted for compatibility.
- Recovery behaviour varies by entry point:

  - `sync` can recover by loading helpers from the freshly fetched bundle.
  - `uninstall` cannot safely trust a foreign helper set and therefore degrades its behaviour rather than executing foreign logic.
  - `check-current` uses plan_foundry's own metadata and reports the ownership issue alongside the result.
- File ownership is determined through install receipts. A bundle may update paths it can prove it previously wrote. It must not overwrite paths whose current contents are no longer vouched for by its own receipt.
- Modified paths are preserved rather than overwritten. Where ownership cannot be established, the bundle reports the conflict and refuses the write.
- Receipt files are namespaced by bundle identity so that multiple bundles cannot overwrite each other's ownership records.

The practical effect is that sibling bundles can coexist without silently taking control of one another's helpers, receipts, or managed paths.

**Verified by:** `plan-foundry-sync/lib/test_sync.py`, `plan-foundry-uninstall/lib/test_uninstall.py`, and `plan-foundry-check-current/lib/test_check_current.py`.

### Invariant: Subagent Permission Inheritance

Subagents dispatched through the Agent tool do not inherit the parent session's `permissions.allow` allowlist. A tool permitted in the parent session must not be assumed to be available to a subagent. In practice, Bash execution is denied inside subagents even when the parent session allows the same command.

**Why this is an invariant**

The harness cannot rely on subagents being able to execute shell commands. Designs that assume allowlist inheritance work in the parent session and fail once execution moves into a subagent. The failure occurs at runtime and is easy to introduce accidentally. This is a platform constraint that the harness must accommodate rather than a behaviour it can configure.

**Consequences**

- Executor agents cannot depend on shell tooling for mechanical work.
- The executor agent variants (`plan-executor`, `plan-executor-sonnet`, `plan-executor-opus`) declare:

  ```text
  disallowedTools: [Bash, WebFetch, WebSearch]
  ```

### Invariant: Agent Description Quoting

Agent `description:` values must be quoted if they contain `: ` (colon followed by a space). Unquoted YAML scalars containing `: ` are parsed as mappings rather than strings, and the harness loader silently drops the affected agent definition instead of reporting an error.

**Why this is an invariant**

The failure mode is silent. An agent appears to disappear from the harness without a parse error or diagnostic. A contributor changing or simplifying a `description:` field can introduce the problem without realising it.

**Consequences**

- Any `.claude/agents/*.md` file whose `description:` contains `: ` must use a quoted form.
- Acceptable forms include:

  - double quotes (`"..."`)
  - single quotes (`'...'`)
  - YAML block scalars (`>` or `|`)
- The rule applies specifically to `description:` fields because they are the fields most likely to contain natural-language text with `: ` sequences.
- Agent definitions must not rely on the loader reporting malformed descriptions. The loader may silently omit the affected agent.

**Verified by:** `scripts/ci/check-invariants.py`, which asserts that all agent `description:` fields are either quoted or otherwise safe.

### Invariant: PLAN ID Active-Set Uniqueness

Active PLAN IDs must be unique within the active PLAN set. Historical PLAN IDs remain part of the permanent record and are never re-issued. When an ID format changes across generations, the slug remains the durable cross-generation identifier.

Active PLANs use the `PLAN-[A-Z][A-Z][0-9]` format. Historical `PLAN-NNN` identifiers remain valid historical references and are preserved unchanged.

**Why this is an invariant**

PLAN identity serves two purposes: uniquely identifying active work and preserving historical references. The active set requires uniqueness. The historical record requires continuity. The harness relies on both.

ID reuse has previously caused collisions between active work and historical records. The current scheme exists to prevent those collisions while preserving existing references.

**Codified by:** `.claude/skills/write-plan/scripts/next_id.py`

**Consequences**

- The allocator treats active PLANs and retired PLANs as part of the same identity space when checking for collisions.
- Allocation is filesystem-first, using `Workbench/` and `Retired/` as the primary sources of truth. Historical references found only in the LOG are surfaced for human review.
- Active-set uniqueness applies to active PLANs. Historical identity is preserved indefinitely.
- Tooling that consumes PLAN IDs must support both historical and current formats:

  - `PLAN-\d{3,4}` (historical)
  - `PLAN-[A-Z]{2}[0-9]` (current)
- The AA-form scheme provides a finite identifier space. Extending the scheme after `ZZ9` is a future design problem and not a reason to weaken uniqueness today.

**Verified by:** `.claude/skills/write-plan/scripts/test_next_id.py`, which exercises allocator behaviour, collision avoidance, and LOG fallback handling.

### Invariant: Substrate Verification

PLAN authors must treat declared substrate files as the source of truth. Before writing any PLAN steps that reference existing schemas, APIs, enums, modules, or other constrained interfaces, the relevant substrate files must be read and used as the authoritative reference.

Substrate fidelity is enforced twice:

1. At authoring time, by requiring the PLAN author to read the declared substrate before writing.
2. At audit time, by independently checking PLAN references against the declared substrate.

Neither layer is sufficient on its own. The design depends on both.

**Why this is an invariant**

Hallucinated identifiers are often plausible enough to survive review and expensive enough to discover late. Reading substrate before authoring reduces the error rate. Auditing substrate fidelity afterwards catches mistakes that still make it through. The two layers work together to prevent plans from being grounded in invented schemas, symbols, attributes, or enum values.

**Enforcement**

- `write-plan` requires declared substrate files to be read before authoring begins.
- `audit-haiku-safe` performs substrate-fidelity checks against the declared substrate and raises:
  - `SFV001` and `SFV002` for blocking substrate-fidelity defects
  - `SFV003` for advisory findings

**Consequences**

- `substrate_files` must be populated whenever a PLAN references:

  - SQL schemas, tables, or columns
  - existing Python modules or symbols
  - enum values
  - third-party API attributes
  - other constrained interfaces whose valid values are defined elsewhere
- `SFV001` and `SFV002` findings are blockers and must be resolved before the PLAN can advance to `checked`.
- The substrate-fidelity checks and their tests are a load-bearing part of the planning process and should be updated together.

**Verified by:** `.claude/skills/audit-haiku-safe/lib/test_substrate_fidelity.py`

### Invariant: Executor Capability Boundary

A PLAN may not assign work to an executor that the executor is not capable of performing. The capability boundary is derived from the executor's own agent definition, specifically its `skills:` and `disallowedTools:` declarations. The boundary is not maintained as a separate list of prohibited skills or actions. This invariant exists to prevent PLANs from requesting capabilities that are unavailable at execution time.

**Why this is an invariant**

The capability boundary must be derived from the agent definition itself. Maintained lists of forbidden skills drift over time. A renamed skill, a removed capability, or an outdated exclusion list can silently weaken the boundary while appearing correct. The executor's agent file is the authoritative source of truth for what that executor can and cannot do.

As with substrate verification, the design relies on two layers:

1. An audit-time check that validates the PLAN against the executor's declared capabilities.
2. A runtime defence that prevents silent execution when a boundary violation reaches the executor.

Neither layer is sufficient on its own.

**Enforcement**

`audit-haiku-safe` derives the executor's capability boundary from the target agent file and raises:

- `EBV001` when a PLAN step requests a capability outside that boundary.
- `EBV002` when the boundary cannot be derived reliably, for example because the agent file is unreadable or omits a `skills:` declaration.

At runtime, executor agents treat unresolved capability-boundary violations as exceptions rather than proceeding silently.

**Consequences**

- Agent definitions are the source of truth for executor capabilities.
- Agent files must continue to declare their available `skills:` explicitly. An unreadable or incomplete agent definition degrades the check to `EBV002` rather than widening the boundary.
- `EBV001` findings are blockers and must be resolved before a PLAN advances to `checked`.
- `EBV002` findings indicate that the capability boundary cannot be verified and must be investigated.
- Capability-boundary findings may be acknowledged through `audit_acknowledgements` when a deliberate exception is required.
- `_shared/executor-capability-boundary.md` records the rationale for specific exclusions. The capability boundary itself remains derived from the live agent definitions.

**Verified by:** `.claude/skills/audit-haiku-safe/lib/test_capability_boundary.py`

### Invariant: Deterministic Projection

`audit-foundry.py` must produce deterministic output. Given the same repository state, the tool must emit byte-identical findings regardless of the machine, operating system, or filesystem on which it runs.

**Why this is an invariant**

The output is compared in CI. Any source of non-determinism creates flaky behaviour where the same tree passes on one machine and fails on another. Directory iteration is the primary known failure mode. Functions such as `Path.iterdir()`, `.glob()`, and `os.listdir()` do not guarantee a consistent ordering across filesystems, so any iteration whose order can influence findings output must be made deterministic.

**Codified by:** `audit-foundry.py`

**Consequences**

- Any directory iteration that can affect findings output must be wrapped in `sorted()`.
- An iteration that is genuinely order-independent must carry an explicit `# determinism-ok` annotation explaining why ordering cannot affect the outcome.
- New contributors should assume that filesystem iteration is non-deterministic unless proven otherwise.

**Verified by:** `scripts/ci/check-invariants.py`, which AST-lints `audit-foundry.py` for directory iteration not wrapped in `sorted()`.

### Invariant: Prove It Can Fail

A check that cannot fail is not a check. The harness must not rely on guards, tests, or validation steps whose failure path has never been demonstrated.

Checks commonly become ineffective in three ways:

1. **Unregistered.** The check exists but is never executed.
2. **Vacuous.** The check passes regardless of whether the fault is present.
3. **Overly narrow.** The check validates only a subset of what it claims to cover.

**Why this is an invariant**

An ineffective check creates a false sense of safety. A missing check is often easier to detect than a check that appears to be running while validating the wrong thing. The failure may remain hidden until the guarded property is violated in production.

**Enforcement**

`scripts/ci/check-check-registration.py` prevents unregistered checks by ensuring that every check-shaped file is either:

- explicitly invoked by `run-all.sh`, or
- covered by a discovery pattern that `run-all.sh` executes.

The suite's `--list` output is derived from the checks that actually run, preventing the suite from describing coverage it does not provide.

**Consequences**

- A newly added check must be proven capable of failure before it is trusted.
- When practical, validation should include a negative test that demonstrates the guard turning red when the protected property is violated.
- Reviewers should ask of every new check whether it fails when the guarded property is broken.

### Invariant: Single Active Orchestrator and No Published Fork

At most one `plan-pipeline` orchestrator walk may operate on a working tree at a time. A push that would publish a divergent history must be refused.

**Why this is an invariant**

Concurrent orchestrator runs share the same working tree, commit history, and remote. Without coordination they can:

- overwrite each other's intermediate state
- intermingle uncommitted changes
- create divergent commit histories
- publish conflicting views of repository state

The harness depends on orchestrator execution being serialised and on pushes preserving a single coherent history.

**Enforcement**

Two independent guards enforce this invariant.

1. **Repository lock (`orchestrator_lock.py`).** A gitignored lock file at `Workbench/.orchestrator.lock` is acquired before an orchestrator walk begins and released on every exit path. If another walk already holds the lock, the new invocation refuses to run and exits without modifying state. The lock answers one question only: whether an orchestrator walk is already active in this working tree.
2. **Divergence guard (`push_guard.py`).** Before an automatic push, the orchestrator checks whether the local branch is behind its remote. If publishing would create a divergent history, the push is refused and the run halts pending manual reconciliation. The same protection is also applied through the shipped `.claude/hooks/pre-push` hook, so pushes initiated outside the orchestrator follow the same rule.

**Consequences**

- Orchestrator execution is serial rather than concurrent.
- Workflows must assume that another active orchestrator run is a blocking condition rather than attempting coordination.
- A repository that has diverged from its remote must be reconciled before publication.
- Push safety is enforced both within the orchestrator and at the git-hook layer.
- The lock is intentionally a concurrency guard, not a session-identity mechanism. Once a walk completes and releases the lock, a later invocation may acquire it and continue from the current on-disk state.

**Scope**

This invariant governs orchestrator execution and publication safety. It does not govern subagent capability boundaries or subagent tool restrictions, which are covered by separate invariants.

**Current limitations**

The pre-push hook can be bypassed with `git push --no-verify` and depends on hook installation being present. The orchestrator-level guard therefore remains part of the defence even when the git hook exists.

**Verified by:** `test_push_guard.py` and `test_orchestrator_lock.py`, which are executed through `run-all.sh`.

### Invariant: Orchestrator-Owned State Is Never Trusted From Subagents

The orchestrator does not trust orchestrator-owned PLAN state written by a subagent. A subagent may propose state changes, but the orchestrator remains the sole authority for orchestration state. Before acting on any subagent result, the orchestrator restores orchestrator-owned fields to a trusted snapshot and then applies any state transitions itself.

**Why this is an invariant**

A subagent can produce plausible state without performing the work required to justify that state. The harness therefore treats subagent-reported orchestration state as a claim rather than evidence. Orchestration state must be derived or verified by the orchestrator itself. This invariant exists to prevent state forgery and accidental advancement through the pipeline.

**Orchestrator-owned fields**

The orchestrator owns the following PLAN frontmatter fields:

```text
pipeline_phase
audit_state
last_executor_outcome
verification_state
```

### Invariant: No Party Grades Its Own Constraint

A constraint must not be graded by the party it constrains. Where complete separation is impossible, the constrained party may move the grade only toward greater rigour, never toward less. Any loosening path belongs to a human decision made before execution begins.

**Preferred implementations**

In order of preference:

1. Derive the value from an independent source so no runtime party sets it.
2. If a runtime party must participate, make the judgement one-directional: it may tighten the constraint but not relax it.

**Why this is an invariant**

The harness arrived at this pattern multiple times from independent failures. The specific mechanisms differ, but the underlying defect is always the same: a system component is allowed to grade, count, scope, or evaluate the very constraint that limits it. When that happens, the constraint eventually becomes advisory rather than binding.

**Existing applications**

- **Audit iteration counting.** The iteration count is derived from audit records on disk rather than maintained by the caller.
- **Executor outcome verification.** The orchestrator re-runs verification in parent context rather than trusting executor-reported outcomes.
- **Retire post-condition verification.** Retirement success is checked independently rather than accepted from the retiring agent's report.

**Relationship to Orchestrator-Owned State**

The invariant *Orchestrator-Owned State Is Never Trusted From Subagents* is a special case of this principle. That invariant applies the rule to orchestration state. This invariant applies it generally. The constrained party need not be a subagent, and the graded item need not be state. Any of the following can fall under this rule:

- state transitions
- execution outcomes
- scope boundaries
- iteration counts
- risk classifications
- escalation thresholds

**Design consequences**

When designing a new grading or classification mechanism:

- Prefer values derived from independent data.
- Prefer verification over self-reporting.
- Allow automatic escalation but require human approval for de-escalation.
- Treat self-certified success with suspicion.

A future risk-classification system would follow this pattern: derive risk from declared scope, allow any party to raise the classification, and reserve lowering it to a human decision made before execution.

**Current status**

This invariant is intentionally not asserted by a single mechanical check.

## Bootstrap

plan_foundry installs by fetching the public bundle into a temporary directory inside the target repository and copying the bundle-managed content into place. The non-invasive design properties (no machine-global state, no plugin namespace, bare-name skill invocation) and the promotion path from `plan_foundry_dev` to `plan_foundry` via `scripts/promote.sh` are recorded once, in the Portable Bundle invariant above.

### Install

A fresh installation bootstraps from the public repository using the clone-copy-delete procedure defined in `BOOTSTRAP.md`. Installation is idempotent.

### Sync, currency check, and uninstall

`/plan-foundry-sync` refreshes the bundle-managed surface, `/plan-foundry-check-current` compares the installed version against upstream, and `/plan-foundry-uninstall` removes bundle-managed content. Three design properties matter here: sync quarantines files that are no longer shipped rather than deleting them, the currency check needs no local bundle clone, and uninstall preserves project-owned data (`Workbench/`, `Retired/`, and project-local configuration) and runs offline. The step-by-step procedures are in `init-plan-foundry/operating-rules.md` and `README.md`.
