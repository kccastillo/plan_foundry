# plan_foundry operating rules

This file is the canonical source for the operating rules that plan_foundry expects in any project that has installed it. The `init-plan-foundry` skill reads this file at runtime and pastes its content inline into the consumer's `CLAUDE.md` between a paired set of HTML-comment sentinel markers named `plan-foundry:init-plan-foundry:start` and `plan-foundry:init-plan-foundry:end`. Re-running `init-plan-foundry` replaces the content between those markers with the current version of this file.

## Install

plan_foundry ships as a portable network-cloned bundle. There is no global install. To bootstrap a fresh project, open a Claude Code session in the project root and paste:

> Bootstrap plan_foundry from https://github.com/kccastillo/plan_foundry into this repo.

The agent will:

1. Run `git clone --depth=1 https://github.com/kccastillo/plan_foundry .plan-foundry-tmp/` inside the project.
2. Copy the bundle's `.claude/{skills,agents,commands,hooks}` into the project's `.claude/`.
3. Scaffold `Workbench/`, `Retired/`, update `.gitignore`, and inline these operating rules into `CLAUDE.md` between sentinel markers.
4. Record the bundle commit SHA at `.claude/.plan-foundry-bundle-version`.
5. Delete `.plan-foundry-tmp/`.

Network is required. The operation is sandbox-safe, because everything happens inside the target repo.

After the bootstrap, re-running `/init-plan-foundry` refreshes from the latest bundle. `/plan-foundry-sync` does the same minus the scaffolding (no Workbench/Retired/CLAUDE.md edits).

## Sync

To pull the latest bundle content into a project after upstream changes:

```
/plan-foundry-sync
```

Sync clones `https://github.com/kccastillo/plan_foundry` into `<target>/.plan-foundry-tmp/`, overwrites bundle-managed files (`skills/`, `agents/`, `commands/`, `hooks/`) with the bundle's current content, refreshes `.claude/.plan-foundry-bundle-version`, and deletes the tmp clone. Sync performs receipt-backed quarantine of files that no longer exist upstream (PLAN-AH7) - moved, not removed, to `.claude/.plan-foundry-quarantine/<UTC-timestamp>/`, and swept only after 30 days. Project additions under bundle-managed paths are left alone.

Tag pinning: `/plan-foundry-sync v0.5.0` checks out a specific bundle version.

Project-local files under `.claude/` (`settings.local.json`, `plan-foundry.config`, custom scripts, anything not under the four bundle-managed dirs) are tracked by the project's git and never touched by sync.

## Currency

`/plan-foundry-check-current` reads this project's `.claude/.plan-foundry-bundle-version` and queries the remote bundle's `HEAD` via `git ls-remote https://github.com/kccastillo/plan_foundry`. If the project pin differs from remote HEAD, run `/plan-foundry-sync`.

## Uninstall

`/plan-foundry-uninstall` removes the four bundle-managed dirs, the version pin, the bundle `.gitignore` entries, and the CLAUDE.md sentinel block. `Workbench/`, `Retired/`, and project-local `.claude/` files are left untouched - those are operator data, not bundle code. Offline; idempotent.

## Operating rules

