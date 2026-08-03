---
title: Fable Escalation Policy
description: The single rule set governing when Claude Fable 5 may be dispatched. Escalation only, never selection. Referenced by plan-pipeline dispatch and autonomous-loop rather than restated in each.
created: 2026-07-27
---
# Fable escalation policy

**Scope.** This file is the single source of truth for when Claude Fable 5 (`claude-fable-5`) may be dispatched anywhere in plan_foundry. Skills that dispatch models - `plan-pipeline`, `autonomous-loop` - reference this file rather than restating its rules. Per PLAN-AD2 W0.3.

**Default position: never.** No PLAN, fan-out, or autonomous loop in this repo currently meets the escalation bar below. If you are reading this file while deciding a model tier, the answer is almost certainly Opus 5.

## The five rules

All five must hold before a Fable request is issued. Any one failing means the answer is no.

### 1. Escalation, never selection

Fable is only reachable **after** a recorded Opus 5 attempt at `xhigh` or `max` effort has fallen short, with the shortfall named in writing. It is never chosen at planning time as the model for a task.

**Difficulty is the trigger; importance is not.** A task being high-stakes, consumer-facing, or irreversible does not qualify it. The only qualifying condition is that a frontier attempt was made and demonstrably did not succeed, and the reason is stated - not "the output was disappointing" but what specifically the attempt failed to do.

*Rationale:* importance is judged before the work and is systematically over-claimed; difficulty is observed after an attempt and is falsifiable. Gating on the observable one is what keeps this channel from becoming the default.

### 2. Never in fan-out

A Fable call is never issued from inside a parallel fan-out - not in a `Workflow` `parallel()` or `pipeline()` stage, not across a set of subagents. Fan-out multiplies whatever sits inside it, and this is the most expensive model available.

If a fan-out stage is producing inadequate results, the fix is to re-scope the stage or raise the Opus 5 effort level, not to swap the model inside it.

### 3. A single call, never a loop

One Fable request per escalation. No retry loop, no iterate-until-satisfied, no agentic loop with Fable as the driving model. If one call does not resolve the shortfall named under rule 1, escalate to the human rather than calling again.

*Rationale:* the failure mode this prevents is a loop that silently consumes an unbounded budget while each individual call looks defensible.

### 4. Preconditions checked before dispatch

Two conditions are verified **before** the request is issued, not discovered from the error:

- **30-day data retention is mandatory.** Fable 5 is not available under zero data retention. Under ZDR - or any retention configuration below 30 days - *every* Fable request returns `400 invalid_request_error`, regardless of how well-formed the payload is. A 400 with no visible problem in the request body means checking the organisation's retention configuration first, before debugging the payload.
- **Refusal handling is wired.** See rule 5.

### 5. Refusal handling with a fallback

Fable's safety classifiers can decline a request. A decline is **not an error**: it returns a normal `HTTP 200` with `stop_reason: "refusal"` and a `stop_details` object carrying the policy category. Code that reads `response.content[0]` unconditionally breaks on a refusal, and an orchestrator that only checks HTTP status reads a decline as a stalled pipeline rather than a completed one.

**Branch on `stop_reason` before reading `content`.** Do not branch on `stop_details` - it is informational and can be `null` even on a genuine refusal.

Two shapes of decline:
- **Pre-output:** `content` is empty. Not billed at all - no input tokens, no output tokens, no rate-limit consumption.
- **Mid-stream:** partial output already streamed. That partial *is* billed at normal rates. Discard it; do not treat it as a complete answer.

**Wire the server-side fallback rather than hand-rolling one.** Fallbacks are opt-in - without them a refused request simply stops. Prefer the scalar form, which routes by refusal category and needs no model list to maintain:

```
anthropic-beta: server-side-fallback-2026-07-01
"fallbacks": "default"
```

The older array form (`"fallbacks": [{"model": "claude-opus-4-8"}]` with beta header `server-side-fallback-2026-06-01`) still works, but pins a model that will eventually need migrating. Pairing either header with the other form returns a 400.

## Two things that are not levers

**Thinking cannot be disabled.** Thinking is always on for Fable 5. An explicit `thinking: {"type": "disabled"}` returns a 400 at any effort level, and `{"type": "enabled", "budget_tokens": N}` also returns a 400. Omit the `thinking` parameter entirely. The raw chain of thought is never returned - `display: "summarized"` yields a summary, and the default `"omitted"` leaves the thinking text empty.

The consequence for dispatch: **there is no cheap Fable call.** Every request pays for thinking. `output_config.effort` (`low` through `max`) still modulates depth and is the only cost control available, but it does not produce a low-cost call in the way disabling thinking would on other models.

**Assistant prefill is not supported.** Any pattern that constrains output by prefilling the final assistant turn must be replaced with `output_config.format` (structured outputs) or a system-prompt instruction before a request can be sent.

## Cost context

Fable 5 is `$10 / $50` per million tokens (input / output), against Opus 5 at `$5 / $25`. Escalation is therefore roughly a 2x per-token cost on top of whatever the failed Opus 5 attempt under rule 1 already cost - the true cost of an escalation is both calls, not just the second one.

## Model IDs

- `claude-fable-5` - the general-availability model.
- `claude-mythos-5` - identical capabilities, pricing, and API behaviour; available only to Project Glasswing participants. Use it only if this organisation participates; otherwise `claude-fable-5`.

Never append a date suffix to either ID.

## When the bar is genuinely met

Record the escalation in the PLAN's Executor Notes (or the research report's provenance section) with: the Opus 5 attempt that fell short, its effort level, the named shortfall, and the outcome of the single Fable call. Under PLAN-AD2 D5 the retired handoff chain is this repo's durable history, so an escalation that is not written down did not happen as far as any future session is concerned.
