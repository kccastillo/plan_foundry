# test-foundry - run-tests workflow

Orchestrates the two-tier harness and writes the TESTREPORT.

`SKILL.md` invokes this workflow, which runs in **parent session** (orchestrator) context, because the LLM tier issues `Skill(...)` dispatches that subagents cannot make.

---

## Inputs

- `mode`: `full` (default) | `llm-tier-only`
- `slug`: optional human-readable slug, defaulting to `YYYY-MM-DD` from today's date.

---

## Step 1 - Resolve repo root and `Workbench/`

Locate the repository root by walking up from cwd until a directory containing `Workbench/` is found. If `.claude/plan-foundry.config` exists and declares `workbenchDir`, prefer that. Default: `Workbench/` relative to repo root.

If `Workbench/testreports/` does not exist, create the directory.

---

## Step 2 - Python tier

### Step 2a - `mode=full`: run the Python tier discovery + execution

Invoke:

```
python3 .claude/skills/test-foundry/lib/run_python_tier.py --json --output Workbench/.python-tier-result.json
```

Then read `Workbench/.python-tier-result.json` from disk into a Python dict named `python_tier`.

### Step 2b - `mode=llm-tier-only`: read the pre-run result

Read `Workbench/.python-tier-result.json` from disk. If missing, exit with `outcome: exception` and diagnostics `"mode=llm-tier-only requires pre-run Python tier result at Workbench/.python-tier-result.json"`.

The expected schema:

```json
{
  "schema_version": 1,
  "tier": "python",
  "scenarios": [
    { "scenario": "<name>", "status": "pass | fail | skip", "symptoms": [...], "diagnostics": "...", "duration_ms": N }
  ],
  "summary": { "passed": N, "failed": N, "skipped": N }
}
```

---

## Step 3 - Load LLM scenario specs

Glob `.claude/skills/test-foundry/scenarios/llm/*.md`. For each spec file, parse:

- Title (first `# ` heading).
- Scenario ID (filename stem).
- Body (the markdown, used by the executor narrative and by the driver for fixture instructions).
- Mechanical assertions: the JSON array under the spec's `## Mechanical assertions` heading. Each element is one assertion dict in a kind recognised by `capture_assertions` in `lib/llm_tier_helpers.py`. No other tag marks an assertion.

---

## Step 4 - Run LLM scenarios (parent-session loop)

For each LLM scenario spec, in deterministic order (alphabetical by scenario ID):

1. Call `prep_scenario(spec_path)` from `lib/llm_tier_helpers.py`. It creates one fresh empty temp directory and returns `{"scenario_id", "spec_path", "tmpdir", "spec_body"}`. It seeds no PLAN file, creates no `Workbench/` tree and sets no environment variable. Perform the fixture preparation the spec's `## Fixture preparation` section describes yourself, inside the returned `tmpdir`, before dispatching anything.
2. Read the scenario spec body to identify which `Skill(...)` calls the scenario specifies (e.g. `Skill("write-plan", ...)`, `Skill("audit-sufficiency", ...)`, `Skill("plan-pipeline", ...)`).
3. **Dispatch each `Skill(...)` call from parent session.** Capture the structured response.
4. Call `capture_assertions(scenario_id, expected)` from `lib/llm_tier_helpers.py`, passing the assertion list read in Step 3, with every path placeholder such as `<repo>` already resolved to the prepared temp directory. `capture_assertions` substitutes nothing and treats each `path` literally. The helper inspects disk state and returns:

   ```json
   { "scenario": "<id>", "status": "pass | fail", "symptoms": [...], "diagnostics": "...", "duration_ms": N }
   ```

5. Append the result to a list `llm_tier_scenarios`.
6. Clean up the fixtures prepared in (1) - remove the temp directory `prep_scenario` returned, and restore any pre-existing file the scenario overwrote.

If parent-session dispatch is not feasible, because this workflow is read from a subagent context, halt the run. Nothing records a scenario as skipped: `lib/llm_tier_helpers.py` has no skip path, and `capture_assertions` returns `pass` or `fail` and nothing else, so continuing would report every undispatched scenario as a failure of the skill under test. Exit with `outcome: exception` and diagnostics naming the invocation-context constraint in `SKILL.md`.