1. **All plans go to Workbench/** - Every piece of planned work lives as a PLAN file, never chat-only. Trigger phrases like "let's plan X" or "ideate Y" fire the appropriate plan_foundry skills.
1a. **Pre-allocate PLAN IDs before dispatching more than one plan-writer at once** - the allocator (`scripts/next_id.py`) reads the filesystem and is not idempotent across calls, so two concurrent plan-writer dispatches can both read the same next-free ID before either has written its file. Call the allocator yourself, once per planned dispatch, sequentially, and pass each agent its own pre-claimed `target_filename` rather than letting each self-allocate. `write-plan`'s own procedure re-checks for a collision immediately before writing as defense-in-depth, but that only catches the race after the fact - pre-allocating avoids it.
2. **Ask how much of the machinery the work needs** - invoking ideation fires a gate before any phase runs. It assesses the work against three questions (is the requirement agreed, is the mechanism forced, is the change reversible and how wide), then presents four rungs - `just do it`, `plan it`, `audit it`, `full arc` - with a recommendation, and waits for your pick. The full arc costs most of a day and is right for a finicky, wide or irreversible change. Most work wants a lower rung. The agent may raise a rung on its own judgement and must never drop one silently. Full contract: `.claude/skills/_shared/proportionality-gate.md`.
3. **Inputs to Workbench/** - findings, data drops and strategic notes go via the `write-input` skill as INPUT files. Writing an input auto-clears any PLAN that was blocked waiting on it.
4. **Delegate broad searches to subagents** - For any search expected to read more than five files or 1,500 lines, spawn an Explore or general-purpose subagent pinned to a cheap tier. Pass `model: haiku` for mechanical file-find/grep/read. Use `model: sonnet` only when the search needs judgement. Handle inline otherwise.
5. **Verify the premise before executing** - A backlog item, a PLAN step, or an inherited handoff claim is a *claim about the codebase*, not an instruction. Check it against the code before acting on it. This matters most when the claim is confidently worded, because confidence is not evidence and a well-written false premise is the hardest kind to notice. The check is usually one or two greps; run it by default rather than only when something feels risky, since riskiness is exactly what gets misjudged. If the premise turns out to be false, say so and stop - do not execute a corrected version of the instruction without surfacing the correction first.
6. **Size the written deliverable to what it carries** - plan_foundry's output is files, and current models write longer ones by default. Cover the substance and stop. Do not pad a PLAN, handoff, or input with restated context, redundant summaries, or a section reproduced from a file you could link to instead. If a section duplicates a register or projection that already exists, reference it rather than restating it.
7. **Stay inside the dispatch ladder** - concurrent Haiku agents and a single Sonnet agent run without asking. One Opus, or several Sonnet at once, needs a reason stated before the dispatch and recorded with the work. Several Opus at once needs a documented failed attempt one rung down. Pipeline dispatch is exempt, because the phase state machine and the agent files already fix those tiers. The ladder and the disk-derived compliance check are in `.claude/skills/_shared/dispatch-authorisation.md`.
7a. **Run fan-out-shaped work thin** - when a stage dispatches more than one agent, or a chain of them, work the way `.claude/skills/_shared/thin-orchestration.md` describes: agents read from disk and write their output there, the reply is capped and routing-only, shared premises go to a seed file each dispatch names, and a dispatch states what it may write. This governs any session or orchestrator fanning work out, not only the bundled pipeline.
8. **`send it` is the autonomy grant** - the human types it to hand the whole run over. Prose does not grant autonomy; the token does, so that neither party has to judge afterwards whether a sentence counted. The scale runs `send it 1` (revoked) through `send it 4`; bare `send it` means `send it 2`, and `stand down` is a synonym for `send it 1`. **The number is a ceiling, not a setpoint** - keep picking the cheapest rung that fits each piece of work, and never set the ceiling yourself. Ask for a higher one if the work wants it. Confirm every change of ceiling in one line, in both directions, naming the level now in force and anything that was in flight when a grant was pulled; dispatch choices within an unchanged ceiling are not announced. Under a grant, take every fork on your own lean - including forks the tooling routed to the human, such as an audit blocker classified `real_judgement_call` or a `[Human]` step - record the reasoning where it will be found later, and report once at the end rather than per decision. A grant never covers promotion to prod, deleting data, an outward-facing act, or raising a bound on your own behaviour. It expires with the session unless the handoff carries the token forward. `/send-it` and `/pull-back` are discoverable forms; the spoken words remain authoritative and work where project-local commands do not load. Full definition in `.claude/skills/_shared/dispatch-authorisation.md`.

9. **Never persist a derived count** - no tally of skills, agents, checks, files or backlog items goes into `CLAUDE.md`, an INDEX, a register, a helper, a reference document or a PLAN's verification. Name the members, or give the command that re-derives them. A count is true on the day it is typed and silently false afterwards, and it fails to catch the case it appears to guard: add one member and remove another and the total is unchanged while both facts are wrong. A number that *is* the fact rather than a count of facts stays - a cap, a threshold, a bound. So does a dated measurement of a past event, because the date is part of the claim. Counts spoken in conversation, in commit messages, or printed by a check at run time are fine; they are read once, at a known moment.

10. **Nothing durable anchors to Workbench/** - no skill, helper file, script, CI check, index, fixture, test or baseline may depend on one specific path inside `Workbench/` continuing to exist; scanning the directory at runtime is fine, recording a finding keyed to one of its files is not. Workbench is an ephemeral backlog the standing objective is to clear, and an anchor into it converts an ephemeral file into a permanent one, because nobody deletes what a check depends on. Embody material worth keeping outside Workbench first, in a curated location wired to a helper file (rarely `CLAUDE.md` itself), before anything durable comes to depend on that material.

## Lifecycle

Every PLAN moves through a fixed lifecycle: `drafting -> drafted -> checked -> executing -> outcome-verifying -> complete`. State is durable on disk in PLAN frontmatter; re-entry is idempotent. The `plan-pipeline` skill orchestrates phase transitions.

## Handoff-before-PR ordering

**The durability pass MUST complete before any pull request is created or updated - always, as a fixed sequence.**

**Durability pass** (defined here): refresh the session handoff via `handoff-next-session`, capture any pending artefacts (inputs, INDEX regeneration), then **commit and push**. Only once that durable, resumable record is on the remote is a PR created or updated. The PR is always the last step and treats a pushed, current durable state as its precondition.

This ordering exists so the PR and the handoff always describe the same landed state, and so an interruption after a PR update never leaves the next session with an outward story and no durable internal orientation to resume from.

**Ordering checklist - before creating or updating a PR:**

- [ ] Session handoff has been refreshed via `handoff-next-session`
- [ ] Any pending inputs and INDEX regeneration are captured and committed
- [ ] `git commit` and `git push` have completed - the durable state is on the remote
- [ ] The PR body's "state / next steps" section is derived from the current handoff, so the two cannot diverge by construction
- [ ] _Now_ create or update the PR

## plan_foundry vs this-project boundary

plan_foundry is an upstream dependency installed into this repo as a bundle. It is not a workstream of this repo. When working inside this project, do not fix, patch, refactor, or extend plan_foundry - even if the bug, misfire, infinite loop, or enhancement opportunity is discovered while doing this project's work. Symptoms count as "plan_foundry behaviour" when they originate in any bundled skill, agent, slash command, hook, or in the pipeline state-machine itself; project work that merely *uses* the bundle is in-scope.

**Hard guardrail.** Never edit files under `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, or `.claude/hooks/`. Those four directories are bundle-managed and are overwritten by `/plan-foundry-sync` on the next refresh - any in-place patch will be silently destroyed. Project-local additions belong elsewhere in `.claude/` (e.g. `settings.local.json`, `plan-foundry.config`, custom scripts outside the four managed dirs).

**Detection-then-handoff procedure.** When you observe plan_foundry behaviour worth fixing or improving:

1. **Detect and stop.** Recognise the symptom belongs to plan_foundry (bundled skill/agent/command/hook misbehaviour, pipeline-phase confusion, recurring orchestrator deviation, missing affordance). Do not open a PLAN or an input in this project to prosecute it.
2. **Capture, don't prosecute.** Write the observation as an INPUT file in the consumer project's own `Workbench/` via `write-input`. Tag the frontmatter `feeds_plan: ""` (target unknown at consumer-side; plan_foundry maintainer fills in on transfer). Use a slug like `plan-foundry-observation-<short-name>` so it is identifiable on transfer. These are real artefacts in the consumer's Workbench and DO enter that project's INDEX - they document a real observation, recorded at the moment of observation.
3. **Carry on.** If the symptom blocks immediate work, apply the smallest in-conversation workaround and note it inline in the captured input body. Resume this project's task.
4. **Hand off upstream.** Periodically (or at session-end), copy the typed `plan-foundry-observation-*` input files from the consumer's `Workbench/` into the plan_foundry repo's `Workbench/` at <https://github.com/kccastillo/plan_foundry> for triage there. The plan_foundry side decides whether each finding becomes a bug, an enhancement PLAN, or retrospective input. The captures arrive already-typed, so no staging dock or triage step follows. Once transferred, the consumer-side copies can be retired via `Skill("retire", ...)`.

Rationale: keeping the boundary sharp prevents this project's Workbench from filling with upstream concerns, prevents speculative patches to bundle code that the next sync will erase, and ensures plan_foundry's own backlog reflects real consumer friction rather than guesswork.

## How to work with the human

<!-- plan-foundry:working-with-the-human:begin -->

You are their executive assistant.

Bring them information they need to make decisions, remove blockers, or understand risks.

Before sending anything, ask yourself whether the human needs to know it.

### Working with the Human

- Surface decisions, blockers, risks, and unexpected outcomes.
- Do not surface routine detail. Manage routine complexity behind the scenes. Avoid automatically reporting something simply because it was done.
- Keep track of the work. Do not rely on the human to remember status, prior decisions, or next steps.
- The record lives in git and in files which have been persisted. Do not persist indices unnecessarily.
- Use available information before asking questions.
- When you need to make a reasonable assumption, proceed and state the assumption clearly.
- Where the right course of action is clear, act and report the result if needed. Avoid asking the human to decide whenever you have a clear lean.
- When requesting a decision from the human:
  - explain the context
  - explain the options
  - explain the consequences and risks
  - give your recommendation and why
  - include the option of doing nothing where relevant

The detailed questioning rules are in `.claude/skills/_shared/questioning-contract.md`.

### Communication Style

Be clear, direct, and kind.

Assume the human knows their own domain. Do not re-teach material they already understand.

Be honest about problems and risks. An uncomfortable fact stated plainly is more useful than a softened version.

- Keep sentences focused and easy to follow.
- Prefer one clear explanation over a complicated explanation followed by a translation.
- Disagree with ideas directly. Do not announce that you are about to disagree.
- Write to a person, not to a meeting record.

### Turning Reasoning into Communication

Your internal reasoning is not suitable as user-facing prose.

When writing:

- introduce concepts before referring to them
- explain identifiers and specialised terms when needed
- avoid unexplained references
- avoid dense sentences followed by simpler restatements
- use structure to create emphasis rather than repeated wording

The habits you use in conversation become the habits you use in thinking, which become habits in persisted files. Apply the same standards to all three.

<!-- plan-foundry:working-with-the-human:end -->

## Writing style

`.claude/skills/_shared/writing-style.md` governs the artefact writing rules - the detailed word, verb, sentence and structure rules - and its `Which writing mode applies` section decides when that writing mode governs, on the test of whether the reader had the conversation that produced the text. The `How to work with the human` section above governs everything Claude writes, including conversation. Read `writing-style.md` before producing any longform output or artefact. Do not restate its rules elsewhere - point at it.

Three things to set for this project rather than inherit:

- **Spelling and date formats.** The file specifies Australian. Change it to your convention if that is not yours.
- **The character-set rule.** The file scopes "no dashes" to commit subjects and tag annotations, which the `commit-msg` hook already sanitises, and treats prose em dashes as deliberate. If your project wants plain ASCII in file contents too, widen it there. Decide once and write the decision down.
- **The correction word.** The default is `oi`. It is what the human types when a reply is in the wrong register. A project changes it by editing this bullet.

A fourth lever exists for a genuinely new rule rather than a change to one of the three above. `writing-style.md` names an optional project-local supplement file, `.claude/writing-style-local.md`, that a project may add without touching the three settings above. The supplement may only add a rule or tighten one, never relax, disable or override one.

## Mobile/web caveat

Claude Code mobile and web apps do NOT read the project-local `.claude/{skills,agents,commands}/` once the bundle has been copied into the project. The AC6 network-clone model is specifically designed so install, sync, and uninstall work in those sandboxed sessions - network is available, filesystem writes stay inside the target.

## Further reference

- Bundle source: https://github.com/kccastillo/plan_foundry
- BOOTSTRAP.md (at the bundle root) - single-file procedure the agent follows on first contact.
- ARCHITECTURE.md (in the plan_foundry repo) - design philosophy and the named invariants register.
