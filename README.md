# plan_foundry

plan_foundry turns Claude Code planning and execution into a state machine on
disk. Each stage - drafted, audited, executed, verified - is a file in your
repo rather than model context that expires between turns.

plan_foundry is a planning-and-execution **scaffold** for Claude Code. You
write down what you intend to do, and the harness audits that intent with a
second model and helps you correct the plan before any code is written. The
harness then executes the plan under supervision and records what happened, as
version-controlled files in your repo.

## The idea: a scaffold, not a new harness

Two common approaches make a coding agent more reliable. plan_foundry takes a
third position between them.

- **Context engineering** - better prompts, rule files and skill packs. Context
  engineering improves how an agent behaves, but every rule is a *request*: the
  model may comply or may not, and no structure catches the non-compliance.
  Compliance is probabilistic.
- **Harness engineering** - building a new agent runtime, in effect a new
  Claude Code, with its own execution loop, tool layer and control flow.
  Harness engineering buys real determinism at the cost of a large and
  continuing engineering project.

plan_foundry is a **scaffold**. The scaffold extends Claude Code - the harness
you already have - and supplies much of the determinism of a custom runtime
without one being built. State recorded on disk decides what runs next, audit
gates block wrong work before that work becomes code, and verification re-runs
in a trusted context. Each guarantee is mechanical - a phase enum, a shell
assertion, a tool-access boundary - rather than a request the model is trusted
to honour. The scaffold is files and skills, so there is nothing to compile,
nothing to host, and nothing to maintain beyond a `git`-style sync.

Context-engineering-only approaches, custom harnesses and lightweight wrappers
do adjacent things. The mechanical differences matter.

- **(a) Context-engineering-only approaches** (rule files, skill packs, system-prompt frameworks). These improve how a single agent behaves by asking the agent to behave well. The guidance can be excellent, but the gap is structural, because compliance is probabilistic. No audit runs in a separate invocation with no prior turns, no phase gate blocks on file content, and no verification re-executes in a fresh context. plan_foundry's audit passes are separate model invocations rather than the same model reviewing its own output in the same turn. Prompts alone do not reproduce that asymmetry.

- **(b) Custom harnesses and agent runtimes** (Aider, Cursor agent mode, hand-rolled execution loops). These buy real determinism by owning the execution loop, tool layer and control flow. The cost is proportional, because a custom runtime is a continuing engineering project and every new model or capability requires harness-level integration. plan_foundry supplies state-machine determinism and audit gates without a runtime being built: state is recorded in files, transitions are defined by skills, and the harness is Claude Code itself.

- **(c) Lightweight wrappers** (just-a-prompt-library, `/init`-style commands that scaffold a folder but carry no state). These reduce setup friction without tracking state across sessions. When context compresses or a session ends, the wrapper's scaffolding survives on disk, but there is no frontmatter state machine, no phase enum naming where to resume, and no audit record showing what passed and what did not. plan_foundry records state in structured frontmatter committed to git, so re-entry is idempotent: the state is the file rather than the session.

plan_foundry accepts one trade-off. The harness overhead is justified only when
writing the wrong plan is expensive.

## What it actually does

Coding agents produce plausible-looking output quickly. Plausible-looking and
actually right come apart on anything beyond a small, well-specified change,
and that divergence is the problem. You ask for a feature, and the agent picks
an interpretation you did not intend and writes 500 lines before you see the
diff. The agent references a database column that does not exist, because the
model invented the column. You spend two sessions agreeing on an approach, and
afterwards neither you nor the agent can reconstruct what was decided or why.

plan_foundry slows that loop down deliberately. Before any code is written, the
agent records what it is about to do as a **PLAN file**, in enough detail that
a separate pass by a different model can catch the mistakes. You read the PLAN
and push back, and the PLAN is revised until it is right. Only then is the work
executed, against the PLAN rather than against an interpretation the agent
holds in context and loses at session end.

Agents are bad at imposing that discipline on themselves and good at following
the discipline once imposed. plan_foundry is built on that observation.

## Artefacts and skills

plan_foundry uses a small, fixed vocabulary.

