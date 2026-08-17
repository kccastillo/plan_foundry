---
title: Capacity Thresholds
description: Registry of known capacity ceilings consulted by plan-writer during Spec-Draft to flag deliverable counts brushing capacity boundaries.
created: 2026-05-26
schema_version: 1
---
# Capacity Thresholds Registry

This registry lists the known capacity ceilings that Spec-Draft authors must check deliverable counts against. Each entry that records a threshold carries the threshold value, a research-source citation, and the recommended action when a deliverable count approaches (>0.8x) it. A deferred entry carries none of the three. It names a unit type that has been considered and has no research-anchored ceiling yet, so no count can brush it and nothing fires on it.

When a spec's deliverable count exceeds **0.8x** any threshold listed here, the plan-writer MUST surface the brushing explicitly in the PLAN's Context section and dispatch a research bot to confirm the threshold's current relevance.

---

## MCP Tool Count

| Field | Value |
|---|---|
| **Threshold** | ~50 tools (soft degradation boundary) |
| **Degradation mode** | LLM context-window tool-description saturation, after which the model begins missing or misrouting tool calls |
| **Research source** | H2 hiccup retrospective, 2026-05-16 (`Retired/202605160300_RESEARCH_hiccup-log.md` section H2), plus a self-critique bot research run confirming the ~50-tool soft ceiling during Plan B spec review |
| **0.8x trigger** | 40 tools in a single MCP server registration |
| **Recommended action** | Surface in spec Context: "Deliverable tool count N brushes the ~50-tool MCP degradation threshold. Research bot dispatched to confirm threshold relevance for this integration." Dispatch a research subagent to verify the threshold is still current for the Claude Code version in use. |

---

## Skill Listing Budget

| Field | Value |
|---|---|
| **Threshold** | The always-loaded skill listing is budgeted at a fraction of the model's context window. The live figure, the overflow behaviour and the per-skill description cap are registered in [harness-contract.md](harness-contract.md) with the version each was observed against. Read them from there. |
| **Degradation mode** | Silent. Past the budget the harness keeps every skill name and drops descriptions, starting with the skills invoked least. In a fresh session there is no invocation history to rank on, so the descriptions dropped are not reliably the ones that matter least. Nothing reports the drop. |
| **Research source** | Ideation on skill authoring and corpus curation, 2026-08-03. The bundle's own name-plus-description total was measured that day and already exceeded the budget on a 1M-window model before a consumer added anything. |
| **0.8x trigger** | Run `python3 scripts/ci/skill-listing-size.py`. The figure is re-derived by that command and is deliberately not recorded anywhere on disk. A spec that adds a skill checks the current total against the registered budget rather than against a number in this table. |
| **Recommended action** | Surface in spec Context: every skill this spec adds spends listing budget in every project that installs the bundle, permanently and whether or not the skill is used. Name what the spec recovers to offset that cost - a tightened description, or a delisted skill. Delisting is `disable-model-invocation: true`, which also blocks subagent preloading and is therefore unavailable for any skill an agent preloads. |

---

## Schema Table Count

| Field | Value |
|---|---|
| **Threshold** | Deferred - research-anchor if a future ideate session hits schema-table-count degradation |
| **Research source** | None yet. This entry is a placeholder added for completeness |
| **0.8x trigger** | TBD |
| **Recommended action** | When a future ideate session produces a research-anchored threshold, update this entry with the value, source, and trigger count. |

---

## Context-Window Slice

| Field | Value |
|---|---|
| **Threshold** | Deferred - research-anchor if a future ideate session hits context-window slice degradation |
| **Research source** | None yet. This entry is a placeholder added for completeness |
| **0.8x trigger** | TBD |
| **Recommended action** | When a future ideate session produces a research-anchored threshold (e.g., token budget for a single plan-pipeline dispatch), update this entry. |

---

## Boundary with harness-contract.md

This registry holds ceilings a spec author checks a deliverable count against while
drafting. Its reader is writing a PLAN and wants to know whether the work brushes a
limit.

[harness-contract.md](harness-contract.md) holds the observed harness values and the
command that re-derives each. Its reader wants to know which harness values this
bundle relies on and how well each one is verified.

Where a fact belongs in both, the entry here references the contract entry and does
not restate its value. A threshold recorded only in the contract would never reach a
spec author, and a value copied into both goes stale in one of them.

## Registry Maintenance

- Add new entries when a hiccup log or ideate session produces a research-anchored threshold.
- Each entry that records a threshold value MUST include a research-source citation. Do not add a speculative threshold without a source. A deferred entry is the alternative to a speculative one - it records the unit type and carries no value and no citation, and it becomes a real entry only when a hiccup log or ideate session supplies both.
- The `0.8x trigger` value is the alerting floor - not a hard block. The spec author decides whether the threshold is relevant after the research bot confirms.
- This file is referenced by `plan-writer.md` (H2 capacity-ceiling heuristic), `_shared/spec-rigour-heuristics.md` (H2), and `audit-sufficiency` (Lens 8, Rigour heuristics applied).
