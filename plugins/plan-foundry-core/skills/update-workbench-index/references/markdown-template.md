# INDEX.md Template Specification

Documents the sections of `Workbench/INDEX.md` in canonical order. The `build_index.py` script renders these sections deterministically from PLAN frontmatter and `.audit/` data.

---

## Section Order

1. [Header](#1-header)
2. [Summary](#2-summary)
3. [Kanban](#3-kanban)
4. [Alerts](#4-alerts)
5. [Threads](#5-threads)
6. [Dependency Graph](#6-dependency-graph)
7. [Recent Activity](#7-recent-activity)
8. [Recently Retired](#8-recently-retired)

---

## 1. Header

```markdown
# Workbench INDEX

_Generated: <ISO-8601 UTC timestamp> by build_index.py v1_

This document is a deterministic projection of all PLAN files in `Workbench/`. 
Regenerated automatically after every phase transition. 
Do not edit manually — changes will be overwritten.
```

**Purpose:** Identifies the file as auto-generated and gives its provenance.

---

## 2. Summary

A quick-glance table of aggregate counts.

```markdown
## Summary

| Metric | Count |
|---|---|
| Total PLANs | 25 |
| Active (non-terminal) | 8 |
| Terminal (done/cancelled/etc.) | 17 |
```

**Terminal statuses:** `done`, `cancelled`, `partially-complete`, `closed`.

---

## 3. Kanban

The main kanban view. PLANs are grouped by `pipeline_phase`. PLANs with terminal `status` are moved to the Done/Terminal bucket regardless of their `pipeline_phase` value.

```markdown
## Kanban

PLANs grouped by `pipeline_phase`. Terminal-status PLANs appear in the Done column regardless of phase.

### Drafting (N)

| Plan ID | Title | Status | Priority | Assigned |
|---|---|---|---|---|
| 202605121430_PLAN_... | Some plan title... | in-progress | high | sonnet |

### Drafted (N)

...

### Checked (N)

...

### Executing (N)

...

### Outcome-Verifying (N)

...

### Complete (N)

...

### Done / Terminal (N)

| Plan ID | Title | Status | Priority | Assigned |
|---|---|---|---|---|
...
```

**Sort order within each phase:** descending by `plan_id` (newest first by timestamp prefix).
**Title truncation:** titles longer than 60 characters are truncated with `...`.
**Done bucket:** shows the most recent 20 terminal PLANs; remainder indicated with "... and N more".

---

## 4. Alerts

Eight subsections, one per alert category. Each section always appears (even if empty).

```markdown
## Alerts

_N alert(s) detected._

### Stuck Audits (N)

- **202605121430_PLAN_...**: Audit iterations: sufficiency=3, plan_safety=0

### Long Blocked (N)

_None._

### Recurring Blockers (N)

...

### Orphaned Audit Files (N)

...

### Circular Dependencies (N)

...

### Verification Pending Too Long (N)

...

### Orphaned Threads (N)

...

### Malformed Frontmatter (N)

...
```

**Alert section headers** (in canonical order):
1. Stuck Audits
2. Long Blocked
3. Recurring Blockers
4. Orphaned Audit Files
5. Circular Dependencies
6. Verification Pending Too Long
7. Orphaned Threads
8. Malformed Frontmatter

**Empty state:** `_None._` (not omitted).

---

## 5. Threads

Groups PLANs by `closes_thread` and `advances_thread` values.

```markdown
## Threads

| Thread ID | Status | Plans | Closed By |
|---|---|---|---|
| T01 | open | 202605111200_PLAN_..., 202605111800_PLAN_... | — |
| T02 | closed | 202605020000_PLAN_... | 202605020000_PLAN_... |
```

**Empty state:** `_No threads defined._`
**Status values:** `open` (no plan with `status: done` closes this thread) or `closed` (a done plan has `closes_thread: <id>`).

---

## 6. Dependency Graph

Text-based representation of `triggers_plans` and `blocked_by` edges. Not a Mermaid diagram (Mermaid rendering deferred to future dev).

```markdown
## Dependency Graph

```
  202605111200_PLAN_plugin-extraction → 202605111700_PLAN_phase-0  (triggers)
  202605111200_PLAN_plugin-extraction → 202605111800_PLAN_phase-1  (triggers)
  202605111800_PLAN_phase-1 ⊣ 202605111900_PLAN_phase-2-claude-md  (blocks)
```
```

**Arrow conventions:**
- `→` for `triggers` edges (parent triggers child)
- `⊣` for `blocks` edges (blocker blocks blocked plan)

**Empty state:** `_No dependencies defined._`

---

## 7. Recent Activity

Last 10 `plan-pipeline:` commits from `git log`.

```markdown
## Recent Activity

| SHA | Date | Commit Message |
|---|---|---|
| `a1b2c3d` | 2026-05-13 | plan-pipeline: complete 202605121430_PLAN_... |
| `e4f5a6b` | 2026-05-12 | plan-pipeline: update-workbench-index |
```

**Empty state:** `_No recent plan-pipeline commits found._`
**Date format:** `YYYY-MM-DD` (date portion of ISO timestamp only).
**Message truncation:** messages longer than 80 characters are truncated with `...`.

---

## 8. Recently Retired

The 10 most recently retired PLANs, read from `Retired/` directory.

```markdown
## Recently Retired

| Plan ID | Title |
|---|---|
| 202605011440_PLAN_dogfood-plan-pipeline | Dogfood plan-pipeline against a real small target |
| 202605011430_PLAN_create-plan-pipeline-skill | Create plan-pipeline orchestrator skill |
```

**Sort order:** descending by filename (newest first).
**Count:** last 10 only.
**Empty state:** `_No retired PLANs found._`
**Missing Retired/ directory:** `_Retired/ directory does not exist._`

---

## Full example (abridged)

```markdown
# Workbench INDEX

_Generated: 2026-05-13T10:00:00Z by build_index.py v1_

...

## Summary

| Metric | Count |
|---|---|
| Total PLANs | 3 |
| Active (non-terminal) | 2 |
| Terminal (done/cancelled/etc.) | 1 |

## Kanban

PLANs grouped by `pipeline_phase`. Terminal-status PLANs appear in the Done column regardless of phase.

### Drafting (0)

_No PLANs in this phase._

### Drafted (1)

| Plan ID | Title | Status | Priority | Assigned |
|---|---|---|---|---|
| PLAN-022_audit-and-index-v2 | Audit schema v2, INDEX projection... | in-progress | high | sonnet |

...

## Alerts

_2 alert(s) detected._

### Stuck Audits (0)

_None._

...

### Malformed Frontmatter (2)

- **PLAN-001_rewrite-roadmap**: Missing schema_version field. Expected schema_version: 2.
- **PLAN-002_adapt-imported-skills**: Missing schema_version field. Expected schema_version: 2.

## Threads

_No threads defined._

## Dependency Graph

```
  PLAN-022_audit-and-index-v2 → PLAN-023_executor-heartbeat  (triggers)
  PLAN-022_audit-and-index-v2 → PLAN-024_severity-classified-human-surface  (triggers)
```

## Recent Activity

| SHA | Date | Commit Message |
|---|---|---|
| `abc1234` | 2026-05-13 | plan-pipeline: complete PLAN-022_audit-and-index-v2 |

## Recently Retired

_No retired PLANs found._
```