| Artefact or skill | What it is |
|---|---|
| **PLAN** | The primary artefact. A Markdown file in `Workbench/` with structured frontmatter capturing intent, steps, verification, and outcome. `type: plan`. Schema reference: [plan-conventions.md](.claude/skills/write-plan/references/plan-conventions.md). |
| **INPUT** | A context artefact - findings, a data drop, survey results, or a strategic note captured mid-flight. `type: input`. Written via `write-input`, then consumed and retired once integrated into a PLAN. Files under the older `ADVICE-*` and `RESEARCH-*` names are the same thing and stay readable. |
| **FOUNDRYREQ** | A bug report, feature request or model-fit finding raised from a consumer repo against plan_foundry itself. `kind: bug \| feature \| model-fit`. Written via `raise-foundry-request` so a consumer never hand-edits a bundle file. |
| **HANDOFF** | Session-boundary brief: what was done, what is next, what blockers exist. `type: handoff`. Written at session end by `handoff-next-session`, and read at the next session start by `rehydrate-handoff`. |
| **TESTREPORT** | Portable test output emitted by `test-foundry`. **Not a `type:` frontmatter artefact** - the TESTREPORT is a consumer-visible emission from the test runner, stored outside the Workbench artefact family. |
| **`ideate`** | Skill (verb). Structured problem-shaping before a PLAN is written - an eight-phase cadence running Clarify -> Survey -> Converge -> ... -> Consolidate, behind a proportionality gate. |
| **`write-input`** | Skill (verb). Records an INPUT file and auto-clears any PLAN blocked waiting on that input. |
| **`plan-pipeline`** | Skill (verb). The orchestrator. Reads PLAN frontmatter, fires the correct sub-skill for each phase, and advances the state machine. |
| **`execute-plan`** | Skill (verb). Runs a checked PLAN end-to-end, records the outcome, and writes `last_executor_outcome` to frontmatter. |
| **`retire`** | Skill (verb). Moves completed PLANs, integrated inputs, and superseded research to `Retired/`, then verifies the post-condition. |

## How it works

These mechanical guarantees are structurally enforced rather than followed by
convention:

