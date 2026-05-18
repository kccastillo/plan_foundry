# rehydrate-handoff workflow

Idempotent four-step procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Step 1: Check for handoff file

Read `Workbench/HANDOFF-NEXT-SESSION.md`.
- **If present and non-empty:** PASS, proceed to Step 2.
- **If absent or empty (0 bytes / whitespace-only):** SKIPPED. Surface "no handoff to rehydrate (first session in this project or already retired)." Skip to Step 4 with empty payload.

## Step 2: Parse and surface structured sections

Parse the handoff body by H2 headings. Expected sections (per `handoff-next-session/templates/handoff-template.md`):
- `## What's on main right now`
- `## What's open / queued / paused`
- `## Conventions you must know`
- `## Pitfalls / gotchas`
- `## Resumption checklist`

For each section found, surface to the operator as a named block. Preserve verbatim — do NOT summarise (the handoff is already summarised by its writer; re-summarising loses signal).

If a section is missing or empty, note it ("no `Pitfalls / gotchas` section in this handoff") but do not fail — the template structure is a soft contract.

Also surface the `last_updated:` (or `created:`) frontmatter date. If `today - last_updated > 14 days`, prepend a one-line warning: "⚠ Handoff is N days old; prefer recent commits + Workbench/INDEX.md for current state."

Also extract any PLAN ID referenced in the title or first H2 section (regex `PLAN-[A-Z]{2}\d`). For each such PLAN ID found, check whether the corresponding file now lives under `Retired/**`. If yes, prepend a one-line note: "ℹ Subject `PLAN-<ID>` is now retired — handoff is likely fully absorbed."

## Step 3: Prompt for retire confirmation

Ask the operator: "Absorbed? Retire HANDOFF to `Retired/HANDOFF-NEXT-SESSION-{YYYYMMDDHHMI}.md`? [y/N]"

- **If `y` (or operator confirms):**
  1. Compute timestamp `YYYYMMDDHHMI` from current UTC.
  2. Destination path: `Retired/HANDOFF-NEXT-SESSION-{YYYYMMDDHHMI}.md`.
  3. Move via `git mv Workbench/HANDOFF-NEXT-SESSION.md <destination>` (the orchestrator runs this in parent context; subagents must defer to parent).
  4. Post-condition verification (AA2 defence-in-depth pattern): assert source absent on disk; assert destination exists, is readable, and non-zero size. If any check fails, return `outcome: exception` with `diagnostics.reason` naming the failed check; do NOT commit.
  5. Commit: `rehydrate-handoff: retired HANDOFF after operator-confirmed absorption → <destination>`. Push subject to push_policy.
  6. PASS.
- **If `N` (or operator defers):** SKIPPED. Surface "HANDOFF left in Workbench/; re-invoke when ready to retire." No file mutation.

## Step 4: Emit pipeline-result

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` (always — read-only with graceful absence handling, retire-on-confirm with verified post-condition).
- `payload.handoff_present`: `true` | `false`.
- `payload.handoff_last_updated`: ISO date or `null`.
- `payload.sections_found`: array of H2 heading strings actually present.
- `payload.staleness_warning`: `true` | `false`.
- `payload.subject_plan_retired`: `true` | `false` | `null` (when no PLAN ID detected).
- `payload.handoff_path`: `Workbench/HANDOFF-NEXT-SESSION.md` (or `null` if absent).
- `payload.retired`: `true` | `false`.
- `payload.retired_path`: `Retired/HANDOFF-NEXT-SESSION-{YYYYMMDDHHMI}.md` (if retired) or `null`.
- `diagnostics`: any per-step notes.

## Reporting

PASS / SKIPPED / FAIL per step. FAIL only on Step 3 post-condition violation (after the operator confirmed retire). Absent handoff is SKIPPED at Step 1; deferred retire is SKIPPED at Step 3.
