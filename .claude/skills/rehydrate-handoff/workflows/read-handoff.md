# rehydrate-handoff workflow

This procedure is idempotent. Each step PASSes, SKIPPEDs, or FAILs. See [../../handoff-next-session/references/handoff-naming.md](../../handoff-next-session/references/handoff-naming.md) for the filename grammar.

## Step 0: Resumption drift preflight

Run the deterministic resumption drift preflight *before* any handoff is discovered or surfaced. This step is read-only and fail-open: a `checked: false` axis or unavailable PR state never blocks progression to Step 1.

**Desktop-only limitation:** Project-local skills (including this skill and `.claude/skills/_shared/resume_preflight.py`) do not load in Claude Code mobile/web sessions. This preflight is therefore a desktop-session guarantee only.

**Procedure:**

1. Glob `Workbench/HANDOFF-*.md`. For each present handoff file, parse its `## Plan-state baseline` fenced-yaml block (if any). Merge all entries into a single `expected_plan_states` mapping (`{ relpath: { pipeline_phase, status, last_executor_outcome } }`). On a key conflict between handoffs, prefer the entry from the more-recently-modified handoff. When no handoff exists or no baseline block is present in any handoff (e.g. a handoff written before PLAN-AG4 landed), `expected_plan_states` is empty - the PLAN-drift axis stays informational and never fires.

1a. Likewise parse each present handoff's `## Carried-claims baseline` fenced-yaml block (if any) and merge into a single `expected_claim_checks` mapping (`{ claim_id: {nickname, check, carried_count} }`), same last-modified-wins conflict rule. When no handoff exists or no baseline block is present (a handoff written before PLAN-AL1 landed, or no claims ever carried), `expected_claim_checks` is empty - the claim-drift axis stays informational and never fires. See [../../handoff-next-session/references/claim-carry-gate.md](../../handoff-next-session/references/claim-carry-gate.md).

2. Call `.claude/skills/_shared/resume_preflight.py::check_resume_drift(repo_root, expected_plan_states=<merged baseline>, expected_claim_checks=<merged claim baseline>)` at the very start of the resume procedure, before Step 1 selects or surfaces any handoff.

3. **If `result["drift"]` is `True`:** halt and surface `result["summary"]` as a re-orientation block. Require the operator/orchestrator to reconcile the drift before proceeding to Step 1. The reconciliation action depends on the signal:
   - *Branch behind/diverged:* `git fetch` + rebase/merge or discard local changes as appropriate.
   - *PR merged -> restart from default:* per the existing restart-from-default rule, switch to the default branch before resuming work.
   - *PLAN-phase drift (disk != baseline):* re-read the drifted PLAN's current frontmatter before assuming its phase or executor outcome.
   - *Claim no longer reproduces:* re-read the claim against the repository before trusting the claim, and do not carry the claim forward unexamined.
   After the operator has reconciled, re-invoke the preflight (re-run Step 0) or proceed with full awareness of the drift.

4. **If `result["drift"]` is `False`:** proceed silently to Step 1 - no friction on a clean state.

**Failure mode notes:**
- The check is read-only, and never mutates any file, branch, or PLAN.
- Fail-open: a git error (offline, missing ref, timeout) marks that axis `checked: false` and adds a notes entry - the error does not produce drift. Only actual, confirmed differences count as drift.
- The merged-PR git-ancestry heuristic (used when `gh`/MCP PR state is unavailable) is a **degraded signal**: a `False` `merged_into_default` result under `pr_state.available: false` is not a guarantee the branch is unmerged (squash-merge and fast-forward-merge false negatives exist - see PLAN-AG4 J2).
- On non-sticky drift: a handoff left un-retired (retire deferred to session end, or no explicit operator override at Step 3) keeps its `## Plan-state baseline` on disk. If the underlying PLAN state has not changed since the last run, the preflight re-fires the same drift signal on the next resume. This is harmless - the preflight is read-only and the re-orientation is the same information - but explains why the same drift can appear across successive resumes until the handoff is retired at session end (via handoff-next-session) or on an explicit operator override.

