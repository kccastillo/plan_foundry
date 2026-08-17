---
title: Spec Rigour Heuristics
description: Spec-Draft rigour heuristics (H2/H4/H8) - applied author-side by write-plan during Spec-Draft, and checked auditor-side by audit-sufficiency Lens 8.
created: 2026-08-17
---

# Spec-Draft rigour (per PLAN-AB2)

plan-writer applies the heuristics below during Spec-Draft, before declaring the spec complete. audit-sufficiency also checks all of them (Lens 8 - Rigour heuristics applied, warn-severity).

## H2 - Capacity ceiling check

If a discrete deliverable count exceeds **0.8x** a threshold in `.claude/skills/_shared/capacity-thresholds.md`, the PLAN's Context section MUST acknowledge the brushing and note that a research bot was dispatched to confirm the threshold's current relevance. The unit types in scope are whichever ones that registry currently carries a threshold for, so read the registry rather than a list restated here - an entry marked deferred carries no threshold and nothing fires on it.

**Origin:** Plan B initially specced 49 tools against a ~50-tool MCP degradation threshold, and only a self-critique research bot caught the brushing, which the spec itself should have pre-empted (2026-05-16 hiccup log section H2).

## H4 - Calling-convention checklist (conditional)

**Trigger:** Steps body contains test-runner keywords (`pytest`, `unittest`, `async def`, `asyncio`), API client patterns, or platform-specific behaviour keywords (async/sync boundaries, fixture patterns, mock/patch conventions, OS-specific path handling).

When triggered, the PLAN's Context section MUST enumerate: test-runner async/sync posture, fixture patterns (e.g. `tmp_path` vs `tmpdir`), and any relevant platform conventions - before the Step body is authored. The check is cheap when not triggered, so skip the enumeration entirely if no trigger keywords are present.

**Origin:** Plan B's spec stated "tests are sync" without documenting the async/sync boundary, so the executor had to make a judgement call that the spec should have pre-empted (2026-05-16 hiccup log section H4).

## H8 - Literal-heading discipline

When a Step body specifies that a deliverable must include a named section, the prose MUST use literal heading syntax, not ambiguous prose.

- **Correct:** "The output MUST include a `## Notes` heading."
- **Incorrect:** "The output should have a Notes sub-section." (executor interprets as "content appears somewhere").

**Origin:** Plan A's executor produced an ADVICE doc with L-tier notes integrated inline rather than under a dedicated `## Notes` heading, because the spec said "should have a Notes sub-section" rather than specifying the heading literally (2026-05-16 hiccup log section H8).
