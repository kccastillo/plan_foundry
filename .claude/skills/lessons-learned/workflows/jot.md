# Workflow: Jot a Lesson

<inputs>
- `lesson_text: string` — one or two lines of plain prose, the lesson itself.
- `category: enum[architectural, process, user-preference, convention]` — exactly one.
- `source: string` — PLAN ID (e.g. `202605020000`) or short slug (e.g. `f14-closeout`).
- `mode: enum[append, increment]` (optional, default `append`) — `append` adds a new bullet at `recurrences: 1`; `increment` finds an existing bullet by `(source, category)` and bumps its `recurrences` counter by 1 instead of duplicating. Use `increment` when the caller has observed the same lesson pattern again.
</inputs>

<process>

## Step 1: Locate the current month LOG

Path: `Workbench/{YYYYMM}010000_LOG_{YYYYMM}.md` where YYYYMM is the current month.

If the LOG does not exist, do NOT create it. Return an exception via `<pipeline-result>` and instruct the caller to create the LOG via `write-plan` first. Jot mode is strictly write-only; LOG creation is `write-plan`'s job.

## Step 2: Locate or create the Lessons Learned section

Search the LOG for `## Lessons Learned`. If missing, insert the section header (and the empty-section placeholder `_(none carried forward)_`) immediately before `## Month Summary`. If `## Month Summary` is also missing, append the section at the end of the file.

## Step 3: Validate inputs

- `category` must be exactly one of the four allowed values. Reject otherwise with an exception.
- `source` must be non-empty. If the caller cannot supply a PLAN ID, accept a short slug.
- `lesson_text` must be non-empty and fit on one or two lines (<= ~250 characters as a soft cap).
- `mode` defaults to `append`; reject any value other than `append` or `increment`.

## Step 4: Apply the write (mode-dependent)

### Step 4a (mode: append, the common case)

Format the bullet exactly as:

```
- [<category>] (src: <source>; recurrences: 1) — <lesson_text>
```

Append it as the last bullet under `## Lessons Learned`. If the placeholder line `_(none carried forward)_` is present, replace it with the new bullet.

### Step 4b (mode: increment)

Scan the section's bullets for a match: a bullet whose `[<category>]` token matches the supplied `category` AND whose `src:` field matches the supplied `source` (allowing for an arrow chain — match the leftmost source token before any `→` if present).

- **Exactly one match:** parse the bullet's current `recurrences: N` value (default 1 if the field is missing — legacy format). Write back the bullet with `recurrences: N+1`. Leave `lesson_text` unchanged from the existing bullet — do NOT replace it with the caller's `lesson_text` (callers may rephrase; the existing text is canonical for that lesson). Optionally append a brief annotation about the re-observation as a separate parenthetical in the source field, e.g. `(src: PR-28 → re-observed PR-42; recurrences: 2)`.
- **Zero matches:** fall through to Step 4a (treat as append).
- **Multiple matches:** ambiguous — return exception with diagnostics listing all matching bullets. The caller must disambiguate (consolidate or use a more specific source tag).

## Step 5: Update LOG frontmatter

Set `last_updated: <today's YYYY-MM-DD>` in the LOG's frontmatter.

## Step 6: Report

Emit `<pipeline-result>` with a JSON code fence reporting:
- `outcome: success`
- `log_path: <path>`
- `lesson_count_after: <integer>` — total bullets in the section after the write
- `mode_applied: <"append" | "increment">` — which path was taken (helpful when mode=increment falls through to append)
- `recurrences_after: <integer>` — final recurrences value for the affected lesson

</process>

<success_criteria>

- [ ] Bullet appears under `## Lessons Learned` in the correct format including `recurrences:` field.
- [ ] Category is one of the four allowed values.
- [ ] Source tag is present and non-empty.
- [ ] LOG `last_updated` frontmatter refreshed.
- [ ] Placeholder `_(none carried forward)_` removed if it was present.
- [ ] `mode: increment` with a unique match incremented the existing bullet's counter; the bullet's text was NOT replaced.
- [ ] `mode: increment` with zero matches fell through to append (no error).
- [ ] `mode: increment` with multiple matches returned an exception rather than silently picking one.
- [ ] `<pipeline-result>` returned with `outcome: success`, `mode_applied`, and `recurrences_after`.

</success_criteria>
