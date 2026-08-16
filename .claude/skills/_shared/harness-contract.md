---
title: Harness Contract
description: Register of the Claude Code harness surfaces this bundle depends on. One entry per surface, each naming the version observed, the value or behaviour assumed, the command or page that re-derives it, and how well it is verified.
created: 2026-08-03
schema_version: 1
---
# Harness Contract

This bundle consumes harness capabilities rather than rebuilding them, and harness
surfaces move. The per-skill description cap and the skill-listing budget have both
changed, and community material still repeats superseded figures for each. Every
dependency this bundle has on a harness surface is registered below with what is
assumed of it and how that assumption is re-derived.

`scripts/ci/check-harness-contract.py` parses this file. It asserts every entry is
complete and that no other bundle file restates a value guarded here. Detecting that
this bundle has drifted from its own recorded assumptions is that check's job.
Detecting that a documented surface has moved is a human or `audit-skills` job, and
needs a network call this check does not make.

## Boundary with capacity-thresholds.md

The two registers answer different questions and must not duplicate values.

`capacity-thresholds.md` holds ceilings a spec author checks a deliverable count
against while drafting. Its reader is writing a PLAN and wants to know whether the
work brushes a limit.

`harness-contract.md` holds the observed harness values and the command that
re-derives each. Its reader wants to know what this bundle currently believes about
the harness and how sure it is.

Where a fact belongs in both, the threshold entry references the contract entry and
does not restate its value.

## Entry format

Each entry under **Registered surfaces** carries five required fields. A missing
verification status is treated exactly as a missing field.

| Field | Meaning |
|---|---|
| **Surface** | The harness capability depended on. |
| **Version observed** | The harness version, or the date, the value was taken against. |
| **Assumption** | The value or behaviour this bundle relies on. |
| **Re-derivation** | The command or documentation page that establishes it again. |
| **Status** | `observed`, `documented`, or `unverified`. See below. |

An optional **Value guard** field carries a regular expression. Any match for it in
the bundle outside this file fails the check. Use it where a value must live here and
be read from here rather than copied.

**Status meanings.** `observed` means the value was checked first-hand against the
named version. `documented` means it comes from live vendor documentation. `unverified`
means it is inferred or reported and has not been checked. An `unverified` entry is a
legitimate entry, and marking one honestly is the point of the field.

## Registered surfaces

### Per-skill description cap

| Field | Value |
|---|---|
| **Surface** | Combined `description` and `when_to_use` length in the skill listing. |
| **Version observed** | 2026-08-03, against the live Claude Code documentation. |
| **Assumption** | The combined text is truncated at 1,536 characters. The narrower platform API limit is 1,024 characters for `description` alone, and this bundle takes the Claude Code superset per `skill-standard.md`. |
| **Re-derivation** | https://code.claude.com/docs/en/skills - frontmatter reference. |
| **Status** | documented |
| **Value guard** | `1,?536\s*character` |

The claim that this cap changed in Claude Code v2.1.105 from an earlier value of 250
could not be substantiated. The changelog does not reach back far enough and no issue
correlates the current figure to a release. The cap itself is documented and current.
The earlier figure of 250 characters appears to belong to the `/skills` command's
display listing rather than to the context-loading budget, which is a different
surface. Do not record the version history as fact.

### Skill listing budget

| Field | Value |
|---|---|
| **Surface** | The context allowance for the always-loaded skill listing. |
| **Version observed** | 2026-08-03, against the live Claude Code documentation. |
| **Assumption** | The budget scales at 1 per cent of the model's context window. Community sources still repeat a figure of twice that, which the current documentation contradicts. |
| **Re-derivation** | `/context` reports the post-budget size in a live session. `/doctor` estimates the listing cost. `python3 scripts/ci/skill-listing-size.py` prints this bundle's own contribution. |
| **Status** | documented |

### Listing overflow behaviour

| Field | Value |
|---|---|
| **Surface** | What the harness drops when the skill listing exceeds its budget. |
| **Version observed** | 2026-08-03, against the live Claude Code documentation. |
| **Assumption** | Every skill name is always retained. Descriptions are dropped, starting with the skills invoked least, so the most-used skills keep their full text. |
| **Re-derivation** | https://code.claude.com/docs/en/skills - the skill listing section. |
| **Status** | documented |

