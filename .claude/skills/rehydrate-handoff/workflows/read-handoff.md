# rehydrate-handoff workflow

Idempotent procedure. Each step PASSes, SKIPPEDs, or FAILs. See [../../handoff-next-session/references/handoff-naming.md](../../handoff-next-session/references/handoff-naming.md) for the filename grammar.

## Step 0: Resumption drift preflight

Run the deterministic resumption drift preflight *before* any handoff is discovered or surfaced. This step is read-only and fail-open: a `checked: false` axis or unavailable PR state never blocks progression to Step 1.

**Desktop-only limitation:** Project-local skills (including this skill and `.claude/skills/_shared/resume_preflight.py`) do NOT load in Claude Code mobile/web sessions. This preflight is therefore a desktop-session guarantee only.

**Procedure:**

1. Glob `Workbench/HANDOFF-*.md`. For each present handoff file, parse its `## Plan-state baseline` fenced-yaml block (if any). Merge all entries into a single `expected_plan_states` mapping (`{ relpath: { pipeline_phase, status, last_executor_outcome } }`). On a key conflict between handoffs, prefer the entry from the more-recently-modified handoff. When no handoff exists or no baseline block is present in any handoff (e.g. a handoff written before PLAN-AG4 landed), `expected_plan_states` is empty — the PLAN-drift axis stays informational and never fires.

2. Call `.claude/skills/_shared/resume_preflight.py::check_resume_drift(repo_root, expected_plan_states=<merged baseline>)` at the very start of the resume procedure, before Step 1 selects or surfaces any handoff.

3. **If `result["drift"]` is `True`:** halt and surface `result["summary"]` as a re-orientation block. Require the operator/orchestrator to reconcile the drift before proceeding to Step 1. The reconciliation action depends on the signal:
   - *Branch behind/diverged:* `git fetch` + rebase/merge or discard local changes as appropriate.
   - *PR merged → restart from default:* per the existing restart-from-default rule, switch to the default branch before resuming work.
   - *PLAN-phase drift (disk ≠ baseline):* re-read the drifted PLAN's current frontmatter before assuming its phase or executor outcome.
   After the operator has reconciled, re-invoke the preflight (re-run Step 0) or proceed with full awareness of the drift.

4. **If `result["drift"]` is `False`:** proceed silently to Step 1 — no friction on a clean state.

**Failure mode notes:**
- The check is read-only: it never mutates any file, branch, or PLAN.
- Fail-open: a git error (offline, missing ref, timeout) marks that axis `checked: false` and adds a notes entry — it does NOT produce drift. Only actual, confirmed differences count as drift.
- The merged-PR git-ancestry heuristic (used when `gh`/MCP PR state is unavailable) is a **degraded signal**: a `False` `merged_into_default` result under `pr_state.available: false` is not a guarantee the branch is unmerged (squash-merge and fast-forward-merge false negatives exist; see PLAN-AG4 J2).
- On non-sticky drift: a handoff left un-retired (retire deferred to session end, or no explicit operator override at Step 3) keeps its `## Plan-state baseline` on disk. If the underlying PLAN state has not changed since the last run, the preflight re-fires the same drift signal on the next resume. This is harmless — the preflight is read-only and the re-orientation is the same information — but explains why the same drift can appear across successive resumes until the handoff is retired at session end (via handoff-next-session) or on an explicit operator override.

**Pipeline-result additions:** Step 4 MUST add `payload.preflight_drift` (bool) and `payload.preflight_summary` (string) to the `<pipeline-result>` payload. These reflect the Step 0 outcome. No other Step 4 payload fields are renamed or renumbered.

PASS when the preflight has run (even if drift=True, the step itself passes — the halt is a procedural halt for reconciliation, not a skill failure). SKIPPED only if `resume_preflight.py` is not available in the session (mobile/web; log a one-line note).

## Step 1: Discover handoff files and select one

Glob `Workbench/HANDOFF-*.md` (case-insensitive; this matches legacy `HANDOFF-NEXT-SESSION.md`, old-grammar thread-scoped `HANDOFF-<scope>.md`, and new-grammar `HANDOFF-YYYYMMDD-hhmm-<slug>.md`). The glob intentionally spans all HANDOFF forms per PLAN-AF6 D2 — do not change it. Note: `HANDOFF-NEXT-SESSION.md` is a legacy read/retire-only form from PLAN-AH0 D1 onward — it may still be present on disk from prior sessions and is discovered and retired normally; it is no longer written as a new handoff. Ignore zero-byte / whitespace-only files. Reads use `encoding='utf-8', errors='replace'`.

- **If zero non-empty handoffs:** SKIPPED. Surface "no handoff to rehydrate (first session in this project or all already retired)." Skip to Step 4 with empty payload.
- **If exactly one:** select it. PASS, proceed to Step 2.
- **If more than one:** surface a selection list — for each handoff show its scope (derived from the filename), last-modified date, and the title line (first `# ` heading). Ask the operator which to surface/resume. Do NOT dump every body. Once the operator picks, select that file. PASS, proceed to Step 2 for the selected file. (The operator may ask to surface several in sequence — re-run Steps 2–3 per selection.)

