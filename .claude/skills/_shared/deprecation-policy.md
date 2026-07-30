---
asset_id: deprecation-policy
kind: reference
topic_tags: [deprecation, migration, versioning, bundle-contract, v2]
last_consulted: ""
consulted_by: []
---

# Deprecation policy (PLAN-AH9, guarantee 4 / gate criterion C7)

How long a deprecated plan_foundry surface survives, how the deprecation is
signalled, and a worked example against a real case this wave produced.

## The rule

A deprecated surface must:

1. Carry a ledger entry in `.claude/skills/_shared/bundle-contract.json`'s
   `deprecations` array, read via `preflight.read_deprecations`.
2. Survive at least one minor release carrying a shim before it can be
   removed.
3. Be removed only at a major version.

"Shim-then-delete across a minor release" is what makes this load-bearing
rather than paper: a policy asserting a surface must survive is not a
mechanism, and the substrate this wave built (the ledger, `shim_body`, and
the maintainer-run `scripts/generate-deprecation-shim.py`) is what turns
the assertion into something a consumer actually experiences before the
surface disappears.

## Two address spaces

A deprecation ledger entry's `kind` selects which address space its `path`
uses, and this is load-bearing, not descriptive:

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
slot for a shim to occupy, and it can never equal a quarantined file path,
so it is **never** shim-generated and **never** offered to the quarantine
matcher. It is recorded for provenance and read by this policy - and by a
maintainer deciding whether the symbol is still needed - only.

Omitting this distinction would have the shipped policy contradict the one
ledger entry it documents, which carries exactly one entry and it is
`kind: helper`.

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
receipt-backed `classify_stale`. This is the **symbol-addressed, no-shim
case** the address-space split above describes: it is recorded here for
provenance, it will not receive a shim, and it will not be offered to the
quarantine matcher when it is eventually removed at a major - a maintainer
deletes the function directly once the receipt has propagated widely
enough, guided by this ledger entry rather than by memory.

A file-level (shim-generated, quarantine-matched) worked example does not
yet exist in this wave - see "Coverage" below.

## Coverage

The policy and the symbol-addressed worked example above are real and earn
C7. **The file-level shim-and-quarantine path has fixture-only coverage**
until a genuine file-level deprecation exists in the bundle: W4.3's merge
of `plan-foundry-check-current` into `plan-foundry-sync` will be the
first, and it is D7-gated behind this wave. This limitation is deliberate
and recorded rather than implied away - see PLAN-AH9's Context, "Two
design calls taken 2026-07-28": inventing a file-level deprecation to
serve as the worked example would have been fabricating evidence to
satisfy a gate criterion, which is the precise failure AD2 exists to
prevent.

## Who authors a shim

A shim is written by the maintainer, at the moment a ledger entry is
added, via `scripts/generate-deprecation-shim.py` - a maintainer-run,
repo-local tool that is never shipped to consumers (excluded from
`promote.sh`'s `ALLOWLIST` by construction). Sync does not generate shims;
it only reads the ledger to annotate a quarantine report. Promote-time or
sync-time shim generation were both rejected: either would place content
into the shipped bundle or the consumer's tree that the repo itself does
not contain, breaking the invariant that the bundle is the source of
truth.

## See also

- `.claude/skills/_shared/preflight.py` - `read_deprecations`, `shim_body`.
- `scripts/generate-deprecation-shim.py` - the shim's caller.
- `.claude/skills/plan-foundry-sync/workflows/sync.md` - the shim-then-delete
  lifecycle and the quarantine cross-reference.
- `Workbench/PLAN-AD2_v2-0-0-readiness-gate.md` - gate criterion C7.