PASS when the preflight has run (even if drift=True, the step itself passes - the halt is a procedural halt for reconciliation, not a skill failure). SKIPPED only when `resume_preflight.py` is not available in the session (mobile/web), and log a one-line note.

## Step 1: Discover handoff files and select one

Glob `Workbench/HANDOFF-*.md` (case-insensitive, matching legacy `HANDOFF-NEXT-SESSION.md`, old-grammar thread-scoped `HANDOFF-<scope>.md`, and new-grammar `HANDOFF-YYYYMMDD-hhmm-<slug>.md`). The glob intentionally spans all HANDOFF forms per PLAN-AF6 D2 - do not change the glob. `HANDOFF-NEXT-SESSION.md` is a legacy read/retire-only form from PLAN-AH0 D1 onward - the file may still be present on disk from prior sessions and is discovered and retired normally, but is never written as a new handoff. Ignore zero-byte / whitespace-only files. Reads use `encoding='utf-8', errors='replace'`.

- **If zero non-empty handoffs:** SKIPPED. Surface "no handoff to rehydrate (first session in this project or all already retired)." Skip to Step 4 with empty payload.
- **If exactly one:** select that handoff. PASS, proceed to Step 2.
- **If more than one:** surface a selection list - for each handoff show its scope (derived from the filename), last-modified date, and the title line (first `# ` heading). Ask the operator which to surface/resume. Do not dump every body. Once the operator picks, select that file. PASS, proceed to Step 2 for the selected file. (The operator may ask to surface several in sequence - re-run Steps 2-3 per selection.)

The resolved scope of the selected file is used by the retire step. Scope is derived robustly from either grammar:
- **Reserved default (`HANDOFF-NEXT-SESSION.md`):** scope is `NEXT-SESSION`.
- **Old grammar (`HANDOFF-<scope>.md`):** scope is the filename segment after `HANDOFF-`.
- **New datetime grammar (`HANDOFF-YYYYMMDD-hhmm-<slug>.md`):** the filename carries a gist slug, not a thread scope. Recover the scope from the handoff body's scope banner (the one-line banner written by write-handoff.md Step 4), and fall back to the gist slug when no banner is present (this fallback fires only for malformed new-grammar handoffs).

## Step 2: Parse and surface structured sections

