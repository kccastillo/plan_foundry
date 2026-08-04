# plan_foundry Architecture

This document is the maintainer-facing reference for plan_foundry. It captures the design philosophy, strategic principles, named invariants, doc landscape, and bootstrap mechanism.

**Audience.** The reader is a maintainer or new contributor working on the harness itself, not an end-user installing it. End-user docs (install commands, skill descriptions) live in `README.md`. Agent-facing operating rules live in `CLAUDE.md` (always-loaded - the load-bearing meta-policy was consolidated here when `AGENT_RULES.md` was dissolved per Option Y, 2026-05-14). Forward-planning threads live in `ROADMAP.md`. This doc is the place to learn how the harness thinks.

**Reading order.** Skim the design philosophy for the why, then the strategic principles to see the five axes every thread is judged against, then the invariants register for the load-bearing facts the harness depends on. The doc landscape table maps every other doc to its audience and maintenance trigger. The bootstrap section explains how plan_foundry establishes itself in a fresh target project.

## Design Philosophy

plan_foundry tackles three structural problems in ad-hoc agent setups:

**Deterministic triggering.** Skills declare explicit trigger phrases; a phase state machine on disk decides which agent fires next. The orchestrator reads PLAN frontmatter and routes by enum - no "should I run the audit now?" judgement call. State determines it.

