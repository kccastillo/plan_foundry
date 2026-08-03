# plan_foundry

A planning-and-execution **scaffold** for Claude Code. You write down what you
intend to do; the harness audits it with a second model, helps you fix it before
any code is written, then executes it under supervision and records what
happened - all as files in your repo, all version-controlled.

## The idea: a scaffold, not a new harness

There are two common ways to make a coding agent more reliable. plan_foundry is
neither of them - it is the layer in between, and that is the whole pitch.

- **Context engineering** - better prompts, rule files, skill packs. This
  improves how an agent behaves, but every rule is a *request*: the model may
  comply or may not, and nothing structurally catches it when it doesn't.
  Compliance is probabilistic.
- **Harness engineering** - building a whole new agent runtime, in effect a new
  Claude Code, with its own execution loop, tool layer, and control flow. This
  buys real determinism, but it is a large and ongoing engineering project.

plan_foundry is a **scaffold**: it sits on top of Claude Code - the harness you
already have - and gives you much of the determinism of a custom runtime without
building one. State on disk decides what runs next. Audit gates block bad work
before it becomes bad code. Verification re-runs in a trusted context. The
guarantees are mechanical - a phase enum, a shell assertion, a tool-access
boundary - not a request the model is trusted to honour. And it is all just
files and skills: nothing to compile, nothing to host, nothing to maintain
beyond a `git`-style sync.

You don't have to choose between "hope the prompt holds" and "go build
infrastructure." The scaffold is the middle path.

## What it actually does

Coding agents are very good at producing plausible-looking output very quickly.
That is a problem when "plausible-looking" and "actually right" come apart -
which they do, a lot, on anything beyond a small well-specified change. You ask
for a feature; the agent picks an interpretation you didn't intend and writes
500 lines before you see the diff. Or it references a database column that does
not exist because the model quietly invented one. Or you spend two sessions
agreeing on an approach and nobody - you or the agent - can later reconstruct
what was decided or why.

plan_foundry slows that loop down on purpose. Before any code is written, the
agent records what it is about to do as a **PLAN file** - in enough detail that
a separate pass, by a different model, can catch the mistakes. You read it. You
push back. The plan is revised until it is actually right. Only then is the work
executed - against the plan, not against an interpretation that lives in the
agent's head and evaporates at session end.

Imposing that discipline is the thing agents are bad at doing to themselves and
good at following once it is imposed. That is the bet.

## Artefacts and skills

plan_foundry uses a small, fixed vocabulary. Knowing these terms makes the rest of the docs readable without consulting the source.

| Artefact or skill | What it is |
|---|---|
| **PLAN** | The primary artefact. A Markdown file in `Workbench/` with structured frontmatter capturing intent, steps, verification, and outcome. `type: plan`. Schema reference: [plan-conventions.md](.claude/skills/write-plan/references/plan-conventions.md). |
| **ADVICE** | A strategic note or recommendation captured mid-flight. `type: advice`. Written via `write-input`; consumed and retired once integrated into a PLAN. |
| **RESEARCH** | A data drop - findings, survey results, or reference material. `type: research`. Same write/integrate/retire lifecycle as ADVICE. |
| **FOUNDRYREQ** | A bug report, feature request or model-fit finding raised from a consumer repo against plan_foundry itself. `kind: bug \| feature \| model-fit`. Written via `raise-foundry-request` so a consumer never hand-edits a bundle file. |
| **HANDOFF** | Session-boundary brief: what was done, what is next, what blockers exist. `type: handoff`. Written at session end by `handoff-next-session`; consumed at the next session start by `rehydrate-handoff`. |
| **TESTREPORT** | Portable test output emitted by `test-foundry`. **Not a `type:` frontmatter artefact** - it is a consumer-visible emission from the test runner, stored outside the Workbench artefact family. |
| **`ideate`** | Skill (verb). Structured problem-shaping before a PLAN is written - Clarify -> Survey -> Converge -> Consolidate. |
| **`write-input`** | Skill (verb). Records an ADVICE or RESEARCH file and auto-clears any PLAN blocked waiting on it. |
| **`plan-pipeline`** | Skill (verb). Orchestrator. Reads PLAN frontmatter, fires the correct sub-skill for each phase, and advances the state machine. |
| **`execute-plan`** | Skill (verb). Runs a checked PLAN end-to-end, records the outcome, and writes `last_executor_outcome` to frontmatter. |
| **`retire`** | Skill (verb). Moves completed PLANs, integrated inputs, and superseded research to `Retired/`; verifies the post-condition. |