Parse the **selected** handoff body by H2 headings. Expected sections (per `handoff-next-session/templates/handoff-template.md`, which is a forward-only action brief):
- `## Session roadmap` (the actionable spine - always present, with ordered phases, gates, and checkpoints)
- `## Audit & execution-readiness gate` (**mandatory and never deleted on the write side** - a per-PLAN readiness table, or the literal line `No in-flight PLANs.` Surface the table verbatim whenever it names a PLAN, because the gate exists so a NOT-READY plan is never mistaken for a ready one at handover. Definition: [../../handoff-next-session/references/readiness-gate.md](../../handoff-next-session/references/readiness-gate.md).)
- `## Agentic & model plan` (optional - per-roadmap-step delegation and model assignments, and the verbatim dispatch-grant token when one was carried forward)
- `## Next-handoff trigger` (optional - the expected/anticipated seam to stop-write-clear, advisory)
- `## Lessons & decision rationale` (**mandatory in any handoff written after 2026-07-27** - lessons learned paired with what each changes about future work, plus the motivation, rejected alternative and reasoning behind every decision locked. Surface this section in full, because the section is the *why* behind the roadmap and, under the retired-handoff-chain-as-history model, the project's only durable record of reasoning. Absent only in legacy handoffs predating the content contract - note the absence in one line, do not fail.)
- `## Blocking decisions` (optional)
- `## Constraints & do-nots` (optional)
- `## Where things live` (optional)

For each section found, surface to the operator as a named block. Preserve verbatim - do not summarise (the handoff is already a curated forward brief, so re-summarising loses signal). Surface `## Session roadmap` first, then `## Lessons & decision rationale` - the roadmap says what to do, and the lessons/rationale say why the roadmap is shaped that way. Surfacing the roadmap without its reasoning is what lets a next session execute a plan it does not understand and cannot correctly revise.

The template's two remaining H2 sections, `## Plan-state baseline` and `## Carried-claims baseline`, are machine-readable blocks already parsed at Step 0. Do not re-surface either as a prose block.

If a section is missing or empty, do not note the absence as a gap and do not fail. The writer deletes empty sections by design, and the only sections the writer never deletes are `## Session roadmap`, `## Lessons & decision rationale`, `## Audit & execution-readiness gate`, `## Plan-state baseline` and `## Carried-claims baseline` (per write-handoff.md Step 3) - a handoff predating any one of those rules may lack it. The structure is a soft contract, and actionability is the real one.

Also surface the `last_updated:` (or `created:`) frontmatter date. If `today - last_updated > 14 days`, prepend a one-line warning: "⚠ Handoff is N days old; prefer recent commits for current state."

Also extract any PLAN ID referenced in the title or first H2 section (regex `PLAN-[A-Z]{2}\d`). For each such PLAN ID found, check whether the corresponding file has moved under `Retired/**`. If yes, prepend a one-line note: "ℹ Subject `PLAN-<ID>` is now retired - handoff is likely fully absorbed."

## Step 3: Defer retire decision to session end

The retire decision belongs at **session end**, not session start. Rehydration surfaces the handoff and leaves the handoff on disk. Do **not** prompt the operator to retire at this point.

Surface a brief note: "Handoff surfaced and left in `Workbench/`. Retire decision deferred to session end - `handoff-next-session` will resolve it as either updated-into-successor (fresh handoff written) or retired-outright (no successor, roadmap fully discharged)."

**Explicit operator override (unprompted):** If the operator - without being prompted - says they want to retire the handoff now (e.g. "retire this handoff", "retire it now"), honour the request using the retire path set out below:

Let `<scope>` be the selected file's scope (derived per the scope-derivation rules in Step 1) and `<src>` its path.

1. Compute timestamp `YYYYMMDDHHMI` from current UTC.
2. Resolve the anchor: try `git rev-parse --show-toplevel` first. If that fails (git unavailable, or cwd is outside any git worktree), walk up from cwd for the nearest ancestor containing `.claude/` or `CLAUDE.md` and use that ancestor instead. Destination path: `<anchor>/Retired/HANDOFF-<scope>-{YYYYMMDDHHMI}.md`.
3. Move the file: when git resolved the anchor, use `git mv <src> <destination>` (the orchestrator runs this in parent context, and subagents must defer to parent). When the walk-up fallback resolved the anchor instead, move the file as a plain filesystem operation - read `<src>`, write the content to `<destination>`, then delete `<src>` - since there is no git worktree to stage the move against. Only the selected file is moved - never a sibling handoff.
4. Post-condition verification (AA2 defence-in-depth pattern): assert source absent on disk, and assert destination exists, is readable, and non-zero size. If any check fails, return `outcome: exception` with `diagnostics.reason` naming the failed check, and do not commit.
5. Commit: `rehydrate-handoff: retired HANDOFF-<scope> on explicit operator request -> <destination>`. The push is subject to push_policy.
6. PASS.

Default path (no override): SKIPPED - the handoff stays in `Workbench/` and the step report records the retire as deferred to session end.

## Step 4: Complete

This skill runs in the parent session only - there is no consuming orchestrator to parse a `<pipeline-result>` block. Do not emit one. The operator has already received all information via the structured surface in Steps 2-3.

PASS unconditionally at this step.

## Reporting

PASS / SKIPPED / FAIL per step. FAIL only on Step 3 post-condition violation (after an explicit operator override retire). Absent handoff is SKIPPED at Step 1. Step 3 is SKIPPED on the default path (retire deferred to session end via handoff-next-session) and PASS when the operator explicitly overrides to retire-now.
