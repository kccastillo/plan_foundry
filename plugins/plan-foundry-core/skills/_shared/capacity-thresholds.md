# Capacity Thresholds Registry

Curated list of known capacity ceilings that Spec-Draft authors must check against deliverable counts. Each entry: threshold value, research-source citation, and recommended action when a deliverable count approaches (>0.8×) the threshold.

When a spec's deliverable count exceeds **0.8×** any threshold listed here, the plan-writer MUST surface the brushing explicitly in the PLAN's Context section and dispatch a research bot to confirm the threshold's current relevance.

---

## MCP Tool Count

| Field | Value |
|---|---|
| **Threshold** | ~50 tools (soft degradation boundary) |
| **Degradation mode** | LLM context-window tool-description saturation; model begins missing or misrouting tool calls |
| **Research source** | H2 hiccup retrospective, 2026-05-16 (`Workbench/202605160300_RESEARCH_hiccup-log.md` §H2); self-critique bot research run confirming ~50-tool soft ceiling during Plan B spec review |
| **0.8× trigger** | 40 tools in a single MCP server registration |
| **Recommended action** | Surface in spec Context: "Deliverable tool count N brushes the ~50-tool MCP degradation threshold. Research bot dispatched to confirm threshold relevance for this integration." Dispatch a research subagent to verify the threshold is still current for the Claude Code version in use. |

---

## Schema Table Count

| Field | Value |
|---|---|
| **Threshold** | Deferred — research-anchor if a future ideate session hits schema-table-count degradation |
| **Research source** | None yet; placeholder added for completeness |
| **0.8× trigger** | TBD |
| **Recommended action** | When a future ideate session produces a research-anchored threshold, update this entry with the value, source, and trigger count. |

---

## Context-Window Slice

| Field | Value |
|---|---|
| **Threshold** | Deferred — research-anchor if a future ideate session hits context-window slice degradation |
| **Research source** | None yet; placeholder added for completeness |
| **0.8× trigger** | TBD |
| **Recommended action** | When a future ideate session produces a research-anchored threshold (e.g., token budget for a single plan-pipeline dispatch), update this entry. |

---

## Registry Maintenance

- Add new entries when a hiccup log or ideate session produces a research-anchored threshold.
- Each entry MUST include a research-source citation. Do not add speculative thresholds without a source.
- The `0.8× trigger` value is the alerting floor — not a hard block. The spec author decides whether the threshold is relevant after the research bot confirms.
- This file is referenced by `plan-writer.md` (H2 capacity-ceiling heuristic) and `audit-sufficiency` (Rigour heuristics lens).
