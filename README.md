# plan_foundry

A **deliberative** planning harness for Claude Code. You write down what you're trying to do; the harness audits it, helps you fix it before any code is written, then executes it under supervision and records what happened. Install once on your machine, use across all your repos, update via `git pull`.

## Why you might want this

Coding agents are very good at producing plausible-looking output very quickly. That's a problem when "plausible-looking" and "actually right" come apart — which they do, a lot, on anything beyond a small well-specified change.

You ask for a feature. The agent picks an interpretation you didn't intend, writes 500 lines, and you only notice when the diff lands. Or it references a database column that doesn't exist because the model quietly invented one. Or you spent two sessions agreeing on an approach, came back the next day, and nobody — you or the agent — can quite remember what you decided or why.

plan_foundry slows that loop down on purpose. Before any code gets written, the agent writes down what it's about to do, in enough detail that a separate pass — by a different model — can catch the mistakes. You read it. You push back. The plan gets revised until it's actually right. Then the work gets executed against the plan, not against an interpretation that lives in the agent's head and disappears at the end of the session.

The slowing-down part is what agents are bad at imposing on themselves and good at following once it's imposed. That's the whole bet.

## What it's for (and what it isn't)

**Reach for plan_foundry when:**

- The work is high-stakes, novel, or shape-defining — refactors, architectural decisions, new features, anything where building the wrong thing is expensive.
- You want decisions and reasoning preserved in version control, not in chat history.
- You want the agent to surface a half-formed plan early, get it critiqued, and revise — instead of producing 500 lines of "almost right" code.
- You're collaborating with the agent over many sessions and need durable state.

**It is not for:**

- Throughput. If you want an agent to ship code as fast as possible, there are tools for that — plan_foundry is not one of them. It's deliberately sequential and keeps you in the loop. Going faster doesn't help you think harder.
- One-shot edits. Asking "rename this function" doesn't need a PLAN. The harness's overhead is justified only on work where a plan is worth writing in the first place.
- Hiding work from the human. plan_foundry surfaces uncertainty — that's the point. If you want an agent that asks fewer questions, this is the wrong tool.

## What it's good at

- **Catching wrong plans before they become wrong code.** A PLAN gets two audit passes (conceptual sufficiency + mechanical safety) before any edit is made. Findings are blockers; revision is the supported path. A PLAN that fails an audit isn't the system regressing — it's the system working.
- **Pinning model tiers to job shape.** Opus for design judgement, Sonnet for mechanical review and execution, Haiku for cheap structured work. Cheap models get bounded jobs they can actually complete; expensive models are reserved for what needs them.
- **Surviving context loss.** PLAN files live on disk with structured frontmatter. State machine transitions are recorded. If a session compresses, crashes, or hands off to tomorrow, the next session reads frontmatter and resumes — no "where were we?" reconstruction.
- **Refusing to silently hallucinate.** PLANs declare their `substrate_files` (schemas, API docs, modules they touch). The plan-writer skill must `Read` these before authoring. The audit then greps Steps for references that don't exist in the declared substrate and blocks on findings.
- **Making "done" mean something.** Each PLAN carries a `verification_state` enum + executable acceptance checks. The orchestrator re-runs the checks in the parent context after execution. Boxes don't get ticked optimistically.
- **Keeping the design landscape readable.** Maintenance skills audit `CLAUDE.md` and `ARCHITECTURE.md` for context-rot. Lessons get codified into permanent rules when they recur, not hoarded as episodic memory.

## How the pieces solve specific problems

The bundle is a collection of skills (Markdown prompts pinned to model tiers), agents (delegated workers with bounded tool access), and slash commands. Each one targets a specific failure mode.

### The PLAN lifecycle: `plan-pipeline` + `write-plan` + `execute-plan`

**Problem:** Ad-hoc agent setups have no consistent moment of "what are we doing and why?" Decisions live in chat, get lost on compression, get re-litigated next session.

**Solution:** Every piece of intended work becomes a PLAN file in `Workbench/` with structured frontmatter. PLANs move through a fixed lifecycle: `drafting → drafted → checked → executing → outcome-verifying → complete`. The `plan-pipeline` skill is the orchestrator — it reads frontmatter, decides which phase fires next, and dispatches the right sub-skill. The state machine is on disk, not in the model's head, so re-entry is idempotent.

- `write-plan` authors a new PLAN, populates frontmatter, enforces the substrate-verification preflight.
- `execute-plan` runs an already-checked PLAN end-to-end, populates Executor Notes, logs to the monthly LOG.

### The audit gates: `audit-sufficiency` + `audit-haiku-safe`

**Problem:** "Looks fine to me" is a terrible quality gate. Humans and agents both miss things; they miss *different* things on different passes.

**Solution:** Two audits, each scoped narrowly. `audit-sufficiency` runs on Opus and asks the conceptual question: does this PLAN actually have what it needs to succeed — clear acceptance criteria, identified risks, real verification? `audit-haiku-safe` runs on Sonnet and does mechanical checks: substrate fidelity (does every referenced symbol exist?), destructive-action discipline, executor-tier safety. Findings are blockers, not advisories — the PLAN doesn't advance until they're resolved.

### The Workbench: `update-workbench-index` + `/index` + `/status`

**Problem:** A folder full of PLAN files is just a folder. You need to see what's drafting, what's blocked on review, what's stalled in execution.

**Solution:** `update-workbench-index` regenerates `Workbench/INDEX.md` from PLAN frontmatter — pure projection, deterministic, fast. `/index` is the slash-command form. `/status` reads live `.heartbeat/` files plus PLAN state and shows what's actively running, what's stalled, what needs attention.

### Carrying context across sessions: `handoff-next-session` + `rehydrate-handoff` + `foundry-log` + `lessons-learned`

