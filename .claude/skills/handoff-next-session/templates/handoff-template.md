# Handoff — for the next session

*Last updated: {YYYY-MM-DD}. If this is stale (>2 weeks since last_updated), re-read the recent PRs on `main` and prefer those.*

{ONE-PARAGRAPH ORIENTATION: where the project is at, what kind of work has been happening recently.}

## What's on main right now

{SUMMARY OF RECENT MERGES — PR numbers, one-line descriptions, dates. List the latest N commits or the latest few merged PRs. Skip if main is stable and nothing notable has merged.}

## What's open / queued / paused

{LIST UNMERGED / IN-FLIGHT WORK: open PRs with status; PLANs in Workbench/ with status:; any explicitly paused threads. If nothing is open, say so explicitly.}

## Conventions you must know

{ANY NON-OBVIOUS CONVENTIONS THE NEXT SESSION SHOULD INHERIT — naming patterns, harness rules that aren't in AGENT_RULES.md, gotchas about plugin paths, AU spelling, etc. Lean on what's NEW since the last handoff; assume the next session has read CLAUDE.md and ARCHITECTURE.md.}

## Pitfalls / gotchas

{KNOWN ROUGH EDGES, BUGS, OR BEHAVIOURS THE NEXT SESSION SHOULD WATCH FOR. Examples: a tool that's flaky; a workflow that diverges from docs; a recurring drift the harness hasn't fixed yet.}

## Resumption checklist

1. Read this file end-to-end.
2. Run quick state-check commands ({EXAMPLE: `git log --oneline -10`, `ls Workbench/`, `python "${CLAUDE_PLUGIN_ROOT:-plugins/plan-foundry-core}/skills/write-plan/scripts/next_id.py" PLAN`}).
3. {ANY SPECIFIC NEXT-ACTION THE PRIOR SESSION HANDED OFF — e.g., "resume PLAN-NN at sufficiency iter X" or "merge PR #N then start PLAN Y".}
4. Re-run `handoff-next-session` at end-of-session to refresh this file for the next reader.

---

If you read this far: you're caught up. Pick up from whatever was flagged in "Resumption checklist" step 3, or raise something new with the human.
