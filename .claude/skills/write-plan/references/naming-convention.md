---
name: naming-convention
description: Complete naming rules, type tokens, and worked examples for Workbench/ files.
---

# Naming Convention

## Pattern

```
<TYPE>-<ID>_<slug>.md
```

- `<TYPE>` - one of three item tokens (uppercase): `PLAN`, `ADVICE`, `RESEARCH`
- `<ID>` - type-dependent identifier (see below)
- `<slug>` - lowercase-hyphenated descriptor, max 5 words, no spaces

Separators: `-` between TYPE and ID; `_` between ID and slug.

## ID schemes by type

**PLAN - active scheme (2026-05-16 onward): `[A-Z][A-Z][0-9]`** (alpha-alpha-numeric, 6,760 slots). Allocated lexicographically: AA0 -> AA9 -> AB0 -> ... -> ZZ9. Strict-sequential; burned IDs leave permanent gaps. Per PLAN-AA0 plan-of-plans D1+D2.

**PLAN - historical scheme (frozen): `\d{3,4}`** (3-digit zero-padded, expands to 4 when 999 exceeded). PLAN-001..PLAN-037 inclusive. Frozen forever per D3; never re-issued; referenced exactly as historically recorded. Used between 2026-05-12 (PLAN-NNN migration via PR #13) and 2026-05-16 (AA-form migration via PLAN-AA0/AA1/AA3).

**ADVICE - `\d{3,4}`** (3-digit zero-padded). ADVICE never had the collision problem (retire bug only bit PLAN files via plan-retirer); stays numeric. Asymmetry justified by history, not principle.

**RESEARCH - `\d{3,4}`** (3-digit zero-padded). Same rationale as ADVICE.

The canonical allocator is `.claude/skills/write-plan/scripts/next_id.py`. It issues AA-form IDs for PLAN, numeric for ADVICE/RESEARCH. Source of truth: the filesystem (Workbench/ + Retired/), and only the filesystem. See PLAN-AA1's Decision Classification for design lineage.

---

## Type Tokens

| Token | What it is |
|---|---|
| `PLAN` | Actionable task to execute |
| `RESEARCH` | Data drop - feeds a PLAN |
| `ADVICE` | Strategic note (e.g., the human pastes Opus output) - feeds a PLAN |

---

## Special Rules

### Recurring PLAN files
Slug must start with `RECUR-`:
```
PLAN-<NNN>_RECUR-<slug>.md
```
Recurring PLAN files are **persistent** - one file per recurring task. Each completed cycle appends a row to the `## History` table. Do not create a new file each cycle.

### RESEARCH and ADVICE files
Written via the `write-input` skill - see [../../write-input/SKILL.md](../../write-input/SKILL.md) for content rules. The target filename is generated when the PLAN is drafted, so the PLAN can pre-link via `linked_inputs` before the input file exists.

**Forward-only datetime grammar (per PLAN-AF6 D1/D2):** NEW inputs MAY use the unified datetime grammar `TYPE-YYYYMMDD-hhmm-<slug>.md` (colon-free, agent-supplied datetime, no numeric ID - e.g. `ADVICE-20260712-1430-restructure-mandate.md`). The legacy `TYPE-NNN_slug.md` scheme remains valid and `next_id.py` still serves the numeric path. Do NOT bulk-rename existing inputs. Both grammars coexist during transition.

### Counter derivation
At write time, invoke `scripts/next_id.py <TYPE>` to compute the next sequential ID:
```
python .claude/skills/write-plan/scripts/next_id.py PLAN
python .claude/skills/write-plan/scripts/next_id.py ADVICE
python .claude/skills/write-plan/scripts/next_id.py RESEARCH
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
PLAN-001_rewrite-roadmap.md
  -> First PLAN: roadmap rewrite

PLAN-015_RECUR-hormuz-tracker.md
  -> Recurring plan: monthly Hormuz signals tracker update

ADVICE-001_hormuz-portfolio-strategy.md
  -> First ADVICE: Hormuz scenario portfolio strategy

RESEARCH-003_fbt-exemption-apr26.md
  -> Third RESEARCH: FBT exemption status April 2026
```

---

## Directory Listing Behaviour

Files sort lexicographically. Within each type, lower NNN files appeared earlier in the project's history.

---

## Legacy convention (pre-2026-05-13)

Prior to 2026-05-13, files used a 12-digit timestamp prefix:

```
{YYYYMMDDHHMI}_{TYPE}_{slug}.md
```

- `{YYYYMMDDHHMI}` - 12-digit compact datetime: year(4) + month(2) + day(2) + hour(2) + minute(2)
- `{TYPE}` - PLAN, RESEARCH, or ADVICE
- `{slug}` - lowercase-hyphenated descriptor

Example old-format filenames (backtick-quoted to survive future migration tooling):
- `` `202604191430_PLAN_rewrite-roadmap.md` ``
- `` `202604191700_RESEARCH_fbt-exemption-apr26.md` ``
- `` `202604191800_ADVICE_hormuz-portfolio-strategy.md` ``
- `` `PLAN-022_audit-and-index-v2.md` ``

These names are frozen. Read them; never generate them.
