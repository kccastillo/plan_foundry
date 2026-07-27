# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Filesystem-native planning and execution scaffold for agentic software work. PLAN files in `Workbench/` move through a fixed lifecycle (`drafting → drafted → checked → executing → outcome-verifying → complete`) under an orchestrator skill (`plan-pipeline`). The repo ships as a public-URL bundle: each consumer installs via paste-prompt that has the agent clone `https://github.com/kccastillo/plan_foundry` into a transient `<target>/.plan-foundry-tmp/`, copy bundle content into the target's `.claude/`, then delete the tmp clone (per [BOOTSTRAP.md](BOOTSTRAP.md)). Sandbox-compatible — works in Claude Code mobile/web sessions. See [README.md](README.md) for install and skill overview.
Maintainer reference: see [ARCHITECTURE.md](ARCHITECTURE.md) for design philosophy, strategic principles, and the named invariants register.

## Working style

- AU spelling, usage, date formats.
- New conversation: check the request is well-specified; ask clarifying questions first when it isn't.
- **IMPORTANT:** No unprompted output of artefacts, illustrations, code, or longform sections. If producing one seems like the best move, ask permission first.
- Long output: ask whether the direction is right before continuing.
- No cross-chat references between projects unless prompted; isolate within projects by default.
- **IMPORTANT:** To the human: plain language; do not compress, abbreviate, or elide. Ruthless token economy is for internal planning only. Always name the thing, the operation, the result.
- **IMPORTANT:** When offering options / asking the human to choose: apply the **decision-briefing contract** — first run a leading-check (is the "do nothing / not yet" alternative missing?) and a bamboozle-check (too dense to see what's being agreed to?); then serve context, each option's consequence + risk, your lean + why, and an eject button. Full contract: [.claude/skills/_shared/questioning-contract.md](.claude/skills/_shared/questioning-contract.md).
- If a question is answerable from a tool's default behaviour, decide and proceed.
- If something depends on a prior decision or external input, state the dependency — the human will not always remember.
- **IMPORTANT:** Requirement before solution — no mechanism design until requirement and process are agreed.
- **IMPORTANT:** Reviews: brief verification preamble (what was checked against — files, not just the document under review) → one-line overall verdict → priority-ordered numbered punch list (blockers first, nits last) → "Not blockers" subgroup → net verdict (what's ready, what needs fixing).

## Agent execution rules

**Operating rules:**
1. **All plans go to Workbench/** — Every piece of planned work lives as a PLAN file, never chat-only.
2. **Research and advice to Workbench/** — RESEARCH (data drops) and ADVICE (strategic notes) go via `write-input` skill. Writing an input auto-clears blocked plans waiting on it.
3. **Delegate broad searches to subagents** — For any search expected to read >5 files or >1500 lines, spawn an Explore or general-purpose subagent pinned to a cheap tier — pass `model: haiku` for mechanical file-find/grep/read; use `model: sonnet` only when the search needs judgement. Handle inline otherwise.

**Plan lifecycle and phases:** PLAN status enum and pipeline-phase state-machine are canonical in [plan-conventions.md](.claude/skills/write-plan/references/plan-conventions.md) (statuses) and [phase-state-machine.md](.claude/skills/plan-pipeline/references/phase-state-machine.md) (orchestrator phases). Both are referenced by skill workflows directly; this file does not duplicate them.

**PLAN identity:** active PLANs use the `PLAN-[A-Z][A-Z][0-9]` scheme (AA0–ZZ9). Historical `PLAN-NNN` IDs in `Retired/` and the LOG are frozen. Full policy in [plan-conventions.md §PLAN Identity Policy](.claude/skills/write-plan/references/plan-conventions.md). Allocator is `.claude/skills/write-plan/scripts/next_id.py`.

**Decision-naming convention.** When a PLAN (especially a plan-of-plans) locks judgement-call decisions:
- Assign each decision an ID: D1, D2, ... DN, anchored in the CONTEXT section.
- Give each a 2–3 word nickname (e.g., "Mono-Repo", "Max Triggerability").
- Reference decisions elsewhere as "per D2 — Max Triggerability".
- Prose stays in the CONTEXT section; no separate decision files unless audit-trail demands.

Aids human recall, quotability, and decision re-opening.

**Halt conditions:**
- **Interrupted runs:** if the human halts a run mid-execution, their description of what they caught is a hiccup entry — write it to `Workbench/_hiccups.md` before resuming.
- **Ambiguity:** if a step is ambiguous, unsafe, or marked [Human]: halt, set `status: needs-revision`, surface to the human. Do not improvise.
- **Verification failure:** if any verification check fails, halt before commit; do not tick boxes that have not been verified.

**Autonomous execution.** During PLAN execution and pipeline orchestration:
- Do not surface fork-direction questions on routine decisions. Use best judgment.
- If genuinely uncertain between alternatives of comparable weight, spawn a sonnet subagent to research/decide rather than escalating to the human.
- Escalate to the human ONLY for:
  1. True blockers (cannot proceed without input — e.g., authentication, missing API access, ambiguous requirements).
  2. Major architectural decisions (irreversible or shape-defining choices — e.g., framework swap, schema migration, data deletion, choice between fundamentally different design approaches).
- In the audit loop, audit blockers classified as `real_judgement_call` by the sufficiency auditor's `triaged_human_items` output are the concrete definition of (1) and (2). Blockers classified as `mechanically_forced` are resolved by the auto-fixer agent autonomously; they do not surface to the human.
- Routine items — phrasing, naming, ordering, formatting, scope-internal tradeoffs — resolve via best judgment + record the decision in the PLAN's Executor Notes so it's auditable later.
- plan_foundry exists to automate this kind of orchestration. Excessive fork-prompts defeat the purpose.

## Skills

Authoritative skills live at `.claude/skills/<skill-name>/SKILL.md` as real directories (post-PLAN-AC3 — the plugin marketplace path has been abandoned in favour of a portable copy-paste bundle). Invoked via `Skill("<name>")`. Run `ls .claude/skills/` for the current inventory. The Claude Code harness loads every `SKILL.md` frontmatter `description:` into the per-turn system-reminder; that is the primary trigger surface. The lifecycle map below groups the 22 skills by when they fire so workflow discovery does not depend on reconstructing wiring from descriptions alone.

**Skill lifecycle map** (as of 2026-07-26, 27 skills):
- **Session start (orient):** `rehydrate-handoff` (read prior HANDOFF, surface it; retire deferred to session end — never solicited at start, per PLAN-AG9 D4; explicit operator "retire now" override honoured), `rehydrate-input` (input mode: consume RESEARCH/ADVICE → `integration_status: integrated`; asset mode: stamp `last_consulted` + `consulted_by` on a helper/reference and write a per-asset memory pointer; late-auto-retire if all consuming PLANs already retired).
- **Plan authoring:** `ideate` (8-phase cadence; two risk-assessment gates — Risk-Assess-Idea and Risk-Assess-Spec — fire between numbered phases Converge↔Spec-Draft and Spec-Draft↔Self-Critique), `write-plan` (PLAN file authoring + ID allocation), `write-input` (RESEARCH/ADVICE files with `integration_status: pending`), `foundry-research` (model-tiered + budget-sized deep-research fan-out — cheapest-capable model per role, no Fable, Opus only for synthesis; prefer over native `deep-research`. Ships a Workflow script; see `.claude/skills/foundry-research/references/model-tiering.md`), `raise-foundry-request` (writes `Workbench/FOUNDRYREQ-<origin>-<datetime>-<slug>.md` so consumer repos raise bugs and feature requests against plan_foundry without hand-editing bundle files; per PLAN-AH0 D2).
- **Plan execution (orchestrator-driven, mostly auto-fire):** `plan-pipeline` (orchestrator — every commit-worthy phase transition), `execute-plan` (sonnet executor body), `audit-sufficiency` + `audit-haiku-safe` (auto-fire from plan-pipeline during the audit loop).
- **Closeout (auto-fire from plan-pipeline §4F):** `retire` (move file to `Retired/` with AA2 post-condition check), `update-workbench-index` (regenerate INDEX after every commit), `maintain-claude-md` (doc-drift check after PLAN retire if `files_touched` matches), `handoff-next-session` (write at session end — assesses the four-part content contract [session roadmap · agentic use · model assignation+rationale · next-handoff trigger, per PLAN-AG9] and resolves one of two terminal states: updated-into-successor [retire prior + write fresh] or retired-outright [retire prior, no successor when roadmap fully discharged]).
- **Document ingestion (human-triggered, parent-session-only):** `convert-pdf` (orchestrator — chains doc-to-md, segment-doc, reformat-md end-to-end; manages `sources/` + `originals/` directories, updates both INDEX files, writes CLAUDE.md sentinel block), `doc-to-md` (convert PDF/DOCX/MD to raw Markdown; pdftotext primary path, Claude native reader fallback, pandoc for DOCX), `segment-doc` (detect document boundaries, propose segment list, await user confirmation, write per-segment files to `originals/`), `reformat-md` (heading normalisation, PDF artefact removal, image characterisation via Claude vision for PDF sources, frontmatter application, write to `sources/`).
- **Maintenance (human-triggered):** `lessons-learned` (post-PLAN retrospective), `test-foundry` (run harness), `foundry-log` (log-month rotation), `init-plan-foundry` (bootstrap a target repo), `plan-foundry-check-current` (is the bundle current with origin), `plan-foundry-sync` (copy bundle into target's `.claude/`; refresh operating-rules sentinel block in root `CLAUDE.md`), `plan-foundry-uninstall` (reverse of init-plan-foundry), `autonomous-loop` (create a server-side hourly Routine that drives a PLAN from `drafted` through `complete` without human intervention; self-terminates on completion, human escalation, or IAL ceiling).

Slash commands live in `.claude/commands/`: `/index` regenerates the Workbench INDEX projection; `/status` shows live executor heartbeat + stalled-audit state; `/checkpoint` captures a conversation summary during ideate phases 1–3 (forensic trace for compression-survival); `/init-plan-foundry` bootstraps a target repo; `/test-foundry` runs the test harness; `/plan-foundry-check-current` reports whether the bundle is current.

## Reusable asset registry

A load-bearing cross-skill surface, not itself a skill. Two surfaces hold tagged, frontmatter-described reusable artefacts: `references/` (markdown reference material) and `.claude/skills/_shared/` top-level files (helpers shared across skills). Both are walked by the pure-projection primitive `.claude/skills/_shared/list_reusable_assets.py`, which emits `references/.registry.json` and `references/INDEX.md` and exposes `query_by_tags` + `query_by_seed` pure functions.

Three integration moments — knowing these prevents rediscovering them per session:

- **`ideate` Clarify (Phase 1)** — seeds a tag-overlap query against the working PLAN's topic and surfaces matching assets inline, so the human and the model see prior work before authoring.
- **`rehydrate-input` asset mode** — when the operator marks an asset consulted by a specific PLAN, the skill stamps `last_consulted: <today>`, appends the consuming PLAN to `consulted_by` (FIFO-capped at 20), and writes a per-asset memory pointer under the Claude auto-memory directory. Late-auto-retire fires when an integrated input has no remaining un-retired consuming PLANs and `lifecycle_mode != reference`.
- **`audit-foundry` (CI script, not a skill)** — emits `reference-freshness` (`info` for never-consulted, `warn` for `last_consulted ≥ 6mo` or malformed-date) and `tag-hygiene` (`warn` for any non-kebab `topic_tags`). Both stay non-blocking — only `error` severity fails CI, by design. The monthly RECUR-`monthly-asset-freshness-eyeball` PLAN cycles a human read of the findings so warns don't pile up invisibly.

Asset frontmatter contract (PLAN-AD6): `asset_id`, `kind`, `topic_tags` (kebab-lowercase, validated by audit-foundry), `last_consulted` (ISO date or empty string), `consulted_by` (list of PLAN IDs).

## Pre-prod / prod separation

This repo (`plan_foundry_dev`) is **pre-prod** — the maintainer's working surface with `Workbench/`, internal PLANs, audit files, and the test harness. Consumers clone the prod bundle from `plan_foundry`, not `_dev`. Promotion uses `scripts/promote.sh <tag>` which copies an allowlisted subset of the dev tree into a temp dir, inits a fresh git repo, and force-with-lease pushes to `kccastillo/plan_foundry`; then mirrors the same tag and current HEAD back to dev `origin` so both repos stay at version parity. The prod repo coordinates live in `scripts/prod-repo.txt`. See ARCHITECTURE.md "Portable Bundle" invariant for the rationale.

## CI

`.github/workflows/checks.yml` runs `bash scripts/ci/run-all.sh` on every PR and push to `main`. The script is the single source of truth for what "green" means and runs identically locally and in CI — run it before pushing. List the checks with `bash scripts/ci/run-all.sh --list`. Covers: skill Python tests under `.claude/skills/*/lib/`, `scripts/test_audit_foundry.py` (asset-freshness + tag-hygiene category tests), INDEX freshness, pre-commit hook syntax, promote.sh syntax, dogfood telemetry hook registered, audit-foundry baseline (frontmatter-v2, cross-refs, reference-freshness, tag-hygiene categories — only `error` severity fails CI, `warn`/`info` are visibility signals only), foundry invariants, CLAUDE.md hard line-cap (150). The LLM-driven test-foundry harness runs out-of-CI (requires a Claude Code session).

## Caveats

- **CONTEXT_CONSTITUTION.md** is not used in this project (single-developer scope). Create one if this harness is adopted by a team.
- **No personal names in documentation.** Refer to the repo owner as "the human" in all PLAN files, skills, and documentation.
- **Mobile/web app gap.** Claude Code mobile and web apps do NOT read project-local `.claude/{skills,agents,commands}/`. CLAUDE.md (this file) IS visible there, but skill/agent/slash command invocations only work in desktop sessions.
