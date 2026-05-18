# handoff-next-session workflow

Idempotent four-step procedure. Each step PASSes, SKIPPEDs, or FAILs.

## Step 1: Retire any existing handoff

Check if `Workbench/HANDOFF-NEXT-SESSION.md` exists.
- **If present:** Move it to `Retired/HANDOFF-NEXT-SESSION-{YYYYMMDDHHMI}.md` (timestamp-suffixed to avoid collisions with prior retirements). Use the Bash-disallowed-friendly approach: read the source content, write it to the destination, then delete the source (or use the `retire` skill if the orchestrator is dispatching). PASS.
- **If absent:** SKIPPED. First-time invocation in this project.

## Step 2: Gather current-session observations

Read context for the handoff body:
- **Recent commits:** Use Bash (`git log --oneline -10 main`) if available in parent context; otherwise summarise from conversation memory.
- **Open PRs touching this repo:** Mention numbers and one-line titles. If no PR-list tool is available in the executor context, leave that subsection sparse and note "see GitHub UI".
- **Workbench/ contents:** List PLAN files currently in `Workbench/` with their `status:` frontmatter values (extract via Read + grep on each PLAN file).
- **Active branch:** Note the current git branch if not main; flag any unmerged work-in-flight.
- **Carryover items:** Anything explicitly paused mid-pipeline; any blocked PLANs; any deferred work the human flagged during the session.

The skill is expected to be invoked at end-of-session by the human ("write session handoff"); the executor uses conversation context as the primary input. If invoked early or in an empty session, populate from observable repo state alone.

## Step 3: Render handoff body from template

Read `../templates/handoff-template.md` and populate each placeholder section with the observations from Step 2. Sections in the template:
- `# Handoff — for the next session`
- `## What's on main right now`
- `## What's open / queued / paused`
- `## Conventions you must know`
- `## Pitfalls / gotchas`
- `## Resumption checklist`

Each section can be empty if no content applies; do not delete section headings (the structure is the contract for next-session orientation).

## Step 4: Write the handoff file

Write the rendered body to `Workbench/HANDOFF-NEXT-SESSION.md`. PASS.

## Reporting

Return a `<pipeline-result>` JSON block with:
- `outcome`: `success` if no FAILs.
- `payload.step_results`: object with keys `step_1` through `step_4`, each value `PASS` / `SKIPPED` / `FAIL`.
- `payload.handoff_path`: `Workbench/HANDOFF-NEXT-SESSION.md`.
- `payload.retired_path` (if Step 1 retired a prior handoff): the retired path.
- `diagnostics`: any per-step notes.
