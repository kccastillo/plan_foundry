# Workflow: Curate Lessons Forward (Rollover)

<inputs>
- `prior_log_path: string` — path to the prior month's LOG (e.g. `Workbench/202604010000_LOG_202604.md`).
- `new_log_path: string` — path to the new month's LOG, already created by write-plan with rollover Status Table populated.
</inputs>

<process>

## Step 1: Read the prior LOG's Lessons Learned section

Open `prior_log_path`. Locate `## Lessons Learned`. Extract the section content.

If the section is missing or contains only the placeholder `_(none carried forward)_`, skip to Step 5 and write `(none carried forward)_` to the new LOG.

## Step 2: Parse each lesson

Each bullet should match the format `- [<category>] (src: <source>; recurrences: <N>) — <text>`. For each bullet, extract `category`, `source`, `recurrences` (default `1` if absent — backwards compatible with pre-T06 bullets), and `text`.

Tolerate legacy free-form bullets that predate the structured format: treat them as `category: convention, source: legacy, recurrences: 1` and apply the same triage.

## Step 3: Triage each lesson into one of three buckets

For each parsed lesson, classify:

**forward** — the lesson is still architecturally load-bearing AND is NOT yet codified into a permanent doc (skill SKILL.md, CLAUDE.md, ARCHITECTURE.md). It describes a truth likely to apply to future work.

**drop (episode)** — the lesson describes a one-time mishap or context-specific observation that has no general principle surviving the episode. Hallmark: refers to a single PLAN by ID and would be irrelevant to a reader who didn't live that PLAN.

**drop (codified)** — the substance of the lesson has been captured in `.claude/skills/<name>/SKILL.md`, `CLAUDE.md`, or `ARCHITECTURE.md`. To check: Grep the relevant doc area for keywords from the lesson text. If a clear match exists, the doc is now authoritative — drop the lesson.

**Bias toward dropping.** If you're unsure whether a lesson still applies, drop it. A lesson worth keeping will resurface as a fresh observation in the new month.

### Recurrence-driven curation flags (T06)

Each lesson's `recurrences` value adds a curation hint that runs alongside the three-bucket triage. The hint does not override the triage — it informs the human reviewer who's reading the rollover report:

- **Promotion candidate** — `recurrences >= 3`. The lesson has been observed enough times that the underlying truth probably belongs in a permanent doc (skill SKILL.md, CLAUDE.md, or ARCHITECTURE.md's invariants register). Collect these into the rollover report's `promotion_candidates` list. The lesson can still forward this month; the flag is a prompt for the next maintenance pass to codify. `maintain-claude-md`'s monthly audit consumes the same signal and surfaces it as a "consider codifying" finding (wired 2026-05-14).

- **Eviction candidate** — `recurrences == 1` AND the source-tag arrow chain shows the lesson has been forwarded for **2 or more months** without being re-observed (count the arrows in the source tag; 2+ arrows = 2+ forwards). The lesson was a single observation that has not recurred. Collect these into the rollover report's `eviction_candidates` list. Triage bias: such lessons typically belong in `drop (episode)`.

Counter behaviour on forward: `recurrences` is preserved as-is. The curate-forward workflow never increments the counter — only the `jot` skill's `mode: increment` does that, and only when the caller observes the lesson again. A lesson forwarded across months without re-observation has `recurrences: 1` throughout its lifetime.

## Step 4: Build the forwarded section content

For each `forward` lesson:
- Preserve the `[category]` tag exactly.
- Preserve the original `source` value, but append `→ <YYYYMM>` (the new month) so multi-month survivors are visible. Example: `(src: 202605020000)` becomes `(src: 202605020000 → 202606)`. If the source already contains an arrow chain, append the new month after the rightmost arrow.
- Preserve the lesson text verbatim. Never edit a lesson's prose during forwarding — tag updates only.

For each `drop (codified)` lesson where the codification landed in the prior month (i.e., the codifying skill/doc was created or substantively updated within the prior month), prepend a single one-line cross-reference at the top of the section:

```
> Codified in <skill-or-doc-path>: was lesson from src: <source>.
```

Carry these cross-references for one month only — do not propagate them forward at the next rollover.

If after triage nothing forwards, the section content is the placeholder line: `_(none carried forward)_`.

## Step 5: Write the new LOG's Lessons Learned section

Locate `## Lessons Learned` in `new_log_path`. (The LOG template guarantees the heading exists, placed before `## Month Summary`.) Replace any existing content under that heading with the content built in Step 4.

Update `new_log_path`'s frontmatter `last_updated` to today.

## Step 6: Report

Emit `<pipeline-result>` with a JSON code fence reporting:
- `outcome: success`
- `prior_log_path: <path>`
- `new_log_path: <path>`
- `forwarded: <integer>` — count of bullets carried forward
- `dropped_episode: <integer>` — count dropped as episode-specific
- `dropped_codified: <integer>` — count dropped because codified elsewhere
- `cross_references: <integer>` — count of one-month codification references inserted
- `promotion_candidates: [<lesson_summary>, ...]` — short summaries of forwarded bullets with `recurrences >= 3`. Format: `"[<category>] <source> — <first 60 chars of text>"`. Empty list if none.
- `eviction_candidates: [<lesson_summary>, ...]` — short summaries of bullets with `recurrences == 1` AND 2+ months in their source-tag arrow chain. Format identical to `promotion_candidates`. Empty list if none.

</process>

<success_criteria>

- [ ] New LOG's `## Lessons Learned` section exists and contains only the triaged-forward bullets (or the placeholder).
- [ ] Forwarded bullets retain `[category]` and have source updated with `→ <YYYYMM>` annotation.
- [ ] Forwarded bullets preserve `recurrences: N` unchanged (workflow never increments the counter).
- [ ] No bullet text was edited (only tag updates).
- [ ] Section is materially smaller than the prior month's, unless the prior section was already empty or every prior lesson genuinely still applies.
- [ ] Codification cross-references (if any) appear at the TOP of the section as `> Codified in ...` lines.
- [ ] `<pipeline-result>` returned with all four counts plus `promotion_candidates` and `eviction_candidates` lists (possibly empty).
- [ ] Legacy bullets without `recurrences:` are tolerated and treated as `recurrences: 1`.

</success_criteria>
