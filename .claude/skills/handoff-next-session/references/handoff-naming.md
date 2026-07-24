# Artefact file naming

Single source of truth for datetime-stamped artefact filenames, shared by `handoff-next-session` (write side), `rehydrate-handoff` (read side), and `raise-foundry-request` (write side). Introduced by PLAN-AE8 for handoff files; extended by PLAN-AF7 to add the datetime + gist-slug convention (per PLAN-AF6 D1); broadened by PLAN-AH0 to cover FOUNDRYREQ artefacts and the shared validator contract (D6).

## Filename grammar

### HANDOFF

- **Live (new, mandatory for all new writes, per PLAN-AF6 D1 + PLAN-AH0 D1):** `Workbench/HANDOFF-YYYYMMDD-hhmm-<slug>.md`
  - `YYYYMMDD-hhmm` is the local write-time datetime, colon-free and lexically sortable — e.g. `HANDOFF-20260712-1430-restructure-mandate.md`. The `hhmm` component uses no colon (Windows-path-safe).
  - `<slug>` is a lowercase-kebab gist summary of the handoff's headline content, authored at write time by the write-time agent, distinct from the thread scope. The slug is a **discovery aid** — it summarises the handoff's headline content so a reader listing `Workbench/` can triage without opening the file — and is **never a substitute** for the exploded handoff body; the full context (motivation + reasoning) still lives in the body per the handoff content contract (per ADVICE-018).
  - The thread scope is preserved in the body banner (per write-handoff.md Step 4) and is NOT required in the filename.
  - **There is no unscoped fixed-default write target.** An unscoped handoff composes a datetime+slug name just as a scoped handoff does. `HANDOFF-NEXT-SESSION.md` is a **legacy read/retire-only** form — it is discovered, surfaced, and retired on the existing path, but is never written as a new handoff.

### FOUNDRYREQ

- **Live grammar (per PLAN-AH0 D2, D3):** `Workbench/FOUNDRYREQ-<origin>-YYYYMMDD-hhmm-<slug>.md`
  - `<origin>` identifies the originating repo or workspace. It is derived at write time from `git remote get-url origin` basename (e.g. `my-project` from `https://github.com/acme/my-project.git`), falling back to the working-directory name when no remote is configured (D3).
  - `YYYYMMDD-hhmm` is the local write-time datetime — colon-free, Windows-path-safe, lexically sortable.
  - `<slug>` is a lowercase-kebab gist summary of the request's headline content.
  - The `NNN` sequential counter is deliberately absent: consumer repos cannot reach this repo's `next_id.py` allocator, so self-naming via origin + datetime + slug gives each request a globally unique, autonomous name (D4).

## Grammar coexistence (forward-only, per PLAN-AF6 D2)

BOTH HANDOFF grammars are valid and discoverable during coexistence. There is NO bulk rename of existing files:

- **Old grammar:** `HANDOFF-<scope>.md` (e.g. `HANDOFF-dungeon-jaquays.md`) — remains valid; old files keep their names.
- **Reserved default (legacy read/retire-only):** `HANDOFF-NEXT-SESSION.md` — still discovered and retired using the `NEXT-SESSION` scope token; never written as a new handoff from PLAN-AH0 D1 onward.
- **New grammar:** `HANDOFF-YYYYMMDD-hhmm-<slug>.md` — all new handoffs use this form.

Existing `OBSERVATION-*` files written by the prior observation skill remain valid and are never bulk-renamed. New requests use the `FOUNDRYREQ` grammar from PLAN-AH0 D2 onward.

The discovery glob `Workbench/HANDOFF-*.md` intentionally spans all HANDOFF forms. Write-time agents author the new grammar for new handoffs; existing handoffs are read and retired unchanged.

## Discovery

- `rehydrate-handoff` discovers handoffs with the glob `Workbench/HANDOFF-*.md`. Case-insensitive matching is tolerated on read (older hand-written files may be mixed-case); the write side normalises the slug to lowercase-kebab. This glob intentionally spans old `HANDOFF-<scope>.md`, legacy `HANDOFF-NEXT-SESSION.md`, and new `HANDOFF-YYYYMMDD-hhmm-<slug>.md` filenames.
- Reads use `encoding='utf-8', errors='replace'` semantics.

## Retire destination

- **HANDOFF:** `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md`, where `<scope>` is derived from the source file (see Retire scope derivation below). Timestamp-suffixed to avoid collisions with prior retirements, including multiple same-day retirements.
- **FOUNDRYREQ:** `Retired/FOUNDRYREQ-<origin>-<datetime>-<slug>-{YYYYMMDDHHMI}.md` — same timestamp-suffix pattern.
- **OBSERVATION (legacy):** `Retired/OBSERVATION-<datetime>-<slug>-{YYYYMMDDHHMI}.md` — unchanged from prior behaviour.

## Retire scope derivation

When retiring a handoff, the scope for the destination path is determined as follows:

- **Reserved default (`HANDOFF-NEXT-SESSION.md`):** scope is `NEXT-SESSION`.
- **Old grammar (`HANDOFF-<scope>.md`):** scope is the filename segment after `HANDOFF-`.
- **New datetime grammar (`HANDOFF-YYYYMMDD-hhmm-<slug>.md`):** the filename carries a gist slug, not a thread scope. The scope for the retire destination is recovered from the handoff body's scope banner (per write-handoff.md Step 4). If no banner is present, fall back to the gist slug. This fallback fires only for a malformed new-grammar handoff with no banner; in normal operation, scoped handoffs always write a banner.

## Per-scope retire rule (the core invariant)

Writing or retiring scope X touches **only** the relevant handoff file for that scope. No invocation ever reads, moves, or overwrites a *different* scope's handoff. This per-scope (never global) rule is what allows multiple thread handoffs to coexist — it is the entire point of the multi-thread expansion.

## Validator contract (D5 — shared, per PLAN-AH0)

The shared validator at `.claude/skills/_shared/validate_artefact_filename.py` classifies every HANDOFF, FOUNDRYREQ, and OBSERVATION basename into one of four classes:

| Class | Meaning | CI behaviour |
|---|---|---|
| `conforming` | Matches a new-grammar pattern exactly (correct datetime, slug present, no colon) | Silent / pass |
| `legacy_permitted` | A recognised legacy form (see list below) — valid on read, never a new write target | Silent / pass |
| `malformed` | Clearly attempts the new grammar but is broken (missing datetime, missing slug, colon in datetime) | `error` — fails CI |

**Legacy-permitted forms:**
- `HANDOFF-NEXT-SESSION.md` — the reserved unscoped default
- `HANDOFF-<scope>.md` — old grammar (one hyphen-separated segment after `HANDOFF-`, not a datetime)
- `HANDOFF-<scope>-<YYYYMMDDHHMI>.md` — the retire-destination timestamp form encountered under `Retired/`
- `OBSERVATION-<datetime>-<slug>.md` — legacy observation output; never rewritten

A name that matches none of the above patterns and is not a new-grammar conforming file is treated as not-subject (e.g. `INDEX.md`, `PLAN-AH0_…`) and silently skipped — not `malformed`. Only a name that *attempts* a new-grammar datetime segment but is malformed (colon present, datetime component wrong length, slug absent) earns `malformed`.