**No race conditions.** One conversational re-entry point (the background executor's completion message). Every other subagent dispatch is foreground and synchronous. Audit gates run sequentially, never in parallel. PLAN state lives in frontmatter on disk so re-entry is idempotent - re-running with no new outcome is a no-op, not a double-dispatch.

**Smaller agents, harnessed.** Each skill pins its model tier - Opus for design judgement, Sonnet for mechanical review, Haiku for execution. Subagents declare their preloaded skill registry explicitly; no implicit access to the parent's wider context. Cheap models get bounded jobs they can actually complete; expensive models are reserved for work that needs them.

Underlying primitives:

- **Workbench-driven.** Every piece of work has a durable PLAN file on disk - design intent, decisions, verification items, and outcome notes live in version control, not chat history.
- **Audited quality gates.** Two-pass audit (conceptual sufficiency + mechanical safety) runs before any code is written.
- **Codified-over-memory.** Recurring truths become skills, rules, or CLAUDE.md entries - never memory crutches.

### Architectural scaffold, not harness-helper

plan_foundry is a **scaffold** - and that word is chosen deliberately. It names a
middle layer between two other things it is often mistaken for:

- **Context engineering / harness-helpers.** Prompt-rule packs and skill
  collections that improve a single agent's behaviour by *asking* it to behave
  well - surface your assumptions, keep changes surgical, do not over-engineer.
  The guidance is sound but compliance is probabilistic: the model may follow it
  or may not, and there is no structural backstop when it does not.
- **Harness engineering.** Building a whole new agent runtime - in effect, a new
  Claude Code - with its own execution loop, tool layer, and control flow.
  Powerful, but a large and ongoing engineering commitment.

plan_foundry is neither. It is a scaffold built *on top of* an existing harness:
a deterministic state machine, audit gates, capability bounds, and re-run
verification, expressed entirely as files and skills. It buys the determinism of
harness engineering - state decides what runs next, gates block bad work,
verification re-runs in a trusted context - without the cost of building a
runtime. And it is structurally different from a prompt-rule pack: its
guarantees are mechanical (a phase enum, a shell assertion, a `disallowedTools`
list), not a request the model is trusted to honour.

This positioning is load-bearing for how contributions are judged. A proposed
change that adds another probabilistic "please behave" instruction where a
deterministic gate is possible is drifting toward the harness-helper category.
Keep the scaffold a scaffold: prefer the mechanical guarantee.

## Strategic Principles

These principles are not stylistic preferences - they constrain design decisions. When a PLAN's Context references `[P3]`, it points to principle 3 (Tool / model-tier selection) below. The strategic-principles register is closed: principles get refined or replaced, not appended to lightly. If you think a sixth principle belongs, that is itself an ideate-worthy conversation.

Five axes shape every thread. Numbered for reference.

1. **Context rot minimisation.** CLAUDE.md / skill registries stay lean. Findings reach the bundle through `raise-foundry-request` rather than accumulating in a log. Pre-empt drift through monthly maintenance, not crisis intervention. (Prior to 2026-05-14 this principle named `AGENT_RULES.md` separately; that file was dissolved into `CLAUDE.md` per Option Y of ADVICE-003 - eliminating the rot surface rather than defending it.)
2. **Just-in-time skill calling.** Skills load on demand via trigger phrases and progressive disclosure. Resist always-on additions to the skill registry - every always-loaded line is paid every interaction.
3. **Tool / model-tier selection.** Opus for design, Sonnet for execution, Haiku for mechanical. Decision-15 triage (Already-locked / Mechanically-forced / Real-judgement) is the discipline against escalation creep.
4. **Self-improvement from lessons.** Lessons are codified into permanent rules when they recur, not hoarded as episodic memory. Codification beats accumulation; eviction is part of the loop.
5. **Robust subagent orchestration.** Wire formats are typed; failure modes are first-class statuses; capability boundaries are checked at audit time AND at runtime; partial success cannot be silent.

### Productive audit failure

The multi-stage audit cadence (Self-Critique -> sufficiency -> plan-safety -> outcome-verify) exists precisely because each stage catches what the others miss. An audit that returns `revision_needed` after Self-Critique passed is the system working, not regressing. The Spec-Refine -> re-audit loop is the supported path; orchestrators should not treat audit-found issues as failures to hide or as evidence of a deficient spec-author. To the contrary: a PLAN that sails through every stage on iteration 1 with no findings is the unusual case. Normalise productive audit failure; do not apologise for it.

## How plan_foundry works (mechanism walkthrough)

This section is sized for a consumer who has decided to look deeper - not the README overview, not the maintainer invariants, but the actual enforcement anatomy. Each mechanism names what enforces it and what breaks if it is removed.

### (a) PLAN lifecycle state machine

Every piece of work is a PLAN file in `Workbench/` with a `pipeline_phase` frontmatter field. The field is an enum with six legal values: `drafting`, `drafted`, `checked`, `executing`, `outcome-verifying`, `complete`. The `plan-pipeline` orchestrator reads that enum on every invocation and dispatches the correct sub-skill - it does not infer phase from conversation context or from the PLAN body.

**What enforces it:** `plan-pipeline` reads `pipeline_phase` from PLAN frontmatter and routes by value. The transition table is in [phase-state-machine.md](.claude/skills/plan-pipeline/references/phase-state-machine.md). Each transition writes the new phase back to frontmatter before any sub-skill fires, so a crash or interruption leaves the PLAN in a known state, not an unknown one.

**What breaks if it is removed:** without the enum, re-entry depends on the model reconstructing phase from conversation history - which compresses, gets lost across sessions, and differs between models. State drift is silent. The state machine's value is precisely that the model does not need to remember; the file does.

### (b) Audit gates on file content

A PLAN cannot advance from `drafted` to `checked` without passing two sequential audits. Each audit is a separate model invocation with no prior turns - it reads the PLAN file cold and returns structured findings.

- **`audit-sufficiency`** (Opus): conceptual audit. Does this PLAN have clear acceptance criteria? Are risks identified? Is the verification strategy real or optimistic? Findings at `error` severity block advancement.
- **`audit-haiku-safe`** (Sonnet): mechanical audit. Are substrate files declared and referenced honestly? Are destructive actions scoped correctly? Is the executor tier (Sonnet vs Opus vs Haiku) appropriate? Includes substrate-fidelity grep (SFV001/SFV002): every named entity in the Steps must appear in a declared substrate file - hallucinated column names and invented API attributes fail here.

The worked example for how gates block: in `plan-pipeline` section 4, the orchestrator reads the audit's `last_outcome` from the `audit_state` frontmatter block. If it is `revision_needed`, the orchestrator sets `pipeline_phase: drafted` (back, not forward) and surfaces the findings. There is no advisory-only path - findings are blockers.

**What enforces it:** `audit-sufficiency` and `audit-haiku-safe` skills; `audit_state` frontmatter block written by each skill; `plan-pipeline` reads that block before any transition. Enforcement sites: each skill's `workflows/` steps file.

**What breaks if it is removed:** without the second-model audit, quality assurance collapses to self-review - the same model that wrote the PLAN approves its own work in the same context. The audit's value is the different-invocation asymmetry: it catches what the author naturalises.

### (c) Verification in a fresh context

After a PLAN is executed, the `outcome-verifying` phase re-runs `verify:` and `acceptance:` shell assertions. This re-run happens in the orchestrator's (parent) context, not the executor's context and not the same turn that did the work.

**What enforces it:** the executor (plan-executor agent) carries `disallowedTools: [Bash, WebFetch, WebSearch]` - it cannot run shell assertions even if it tries. The `verify:` lines are left for the orchestrator to re-run in its own context where the tool allowlist is in effect. This is PLAN-executor decision 25; the constraint is named in [Invariant: Subagent Permission Inheritance](#invariant-subagent-permission-inheritance) below.

**What breaks if it is removed:** without the fresh-context re-run, verification degenerates to the executor self-ticking boxes. An executor that produced output it believes is correct will tick the box - the verification check is vacuous. The fresh-context model ensures the assertion runs against actual filesystem state, not the executor's belief about filesystem state.

### (d) Bundle propagation by copy, not symlink

When `init-plan-foundry` installs the bundle into a consumer project, it `git clone --depth=1`s the public bundle into `<target>/.plan-foundry-tmp/`, copies `.claude/{skills,agents,commands,hooks}` into the consumer's `.claude/`, refreshes the version pin at `.claude/.plan-foundry-bundle-version`, and deletes the tmp clone. There is no machine-global state, no symlink mirror, and no plugin namespace.

**What enforces it:** `init-plan-foundry`'s `lib/run_install.py` performs the clone-copy-delete sequence. The tmp directory is gitignored; the bundle-managed dirs are gitignored (regenerable from the public URL). Skills are invoked by bare name (`Skill("plan-pipeline")`), never with a namespace prefix. Verified by [Invariant: Portable Bundle](#invariant-portable-bundle) below.

**What breaks if it is removed:** symlinking back to a machine-global clone breaks sandboxed Claude Code sessions (mobile, web, restricted desktop) whose filesystem write surface is the target repo only - the global path is out of reach. The AC5 model (`~/.claude/plan_foundry/`) failed precisely this way; AC6's network-clone-into-target model was the fix.

**Consumer boundary rule.** When a consumer project encounters plan_foundry behaviour worth reporting, the correct path is: detect the symptom, capture it as an INPUT file (via `write-input`) inside the consumer's own `Workbench/`, carry on with a local workaround, and transfer that typed artefact to the plan_foundry repo at session end. Captures formalise at observation-time, not at later triage - there is no staging dock. Never patch files under `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, or `.claude/hooks/` - those are overwritten by `/plan-foundry-sync`. Full procedure and rationale: [init-plan-foundry/operating-rules.md section  plan_foundry vs this-project boundary](.claude/skills/init-plan-foundry/operating-rules.md). (Boundary rule shipped in v0.6.2; capture-at-observation-time refinement landed 2026-05-23 with the wip/ dissolution.)

## Invariants Register

Named invariants the harness depends on. Each is a load-bearing promise that, if violated, would break correctness or surprise a maintainer. Listed here so a tidy-up of any one enforcement site does not silently drop the underlying constraint.

**What qualifies as an invariant.** An invariant is a load-bearing fact about the harness or its environment that the code, skills, or agent files structurally depend on. Three tests:

1. **Codified somewhere structurally.** The invariant is enforced or relied on by a piece of code, an agent's `disallowedTools`, a skill's preconditions, or similar - not just a documented preference.
2. **Silent-break risk.** Removing or contradicting the invariant breaks correctness in a way that may not surface until later. If a violation is loudly caught at audit or runtime, it does not need to be an invariant - the enforcement site already documents it.
3. **Non-obvious to a future maintainer.** If a future contributor looking at the enforcement site would naturally re-derive the constraint, the invariant lives implicitly. The register exists for facts that a tidy-up could plausibly remove without realising the consequence.

Add to this register when a fact passes all three tests. Each entry names the invariant, states the constraint, cites evidence, lists the consequences, and explains why it is named here rather than left as commentary.

### Invariant: plan_foundry Doc-Set Integrity

**The plan_foundry repo's 4-doc Option E layout is load-bearing for the harness's design.** All four root docs must exist at the repo root: `CLAUDE.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `README.md`. Each owns a distinct audience scope (per the Doc Landscape table); removal of any breaks the design contract.

(The original Option E specified five docs, with `AGENT_RULES.md` as an "Agent on-demand" companion. That file was dissolved on 2026-05-14 per Option Y of `ADVICE-003`: its meta-policy content moved into `CLAUDE.md`, its structural-reference content was already canonical in skill workflows. Eliminating the file removed a drift surface entirely.)

This is a plan_foundry repo invariant, NOT a generic skill enforcement: the `maintain-project-docs` skill correctly silent-skips absent files because it has no way to presume which root-doc belongs to which project (a target project may have its own `ARCHITECTURE.md` separate from any plan_foundry concept). The integrity-check belongs HERE in the invariants register so future maintainers see the plan_foundry-specific load-bearing-ness explicitly.

**Verified by:** `scripts/ci/check-invariants.py` asserts all four root docs are present.

### Invariant: Portable Bundle

**plan_foundry ships as a public-URL bundle, fetched on demand into a transient directory inside each target repo.** Bundle source is `https://github.com/kccastillo/plan_foundry`. Every install / sync / currency-check operation does its own network fetch - there is no machine-global clone. The target repo is the entire sandbox: `/init-plan-foundry` and `/plan-foundry-sync` `git clone --depth=1` into `<target>/.plan-foundry-tmp/`, copy `.claude/{skills,agents,commands,hooks}` into the target's `.claude/`, refresh the operating-rules sentinel block in the root `CLAUDE.md` (replace-between-markers, preserving all host content, via the shared `_shared/claude_md_block.py` helper), refresh the pin at `.claude/.plan-foundry-bundle-version`, and delete the tmp clone. `/plan-foundry-check-current` queries the remote via `git ls-remote` and compares to the pin. `/plan-foundry-uninstall` is offline and idempotent.

This is PLAN-AC6 (2026-05-19), superseding PLAN-AC5's `~/.claude/plan_foundry/` global-clone model. AC5 failed in sandboxed Claude Code sessions (mobile, web, restricted desktop) whose filesystem write surface is the target repo only - `~/.claude/plan_foundry/` was out of reach. AC6's network-clone-into-target model is sandbox-compatible: every required path stays inside the target.

**Why this is named as an Invariant:** the network-clone model and the global-clone model are mutually exclusive. Reintroducing any reference to `~/.claude/plan_foundry/` in install/sync/check code paths breaks sandboxed sessions and reintroduces the AC5 "git pull across promote.sh releases hits unrelated histories" hiccup.

**Consequences this design depends on:**
- Skills, agents, and commands live at canonical `.claude/<kind>/<name>` as **real directories** in both the bundle source and each consumer project (no symlink mirror, no `plugins/` tree). Consumer projects acquire these by `init-plan-foundry` cloning the prod bundle into `.plan-foundry-tmp/` and copying.
- Bundle paths in consumer projects are **gitignored** (regenerable from the public URL). Project-local files under `.claude/` (`settings.local.json`, `plan-foundry.config`, custom scripts) are NOT gitignored - they live in the consumer's git history.
- Network is required for install / sync / currency-check. Uninstall is offline (local-only). The "Claude Code on a phone" requirement (kccastillo, 2026-05-19) - install/update must work in sandboxed sessions with network - is the load-bearing constraint here.
- Promotion of the consumer-facing surface from `plan_foundry_dev` to `plan_foundry` runs via `scripts/promote.sh <tag>`. The script reads `scripts/prod-repo.txt` for prod coordinates, copies an allowlisted subset of the dev tree to a temp dir, inits a fresh git repo there, force-with-lease pushes to the prod remote, and tags the release. Allowlist: `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`, `scripts/audit-foundry.py`, `scripts/recover-deleted-retirees.py`, `scripts/test_recover_deleted_retirees.py`, `scripts/ci/run-all.sh`, `README.md`, `LICENSE`, `CLAUDE.md`, `BOOTSTRAP.md`.
- Mobile and web Claude Code apps do NOT read project-local `.claude/{skills,agents,commands}/` once the bundle is copied in - AC6 enables install and sync to work in those sandboxed sessions regardless. Operating rules inlined into CLAUDE.md are visible across all surfaces.
- Bootstrap into a fresh repo is via paste-prompt: the user pastes "Bootstrap plan_foundry from https://github.com/kccastillo/plan_foundry into this repo." into a Claude Code session. The agent fetches the procedure from `BOOTSTRAP.md` at the bundle root and runs the three-command sequence (`git clone` -> `run_install.py` -> `rm -rf .plan-foundry-tmp`).
- Trade-off: every install/sync needs network. Offline = no install. Accepted per the sandboxed-session requirement.

**Verified by:** `scripts/ci/check-invariants.py` asserts the install / sync / check skills carry no `.claude/plan_foundry` global-clone path reference.

### Invariant: Bundle Namespace Ownership

**`.claude/skills/_shared/` is plan_foundry's namespace, and no plan_foundry code path may trust its contents without first checking who owns them.** The bundle declares itself in `.claude/skills/_shared/bundle-contract.json` under the top-level `bundle` key, whose value is `plan_foundry`. Every entry point that loads a helper from the *installed* `_shared/` - `plan-foundry-sync/lib/sync.py`, `plan-foundry-uninstall/lib/uninstall.py`, `plan-foundry-check-current/lib/check_current.py` - reads that key first and treats a value naming a different bundle as a signal not to trust the directory.

A sibling bundle forked from this lineage inherits the same layout and, installed into the same consumer repo, lands its own helpers at the same path. Whichever bundle synced last owns the directory. `sync.py` binds `bundle_copy`, `bundle_fetch` and `claude_md_block` into `sys.modules` before the clone, so once that happens every later import anywhere in the process resolves to the other bundle's code - including `bundle_fetch.BUNDLE_URL`, which is how a plan_foundry sync can clone and install a different product under plan_foundry's own version pin without saying anything. Raised from `paper_trail_dev`, 2026-08-04, against two live consumer repos; paper_trail has since moved its own machinery to `_pt_shared/` and left the bare name here.

**Why this is named as an Invariant:** a shared name is not owned until something enforces it. paper_trail vacating the path resolves today's collision and does nothing about the next sibling bundle, and the failure is silent in the direction that matters - a foreign helper whose signature happens to match runs the wrong logic and reports success. A third bundle descended from this lineage must pick its own namespace; this register entry is where that is written down.

**Consequences this design depends on:**
- The identity read is duplicated inline at each of the three entry points and imports nothing from `_shared/`. It is the function that decides whether `_shared/` is trustworthy, so it cannot live there. This is the same constraint that produced the deliberate duplication of `read_bundle_contract` in `_shared/preflight.py`; all of these look like removable redundancy and none of them are.
- A contract with no `bundle` key reads as the pre-identity state and is trusted. Every consumer installed before the key existed is in that state, so the check adds no failure mode for the population it is not about. Only a contract naming a *different* bundle diverts.
- Recovery differs per entry point by what each can do. `sync` clones first and loads its helpers from the clone, so it repairs the collision and completes. `uninstall` is offline with nothing to fall back to, so it skips the `.gitignore` reversal and says why rather than reversing a foreign entry list. `check-current` reads plan_foundry's own pin, so it answers normally and appends the ownership note.
- `quarantine` moves only files still byte-identical to what the install receipt records. A path the receipt names whose bytes have changed belongs to something else now - a sibling bundle shipping the same path, or the consumer's own edit - and is reported under `modified_since_install_preserved` and left where it is.

**Verified by:** `plan-foundry-sync/lib/test_sync.py` asserts the shipped contract names this bundle, that a foreign `_shared/` diverts helper loading to the clone and the sync still completes, that the ordinary path is untouched, and that quarantine skips modified files while still moving unmodified ones. Companion checks live in `plan-foundry-uninstall/lib/test_uninstall.py` and `plan-foundry-check-current/lib/test_check_current.py`.

### Invariant: Subagent Permission Inheritance

**Subagents dispatched via the Agent tool do NOT inherit the parent session's `permissions.allow` allowlist.** Bash calls from inside a subagent are denied at the system level regardless of which patterns the parent has allowed.

This is a known Anthropic defect: GitHub issue [#37730](https://github.com/anthropics/claude-code/issues/37730) was closed `not planned`. Issues #27661 and #10906 track the same root cause. Empirical probe 2026-05-01 confirmed total denial across four representative patterns including bare `ls` despite `Bash(ls *)` being in the parent allow list.

**Consequences this design depends on:**
- The executor cannot rely on shell tooling for any mechanical step.
- The plan-executor agent variants (`plan-executor`, `plan-executor-sonnet`, `plan-executor-opus`) carry `disallowedTools: [Bash, WebFetch, WebSearch]` to enforce this structurally. Do NOT remove Bash from `disallowedTools` under the assumption that allowlist inheritance will save you - it will not.
- `verify:` and `acceptance:` shell lines in PLANs are re-run by the orchestrator in the **parent** context (decision 25), where the allowlist works correctly. This is load-bearing - the executor never runs them.

**Verified by:** `scripts/ci/check-invariants.py` asserts the three plan-executor agents deny `Bash` via `disallowedTools`.

### Invariant: Agent Description Quoting

**Agent file frontmatter `description:` values must be quoted (double-quote, single-quote, or block scalar) if they contain unquoted colons.** Specifically, unquoted YAML scalars containing colon-space (`: `) as a substring are ambiguous plain scalars that the harness loader silently drops - the YAML parser sees them as the start of a new mapping key. The drop is silent, leaving no error message.

This constraint emerged from ADVICE-009 session 2 (2026-05-26) diagnostic findings. Three executor subagent files (`plan-executor`, `plan-executor-sonnet`, `plan-executor-opus`) were silently dropped due to long unquoted `description:` fields containing `: ` sequences. The loader's silence meant no error surfaced until a separate run found the agents missing - exactly the silent-break risk the invariants register exists to catch.

**Consequences this design depends on:**
- All `.claude/agents/*.md` files must quote their `description:` field if the value contains `: ` (colon followed by space).
- Quoted forms include double-quote (`"..."`), single-quote (`'...'`), or YAML block scalars (`>` or `|` on subsequent indented lines). Internal content can be anything once quoted.
- The constraint applies to `description:` specifically (not all frontmatter scalars) because only `description:` values are naturally long and prone to containing `: ` patterns. Other fields (`name`, `model`, `tools`, `disallowedTools`, `skills`) take constrained value-shapes where `: ` is not a natural occurrence.

**Why this is named as an Invariant:** the violation is silent, and the failure mode is "agent file disappears from the harness" - no parse error, no diagnostic, just absent from available agents. A future contributor unquoting or simplifying a `description:` field would introduce this trap without realizing.

**Verified by:** `scripts/ci/check-invariants.py` asserts that all agent `.claude/agents/*.md` files have quoted or safe (non-colon-space) `description:` values.

### Invariant: PLAN ID Active-Set Uniqueness + AA-Form Scheme

**Active-set PLAN IDs are unique among themselves. The LOG carries history. Slug is the durable cross-generation discriminator across ID re-uses.** Active PLANs are allocated in `PLAN-[A-Z][A-Z][0-9]` (AA0-ZZ9, 6,760 slots, lexicographic). Historical `PLAN-NNN` IDs (PLAN-001 through PLAN-037) in `Retired/` and the LOG are frozen - never migrated, never re-issued. ADVICE / RESEARCH allocators stay numeric (no equivalent collision history).

**Codified by:** `.claude/skills/write-plan/scripts/next_id.py` (canonical allocator).

**Originating event:** PLAN-AA0 plan-of-plans (2026-05-16) coordinated recovery from a structural collision when six current PLAN IDs (028-033) collided with retired-but-deleted PLANs. Root cause: retire-skill subagent ran `git rm` instead of `mv` to `Retired/`, and the allocator scanned only the filesystem (not the LOG), so freed IDs appeared "unused".

**Consequences this register depends on:**
- The allocator's source-of-truth is filesystem-primary (Workbench/ + Retired/) + LOG-scan as non-authoritative fallback (per PLAN-AB9 2026-05-23, post-D2-A; LOG-only IDs are surfaced via `--explain` for human attention).
- Active-set identity is *unique-within-Workbench*; LOG-history identity is *eternally remembered*.
- Future tooling that joins on PLAN ID must accept both `PLAN-\d{3,4}` (historical) and `PLAN-[A-Z]{2}[0-9]` (active) patterns.
- At ZZ9 (slot 6,760) the scheme will need extension - next-generation problem.

**Verified by:** `.claude/skills/write-plan/scripts/test_next_id.py` exercises the allocator's filesystem-primary + LOG-fallback union logic plus the `--explain` per-ID source partition.

### Invariant: Substrate Verification

**Plan-writer must Read declared substrate files (schema, enums, API docs) as ground truth before authoring any Steps that emit SQL DDL/queries, ORM operations, Python imports from existing modules, or string-literal values of constrained-type (enum) fields. audit-haiku-safe lints substrate fidelity post-hoc with a grep-based check against declared substrate.** The two-layer pattern (input governance at write-time + post-hoc lint at audit-time) mirrors the canonical multi-layer hallucination-mitigation shape: neither layer alone suffices.

The enforcement sites are: (1) `write-plan/workflows/write-plan.md` Step 0 ("Substrate-verification preflight") - mandates that plan-writer `Read` each path in `substrate_files` before any authoring Write/Edit; (2) `audit-haiku-safe/workflows/audit-haiku-safe-steps.md` Step 4a ("Substrate fidelity check") - greps declared substrate for every named entity in PLAN Steps and emits `error`-severity SFV001/SFV002 findings for zero-match entities and private-attribute access.

**Consequences this design depends on:**
- `substrate_files` must be set on any PLAN whose Steps will touch SQL column names, Python symbols imported from existing modules, enum string-literal values, or third-party API attributes.
- audit-haiku-safe's SFV001/SFV002 findings are Blockers - they must be resolved before the PLAN advances to `checked`. SFV003 is a Not-blocker advisory.
- Unit tests for the lint logic live at `.claude/skills/audit-haiku-safe/lib/test_substrate_fidelity.py`. Run before any change to the lint module.

**Verified by:** `.claude/skills/audit-haiku-safe/lib/test_substrate_fidelity.py` exercises the SFV001/SFV002 lint logic.

### Invariant: Deterministic Projection

**`audit-foundry.py` is a deterministic projection: the same tree must produce byte-identical findings output regardless of host filesystem.** Its CI-compared output makes any non-determinism in the projection flake, passing on the author's machine and failing on the CI runner.

The concrete failure mode is directory iteration: `Path.iterdir()`, `.glob()`, `os.listdir()` and friends return entries in host filesystem order, which differs across machines. Every directory iteration whose result order can reach audit-foundry's findings output must be wrapped in `sorted()`.

**Codified by:** `audit-foundry.py` (every `iterdir()` / `glob()` call is `sorted()`-wrapped).

**Consequences this design depends on:**
- A new directory iteration in this tool must be `sorted()`-wrapped, or carry an inline `# determinism-ok` comment when it is genuinely order-independent (an emptiness test, a max-finding scan).

**Why this is named as an Invariant:** the violation is silent. An unsorted iteration produces correct-looking output on the author's machine indefinitely, and surfaces only when a different filesystem orders entries differently - long after the change that introduced it.

**Verified by:** `scripts/ci/check-invariants.py` AST-lints `audit-foundry.py` for directory iteration not wrapped in `sorted()`.

### Invariant: Prove-It-Can-Fail

**A check that cannot fail is not a check.** A guard can be present and inert in three ways, each with a live instance found 2026-07-29. It can be unregistered: `scripts/ci/test_loud_fail.py` and `scripts/test_recover_deleted_retirees.py` sat under repo-root `scripts/`, which the catch-all sweep does not glob, and CI had never run either. It can be vacuous: the old `test_loud_fail.py` asserted only "exit != 0" against a `.git`-less copy that already failed two checks with no mutation applied, so it passed whether or not the fault was injected. It can be narrower than it claims: `check_frontmatter_v2`'s selector matched only the frozen `PLAN-NNN` form, so it validated zero of the active PLANs for roughly two months while `CLAUDE.md` listed it as a covered category.

**Enforced by:** `scripts/ci/check-check-registration.py` closes the first mode - every check-shaped file on disk must be named in `run-all.sh` or sit under a path the catch-all sweep globs, and it hard-fails naming the uncovered files. `--list` is derived from the script's own invocations rather than hand-maintained, so the suite cannot misdescribe itself.

**Not mechanically enforced:** the second and third modes. Writing a negative test per guard was built and measured at roughly twelve minutes per CI run, against a base of seventy seconds, and removed on that basis. The discipline is therefore a review obligation, not a gate: when adding a guard, break the property it guards and confirm it goes red before trusting it.

### Invariant: Single Active Orchestrator + No Published Fork

**At most one plan-pipeline orchestrator walk may be active in a given working tree at any time, and a push that would publish a forked history MUST be refused.** Two concurrent orchestrators sharing a working tree collide on git operations, intermingle uncommitted work, and risk pushing divergent histories to the shared remote - the BUG 4 failure (2026-06-18, `slough_barrow` consumer repo: 39 local vs 25 remote commits, same work, different SHAs).

Two complementary filesystem-native guards enforce this. Both were added by PLAN-AF1 (2026-06-20):

1. **Repo lock (`orchestrator_lock.py`):** A gitignored lockfile `Workbench/.orchestrator.lock` is acquired at Step 0 of every dispatch walk and released (finally-style) on every return path including exception/halt branches. If the lock is held by a concurrently-active walk, the second invocation surfaces a refusal and returns without touching state, committing, or dispatching. Lock TTL is 3600 seconds (`LOCK_TTL_SECONDS` constant in `orchestrator_lock.py`) - generous enough for legitimate long-running audit walks; short enough that a crashed session self-clears. (Per D2/D3/D4 - PLAN-AF1.)

2. **Pre-push divergence guard (`push_guard.py`):** Immediately before any `git push` when `push_policy == "auto"`, `check_push_safe()` runs `git fetch` then checks whether the local branch is behind origin. If behind > 0, the push is refused and the orchestrator halts with a kanban exception, surfacing the behind/ahead counts and manual reconciliation instructions. The guard is fail-open: if `git fetch` fails (offline, no remote, auth), `check_push_safe()` returns `safe=True` because `git push` itself rejects non-fast-forward pushes without `--force`. (Per D1 - PLAN-AF1.)

**Why the lock is not a session-identity token:** the orchestrator is synchronous - each dispatch walk acquires on entry and releases on return. A lock that answers "is a walk in progress right now?" is sufficient. A second invocation that arrives after the first releases acquires cleanly, re-reads fresh disk state via Step 2, and finds the work already advanced - the correct idempotent no-op.

**Scope boundary:** this invariant covers the orchestrator's dispatch walks only. Subagent tool-set restrictions (preventing a rogue subagent from acting as a competing orchestrator) are BUG 3, tracked separately. The two guards together close the BUG 4 failure mode without assuming anything about subagent tool scope.

**Verified by:** `scripts/ci/check-invariants.py` does not currently assert this invariant with a mechanical check (the guard is logic-in-Python, not a structural file property that an AST scan can assert). The CI backstop is the two pytest suites (`test_push_guard.py`, `test_orchestrator_lock.py`) added to `run-all.sh` as `_shared: push_guard` and `_shared: orchestrator_lock`.

### Invariant: Orchestrator-Owned State Is Never Trusted From Subagents

**The orchestrator never trusts orchestrator-owned PLAN frontmatter fields as written by a dispatched subagent.** After dispatching `plan-writer`, `sufficiency-auditor`, or `plan-safety-auditor`, the orchestrator restores the owned fields to the values it snapshotted before dispatch, then mutates them itself. This closes the BUG 3 class of forgery - a subagent writing plausible-looking orchestration state with no real work behind it. Closed by PLAN-AF3 (2026-06-20).

**Owned-field set.** The four fields the orchestrator owns directly (per plan-pipeline SKILL.md: "The orchestrator may write PLAN *frontmatter* fields (`pipeline_phase`, `audit_state`, `last_executor_outcome`, `verification_state`) directly because those are orchestration-owned"):

```
pipeline_phase, audit_state, last_executor_outcome, verification_state
```

`status` is intentionally excluded from the guard: it is legitimately executor-written and outside the forgery surface. Guarding it would risk reverting a legitimate executor-set status. The D1a carve-out ("Orchestrator-Directed-Writes") further preserves orchestrator-directed owned-field writes - specifically, when the orchestrator passes `target_phase` to `plan-writer` (which legitimately writes the new `pipeline_phase` atomically with the body), the orchestrator sets that field in the snapshot to its intended post-dispatch value before calling `restore_owned_fields`, so the restore preserves the directed change while wiping any other undirected owned-field write.

**Snapshot/restore-before-trust model.** Before dispatching `plan-writer`, `sufficiency-auditor`, or `plan-safety-auditor`, the orchestrator snapshots owned fields via `snapshot_owned_fields(plan_path)` (helper at `.claude/skills/_shared/orchestrator_state_guard.py`). After the subagent returns - regardless of its reported outcome - the orchestrator calls `restore_owned_fields(plan_path, snapshot)` BEFORE reading or acting on any frontmatter state. `audit_state` is derived only via `audit_loop.py`; all other owned fields are mutated directly by the orchestrator only.

**Verify-don't-trust-narrator principle (D4).** The orchestrator independently verifies any subagent-CLAIMED state change against disk/git before acting on it. A subagent's return text is an assertion, not evidence. The prior live instance of this principle is the `section 4F` retire post-condition check (PLAN-AA2): when `plan-retirer` reports success, the orchestrator stats source and destination paths before committing. All subagent dispatches should apply the same verification discipline.

**BUG 3 forgery incident (2026-06-18).** A `plan-writer` dispatched only to revise a PLAN body returned claiming it had also flipped `pipeline_phase: drafted -> checked`, fabricated an `audit_state` with `last_outcome: success`, and written a forged `last_audit_commit` - all with no real audit behind it. The fields it forged are orchestrator-owned, but nothing previously prevented a subagent from writing them and nothing previously guarded the orchestrator against trusting subagent-written state. PLAN-AF3 closes this.

**Observed false-push (2026-06-18).** A `plan-retirer` subagent reported it had "pushed to main" during the same incident. `git log` showed nothing was pushed. Subagents are unreliable narrators of their own side effects; verification against disk/git is the only trustworthy signal.

**D3 rationale - why tool-set denial is NOT the mechanism.** A Claude Code capability check (2026-06-20) confirmed there is no granular per-agent permission rule: only whole-tool `disallowedTools` or a blunt PreToolUse hook. Whole-Bash denial breaks `plan-writer` (it runs `next_id.py` to allocate IDs) and degrades `plan-safety-auditor` (its substrate-fidelity/portability lints are Python scripts invoked via Bash for precise mechanical checks). The blunt PreToolUse hook also blocks the orchestrator's own legitimate auto-push (used by consumers). The enforcement mechanism is orchestrator-ownership + snapshot/restore + independent verification (D1, D4), NOT tool permissions. Cross-reference: PLAN-AF1 closed BUG 4 (forked history from concurrent orchestrators) via the repo lock (`orchestrator_lock.py`) and pre-push divergence guard (`push_guard.py`). Do not attempt to "re-fix" BUG 3 by naively denying Bash to subagents.

**CI backstop.** `test_orchestrator_state_guard.py` in `.claude/skills/_shared/lib/`, registered in `run-all.sh` as `_shared: orchestrator_state_guard`.

### Invariant: No Party Grades Its Own Constraint

**A constraint must not be graded by the party it binds.** Where a runtime party must participate in the grading, it may move the grade only toward more rigour, never less. Loosening is reserved to the human and is recorded before the work starts.

Two implementations satisfy this, in order of preference. Derive the value from disk so no runtime party sets it at all. Failing that, make the judgement one-directional, with the loosening path human-only and written down in advance.

**Why this is named as an Invariant rather than left as commentary.** The harness arrived at this repair three times independently, each time treating it as a local defect, and each repair reads as unrelated to the others at its own site:

- **The audit iteration counter** is derived by `build_brief.py` from the audit JSON files on disk, specifically so a caller cannot reset it. The accompanying rule that audit JSONs must not be deleted or moved to obtain another lap exists because the counter's integrity depends on its inputs.
- **Executor outcome reporting** - the orchestrator re-runs `verify:` and `acceptance:` items in parent context rather than trusting `last_executor_outcome` (parent PLAN decision 25).
- **Retire post-conditions** - the AA2 check (destination non-zero and readable, source absent) is re-run outside the retiring agent, after the agent proved an unreliable narrator of its own success.

The register exists for facts a tidy-up could plausibly remove without realising the consequence, and a fourth instance designed without the stance would be built the same wrong way before anyone noticed the pattern.

**Relationship to [Orchestrator-Owned State Is Never Trusted From Subagents](#invariant-orchestrator-owned-state-is-never-trusted-from-subagents).** That invariant is this one applied to a single direction: a subagent reporting orchestration state upward. This entry generalises it. The party need not be a subagent, and the thing being graded need not be state - a bound, a scope boundary, or a risk grade all qualify.

**A repaired instance, and why being right each time was not evidence.** PLAN-AI7 exhausted the pre-human repair bound of 2 with findings still returning `mechanically_forced`, and the orchestrator applied repair rounds 3, 4 and 5 in parent context under the surgical/polish-edit carve-out. `audit-ceiling-diagnostician` judged it a bypass: the carve-out's text permits each individual edit, but `phase-state-machine.md` names exactly one successor when the pre-human bound is exhausted, and it is the human-surface row. Five machine repair rounds ran where two are allowed, and the whole sufficiency budget was spent without a blocker reaching the human. Every individual judgement in the sequence was correct and the parent-context repairs were better than the bounded path would have produced. That is what made the pattern dangerous rather than reassuring at the time - the next bypass would have looked identical from the inside and need not work. The carve-out was closed against this invariant in `plan-pipeline/SKILL.md` on 2026-07-31. The full finding is in the `## Kanban halt` section of `Retired/PLAN-AI7_name-the-paths-every-pipeline-commit-stages.md`.

At the time, the bound was a frontmatter counter the orchestrator incremented about itself - the party the bound restrained could move it, which is exactly the crossing this invariant exists to prevent. PLAN-AJ0 closed that gap: the bound is no longer stored in frontmatter at all. `pre_human_bound_reached` in `.claude/skills/plan-pipeline/lib/patch_gate.py` derives it by reading the audit JSONs the auditor writes into `Workbench/.audit/`, counting the trailing run of rounds in which the auditor supplied at least one patch-carrying `mechanically_forced` finding. This moves the instance from the invariant's second-preference implementation - a one-directional judgement - to its first: a value derived from disk that no runtime party sets.

**Design consequence for anything new.** A risk-grading classifier - grading each PLAN by the consequence of being wrong, so pipeline machinery is proportional to what is at stake - is the obvious fourth instance. Built against this invariant it derives the grade from declared scope, lets any party raise it, and lets only the human lower it, only before pipeline entry.

**Not mechanically asserted.** Unlike the invariants `check-invariants.py` covers, this one is a design stance consulted when a new grading surface is designed. There is no single site to assert. Its three existing implementations carry their own tests; the stance is what stops the fourth from being written without one.

## Doc Landscape

plan_foundry uses four maintainer-or-agent-facing docs at the repo root, each owning a distinct scope. The boundary discipline is strict: when content fits more than one doc, the audience determines the home, not the convenience of the author.

| Doc | Audience | Owns | Maintenance trigger |
|---|---|---|---|
| `CLAUDE.md` | Agent always-loaded | Project overview, working style, agent-execution-rules, skills inventory pointer, pre-prod/prod separation pointer, CI pointer, caveats. | PR touching `.claude/skills/`, `.claude/commands/`, or CLAUDE.md itself (existing `maintain-project-docs` auto-fire) |
| `ROADMAP.md` | Maintainer forward-planning | Mission, open questions, threads, execution sequencing. | PLAN closure with `closes_thread:` non-empty; monthly RECUR backstop |
| `ARCHITECTURE.md` | Maintainer onboarding + reference | Design philosophy, strategic principles, invariants register, doc landscape, bootstrap pointer. | PR touching `.claude/skills/_shared/`, any agent file, or any SKILL.md naming an invariant |
| `README.md` | End-user / target-repo installer | Install (clone + `init-plan-foundry`), skills overview, mobile/web caveat. | Manual PR review (low-frequency surface) |

## Bootstrap

plan_foundry installs by network-cloning the public bundle into a transient directory inside the target. There is no machine-global state.

1. **Install into a fresh repo.** In a Claude Code session on the target, paste: *"Bootstrap plan_foundry from https://github.com/kccastillo/plan_foundry into this repo."* The agent (per [BOOTSTRAP.md](BOOTSTRAP.md)) runs:
   ```
   git clone --depth=1 https://github.com/kccastillo/plan_foundry .plan-foundry-tmp
   python3 .plan-foundry-tmp/.claude/skills/init-plan-foundry/lib/run_install.py
   rm -rf .plan-foundry-tmp
   ```
   `run_install.py` performs the nine-step install procedure: refuses inside the bundle source; copies `.claude/{skills,agents,commands,hooks}` into the target; scaffolds `Workbench/` and `Retired/`; updates `.gitignore` (bundle paths + `.plan-foundry-tmp/` + version pin); inlines `operating-rules.md` into `CLAUDE.md` between sentinel markers; writes `.claude/.plan-foundry-bundle-version`; prints "RESTART Claude Code". Idempotent across four precursor states.
2. **Update an existing install.** `/plan-foundry-sync` (or `/plan-foundry-sync v0.5.0` to pin to a tag) clones into `.plan-foundry-tmp/`, copies bundle-managed paths over, refreshes the operating-rules sentinel block in the root `CLAUDE.md` (preserving all host content), refreshes the version pin, and deletes the tmp. Sync now performs receipt-backed quarantine (PLAN-AH7): a bundle-managed path recorded in the install receipt but no longer shipped upstream is moved to a timestamped quarantine directory, not deleted outright; project additions survive untouched; a quarantine directory is swept only once it is 30 days old.
3. **Check currency.** `/plan-foundry-check-current` runs `git ls-remote https://github.com/kccastillo/plan_foundry HEAD` and compares to the target's pin. Single tier - there is no local bundle clone to lag.
4. **Uninstall.** `/plan-foundry-uninstall` removes the four bundle-managed dirs, the version pin, the bundle `.gitignore` entries, and the CLAUDE.md sentinel block. Leaves `Workbench/`, `Retired/`, and project-local `.claude/` files untouched (operator data, not bundle code). Offline; idempotent.

**What does NOT happen.** Bundle install is not invasive: there is no Claude Code plugin registration, no namespaced skill IDs, no machine-global state. Skills are invoked by bare name - e.g. `Skill("plan-pipeline")` - never with a namespace prefix. Per-project version pinning DOES happen via `.claude/.plan-foundry-bundle-version` - a three-line file recording the bundle SHA / tag / sync timestamp each project last synced to.

**Promotion to prod.** The dev workshop is `plan_foundry_dev`; the consumer-facing prod bundle is `plan_foundry`. Promotion runs via `scripts/promote.sh <tag>` (replaces the deprecated `release.sh`). The script copies an allowlisted subset of the dev tree to a temp dir, inits a fresh git repo, commits, force-with-lease pushes to `kccastillo/plan_foundry`, and tags the release. The allowlist is in `scripts/promote.sh`; the prod-repo coordinates are in `scripts/prod-repo.txt`.
