---
title: Deprecation policy
description: How long a deprecated plan_foundry surface survives, how the deprecation is signalled, and the two ledger address spaces (file-path-addressed vs symbol-addressed).
created: 2026-08-17
---

# Deprecation policy (PLAN-AH9, guarantee 4 / gate criterion C7)

This policy states how long a deprecated plan_foundry surface survives and how
the deprecation is signalled, then works through a real case.

## The rule

A deprecated surface must:

1. Carry a ledger entry in `.claude/skills/_shared/bundle-contract.json`'s
   `deprecations` array, read via `preflight.read_deprecations`.
2. Survive at least one minor release carrying a shim before it can be
   removed.
3. Be removed only at a major version.

"Shim-then-delete across a minor release" is the part a consumer actually
experiences. A policy asserting that a surface must survive is not a
mechanism, so the ledger, `shim_body`, and the maintainer-run
`scripts/generate-deprecation-shim.py` supply the mechanism, and a consumer
meets the shim before the surface disappears. Those three mechanise the
shim's content and placement rather than rule 2's release count - nothing
in `scripts/ci/` counts the releases between an entry's `since` and its
`removed_in`, so the grace period is recorded text a maintainer honours
rather than a check that fires.

## Two address spaces

A deprecation ledger entry's `kind` selects which address space its `path`
uses, and that selection changes what the tooling does:

| `kind` | Address | Shim | Quarantine-matched |
|---|---|---|---|
| `skill`, `reference`, `hook` | bundle-relative **file path** | yes | yes |
| `helper` | `file.py::symbol` | **no** | **no** |

**File-path-addressed entries** (`kind` in `skill \| reference \| hook`)
name a real file in the bundle. They get a shim body
(`preflight.shim_body`) written over that path by
`scripts/generate-deprecation-shim.py` at the moment the entry is added,
and they are quarantine-matched: when `plan-foundry-sync` classifies a
path as `gone_upstream` (PLAN-AH7) at the next major, it cross-references
the quarantined path against this ledger and, on a match, reports
`replaced_by` and `note` in the sync report instead of a bare path.

**Symbol-addressed entries** (`kind: helper`) name a function or symbol
inside a file, not a file. A `file.py::symbol` string has no file-level
slot for a shim to occupy, and the string can never equal a quarantined
file path, so such an entry is **never** shim-generated and **never**
offered to the quarantine matcher. The entry is recorded for provenance
alone, read by this policy and by a maintainer deciding whether the symbol
is still needed.

Omitting this distinction would have the shipped policy contradict the only
entry the ledger currently carries, which is `kind: helper`.

## Worked example

The ledger's first real entry, added by this wave:

```json
{
  "path": ".claude/skills/_shared/bundle_copy.py::_is_under_known_subskill",
  "since": "v1.13.0",
  "removed_in": "v2.0.0",
  "replaced_by": "bundle_copy.classify_stale (receipt-backed, PLAN-AH7)",
  "note": "Heuristic fallback that treats a target-only path as a project addition when its top-level subdir is unknown to the bundle. It exists only to carry consumers who hold no install receipt yet ...",
  "kind": "helper"
}
```

`_is_under_known_subskill` is a function inside `bundle_copy.py`, not a
standalone file - PLAN-AH7's `_is_under_known_subskill` fallback exists
only to carry consumers who have no install receipt yet, and it is
superseded once every consumer has synced at least once under the
receipt-backed `classify_stale`. This entry is the **symbol-addressed,
no-shim case** the address-space split above describes: recorded here for
provenance, given no shim, and never offered to the quarantine matcher when
the function is eventually removed at a major. A maintainer deletes the
function directly once the receipt has propagated widely enough, guided by
this ledger entry rather than by memory.

A file-level (shim-generated, quarantine-matched) worked example does not
yet exist in this wave - see "Coverage" below.

## Coverage

The policy and the symbol-addressed worked example above are real and earn
C7. **The file-level shim-and-quarantine path has fixture-only coverage**
until a genuine file-level deprecation exists in the bundle: W4.3's merge
of `plan-foundry-check-current` into `plan-foundry-sync` will be the
first, and it is not yet executed - D7, which gated it, was discharged on
PLAN-AH9's retirement. This limitation is deliberate
and recorded rather than implied away - see PLAN-AH9's Context, "Two
design calls taken 2026-07-28": inventing a file-level deprecation to
serve as the worked example would have been fabricating evidence to
satisfy a gate criterion, which is the precise failure AD2 exists to
prevent.

## Who authors a shim

A shim is written by the maintainer, at the moment a ledger entry is
added, via `scripts/generate-deprecation-shim.py` - a maintainer-run,
repo-local tool that is never shipped to consumers (excluded from
`promote.sh`'s `ALLOWLIST` by construction). Sync does not generate shims
and only reads the ledger to annotate a quarantine report. Promote-time or
sync-time shim generation were both rejected: either would place content
into the shipped bundle or the consumer's tree that the repo itself does
not contain, breaking the invariant that the bundle is the source of
truth.

## See also

- `.claude/skills/_shared/preflight.py` - `read_deprecations`, `shim_body`.
- `scripts/generate-deprecation-shim.py` - the maintainer-run tool that imports
  `shim_body` and writes the shim over the deprecated file's path.
- `.claude/skills/plan-foundry-sync/workflows/sync.md` - the shim-then-delete
  lifecycle and the quarantine cross-reference.
- The v2.0.0 readiness gate, criterion C7 -
  `Workbench/PLAN-AD2_v2-0-0-readiness-gate.md`.
