---
name: test-foundry
description: Run the plan-foundry test harness (Python tier + LLM scenarios) and write a portable TESTREPORT. Trigger phrases "run plan-foundry tests" / "test the harness" / "test-foundry". Accepts an optional `mode` argument — `full` (default) or `llm-tier-only`.
model: sonnet
---

## Purpose

Exercises plan-foundry behaviour against expected outcomes and emits a portable, sequentially-numbered MD test report at `Workbench/testreports/TESTREPORT-NNN_<slug>.md`. Two execution tiers:

- **Python tier** — deterministic / structural tests (run via `lib/run_python_tier.py`).
- **LLM-driven tier** — scenario walks where Claude invokes plan-foundry skills and the harness asserts on mechanical effects (disk state, frontmatter transitions, files created).

Designed for execution in a real consumer (e.g. the Reeve repo) after `init-plan-foundry` has bootstrapped plan_foundry there. The TESTREPORT is the cross-back artefact: the human copies it from the consumer back into the plan_foundry_dev repo's `Workbench/testreports/` to inform further development.

---

## Trigger phrases

- "run plan-foundry tests"
- "test the harness"
- "test-foundry"

---

## Preconditions

- `Workbench/` exists (consumer has run `init-plan-foundry`).
- `Workbench/testreports/` exists or can be created.
- The test-foundry skill is present at `.claude/skills/test-foundry/` (post-PLAN-AC3 flat layout — no longer a separate plugin).
- For `mode=llm-tier-only`: `Workbench/.python-tier-result.json` exists on disk (pre-run by the executor in Step 13a of PLAN-AA8 or equivalent caller).

---

## Inputs

```
mode: full | llm-tier-only   (default: full)
slug: <optional human-readable slug>   (default: auto-generated from date YYYY-MM-DD)
```

- `mode=full` — runs Python tier discovery + execution + LLM tier; used in fresh parent-session invocations.
- `mode=llm-tier-only` — skips Python discovery; reads pre-run Python results from `Workbench/.python-tier-result.json`. Used by the PLAN-AA8 Step 13b orchestrator handoff after Step 13a pre-ran the Python tier from the executor.

**Invocation context constraint:** this skill MUST be invoked from the parent session (orchestrator), not from a subagent. The LLM tier driver issues parent-session `Skill(...)` calls (see `workflows/run-tests.md`), which a subagent cannot dispatch.

---

## Procedure

See [`workflows/run-tests.md`](workflows/run-tests.md) for the full step-by-step procedure.

High-level flow:
1. If `mode=full`: invoke `python3 .claude/skills/test-foundry/lib/run_python_tier.py --json` and parse the structured result. If `mode=llm-tier-only`: read `Workbench/.python-tier-result.json` from disk.
2. Load LLM scenario specs from `.claude/skills/test-foundry/scenarios/llm/*.md`.
3. For each LLM scenario: call `lib/llm_tier_helpers.prep_scenario`, dispatch the enumerated `Skill(...)` invocations from parent session, call `lib/llm_tier_helpers.capture_assertions`, collect the per-scenario result dict.
4. Aggregate Python-tier + LLM-tier results.
5. Allocate the next TESTREPORT ID via `lib/next_testreport_id.py`.
6. Write `Workbench/testreports/TESTREPORT-NNN_<slug>.md` via `lib/write_testreport.py` and the sidecar `Workbench/.testreport-current` (single line: the bare ID, e.g. `TESTREPORT-003`).

---

## Output schema

```json
{
  "outcome": "success | exception",
  "payload": {
    "outcome_subtype": "done | partially-complete | blocked",
    "executor_notes": "string",
    "files_modified": ["Workbench/testreports/TESTREPORT-NNN_<slug>.md", "Workbench/.testreport-current"]
  },
  "diagnostics": {
    "testreport_path": "Workbench/testreports/TESTREPORT-NNN_<slug>.md",
    "python_tier": { "passed": N, "failed": N },
    "llm_tier": { "passed": N, "failed": N }
  }
}
```

---

## References

- [`workflows/run-tests.md`](workflows/run-tests.md) — orchestration procedure
- `lib/run_python_tier.py` — Python tier discovery + execution driver
- `lib/llm_tier_helpers.py` — LLM tier prep + capture helpers
- `lib/write_testreport.py` — TESTREPORT writer
- `lib/next_testreport_id.py` — TESTREPORT ID allocator
- `scenarios/python/` — Python tier scenarios (`test_*.py`)
- `scenarios/llm/` — LLM tier scenario specs (`*.md`)

---

## Constraints

- Never modifies any production PLAN under `Workbench/`. LLM scenarios that synthesise PLANs must use disposable, clearly-prefixed names (e.g. `PLAN-test-retire-XX.md`) and clean them up.
- Always writes the sidecar `Workbench/.testreport-current` alongside the TESTREPORT — downstream verification depends on this anchor.
- Python tier scenarios expose synchronous `run() -> dict`. No pytest dependency.
- LLM tier helpers (`prep_scenario`, `capture_assertions`) never re-enter Claude reasoning themselves — the parent-session SKILL workflow drives the `Skill(...)` dispatches.
