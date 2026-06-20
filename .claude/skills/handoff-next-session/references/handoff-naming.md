# Handoff file naming

Single source of truth for handoff filenames, shared by `handoff-next-session` (write side) and `rehydrate-handoff` (read side). Introduced by PLAN-AE8 to support multiple concurrent thread-scoped handoffs.

## Filename grammar

- **Scoped (per-thread):** `Workbench/HANDOFF-<thread-slug>.md`
  - `<thread-slug>` is lowercase-kebab, no spaces or underscores — e.g. `dungeon-jaquays`, `relationship-jaquays`, `writers-room-format`.
- **Reserved default (unscoped):** `Workbench/HANDOFF-NEXT-SESSION.md`
  - Used when no scope is given. Backward-compatible with all pre-multi-thread behaviour; `NEXT-SESSION` is a reserved scope token and must not be used as a thread slug.

## Discovery

- `rehydrate-handoff` discovers handoffs with the glob `Workbench/HANDOFF-*.md`. Case-insensitive matching is tolerated on read (older hand-written files may be mixed-case); the write side normalises the slug to lowercase-kebab.

## Retire destination

- `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md`, where `<scope>` is the source file's scope (`NEXT-SESSION` for the reserved default). Timestamp-suffixed to avoid collisions with prior retirements.

## Per-scope retire rule (the core invariant)

Writing or retiring scope X touches **only** `HANDOFF-X.md`. No invocation ever reads, moves, or overwrites a *different* scope's handoff. This per-scope (never global) rule is what allows multiple thread handoffs to coexist — it is the entire point of the multi-thread expansion.