The resolved scope of the selected file is used by the retire step. Scope is derived robustly from EITHER grammar:
- **Reserved default (`HANDOFF-NEXT-SESSION.md`):** scope is `NEXT-SESSION`.
- **Old grammar (`HANDOFF-<scope>.md`):** scope is the filename segment after `HANDOFF-`.
- **New datetime grammar (`HANDOFF-YYYYMMDD-hhmm-<slug>.md`):** the filename carries a gist slug, not a thread scope. Recover the scope from the handoff body's scope banner (the one-line banner written by write-handoff.md Step 4); fall back to the gist slug when no banner is present (this fallback fires only for malformed new-grammar handoffs).

## Step 2: Parse and surface structured sections

Parse the **selected** handoff body by H2 headings. Expected sections (per `handoff-next-session/templates/handoff-template.md`, which is a forward-only action brief):
- `## Session roadmap` (the actionable spine — always present; ordered phases, gates, and checkpoints)
- `## Agentic & model plan` (optional — per-roadmap-step delegation and model assignments)
- `## Next-handoff trigger` (optional — the expected/anticipated seam to stop-write-clear; advisory)
- `## Blocking decisions` (optional)
- `## Constraints & do-nots` (optional)
- `## Where things live` (optional)

For each section found, surface to the operator as a named block. Preserve verbatim — do NOT summarise (the handoff is already a curated forward brief; re-summarising loses signal). Surface `## Session roadmap` first.

If a section is missing or empty, do not note it as a gap and do not fail — the writer deletes empty sections by design (only `## Session roadmap` is guaranteed). The structure is a soft contract; actionability is the real one.

Also surface the `last_updated:` (or `created:`) frontmatter date. If `today - last_updated > 14 days`, prepend a one-line warning: "⚠ Handoff is N days old; prefer recent commits + Workbench/INDEX.md for current state."

Also extract any PLAN ID referenced in the title or first H2 section (regex `PLAN-[A-Z]{2}\d`). For each such PLAN ID found, check whether the corresponding file now lives under `Retired/**`. If yes, prepend a one-line note: "ℹ Subject `PLAN-<ID>` is now retired — handoff is likely fully absorbed."

## Step 3: Defer retire decision to session end

The retire decision belongs at **session end**, not session start. Rehydration surfaces the handoff and leaves it on disk. Do **not** prompt the operator to retire at this point.

Surface a brief note: "Handoff surfaced and left in `Workbench/`. Retire decision deferred to session end — `handoff-next-session` will resolve it as either updated-into-successor (fresh handoff written) or retired-outright (no successor, roadmap fully discharged)."

**Explicit operator override (unprompted):** If the operator — without being prompted — says they want to retire the handoff now (e.g. "retire this handoff", "retire it now"), honour the request using the same path as the previous prompt-based flow:

Let `<scope>` be the selected file's scope (derived per the scope-derivation rules in Step 1) and `<src>` its path.

1. Compute timestamp `YYYYMMDDHHMI` from current UTC.
2. Destination path: `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md`.
3. Move via `git mv <src> <destination>` (the orchestrator runs this in parent context; subagents must defer to parent). Only the selected file is moved — never a sibling handoff.
4. Post-condition verification (AA2 defence-in-depth pattern): assert source absent on disk; assert destination exists, is readable, and non-zero size. If any check fails, return `outcome: exception` with `diagnostics.reason` naming the failed check; do NOT commit.
5. Commit: `rehydrate-handoff: retired HANDOFF-<scope> on explicit operator request → <destination>`. Push subject to push_policy.
6. PASS (`payload.retired: true`).

Default path (no override): SKIPPED. `payload.retired: false`, `payload.retire_deferred: true`.

## Step 4: Emit pipeline-result

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` (always — read-only with graceful absence handling, retire-on-explicit-override with verified post-condition).
- `payload.preflight_drift`: `true` | `false` — the Step 0 resumption drift preflight result (`result["drift"]`); `false` when Step 0 was skipped (mobile/web).
- `payload.preflight_summary`: string — `result["summary"]` from the preflight (empty string when clean or skipped).
- `payload.handoffs_found`: array of discovered handoff scopes (empty when none).
- `payload.selected_scope`: the scope surfaced (`NEXT-SESSION` for the reserved default) or `null`.
- `payload.handoff_present`: `true` | `false`.
- `payload.handoff_last_updated`: ISO date or `null`.
- `payload.sections_found`: array of H2 heading strings actually present.
- `payload.staleness_warning`: `true` | `false`.
- `payload.subject_plan_retired`: `true` | `false` | `null` (when no PLAN ID detected).
- `payload.handoff_path`: the selected file path (or `null` if none).
- `payload.retired`: `true` | `false` — `true` ONLY when the operator explicitly requested retire-now (override path); `false` on the default deferred path.
- `payload.retire_deferred`: `true` | `false` — `true` on the default path (retire decision deferred to session end); `false` when the operator explicitly retired now (override path) or no handoff was present.
- `payload.retired_path`: `Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md` (if retired on operator override) or `null`.
- `diagnostics`: any per-step notes.

## Reporting

PASS / SKIPPED / FAIL per step. FAIL only on Step 3 post-condition violation (after an explicit operator override retire). Absent handoff is SKIPPED at Step 1; Step 3 is SKIPPED on the default path (retire deferred to session end via handoff-next-session) and PASS when the operator explicitly overrides to retire-now.