The consequence this bundle relies on: in a fresh session with no invocation history
the ranking has nothing to rank on, so the skills that matter least are not reliably
the ones whose descriptions get dropped. Overflow is therefore not a graceful
degradation and is treated as a defect to fix rather than a state to tolerate.

### disable-model-invocation: subagent preloading

| Field | Value |
|---|---|
| **Surface** | Whether `disable-model-invocation: true` prevents a skill being preloaded into a subagent. |
| **Version observed** | 2026-08-03, against the live Claude Code documentation. |
| **Assumption** | It does prevent it. A skill preloaded into a pipeline agent must therefore never be delisted. |
| **Re-derivation** | https://code.claude.com/docs/en/skills - the `disable-model-invocation` field description. |
| **Status** | documented |

This is what pins `execute-plan`, `retire`, `write-plan`, `audit-haiku-safe` and
`audit-sufficiency` into the listing. Delisting any of them breaks the pipeline.

### disable-model-invocation: listing removal

| Field | Value |
|---|---|
| **Surface** | Whether `disable-model-invocation: true` removes the skill's description from the per-turn listing. |
| **Version observed** | 2026-08-03, against the live Claude Code documentation. |
| **Assumption** | It does. The description is out of context, and the full skill loads on explicit invocation. This is the mechanism by which delisting recovers listing budget. |
| **Re-derivation** | https://code.claude.com/docs/en/skills - the invocation control table. |
| **Status** | documented |

### disable-model-invocation: reachability of a delisted skill

| Field | Value |
|---|---|
| **Surface** | How a skill carrying `disable-model-invocation: true` can still be invoked. |
| **Version observed** | 2026-08-03. Documentation and reported behaviour disagree. |
| **Assumption** | Treated as unsafe to rely on. The documentation's invocation table states the skill can still be invoked manually and says nothing about the Skill tool being called from a slash-command body. Several Claude Code issues report the opposite, that the flag blocks user slash commands and hides the skill from the menu. Those issues were closed as duplicates without a resolution comment, so whether the behaviour was fixed or the documentation predates a regression is not established. |
| **Re-derivation** | Set the flag on a scratch skill, restart the session, and try both `/<skill-name>` and a command body that calls the Skill tool for it. Nothing short of a live session settles this. |
| **Status** | unverified |

Because this is unverified, no delisted skill in this bundle depends on the Skill tool
being dispatched for it. The maintenance commands under `.claude/commands/` read the
skill body directly instead, which is not a Skill-tool call and cannot be affected by
the flag however the ambiguity resolves.

### Skill frontmatter field set

| Field | Value |
|---|---|
| **Surface** | Which frontmatter keys Claude Code recognises in a SKILL.md. |
| **Version observed** | 2026-08-03, against the live Claude Code documentation. |
| **Assumption** | Recognised: `name`, `description`, `when_to_use`, `argument-hint`, `arguments`, `disable-model-invocation`, `user-invocable`, `allowed-tools`, `disallowed-tools`, `model`, `effort`, `context`, `agent`, `background`, `hooks`, `paths`, `shell`. Unknown keys are ignored silently, with no diagnostic. |
| **Re-derivation** | https://code.claude.com/docs/en/skills - frontmatter reference table. |
| **Status** | documented |

`triggers`, `exclude`, `user_intent` and `required_inputs` are not fields, and
circulating third-party guidance recommends all four. A skill configured with one
fails by doing nothing.

### Skill name collision precedence

| Field | Value |
|---|---|
| **Surface** | How Claude Code resolves two skills installed under the same name. |
| **Version observed** | 2026-08-03, against the live Claude Code documentation. |
| **Assumption** | Precedence runs enterprise, then personal, then project, then bundled. Plugin skills are namespaced and never collide. Nothing resolves two differently-named skills whose descriptions both plausibly match a request, which is left to model judgement on description quality. |
| **Re-derivation** | https://code.claude.com/docs/en/skills - the skill sources section. |
| **Status** | documented |

The second half is the one that bites. A name collision is deterministic and
findable. A description collision is neither, and the only place it is visible is a
view of the whole corpus.

### Cost measurement surfaces

