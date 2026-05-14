---
name: naming-convention
description: Complete naming rules, type tokens, and worked examples for Workbench/ files.
---

# Naming Convention

## Pattern

```
<TYPE>-<NNN>_<slug>.md
```

- `<TYPE>` — one of three item tokens (uppercase): `PLAN`, `ADVICE`, `RESEARCH`
- `<NNN>` — 3-digit zero-padded sequential counter, per type (expand to 4 digits only when count exceeds 999)
- `<slug>` — lowercase-hyphenated descriptor, max 5 words, no spaces

Separators: `-` between TYPE and number; `_` between number and slug.

---

## Type Tokens

| Token | What it is |
|---|---|
| `LOG` | Monthly rollup log — special case, retains timestamp convention (see below) |
| `PLAN` | Actionable task to execute |
| `RESEARCH` | Data drop — feeds a PLAN |
| `ADVICE` | Strategic note (e.g., the human pastes Opus output) — feeds a PLAN |

---

## Special Rules

### Monthly LOG files
LOG files retain the timestamp convention — they are aggregates, not items:
```
{YYYYMM}010000_LOG_{YYYYMM}.md
```
This makes them predictable and lexicographically first in the month's directory listing.

### Recurring PLAN files
Slug must start with `RECUR-`:
```
PLAN-<NNN>_RECUR-<slug>.md
```
Recurring PLAN files are **persistent** — one file per recurring task. Each completed cycle appends a row to the `## History` table. Do not create a new file each cycle.

### RESEARCH and ADVICE files
Written via the `write-input` skill — see [../../write-input/SKILL.md](../../write-input/SKILL.md) for content rules. The target filename is generated when the PLAN is drafted, so the PLAN can pre-link via `linked_inputs` before the input file exists.

### Counter derivation
At write time, invoke `scripts/next_id.py <TYPE>` to compute the next sequential ID:
```
python "${CLAUDE_PLUGIN_ROOT:-plugins/plan-foundry-core}/skills/write-plan/scripts/next_id.py" PLAN
python "${CLAUDE_PLUGIN_ROOT:-plugins/plan-foundry-core}/skills/write-plan/scripts/next_id.py" ADVICE
python "${CLAUDE_PLUGIN_ROOT:-plugins/plan-foundry-core}/skills/write-plan/scripts/next_id.py" RESEARCH
```
The script scans `Workbench/` and `Retired/` for existing `<TYPE>-NNN_*.md` files, computes `max(NNN) + 1`, and prints the zero-padded result.

### Slugs
- Lowercase, hyphenated
- Max 5 words
- Descriptive enough to understand without opening the file
- No spaces, no underscores (hyphens only)

---

## Reference Style

In prose and frontmatter cross-references, use the short form:
- `PLAN-005` (not the full filename)
- Full filename only when disambiguation is needed (e.g. in `linked_inputs` frontmatter list)

---

## Worked Examples

```
202604010000_LOG_202604.md
  → April 2026 monthly log (first-of-month timestamp; LOG convention unchanged)

PLAN-001_rewrite-roadmap.md
  → First PLAN: roadmap rewrite

PLAN-015_RECUR-hormuz-tracker.md
  → Recurring plan: monthly Hormuz signals tracker update

ADVICE-001_hormuz-portfolio-strategy.md
  → First ADVICE: Hormuz scenario portfolio strategy

RESEARCH-003_fbt-exemption-apr26.md
  → Third RESEARCH: FBT exemption status April 2026

202605010000_LOG_202605.md
  → May 2026 monthly log
```

---

## Directory Listing Behaviour

Files sort lexicographically. Within each type, lower NNN files appeared earlier in the project's history. LOG files (timestamp-prefixed) sort before all TYPE-NNN files of the same month.

---

## Legacy convention (pre-2026-05-13)

Prior to 2026-05-13, files used a 12-digit timestamp prefix:

```
{YYYYMMDDHHMI}_{TYPE}_{slug}.md
```

- `{YYYYMMDDHHMI}` — 12-digit compact datetime: year(4) + month(2) + day(2) + hour(2) + minute(2)
- `{TYPE}` — LOG, PLAN, RESEARCH, or ADVICE
- `{slug}` — lowercase-hyphenated descriptor

Example old-format filenames (backtick-quoted to survive future migration tooling):
- `` `202604191430_PLAN_rewrite-roadmap.md` ``
- `` `202604191700_RESEARCH_fbt-exemption-apr26.md` ``
- `` `202604191800_ADVICE_hormuz-portfolio-strategy.md` ``
- `` `PLAN-022_audit-and-index-v2.md` ``

The migration script (`scripts/migrate_plan_ids.py`) was used on 2026-05-13 to rename all existing files. This appendix is retained for historical reference. The legacy appendix is explicitly excluded from pass-3 rewrites in the migration tooling.
