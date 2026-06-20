# rehydrate-handoff workflow

Idempotent procedure. Each step PASSes, SKIPPEDs, or FAILs. See [../../handoff-next-session/references/handoff-naming.md](../../handoff-next-session/references/handoff-naming.md) for the filename grammar.

## Step 1: Discover handoff files and select one

Glob `Workbench/HANDOFF-*.md` (case-insensitive; this matches the reserved default `HANDOFF-NEXT-SESSION.md` and any thread-scoped `HANDOFF-<scope>.md`). Ignore zero-byte / whitespace-only files.

- **If zero non-empty handoffs:** SKIPPED. Surface "no handoff to rehydrate (first session in this project or all already retired)." Skip to Step 4 with empty payload.
- **If exactly one:** select it. PASS, proceed to Step 2.
- **If more than one:** surface a selection list — for each handoff show its scope (derived from the filename), last-modified date, and the title line (first `# ` heading). Ask the operator which to surface/resume. Do NOT dump every body. Once the operator picks, select that file. PASS, proceed to Step 2 for the selected file. (The operator may ask to surface several in sequence — re-run Steps 2–3 per selection.)

The resolved scope of the selected file (`NEXT-SESSION` for the reserved default, else the `<scope>` slug) is used by the retire step.

## Step 2: Parse and surface structured sections

Parse the **selected** handoff body by H2 headings. Expected sections (per `handoff-next-session/templates/handoff-template.md`, which is a forward-only action brief):
- `## Next steps` (the actionable spine — always present)
- `## Blocking decisions` (optional)
- `## Constraints & do-nots` (optional)
- `## Where things live` (optional)

For each section found, surface to the operator as a named block. Preserve verbatim — do NOT summarise (the handoff is already a curated forward brief; re-summarising loses signal). Surface `## Next steps` first.

If a section is missing or empty, do not note it as a gap and do not fail — the writer deletes empty sections by design (only `## Next steps` is guaranteed). The structure is a soft contract; actionability is the real one.

Also surface the `last_updated:` (or `created:`) frontmatter date. If `today - last_updated > 14 days`, prepend a one-line warning: "⚠ Handoff is N days old; prefer recent commits + Workbench/INDEX.md for current state."

Also extract any PLAN ID referenced in the title or first H2 section (regex `PLAN-[A-Z]{2}\d`). For each such PLAN ID found, check whether the corresponding file now lives under `Retired/**`. If yes, prepend a one-line note: "ℹ Subject `PLAN-<ID>` is now retired — handoff is likely fully absorbed."

## Step 3: Prompt for retire confirmation

Let `<scope>` be the selected file's scope (`NEXT-SESSION` for the reserved default) and `<src>` its path.

Ask the operator: "Absorbed? Retire this handoff (`<src>`) to `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md`? [y/N]"

- **If `y` (or operator confirms):**
  1. Compute timestamp `YYYYMMDDHHMI` from current UTC.
  2. Destination path: `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md`.
  3. Move via `git mv <src> <destination>` (the orchestrator runs this in parent context; subagents must defer to parent). Only the selected file is moved — never a sibling handoff.
  4. Post-condition verification (AA2 defence-in-depth pattern): assert source absent on disk; assert destination exists, is readable, and non-zero size. If any check fails, return `outcome: exception` with `diagnostics.reason` naming the failed check; do NOT commit.
  5. Commit: `rehydrate-handoff: retired HANDOFF-<scope> after operator-confirmed absorption → <destination>`. Push subject to push_policy.
  6. PASS.
- **If `N` (or operator defers):** SKIPPED. Surface "handoff left in Workbench/; re-invoke when ready to retire." No file mutation.

## Step 4: Emit pipeline-result

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` (always — read-only with graceful absence handling, retire-on-confirm with verified post-condition).
- `payload.handoffs_found`: array of discovered handoff scopes (empty when none).
- `payload.selected_scope`: the scope surfaced (`NEXT-SESSION` for the reserved default) or `null`.
- `payload.handoff_present`: `true` | `false`.
- `payload.handoff_last_updated`: ISO date or `null`.
- `payload.sections_found`: array of H2 heading strings actually present.
- `payload.staleness_warning`: `true` | `false`.
- `payload.subject_plan_retired`: `true` | `false` | `null` (when no PLAN ID detected).
- `payload.handoff_path`: the selected file path (or `null` if none).
- `payload.retired`: `true` | `false`.
- `payload.retired_path`: `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md` (if retired) or `null`.
- `diagnostics`: any per-step notes.

## Reporting

PASS / SKIPPED / FAIL per step. FAIL only on Step 3 post-condition violation (after the operator confirmed retire). Absent handoff is SKIPPED at Step 1; deferred retire is SKIPPED at Step 3.
