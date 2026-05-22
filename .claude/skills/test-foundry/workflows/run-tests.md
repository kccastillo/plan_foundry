# test-foundry — run-tests workflow

Orchestrates the two-tier harness and writes the TESTREPORT.

This workflow is invoked from `SKILL.md`. It runs in **parent session** (orchestrator) context, because the LLM tier issues `Skill(...)` dispatches that subagents cannot make.

---

## Inputs

- `mode`: `full` (default) | `llm-tier-only`
- `slug`: optional human-readable slug; defaults to `YYYY-MM-DD` from today's date.

---

## Step 1 — Resolve repo root and `Workbench/`

Locate the repository root by walking up from cwd until a directory containing `Workbench/` is found. If `.claude/plan-foundry.config` exists and declares `workbenchDir`, prefer that. Default: `Workbench/` relative to repo root.

Ensure `Workbench/testreports/` exists; if not, create it.

---

## Step 2 — Python tier

### Step 2a — `mode=full`: run the Python tier discovery + execution

Invoke:

```
python3 .claude/skills/test-foundry/lib/run_python_tier.py --json --output Workbench/.python-tier-result.json
```

Then read `Workbench/.python-tier-result.json` from disk into a Python dict named `python_tier`.

### Step 2b — `mode=llm-tier-only`: read the pre-run result

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

## Step 3 — Load LLM scenario specs

Glob `.claude/skills/test-foundry/scenarios/llm/*.md`. For each spec file, parse:

- Title (first `# ` heading).
- Scenario ID (filename stem).
- Body (the markdown, used by the executor narrative + by `prep_scenario` for fixture instructions).
- Mechanical assertions (lines or blocks tagged `**Assertion:**` in the body).

---

## Step 4 — Run LLM scenarios (parent-session loop)

For each LLM scenario spec, in deterministic order (alphabetical by scenario ID):

1. Call `prep_scenario(spec_path)` from `lib/llm_tier_helpers.py`. This prepares fixtures on disk (synthetic Workbench dir, seed PLAN files, env vars). Returns a `context` dict.
2. Read the scenario spec body to identify which `Skill(...)` calls the scenario specifies (e.g. `Skill("write-plan", ...)`, `Skill("audit-sufficiency", ...)`, `Skill("plan-pipeline", ...)`).
3. **Dispatch each `Skill(...)` call from parent session.** Capture the structured response.
4. Call `capture_assertions(scenario_id, expected)` from `lib/llm_tier_helpers.py`, passing the assertion list from the spec body. The helper inspects disk state and returns:

   ```json
   { "scenario": "<id>", "status": "pass | fail", "symptoms": [...], "diagnostics": "...", "duration_ms": N }
   ```

5. Append the result to a list `llm_tier_scenarios`.
6. Clean up scenario fixtures created in (1) — remove temp dirs, restore any pre-existing files.

If parent-session dispatch is not feasible (this workflow is being read from a subagent context), the helper will log "skipped — subagent invocation" for every scenario.

---

## Step 5 — Aggregate

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
            "skipped": <count where status=='skip'>,
        },
    },
    "summary": {
        "passed": python_tier.summary.passed + llm_tier.summary.passed,
        "failed": python_tier.summary.failed + llm_tier.summary.failed,
        "skipped": python_tier.summary.skipped + llm_tier.summary.skipped,
    },
}
```

---

## Step 6 — Allocate ID and write TESTREPORT

Invoke `lib/write_testreport.py` with the aggregated results and the slug:

```
python3 .claude/skills/test-foundry/lib/write_testreport.py --slug "<slug>" --results-json Workbench/.python-tier-result.json
```

(Alternatively, the SKILL body can import `write_testreport` and call it in-process; the CLI is the portable invocation surface.)

`write_testreport.py`:

1. Calls `next_testreport_id.allocate()` to get the next ID (e.g. `003`).
2. Writes `Workbench/testreports/TESTREPORT-NNN_<slug>.md` with the schema described inline below (see TESTREPORT structure reference).
3. Writes `Workbench/.testreport-current` (single line: bare ID, e.g. `TESTREPORT-003`).

### TESTREPORT structure (inline reference)

```markdown
---
title: "TESTREPORT-NNN — <slug>"
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

# TESTREPORT-NNN — <slug>

## Summary

| Tier | Passed | Failed | Skipped |
|---|---|---|---|
| Python | N | N | N |
| LLM | N | N | N |
| **Total** | N | N | N |

## Python tier

### PASS: <scenario_id>
- Duration: N ms
- Diagnostics: <text>

### FAIL: <scenario_id>
- Duration: N ms
- Symptoms:
  - <symptom>
- Diagnostics: <text>

## LLM tier

(Same per-scenario PASS/FAIL block structure as above.)

## Diagnostics

(Any cross-cutting diagnostic notes — environment, git sha, harness version, deferred items.)
```

The per-scenario lines `PASS: ...` / `FAIL: ...` are line-anchored (start of line) so the PLAN-AA8 acceptance grep works.

---

## Step 7 — Cleanup and return

- Delete any synthetic PLAN files created by LLM scenarios.
- Return a `<pipeline-result>`-shaped structure with `outcome: success` (if no halt-on-failure trigger fired) and `diagnostics.testreport_path` populated.

Do NOT delete `Workbench/.python-tier-result.json` — that is the orchestrator's responsibility (PLAN-AA8 Step 13b post-commit).