| Field | Value |
|---|---|
| **Surface** | `/doctor` and `/context`, the harness commands that report skill-listing cost. |
| **Version observed** | 2026-08-03. |
| **Assumption** | `/doctor` estimates the skill-listing cost. `/context` reports the post-budget size actually loaded. Between them they answer the cost question, so this bundle does not implement cost measurement and `audit-skills` reports what they give rather than computing its own. |
| **Re-derivation** | Run `/doctor` and `/context` in a live session. |
| **Status** | unverified |

Neither command's output format has been checked first-hand against a current
session. The delegation decision rests on them existing and answering the question,
which is safe. Anything that parses their output is not, and nothing here does.

### Output-style isolation from subagents

| Field | Value |
|---|---|
| **Surface** | Whether a Claude Code output-style reaches a dispatched subagent's own system prompt. |
| **Version observed** | 2026-08-12, against the live Claude Code documentation. |
| **Assumption** | An output-style applies only to the session it is set in. Claude Code documents no mechanism that injects a project or user output-style into a subagent's system prompt. The one related lever, the `--append-subagent-system-prompt` CLI flag, is a launch-time flag rather than a checked-in file, and it applies indiscriminately to every subagent rather than a chosen one. A style set at the orchestrator therefore does not reach the writing subagents that produce this bundle's durable artefacts. |
| **Re-derivation** | https://code.claude.com/docs/en/output-styles and https://code.claude.com/docs/en/sub-agents - dispatch a subagent under a project output-style and inspect its system prompt for the style's text. The documented mechanism list carries nothing that does this. |
| **Status** | documented |

This is why the artefact writing rules are inlined into the writing agent bodies
(`.claude/agents/*.md`) rather than left in an output-style: an output-style cannot
reach the subagent that writes the artefact, so it can shape only the orchestrator's
own conversation. The single source for that inlined block is
`.claude/skills/_shared/artefact-register-agent-block.md`. `scripts/ci/sync-artefact-register.py`
propagates the source into each of the seven writing agents, and its `--check` mode
fails CI when an agent's copy has drifted from the source.

### Sync-managed directory set excludes output-styles

| Field | Value |
|---|---|
| **Surface** | Which `.claude/` subdirectories `plan-foundry-sync` copies into a consumer project. |
| **Version observed** | 2026-08-12, against `BUNDLE_MANAGED_DIRS` in `.claude/skills/_shared/bundle_copy.py`. |
| **Assumption** | The copied set is exactly `skills`, `agents`, `commands`, `hooks`. `.claude/output-styles/` is outside it, so a style file placed there is neither shipped by this bundle nor overwritten by a later sync - it is left alone as an ordinary project-local file, the same way `.claude/writing-style-local.md` is. |
| **Re-derivation** | `BUNDLE_MANAGED_DIRS` in `.claude/skills/_shared/bundle_copy.py`, and Step 3 of `.claude/skills/plan-foundry-sync/workflows/sync.md`. |
| **Status** | observed |

This is why plan_foundry ships no bundled conversational output-style: the copy set
would need to widen before a shipped style file reached a consumer at all, which this
bundle does not do. The user sets their own built-in output-style for a cleaner conversation register.

### AskUserQuestion rendering on Claude Code Mobile

| Field | Value |
|---|---|
| **Surface** | The `AskUserQuestion` tool's rendering on Claude Code Mobile. |
| **Version observed** | 2026-07-24, reported against a live mobile session. |
| **Assumption** | The question and its options do not reliably render, and a selection does not reliably propagate back. Treat the tool as a desktop-only convenience, never the sole channel - prefer plain-text questions carrying the decision-briefing contract instead. Where hard suppression is configured, it is `permissions.deny: ["AskUserQuestion"]` in `settings.json` (a harness config, not skill logic). |
| **Re-derivation** | Invoke `AskUserQuestion` from a live Claude Code Mobile session and inspect whether the question, options, and the returned selection all round-trip correctly. |
| **Status** | observed |

## Maintenance

- Add an entry the moment a bundle file starts depending on a harness behaviour.
  An undocumented dependency is the failure this register exists to prevent.
- Never downgrade a status without changing the value. Moving `documented` to
  `observed` needs a first-hand check recorded in the same edit.
- An `unverified` entry is not a defect to hide. Write the entry, mark it, and name
  what would settle it in the re-derivation field.
- Where a value must be used by code, parse it from this file rather than copying it,
  and add a **Value guard** so a copy fails the check.
