---
name: naming-convention
description: Complete naming rules, type tokens, and worked examples for Workbench/ files.
---

# Naming Convention

## Pattern

```
<TYPE>-<ID>_<slug>.md
```

- `<TYPE>` - a live item token (uppercase): `PLAN` or `INPUT`. `ADVICE` and `RESEARCH` are grandfathered, so read them and never generate them.
- `<ID>` - type-dependent identifier (see below)
- `<slug>` - lowercase-hyphenated descriptor, max 5 words, no spaces

Separators: `-` between TYPE and ID, and `_` between ID and slug.

## ID schemes by type

**PLAN - active scheme (2026-05-16 onward): `[A-Z][A-Z][0-9]`** (alpha-alpha-numeric, 6,760 slots). Allocated lexicographically: AA0 -> AA9 -> AB0 -> ... -> ZZ9. The allocator issues IDs in strict sequence, and burned IDs leave permanent gaps. Per PLAN-AA0 plan-of-plans D1+D2.

**PLAN - historical scheme (frozen): `\d{3,4}`** (3-digit zero-padded, expands to 4 when 999 exceeded). PLAN-001..PLAN-037 inclusive. Frozen forever per PLAN-AA0 D3, never re-issued, and referenced exactly as historically recorded. Used between 2026-05-12 (PLAN-NNN migration via PR #13) and 2026-05-16 (AA-form migration via PLAN-AA0/AA1/AA3).

**INPUT - no ID.** An input carries a datetime in its filename instead: `INPUT-YYYYMMDD-hhmm-<slug>.md`, agent-supplied at write time, colon-free. Nothing is allocated, so nothing can collide.

**ADVICE and RESEARCH - `\d{3,4}`, grandfathered.** Both kinds were collapsed into `INPUT` on 2026-08-03 (PLAN-AJ3). Existing files under either token stay where they are and stay readable. `next_id.py` keeps both tokens because the allocator derives from the filesystem and stays correct for that space, but nothing calls the allocator for an input any more.

The canonical allocator is `.claude/skills/write-plan/scripts/next_id.py`, which issues AA-form IDs for PLAN. The source of truth is the filesystem (Workbench/ + Retired/), and only the filesystem. See PLAN-AA1's Decision Classification for design lineage.

---

## Type Tokens

| Token | What it is |
|---|---|
| `PLAN` | Actionable task to execute |
| `INPUT` | Context artefact - findings, a data drop or a strategic note - that feeds a PLAN |
| `RESEARCH` | Grandfathered and read-only, superseded by `INPUT` on 2026-08-03 |
| `ADVICE` | Grandfathered and read-only, superseded by `INPUT` on 2026-08-03 |

---

## Special Rules

### Recurring PLAN files
Slug must start with `RECUR-`. `<ID>` is an ordinary PLAN ID drawn from the active AA-form scheme, so a new recurring PLAN is named the same way as any other PLAN:
```
PLAN-<ID>_RECUR-<slug>.md
```
Recurring PLAN files are **persistent** - one file per recurring task. Each completed cycle appends a row to the `## History` table. Do not create a new file each cycle.

### Input files
Written via the `write-input` skill - see [../../write-input/SKILL.md](../../write-input/SKILL.md) for content rules. The target filename is generated when the PLAN is drafted, so the PLAN can pre-link via `linked_inputs` before the input file exists.

**Datetime grammar (per PLAN-AF6 D1/D2, made the only form by PLAN-AJ3):** a new input is written as `INPUT-YYYYMMDD-hhmm-<slug>.md` - colon-free, agent-supplied datetime, no numeric ID. Grandfathered `ADVICE-*` and `RESEARCH-*` files remain valid under either the `TYPE-NNN_slug.md` or the `TYPE-YYYYMMDD-hhmm-<slug>.md` grammar. Do not bulk-rename those files.

### Counter derivation
At write time, invoke `scripts/next_id.py <TYPE>` to compute the next sequential ID:
```
python .claude/skills/write-plan/scripts/next_id.py PLAN
```
The script scans `Workbench/` and `Retired/` for existing files of that type and prints the next ID. An input needs no such call - its filename carries a datetime.

The `ADVICE` and `RESEARCH` tokens still resolve, for the grandfathered space only. Do not use them to name a new file.

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
PLAN-AA6_RECUR-monthly-claude-md-audit.md
  -> Recurring plan under the active AA-form scheme: monthly CLAUDE.md audit

PLAN-001_rewrite-roadmap.md
  -> Frozen historical scheme: the first PLAN, a roadmap rewrite. Read this
     form, and never generate it - the allocator issues AA-form only

INPUT-20260803-1430-hormuz-portfolio-strategy.md
  -> Input written 2026-08-03 at 14:30: Hormuz scenario portfolio strategy

RESEARCH-003_fbt-exemption-apr26.md
  -> Grandfathered: FBT exemption status April 2026
```

---

## Directory Listing Behaviour

Files sort lexicographically, so within each type a lower ID sorts earlier. Because the allocator issues IDs in strict sequence, a lower ID was also allocated earlier in the project's history. The two PLAN schemes interleave predictably under that sort: every frozen numeric ID sorts before every AA-form ID, because a digit sorts before a letter.

---

## Legacy convention (pre-2026-05-13)

Before 2026-05-13, files used a 12-digit timestamp prefix:

```
{YYYYMMDDHHMI}_{TYPE}_{slug}.md
```

- `{YYYYMMDDHHMI}` - 12-digit compact datetime: year(4) + month(2) + day(2) + hour(2) + minute(2)
- `{TYPE}` - PLAN, RESEARCH, or ADVICE (all three tokens appear in this frozen form)
- `{slug}` - lowercase-hyphenated descriptor

Example old-format filenames (backtick-quoted to survive future migration tooling):
- `` `202604191430_PLAN_rewrite-roadmap.md` ``
- `` `202604191700_RESEARCH_fbt-exemption-apr26.md` ``
- `` `202604191800_ADVICE_hormuz-portfolio-strategy.md` ``
- `` `PLAN-022_audit-and-index-v2.md` ``

These names are frozen, so read them and never generate them.