**Problem:** Long-running work spans many sessions. Without explicit handoff, every session starts cold and rediscovers what last session already figured out.

**Solution:** `handoff-next-session` writes a session-end brief (what's in flight, what's parked, what's next). `rehydrate-handoff` reads it at session start. Cross-session learnings flow through `lessons-learned` into the monthly LOG; `foundry-log` does self-improvement pattern analysis across the LOG's JSONL events.

### Research and advice: `write-input` + `rehydrate-input`

**Problem:** Mid-PLAN, you realise you need to research something or you receive strategic guidance. Where does it go? If it's chat-only, it evaporates. If you stuff it into the PLAN, the PLAN bloats.

**Solution:** `write-input` records RESEARCH (data drops) or ADVICE (strategic notes) as their own files in `Workbench/`. PLANs blocked on a missing input auto-clear when the input lands. `rehydrate-input` marks the input as integrated once consumed, so it can later be retired cleanly.

### Cleanup: `retire`

**Problem:** Completed PLANs, integrated inputs, superseded research — they pile up and pollute the active surface.

**Solution:** `retire` moves artefacts to a gitignored `Retired/` folder. Completed work stops occupying mental space; the history is still on disk if you need it.

### Shaping problems before they become PLANs: `ideate`

**Problem:** Sometimes the problem isn't ready to be planned. You have a vague intention and need to think it through before committing to a structure.

**Solution:** `ideate` runs a three-phase arc (Clarify → Survey → Converge). Phase 1 narrows what the problem actually is. Phase 2 surveys options. Phase 3 converges on the chosen direction. Output feeds into `write-plan`.

### Doc maintenance: `maintain-claude-md`

**Problem:** Always-loaded docs (`CLAUDE.md`, `ARCHITECTURE.md`) accrue context-rot over time. Every always-loaded line is paid every interaction.

**Solution:** `maintain-claude-md` audits the maintainer-facing docs against drift — proposing additions when a recurring rule deserves codification, proposing removals when content is no longer load-bearing. Output lands as a Workbench PLAN, so the change itself goes through the same lifecycle.

### Self-testing: `test-foundry` + `/test-foundry`

**Problem:** A planning harness that doesn't test itself will rot silently.

**Solution:** A two-tier harness — Python tier for deterministic structural checks (INDEX correctness, schema validation, baseline audit), LLM tier for scenario walks (lifecycle, audit revision loop, retire mechanics). Emits a portable TESTREPORT.

### Bundle hygiene: `init-plan-foundry` + `plan-foundry-check-current`

**Problem:** Installing into a new repo should be one step. Knowing whether your local copy is current should be one query.

**Solution:** `/init-plan-foundry` (or `Skill("init-plan-foundry")`) creates the symlink, scaffolds `Workbench/` and `Retired/`, updates `.gitignore`, inlines operating rules into `CLAUDE.md`. Idempotent. `/plan-foundry-check-current` reports whether the local bundle lags `origin/main` and prints the exact `git pull` command if so.

## Install

Clone the bundle once per machine (canonical location is `~/.claude/plan_foundry/`):

```
git clone https://github.com/kccastillo/plan_foundry ~/.claude/plan_foundry
```

Then, in each target repository:

```
/init-plan-foundry
```

(Or invoke `Skill("init-plan-foundry")` in a Claude Code session running inside the target repo, or say *"set up plan_foundry"*.) The skill creates a single coarse symlink `<target>/.claude → ~/.claude/plan_foundry/.claude`, scaffolds `Workbench/` and `Retired/`, seeds the current-month LOG, updates `.gitignore`, and inlines operating rules into the target's `CLAUDE.md`. Idempotent — safe to re-run.

After install, **restart Claude Code** so the project-local `.claude/` directory is registered.

Update the bundle (which updates every target at once):

```
cd ~/.claude/plan_foundry && git pull
```

Check whether your local bundle is current with `/plan-foundry-check-current`.

## Skills inventory

Every skill at `.claude/skills/<name>/SKILL.md`. Invoke via natural language ("write a plan", "let's ideate") or `Skill("<name>")`.

**Core lifecycle:** `plan-pipeline`, `write-plan`, `audit-sufficiency`, `audit-haiku-safe`, `execute-plan`, `retire`.

**Workbench projection + state:** `update-workbench-index` (plus slash commands `/index`, `/status`).

**Cross-session continuity:** `handoff-next-session`, `rehydrate-handoff`, `lessons-learned`, `foundry-log`.

**Inputs:** `write-input`, `rehydrate-input`.

**Problem-shaping:** `ideate`.

**Maintenance:** `maintain-claude-md`, `test-foundry`.

**Bundle:** `init-plan-foundry`, `plan-foundry-check-current`.

## Mobile and web caveat

Claude Code mobile and web apps do NOT read project-local `.claude/{skills,agents,commands}/`. The operating rules inlined into `CLAUDE.md` ARE visible there, but skill, agent, and slash command invocations only work in Claude Code desktop sessions.

## Configuration

The bundle reads no configuration beyond `Workbench/` defaults. Override the bundle install location at the target by setting `PLAN_FOUNDRY_BUNDLE_PATH` before running `init-plan-foundry`.

## Repository structure (consumer view)

After `init-plan-foundry`, your target repo gains:

```
.claude → ~/.claude/plan_foundry/.claude   (symlink — gitignored)
Workbench/                                 (PLAN files + monthly LOG)
Retired/                                   (completed artefacts, gitignored)
CLAUDE.md                                  (operating rules between sentinel markers)
```

## Further reading

- [CLAUDE.md](CLAUDE.md) — operating rules and agent-execution discipline.
- [ARCHITECTURE.md](ARCHITECTURE.md) — design philosophy, strategic principles, invariants register.