---

## Step 5 - Aggregate

Build the combined result:

```python
results = {
    "schema_version": 1,
    "python_tier": python_tier,
    "llm_tier": {
        "scenarios": llm_tier_scenarios,
        "summary": {
            "passed": <count where status=='pass'>,
            "failed": <count where status=='fail'>,
            "skipped": 0,
        },
    },
    "summary": {
        "passed": python_tier.summary.passed + llm_tier.summary.passed,
        "failed": python_tier.summary.failed + llm_tier.summary.failed,
        "skipped": python_tier.summary.skipped + llm_tier.summary.skipped,
    },
}
```

The LLM tier's `skipped` count is always zero, because `capture_assertions` returns `pass` or `fail` and no third status. The key is still emitted, because `write_testreport.py` reads `llm_tier.summary.skipped` when it renders the summary table. Only the Python tier produces a `skip`, which `run_python_tier.py` accepts as a status a scenario's `run()` may return.

Then serialise this dict as JSON to `Workbench/.testrun-results.json`. Step 6 reads that file, and this is the only file that carries both tiers.

---

## Step 6 - Allocate ID and write TESTREPORT

Invoke `lib/write_testreport.py` with the aggregated results and the slug:

```
python3 .claude/skills/test-foundry/lib/write_testreport.py --slug "<slug>" --results-json Workbench/.testrun-results.json
```

Pass the aggregate written in Step 5, never `Workbench/.python-tier-result.json`. That file carries the Python tier alone, and `write_testreport.py` detects a payload whose top-level `tier` is `python`, wraps it under `python_tier` and substitutes an empty `llm_tier`. Every LLM-tier result would be discarded in silence and the report would read `(no LLM scenarios reported)` under its LLM heading.

(Alternatively, the SKILL body can import `write_testreport` and call `main([...])` in-process with the same arguments, and the CLI remains the portable invocation surface.)

`write_testreport.py`:

1. Calls `next_testreport_id.allocate()` to get the next ID (e.g. `003`). The allocator reads the directory and returns a string, so calling it a second time before a report is written returns the same ID rather than consuming one.
2. Writes `Workbench/testreports/TESTREPORT-NNN_<slug>.md` with the schema described inline below (see TESTREPORT structure reference).
3. Writes `Workbench/.testreport-current` (single line: bare ID, e.g. `TESTREPORT-003`).

Where Step 1 resolved a non-default `workbenchDir`, pass `--testreports-dir <workbenchDir>/testreports` as well. Without it the script writes under `Workbench/testreports/` regardless of the config. The sidecar has no such override and is always written to `Workbench/.testreport-current`.

### TESTREPORT structure (inline reference)

```markdown
---
title: "TESTREPORT-NNN - <slug>"
type: testreport
testreport_id: NNN
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
created_by: test-foundry
git_sha: <short sha if available>
total_scenarios: N
passed: N
failed: N
skipped: N
---

# TESTREPORT-NNN - <slug>

## Summary

| Tier | Passed | Failed | Skipped |
|---|---|---|---|
| Python | N | N | N |
| LLM | N | N | N |
| **Total** | N | N | N |

## Python tier

PASS: <scenario_id>
- Duration: N ms
- Diagnostics: <text>

FAIL: <scenario_id>
- Duration: N ms
- Symptoms:
  - <symptom>
- Diagnostics: <text>

## LLM tier

(Same per-scenario PASS/FAIL block structure as above.)

## Diagnostics

(Any cross-cutting diagnostic notes - environment, git sha, harness version, deferred items.)
```

The per-scenario lines `PASS: ...` / `FAIL: ...` are line-anchored (start of line) so a caller can read a scenario's outcome out of the report with an anchored grep rather than a model.

---

## Step 7 - Cleanup and return

- Delete any synthetic PLAN files created by LLM scenarios.
- Return a `<pipeline-result>`-shaped structure with `outcome: success` (if no halt-on-failure trigger fired) and `diagnostics.testreport_path` populated.

Do not delete `Workbench/.python-tier-result.json`. Disposing of that file belongs to the caller that pre-ran the Python tier, and a later `mode=llm-tier-only` run reads it in Step 2b, so deleting it here breaks the next run.
