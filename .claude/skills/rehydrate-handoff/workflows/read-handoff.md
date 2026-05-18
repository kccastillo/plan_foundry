# rehydrate-handoff workflow

Idempotent three-step procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Step 1: Check for handoff file

Read `Workbench/HANDOFF-NEXT-SESSION.md`.
- **If present and non-empty:** PASS, proceed to Step 2.
- **If absent or empty (0 bytes / whitespace-only):** SKIPPED. Surface "no handoff to rehydrate (first session in this project or already rehydrated)." Skip to Step 3 with empty payload.

## Step 2: Parse and surface structured sections

Parse the handoff body by H2 headings. Expected sections (per `handoff-next-session/templates/handoff-template.md`):
- `## What's on main right now`
- `## What's open / queued / paused`
- `## Conventions you must know`
- `## Pitfalls / gotchas`
- `## Resumption checklist`

For each section found, surface to the operator as a named block. Preserve verbatim — do NOT summarise (the handoff is already summarised by its writer; re-summarising loses signal).

If a section is missing or empty, note it ("no `Pitfalls / gotchas` section in this handoff") but do not fail — the template structure is a soft contract.

Also surface the `last_updated:` frontmatter date (or note its absence). If `today - last_updated > 14 days`, prepend a one-line warning: "⚠ Handoff is N days old; prefer recent commits + Workbench/INDEX.md for current state."

## Step 3: Emit pipeline-result

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` (always — read-only with graceful absence handling).
- `payload.handoff_present`: `true` | `false`.
- `payload.handoff_last_updated`: ISO date or `null`.
- `payload.sections_found`: array of H2 heading strings actually present.
- `payload.staleness_warning`: `true` | `false`.
- `payload.handoff_path`: `Workbench/HANDOFF-NEXT-SESSION.md` (or `null` if absent).
- `diagnostics`: any per-step notes.

## Reporting

PASS / SKIPPED / FAIL per step. No FAIL paths exist by design — absent handoff is SKIPPED, present handoff is PASS, malformed handoff still PASSes with a diagnostic note (graceful degradation).