1. **Phase enum state machine.** A PLAN's `pipeline_phase` field is an enum (`drafting -> drafted -> checked -> executing -> outcome-verifying -> complete`). The `plan-pipeline` orchestrator reads that enum and routes by value rather than inferring the phase from context. Skipping a phase requires editing frontmatter, which is itself a tracked git change. Enforcement: [phase-state-machine.md](.claude/skills/plan-pipeline/references/phase-state-machine.md).
2. **Audit gates on file content.** Before a PLAN advances from `drafted` to `checked`, the PLAN must pass two independent audits: `audit-sufficiency` (conceptual completeness, acceptance criteria, risks) and `audit-haiku-safe` (substrate fidelity, destructive-action discipline, executor-tier safety). Each audit reads the PLAN file fresh and returns structured findings, and a finding at `error` severity blocks the advance. Continuing past a blocker requires a recorded override. Enforcement: `audit-sufficiency` and `audit-haiku-safe` skills.
3. **Verification in a fresh context.** After execution, the orchestrator re-runs `verify:` and `acceptance:` shell assertions in the parent context, which is neither the executor's context nor the same turn that did the work. That separation eliminates the "executor checks its own work" failure mode. Enforcement: the orchestrator's outcome-verifying phase, per plan-pipeline SKILL.md decision 25.
4. **Bundle propagation by copy, not symlink.** Skills, agents, commands and hooks are real directories copied into each consumer project via `init-plan-foundry`. There is no machine-global state, no symlink mirror, and no plugin namespace. A consumer can fork, patch, or extend the bundle without touching upstream. Enforcement: [Portable Bundle invariant](ARCHITECTURE.md#invariant-portable-bundle) + `init-plan-foundry` install procedure.

For consumer projects, when you observe plan_foundry behaviour worth reporting,
the boundary rule applies: do not prosecute upstream issues inside your
project's Workbench. Capture observations at observation-time as INPUT files
(via `write-input`) inside your project's `Workbench/`, then transfer those
typed artefacts to the plan_foundry repo at session end. Because the captures
arrive in plan_foundry already formalised, no staging dock and no later triage
step are needed. Full procedure: [init-plan-foundry/operating-rules.md section plan_foundry vs this-project boundary](.claude/skills/init-plan-foundry/operating-rules.md).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full mechanism walkthrough -
state-machine detail, audit-gate anatomy, verification model, and bundle
propagation trade-offs.

## What it's good at

- **Catching wrong plans before they become wrong code.** A PLAN gets two audit
  passes, conceptual sufficiency then mechanical safety, before any edit is
  made. Findings are blockers, and revision is the supported path. A PLAN that
  fails an audit is the scaffold working as designed.
- **Pinning model tiers to job shape.** Opus for design judgement and audit,
  Sonnet for execution and research, Haiku for cheap structured work. Cheap
  models get bounded jobs they can finish, and expensive models are reserved
  for work that needs the extra capability.
- **Surviving context loss.** PLAN files record structured frontmatter on disk,
  and each state-machine transition is written there. If a session compresses,
  crashes, or hands off to tomorrow, the next session reads the frontmatter and
  resumes without a "where were we?" reconstruction.
- **Refusing to silently hallucinate.** PLANs declare the `substrate_files`
  (schemas, API docs, modules) they touch. The plan-writer must `Read` those
  files before authoring, and `audit-haiku-safe` then greps the Steps for
  references absent from that substrate and blocks the PLAN on each one found.
- **Making "done" mean something.** Each PLAN carries a `verification_state`
  enum plus executable acceptance checks. The orchestrator re-runs the checks
  itself, in a trusted context, after execution. Boxes are not ticked
  optimistically.
- **Keeping the design landscape readable.** The `maintain-project-docs` skill
  audits `CLAUDE.md` and `ARCHITECTURE.md` for context-rot. Recurring lessons
  are codified into permanent rules rather than kept as episodic memory.

## When to reach for it

Reach for plan_foundry on work where building the wrong thing is expensive -
refactors, architectural decisions, new features, anything novel or
shape-defining - and on work that spans many sessions and needs durable state
you can trust.

plan_foundry is deliberately not for raw throughput or one-shot edits. "Rename
this function" does not need a PLAN, because the harness overhead is justified
only when a plan is worth writing. plan_foundry surfaces uncertainty rather
than hiding it, by design.

## How the pieces fit

The bundle is a collection of skills (Markdown prompts pinned to model tiers),
agents (delegated workers with bounded tool access), and slash commands. Each
targets a specific failure mode.

### The PLAN lifecycle: `plan-pipeline` + `write-plan` + `execute-plan`

Every piece of intended work becomes a PLAN file in `Workbench/` with
structured frontmatter, and moves through the fixed lifecycle enum given under
"How it works" above. The `plan-pipeline` skill orchestrates that movement:
`plan-pipeline` reads the frontmatter, decides which phase fires next, and
dispatches the right sub-skill. The state machine is recorded on disk rather
than held in model context, so re-entry is idempotent. `write-plan` authors a
PLAN and enforces the substrate-verification preflight, and `execute-plan` runs
an already-checked PLAN end-to-end and records the outcome.

### The audit gates: `audit-sufficiency` + `audit-haiku-safe`

Humans and agents both miss things, and they miss *different* things on
different passes, so "looks fine to me" is a poor quality gate. A PLAN
therefore gets two narrowly scoped audits, both Opus-pinned.
`audit-sufficiency` asks the conceptual question: does this PLAN have what it
needs to succeed - clear acceptance criteria, identified risks, real
verification? `audit-haiku-safe` performs the mechanical checks: substrate
fidelity, destructive-action discipline, executor-tier safety. Findings are
blockers rather than advisories.

### The Workbench: `/status`

A folder of PLAN files is read directly, as a directory listing plus
frontmatter reads. `/status` reads live `.heartbeat/` files together with PLAN
state to show what is running, what is stalled, and what needs attention.

### Carrying context across sessions: `handoff-next-session` + `rehydrate-handoff`

Long-running work spans many sessions. `handoff-next-session` writes a
session-end brief, and `rehydrate-handoff` reads that brief at the next session
start.

### Inputs: `write-input`

Mid-PLAN you need to research something, or you receive strategic guidance.
`write-input` records inputs - findings, data drops and strategic notes - as
their own files in `Workbench/`. A PLAN blocked on a missing input clears
automatically once that input lands, and an input is marked integrated and
retired when a PLAN listing that input retires.

### Shaping problems before they become PLANs: `ideate`

Sometimes the problem is not ready to be planned - you have a vague intention
and need to think it through first. `ideate` runs a structured ideation cadence
(Clarify -> Survey -> Converge -> ... -> Consolidate) that narrows what the problem
actually is, surveys options, and converges on a plan-ready direction.

Invoking `ideate` does not commit you to the whole cadence. A proportionality
gate runs first and asks how much of the machinery this particular problem
needs. The gate assesses whether the requirement is agreed, whether the
mechanism is forced, and whether the change is reversible and how wide it
reaches, then offers these rungs with a recommendation:

| Rung | What runs |
|---|---|
| `just do it` | The work. No PLAN file. |
| `plan it` | PLAN written, executed, verified, retired. No ideate phases, no audit loop. |
| `audit it` | Plan it, plus the sufficiency and plan-safety auditors. |
| `full arc` | The whole cadence, both risk gates, then the audit loop and the pipeline. |

No phase runs until you pick. The full arc costs most of a day, which is the right
price for a finicky, wide or irreversible change and the wrong price for most work.
The agent may raise a rung on its own judgement and must never drop one silently.
Contract: `.claude/skills/_shared/proportionality-gate.md`.

### Cleanup and doc hygiene: `retire` + `maintain-project-docs`

`retire` moves completed PLANs, integrated inputs, and superseded research into a
`Retired/` folder so the active surface stays legible. `maintain-project-docs`
audits the always-loaded docs for context-rot, proposing codification when a rule
recurs and removal when content is no longer load-bearing. The scope of
`maintain-project-docs` is CLAUDE.md, ARCHITECTURE.md, CONTEXT_CONSTITUTION.md and
the durable `_shared/*.md` helpers.

### Building skills: `skill-standard.md` + `write-skill` + `audit-skills`

`skill-standard.md`, `write-skill` and `audit-skills` have strictly separated jobs,
and each applies to your own skills as much as to this bundle's.

`.claude/skills/_shared/skill-standard.md` is the definition and has no behaviour.
The standard states what a SKILL.md must state, which scaffolding is worth keeping
and which works around a weakness the model no longer has, what the frontmatter
contract is, and what a description has to do to fire reliably.

`write-skill` scaffolds exactly one skill against the standard and then proves the
new skill triggers, measuring its description against a set of prompts that must
fire the skill and a set of near misses that must not.

`audit-skills` reports your whole corpus against the standard: conformance,
description health, overlap, retirement and delisting candidates, and what the
installed set costs in context on every turn. `audit-skills` reports and never
patches. Where a skill belongs to a bundle rather than to you, `audit-skills`
raises a request instead of proposing an edit that the next sync would destroy.

### Self-testing: `test-foundry` + `/test-foundry`

A planning harness that does not test itself will rot silently. `test-foundry`
runs a two-tier harness - a Python tier for deterministic structural checks and
an LLM tier for scenario walks - and emits a portable TESTREPORT.

### Bundle hygiene: `init-plan-foundry` + `plan-foundry-sync` + `plan-foundry-uninstall`

Installing into a new repo takes one paste-prompt, and updating and removing
each take one command. All three work inside Claude Code sessions whose
filesystem write surface is the target repo only (mobile, web, sandboxed
desktop), because the bundle is fetched on demand from a public URL into a
transient `<target>/.plan-foundry-tmp/` rather than any machine-global location.

## Install

Open a Claude Code session inside the target repo and paste:

> Bootstrap plan_foundry from https://github.com/kccastillo/plan_foundry into this repo.

See [BOOTSTRAP.md](BOOTSTRAP.md) for the canonical clone-copy-delete procedure
(the agent reads that file on first contact). The install copies bundle content
into `.claude/{skills,agents,commands,hooks}`, scaffolds `Workbench/` and
`Retired/`, updates `.gitignore`, inlines operating rules into `CLAUDE.md`, and
records the bundle commit SHA at `.claude/.plan-foundry-bundle-version` plus an
install receipt at `.claude/.bundle-receipts/plan_foundry.files` - namespaced by
bundle identity so a second bundle installed alongside plan_foundry cannot
overwrite this one's record of what it wrote. The install is idempotent, so
re-pasting is safe.

After install, **restart Claude Code** so the freshly-copied skills register
with the harness.

## Update

```
/plan-foundry-sync
```

Sync clones the public repo into `<target>/.plan-foundry-tmp/`, overwrites
bundle-managed files with the latest content, refreshes the version pin, and
deletes the tmp clone. Sync quarantines stale bundle files against the install
receipt rather than deleting them outright: a file recorded in the receipt but
no longer shipped upstream is moved to a timestamped quarantine directory, and
swept only after 30 days. Project additions survive untouched. Tag pinning:
`/plan-foundry-sync v0.5.0` fetches a specific bundle version.

Check whether your project is at the latest bundle:

```
/plan-foundry-check-current
```

`/plan-foundry-check-current` compares your `.plan-foundry-bundle-version` to
the remote HEAD via `git ls-remote`.

Per-release migration and cleanup notes - changes that leave something behind in
your project, or that change a habit - are recorded in [CHANGELOG.md](CHANGELOG.md).
Read the CHANGELOG before your first sync onto a new version.

## Uninstall

```
/plan-foundry-uninstall
```

Uninstall removes the bundle-managed directories (`skills`, `agents`,
`commands`, `hooks`), the version pin, the bundle `.gitignore` entries, and the
CLAUDE.md sentinel block. `Workbench/`, `Retired/` and project-local `.claude/`
files (`settings.local.json`, `plan-foundry.config`) are left untouched,
because those are operator data rather than bundle code. Uninstall runs offline
and is idempotent.

## Skills inventory

Each skill is defined at `.claude/skills/<name>/SKILL.md`. Invoke a skill via
natural language ("write a plan", "let's ideate") or `Skill("<name>")`.

**Core lifecycle:** `plan-pipeline`, `write-plan`, `audit-sufficiency`, `audit-haiku-safe`, `execute-plan`, `retire`, `autonomous-loop`. `autonomous-loop` drives a PLAN from `drafted` to `complete` without human turns, and it halts at its own precondition unless the session exposes the `create_trigger` Routines tool, which desktop Claude Code does not.

**Workbench state:** slash command `/status`.

**Cross-session continuity:** `handoff-next-session`, `rehydrate-handoff`.

**Inputs:** `write-input`, `raise-foundry-request` - the latter writes a FOUNDRYREQ, which enters the same input lifecycle and carries a bug, feature or model-fit finding raised against plan_foundry itself.

**Problem-shaping:** `ideate`.

**Maintenance:** `maintain-project-docs`, `audit-skills`, `test-foundry`.

**Skill authoring:** `write-skill`, and the standard at
`.claude/skills/_shared/skill-standard.md`.

**Bundle:** `init-plan-foundry`, `plan-foundry-sync`, `plan-foundry-check-current`, `plan-foundry-uninstall`.

## Configuration

The bundle reads no configuration beyond `Workbench/` defaults. The bundle
source location is not configurable, because `init-plan-foundry` clones the
bundle into a transient `<target>/.plan-foundry-tmp/` and deletes that
directory once the copy completes.

## Repository structure (consumer view)

After `init-plan-foundry`, your target repo gains:

```
.claude/
  skills/agents/commands/hooks/   (copied from bundle - gitignored, regenerable via /plan-foundry-sync)
  .plan-foundry-bundle-version    (version pin - gitignored)
  settings.local.json             (project-local - tracked if you commit it)
  plan-foundry.config             (project-local - tracked if you commit it)
Workbench/                        (PLAN files)
Retired/                          (completed artefacts, tracked)
CLAUDE.md                         (operating rules between sentinel markers)
```

## Further reading

- [CLAUDE.md](CLAUDE.md) - operating rules and agent-execution discipline.
- [ARCHITECTURE.md](ARCHITECTURE.md) - design philosophy, the scaffold-vs-harness-helper positioning, strategic principles, invariants register.
