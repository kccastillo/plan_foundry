# Handoff file naming

Single source of truth for handoff filenames, shared by `handoff-next-session` (write side) and `rehydrate-handoff` (read side). Introduced by PLAN-AE8 to support multiple concurrent thread-scoped handoffs. Grammar updated by PLAN-AF7 to add the datetime + gist-slug convention (per PLAN-AF6 D1).

## Filename grammar

- **Live (new, per PLAN-AF6 D1):** `Workbench/HANDOFF-YYYYMMDD-hhmm-<slug>.md`
  - `YYYYMMDD-hhmm` is the local write-time datetime, colon-free and lexically sortable — e.g. `HANDOFF-20260712-1430-restructure-mandate.md`. The `hhmm` component uses no colon (Windows-path-safe).
  - `<slug>` is a lowercase-kebab gist summary of the handoff's headline content, authored at write time by the write-time agent, distinct from the thread scope. The slug is a **discovery aid** — it summarises the handoff's headline content so a reader listing `Workbench/` can triage without opening the file — and is **never a substitute** for the exploded handoff body; the full context (motivation + reasoning) still lives in the body per the handoff content contract (per ADVICE-018).
  - The thread scope is preserved in the body banner (per write-handoff.md Step 4) and is NOT required in the filename.
  - The unscoped case still targets the reserved default `HANDOFF-NEXT-SESSION.md` (see below).
- **Reserved default (unscoped):** `Workbench/HANDOFF-NEXT-SESSION.md`
  - Used when no scope is given. Backward-compatible with all pre-multi-thread behaviour; `NEXT-SESSION` is a reserved scope token and must not be used as a gist slug.

## Grammar coexistence (forward-only, per PLAN-AF6 D2)

BOTH grammars are valid and discoverable during coexistence. There is NO bulk rename of existing files:

- **Old grammar:** `HANDOFF-<scope>.md` (e.g. `HANDOFF-dungeon-jaquays.md`) — remains valid; old files keep their names.
- **New grammar:** `HANDOFF-YYYYMMDD-hhmm-<slug>.md` — new files use this form from PLAN-AF7 onward.

The discovery glob `Workbench/HANDOFF-*.md` intentionally spans both grammars. Write-time agents author the new grammar for new handoffs; existing handoffs are read and retired unchanged.

## Discovery

- `rehydrate-handoff` discovers handoffs with the glob `Workbench/HANDOFF-*.md`. Case-insensitive matching is tolerated on read (older hand-written files may be mixed-case); the write side normalises the slug to lowercase-kebab. This glob intentionally spans old `HANDOFF-<scope>.md` and new `HANDOFF-YYYYMMDD-hhmm-<slug>.md` filenames.
- Reads use `encoding='utf-8', errors='replace'` semantics.

## Retire destination

- `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md`, where `<scope>` is derived from the source file (see Retire scope derivation below). Timestamp-suffixed to avoid collisions with prior retirements, including multiple same-day retirements.

## Retire scope derivation

When retiring a handoff, the scope for the destination path is determined as follows:

- **Reserved default (`HANDOFF-NEXT-SESSION.md`):** scope is `NEXT-SESSION`.
- **Old grammar (`HANDOFF-<scope>.md`):** scope is the filename segment after `HANDOFF-`.
- **New datetime grammar (`HANDOFF-YYYYMMDD-hhmm-<slug>.md`):** the filename carries a gist slug, not a thread scope. The scope for the retire destination is recovered from the handoff body's scope banner (per write-handoff.md Step 4). If no banner is present, fall back to the gist slug. This fallback fires only for a malformed new-grammar handoff with no banner; in normal operation, scoped handoffs always write a banner.

## Per-scope retire rule (the core invariant)

Writing or retiring scope X touches **only** the relevant handoff file for that scope. No invocation ever reads, moves, or overwrites a *different* scope's handoff. This per-scope (never global) rule is what allows multiple thread handoffs to coexist — it is the entire point of the multi-thread expansion.