## How it works

Four mechanical guarantees underpin the scaffold - not conventions the model is trusted to follow, but structural enforcements:

1. **Phase enum state machine.** A PLAN's `pipeline_phase` field is an enum (`drafting -> drafted -> checked -> executing -> outcome-verifying -> complete`). The `plan-pipeline` orchestrator reads that enum and routes by value - it does not infer phase from context. Skipping a phase requires editing frontmatter, which is itself a tracked git change. Enforcement: [phase-state-machine.md](.claude/skills/plan-pipeline/references/phase-state-machine.md).
2. **Audit gates on file content.** Before a PLAN advances from `drafted` to `checked`, it must pass two independent audits - `audit-sufficiency` (conceptual completeness, acceptance criteria, risks) and `audit-haiku-safe` (substrate fidelity, destructive-action discipline, executor-tier safety). Each audit reads the PLAN file fresh and returns structured findings; a finding at `error` severity is a blocker. There is no "override and continue" path without a recorded override. Enforcement: `audit-sufficiency` and `audit-haiku-safe` skills.
3. **Verification in a fresh context.** After execution, the orchestrator re-runs `verify:` and `acceptance:` shell assertions in the parent context - not the executor's context and not the same turn that did the work. This eliminates the "executor checks its own work" failure mode. Enforcement: execute-plan SKILL.md decision 25.
4. **Bundle propagation by copy, not symlink.** Skills, agents, and commands are real directories copied into each consumer project via `init-plan-foundry`. There is no machine-global state, no symlink mirror, and no plugin namespace. A consumer can fork, patch, or extend the bundle without touching upstream. Enforcement: [Portable Bundle invariant](ARCHITECTURE.md#invariant-portable-bundle) + `init-plan-foundry` install procedure.

For consumer projects, when you observe plan_foundry behaviour worth reporting, the boundary rule applies: do not prosecute upstream issues inside your project's Workbench. Capture observations at observation-time as properly-typed RESEARCH or ADVICE files (via `write-input`) inside your project's `Workbench/`, then transfer those typed artefacts to the plan_foundry repo at session end. The captures arrive in plan_foundry already formalised - no staging dock, no later triage step. Full procedure: [init-plan-foundry/operating-rules.md section plan_foundry vs this-project boundary](.claude/skills/init-plan-foundry/operating-rules.md).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full mechanism walkthrough - state-machine detail, audit-gate anatomy, verification model, and bundle propagation trade-offs.

## What it's good at

- **Catching wrong plans before they become wrong code.** A PLAN gets two audit
  passes - conceptual sufficiency, then mechanical safety - before any edit is
  made. Findings are blockers; revision is the supported path. A PLAN that fails
  an audit is not the system regressing - it is the system working.
- **Pinning model tiers to job shape.** Opus for design judgement, Sonnet for
  mechanical review and execution, Haiku for cheap structured work. Cheap models
  get bounded jobs they can finish; expensive models are reserved for what needs
  them.
- **Surviving context loss.** PLAN files live on disk with structured
  frontmatter; state-machine transitions are recorded. If a session compresses,
  crashes, or hands off to tomorrow, the next one reads frontmatter and resumes -
  no "where were we?" reconstruction.
- **Refusing to silently hallucinate.** PLANs declare the `substrate_files`
  (schemas, API docs, modules) they touch. The plan-writer must `Read` them
  before authoring; the audit then greps the Steps for references that do not
  exist in that substrate and blocks on what it finds.
- **Making "done" mean something.** Each PLAN carries a `verification_state`
  enum plus executable acceptance checks. The orchestrator re-runs the checks
  itself, in a trusted context, after execution. Boxes are not ticked
  optimistically.
- **Keeping the design landscape readable.** Maintenance skills audit `CLAUDE.md`
  and `ARCHITECTURE.md` for context-rot. Lessons are codified into permanent
  rules when they recur, not hoarded as episodic memory.

## When to reach for it

Reach for plan_foundry on work where building the wrong thing is expensive -
refactors, architectural decisions, new features, anything novel or
shape-defining - and on work that spans many sessions and needs durable state
you can trust.

It is deliberately not for raw throughput, and not for one-shot edits: "rename
this function" does not need a PLAN, and the harness overhead is only justified
when a plan is worth writing in the first place. plan_foundry surfaces
uncertainty rather than hiding it - that is the point, not a side effect.

## How the pieces fit

The bundle is a collection of skills (Markdown prompts pinned to model tiers),
agents (delegated workers with bounded tool access), and slash commands. Each
one targets a specific failure mode.

### The PLAN lifecycle: `plan-pipeline` + `write-plan` + `execute-plan`

Every piece of intended work becomes a PLAN file in `Workbench/` with structured
frontmatter, and moves through a fixed lifecycle:
`drafting -> drafted -> checked -> executing -> outcome-verifying -> complete`. The
`plan-pipeline` skill is the orchestrator - it reads frontmatter, decides which
phase fires next, and dispatches the right sub-skill. The state machine lives on
disk, not in the model's head, so re-entry is idempotent. `write-plan` authors a
PLAN and enforces the substrate-verification preflight; `execute-plan` runs an
already-checked PLAN end-to-end and records the outcome.

### The audit gates: `audit-sufficiency` + `audit-haiku-safe`

"Looks fine to me" is a poor quality gate - humans and agents both miss things,
and they miss *different* things on different passes. So a PLAN gets two audits,
each scoped narrowly. `audit-sufficiency` runs on Opus and asks the conceptual
question: does this PLAN have what it needs to succeed - clear acceptance
criteria, identified risks, real verification? `audit-haiku-safe` runs on Sonnet
and does the mechanical checks: substrate fidelity, destructive-action
discipline, executor-tier safety. Findings are blockers, not advisories.

### The Workbench: `/status`

A folder of PLAN files is just a folder read directly - a directory listing
plus frontmatter reads. `/status` reads live `.heartbeat/` files plus PLAN
state to show what is running, what is stalled, and what needs attention.

### Carrying context across sessions: `handoff-next-session` + `rehydrate-handoff`

Long-running work spans many sessions. `handoff-next-session` writes a
session-end brief; `rehydrate-handoff` reads it at the next session start.

### Research and advice: `write-input` + `rehydrate-input`

Mid-PLAN you often need to research something or you receive strategic guidance.
`write-input` records RESEARCH (data drops) or ADVICE (strategic notes) as their
own files in `Workbench/`; PLANs blocked on a missing input auto-clear when it
lands. `rehydrate-input` marks an input integrated once consumed, so it can be
retired cleanly later.

### Discovering and reusing prior work: the reusable-asset registry

A long-running planning project accumulates helpers, references, and reusable
fragments. Without a discovery mechanism, those assets either get rediscovered
from scratch every session - wasted effort - or rot quietly until nobody
remembers they exist. plan_foundry's asset registry is the mechanism that keeps
that landscape navigable, modelled loosely on dendritic memory formation:
sparse, tag-indexed, and surfaced at the moments when a relevant asset would
actually be useful.

Assets live in two surfaces: `references/` (markdown reference material) and
`.claude/skills/_shared/` (helper scripts and snippets shared across skills).
Each carries frontmatter declaring `asset_id`, `kind`, `topic_tags`, and
`last_consulted`. A pure-projection primitive,
`.claude/skills/_shared/list_reusable_assets.py`, walks both surfaces and emits
a registry (`references/.registry.json`) plus a human-readable
`references/INDEX.md`. The same module exposes `query_by_tags` and
`query_by_seed` - pure functions that return ranked pointers, no side effects.

The registry is wired into three workflow moments:

- **At ideate's Clarify phase**, the skill seeds a tag-overlap query against
  the PLAN's working topic and surfaces matching assets inline before the
  human has to remember they exist.
- **At consumption time**, `rehydrate-input` runs in asset mode: it stamps
  `last_consulted` with today's date, appends the consuming PLAN to
  `consulted_by` (FIFO-capped at 20), and writes a per-asset memory pointer
  to Claude's auto-memory directory so future sessions recall what has been
  read.
- **Continuously in CI**, `audit-foundry` emits two finding categories
  against the registry: `reference-freshness` (info for never-consulted
  assets, warn when `last_consulted` is >=6 months old or malformed) and
  `tag-hygiene` (warn on any `topic_tags` value that isn't strict
  kebab-case). Both are non-blocking - slow rot is a visibility signal, not
  a "broken main" signal. A long-lived `RECUR-monthly-asset-freshness-eyeball`
  PLAN cycles the human through the findings monthly so warns don't pile up
  invisibly.

The net effect: prior work is discoverable when it's relevant, consumption is
durably recorded against the asset itself, and rot is surfaced before assets
become silently load-bearing.

### Shaping problems before they become PLANs: `ideate`

Sometimes the problem is not ready to be planned - you have a vague intention
and need to think it through first. `ideate` runs a structured ideation cadence
(Clarify -> Survey -> Converge -> ... -> Consolidate) that narrows what the problem
actually is, surveys options, and converges on a plan-ready direction.

### Cleanup and doc hygiene: `retire` + `maintain-claude-md`

`retire` moves completed PLANs, integrated inputs, and superseded research into a
`Retired/` folder so the active surface stays legible. `maintain-claude-md`
audits the always-loaded docs for context-rot - proposing codification when a
recurring rule earns it, and removal when content is no longer load-bearing.

### Self-testing: `test-foundry` + `/test-foundry`

A planning harness that does not test itself will rot silently. `test-foundry`
runs a two-tier harness - a Python tier for deterministic structural checks and
an LLM tier for scenario walks - and emits a portable TESTREPORT.

### Bundle hygiene: `init-plan-foundry` + `plan-foundry-sync` + `plan-foundry-uninstall`

Installing into a new repo is one paste-prompt; updating is one command;
removing is one command. All three work inside Claude Code sessions whose
filesystem write surface is the target repo only (mobile, web, sandboxed
desktop): the bundle is fetched on demand from a public URL into a transient
`<target>/.plan-foundry-tmp/` rather than any machine-global location.

## Where this fits in the agent-harness landscape (2026)

The May-2026 field has converged on **"harness engineering"** as the term for the entire scaffold-around-a-model layer - see arxiv [2604.25850](https://arxiv.org/abs/2604.25850), OpenAI's "Harness engineering" writeup, and the [`awesome-harness-engineering`](https://github.com/ai-boost/awesome-harness-engineering) community list. By that vocabulary, plan_foundry is best described as **an opinionated workflow harness extension** layered on top of Claude Code (the base harness). The README's "scaffold vs harness" framing is the same thing at finer granularity: Claude Code provides the loop, tool calls, context window, subagent dispatch, and skill loading; plan_foundry adds a phase state machine, two-tier audit gates, fresh-context verification, and a filesystem ontology on top of that.

In the last two weeks, Anthropic has shipped platform primitives that overlap with plan_foundry mechanisms - `/goal` (Haiku-judged stop condition), `/ultraplan` (cloud drafting with reviewable phases), **Outcomes** (rubric-graded fresh-context verification, Managed Agents only), **Dreaming** (memory consolidation, Managed Agents only), and a built-in "Rubber Duck" critic. Independently, three new long-horizon planning benchmarks (DeepPlanning, YC-Bench, UltraHorizon) confirm frontier models still fail at long-horizon verifiable planning unaided. The net effect: **the case for *some* harness on top of a coding agent is reinforced; the case for plan_foundry's specific mechanisms is partially eroded** as Anthropic backports overlapping primitives. The mitigating factor right now is that Outcomes and Dreaming are Managed-Agents-API-only - they are not yet in the Claude Code CLI plan_foundry sits on. Full landscape scan with sources, A/B test candidates, and per-mechanism reasoning: [ADVICE-007 in this repo](Workbench/ADVICE-007_landscape-scan-2026-05-24.md).

## Compared to other approaches

Three categories of tool do adjacent things. The mechanical differences matter.

- **(a) Context-engineering-only approaches** (rule files, skill packs, system-prompt frameworks). These improve how a single agent behaves by asking it to behave well. The guidance can be excellent; the gap is structural: compliance is probabilistic. There is no audit that runs in a separate invocation with no prior turns, no phase gate that blocks on file content, no verification that re-executes in a fresh context. plan_foundry's audit passes are different model invocations - not the same model self-reviewing the same output in the same turn. That asymmetry is hard to replicate with prompts alone.

- **(b) Custom harnesses and agent runtimes** (Aider, Cursor agent mode, hand-rolled execution loops). These buy real determinism by owning the execution loop, tool layer, and control flow. The cost is proportional: a custom runtime is an ongoing engineering project, and every new model or capability requires harness-level integration. plan_foundry gives you state-machine determinism and audit gates without building a runtime - state lives in files, transitions live in skills, and the harness is Claude Code itself.

- **(c) Lightweight wrappers** (just-a-prompt-library, `/init`-style commands that scaffold a folder but carry no state). These reduce setup friction but do not track state across sessions. When context compresses or a session ends, the wrapper's scaffolding survives on disk but there is no frontmatter state machine, no phase enum to resume from, and no audit record showing what passed and what did not. plan_foundry's state lives in structured frontmatter checked into git - re-entry is idempotent because the state is the file, not the session.

The trade-off plan_foundry accepts: harness overhead is only justified when writing the wrong plan is expensive. "Rename this function" should not need a PLAN. For anything where building the wrong thing costs more than the overhead, the scaffold pays off.

## Install

Open a Claude Code session inside the target repo and paste:

> Bootstrap plan_foundry from https://github.com/kccastillo/plan_foundry into this repo.

The agent will (1) `git clone --depth=1 https://github.com/kccastillo/plan_foundry .plan-foundry-tmp/`,
(2) run `python3 .plan-foundry-tmp/.claude/skills/init-plan-foundry/lib/run_install.py`,
(3) `rm -rf .plan-foundry-tmp/`. The install copies bundle content into
`.claude/{skills,agents,commands,hooks}`, scaffolds `Workbench/` and `Retired/`,
updates `.gitignore`, inlines operating rules into `CLAUDE.md`, and records the
bundle commit SHA at `.claude/.plan-foundry-bundle-version` plus an install
receipt at `.claude/.plan-foundry-bundle-files`. Idempotent - safe to re-paste.

After install, **restart Claude Code** so the freshly-copied skills register
with the harness.

See [BOOTSTRAP.md](BOOTSTRAP.md) for the canonical procedure (the agent reads
this on first contact).

## Update

```
/plan-foundry-sync
```

Sync clones the public repo into `<target>/.plan-foundry-tmp/`, overwrites
bundle-managed files with the latest content, refreshes the version pin, and
deletes the tmp clone. It performs receipt-backed quarantine of stale bundle
files rather than deleting them outright - a file recorded in the install
receipt but no longer shipped upstream is moved to a timestamped quarantine
directory, and only swept after 30 days. Project additions survive untouched.
Tag pinning: `/plan-foundry-sync v0.5.0` fetches a specific bundle version.

Check whether your project is at the latest bundle:

```
/plan-foundry-check-current
```

Compares your `.plan-foundry-bundle-version` to the remote HEAD via
`git ls-remote`.

## What changed, and what to clean up after updating

Read this before your first sync onto a new version. It lists only changes that
leave something behind in your project, or that change a habit. Everything else
is in the commit history.

### v1.14.0 (2026-07-31)

**Two skills, one agent and one hook were removed.** They are gone from the
bundle and nothing calls them any more:

| Removed | What it did | What it leaves in your project |
|---|---|---|
| `foundry-log` skill | Managed a unified operation log | `.claude/_foundry_log.jsonl`, and any `foundry-log-export-*.jsonl` in your project root |
| `.claude/hooks/foundry-log.py` | Wrote that log automatically | Nothing, once the file itself is gone |
| `foundry-log-summariser` agent | Summarised the log | Nothing |
| `lessons-learned` skill | Appended lessons to the monthly LOG | Whatever it wrote into your `Workbench/` LOG files |

Nine further scripts, references and templates went with them - migration and
one-shot tooling that had served its purpose. The full list is in the v1.14.0
tag's diff.

**Your first sync will not remove them for you, and this is the one thing worth
knowing.** Quarantine works from an install receipt at
`.claude/.plan-foundry-bundle-files`, which records what the bundle put in your
tree. Receipts are new. If your project was installed or last synced before
receipts existed, the sync that brings you to v1.14.0 *writes* your first
receipt and quarantines nothing - it has no record of what it previously
installed, and it will not guess. Removed files stay where they are.

From your **second** sync onwards this is automatic: a file in the receipt that
upstream no longer ships is moved to
`.claude/.plan-foundry-quarantine/<UTC-timestamp>/`, left there for 30 days in
case you need it back, then swept.

**To clean up now rather than waiting**, delete these if present. All are safe -
nothing in the current bundle reads any of them:

```
.claude/skills/foundry-log/
.claude/skills/lessons-learned/
.claude/agents/foundry-log-summariser.md
.claude/hooks/foundry-log.py
.claude/skills/execute-plan/references/log-rules.md
.claude/skills/write-plan/templates/log-template.md
.claude/skills/write-plan/scripts/migrate_plan_ids.py
.claude/skills/write-plan/scripts/test_migrate_plan_ids.py
.claude/skills/update-workbench-index/scripts/project_context_inputs.py
.claude/skills/update-workbench-index/scripts/regenerate_state.py
.claude/skills/update-workbench-index/lib/test_project_context_inputs.py
```

`.claude/_foundry_log.jsonl` and any LOG files in `Workbench/` are **your data,
not bundle code**. Nothing reads them now. Keep or delete them as you see fit -
the uninstall path deliberately leaves operator data alone.

**If you had a `SessionStart` hook pointed at `foundry-log.py`**, remove that
entry from your `.claude/settings.json`. Sync will not touch your settings
hooks, and a hook pointing at a deleted script fails on every session start.

**Monthly LOG files are no longer part of the model.** `Workbench/` is the
authority for what exists - a directory listing plus PLAN frontmatter reads.
Install no longer seeds a LOG, and no skill writes one. Existing LOG files in
your `Workbench/` are inert - retire them when convenient.

**Pipeline commits now stage named paths.** The orchestrator previously ran
`git add -A` on every commit, which staged your whole working tree and could
publish work the phase did not author. It now stages an explicit list per
commit template. The visible consequence: a file the orchestrator cannot
attribute to the phase is left unstaged, so you may see a dirty tree after a
pipeline run where previously everything was swept in. That is the fix working -
the dirt is visible instead of silently committed.

## Uninstall

```
/plan-foundry-uninstall
```

Removes the four bundle-managed dirs, the version pin, the bundle `.gitignore`
entries, and the CLAUDE.md sentinel block. Leaves `Workbench/`, `Retired/`, the
and project-local `.claude/` files (`settings.local.json`,
`plan-foundry.config`) untouched - those are operator data, not bundle code.
Offline; idempotent.

## Skills inventory

Every skill at `.claude/skills/<name>/SKILL.md`. Invoke via natural language
("write a plan", "let's ideate") or `Skill("<name>")`.

**Core lifecycle:** `plan-pipeline`, `write-plan`, `audit-sufficiency`, `audit-haiku-safe`, `execute-plan`, `retire`.

**Workbench state:** slash command `/status`.

**Cross-session continuity:** `handoff-next-session`, `rehydrate-handoff`.

**Inputs:** `write-input`, `rehydrate-input`.

**Problem-shaping:** `ideate`.

**Maintenance:** `maintain-claude-md`, `test-foundry`.

**Bundle:** `init-plan-foundry`, `plan-foundry-sync`, `plan-foundry-check-current`.

## Mobile and web caveat

Claude Code mobile and web apps do NOT read project-local
`.claude/{skills,agents,commands}/`. The operating rules inlined into `CLAUDE.md`
ARE visible there, but skill, agent, and slash command invocations only work in
Claude Code desktop sessions.

## Configuration

The bundle reads no configuration beyond `Workbench/` defaults. Override the
bundle install location at the target by setting `PLAN_FOUNDRY_BUNDLE_PATH`
before running `init-plan-foundry`.

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
