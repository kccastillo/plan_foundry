# INDEX Alerts Specification v1

Eleven alert categories produced by `build_index.py`. All thresholds are hardcoded in v1. Configurability is tracked for future development.

---

## Hardcoded Thresholds

| Threshold | Value | Field |
|---|---|---|
| `long_blocked` | 7 days | `THRESHOLD_LONG_BLOCKED_DAYS` in `build_index.py` |
| `verification_pending_too_long` | 24 hours | `THRESHOLD_VERIFICATION_PENDING_HOURS` |
| `stuck_audits` | iteration ≥ 3 | `THRESHOLD_STUCK_AUDIT_ITERATIONS` |
| `recurring_blockers` | same fingerprint in 2+ iterations | n/a (direct comparison) |
| `executor_hung` | `phase == running` AND `last_tick_at > 10 min ago` | `THRESHOLD_EXECUTOR_HUNG_SECONDS` in `build_index.py` |
| `stuck_ideation` | `ideate_phase` non-terminal AND last commit modifying PLAN > 24h ago | `THRESHOLD_STUCK_IDEATION_HOURS` in `build_index.py` |

---

## Alert Definitions

### 1. stuck_audits

**Condition:** A PLAN's `audit_state.sufficiency_iterations` or `audit_state.plan_safety_iterations` has reached the stuck-audit threshold (≥ 3 iterations) without the stage completing with `success`.

**Severity:** Warning

**Check logic:**
```python
max(sufficiency_iterations, plan_safety_iterations) >= THRESHOLD_STUCK_AUDIT_ITERATIONS
```

**Example output:**
```json
{
  "plan_id": "PLAN-022_audit-and-index-v2",
  "detail": "Audit iterations: sufficiency=3, plan_safety=0"
}
```

**Remediation:** Human should review the audit findings, resolve blockers, and either revise the PLAN or acknowledge persistent findings.

---

### 2. long_blocked

**Condition:** A PLAN with `status: blocked` and a non-empty `blocked_by` field has been in that state for more than 7 days (measured from the `created` date as an approximation — plan-level block timestamps not tracked in v1).

**Severity:** Warning

**Check logic:**
```python
status == "blocked" and blocked_by and (now - created_date).days >= 7
```

**Example output:**
```json
{
  "plan_id": "PLAN-006_plan-of-plans-harness-cleanup",
  "detail": "Blocked for 12 days (threshold: 7). Blocked by: PLAN-005_foundry-keeper.md"
}
```

**Remediation:** Resolve the blocking dependency or explicitly note in PLAN frontmatter that the block is intentional and the due date has been updated.

---

### 3. recurring_blockers

**Condition:** A PLAN has two consecutive audit iterations (same auditor) where an `error`-level finding with the same fingerprint appears in both. Indicates an error the Human has not resolved and the auditor is re-raising.

**Severity:** Error

**Check logic:**
```python
# For sufficiency or plan_safety iterations:
iter_fps[i] & iter_fps[i-1]  # intersection of error fingerprints across consecutive iterations
```

**Example output:**
```json
{
  "plan_id": "PLAN-022_audit-and-index-v2",
  "detail": "Error fingerprint(s) recur across audit iterations 1 and 2: a3f7c2d1"
}
```

**Remediation:** Resolve the recurring error, acknowledge it in `audit_acknowledgements` (if accepted as-is), or dispute it in `audit_disputes`. The `[STUCK ×N]` badge in the severity-surface downstream is keyed to this alert.

---

### 4. orphaned_audit_files

**Condition:** A JSON file exists in `Workbench/.audit/` whose `<plan-id>` prefix does not correspond to any current `*.md` PLAN file in `Workbench/`.

**Severity:** Note

**Check logic:**
```python
for audit_file in .audit/*.json:
    plan_id = audit_file.stem.rsplit("-", 1)[0]  # strip iteration suffix
    if plan_id not in known_plan_ids:
        raise alert
```

**Example output:**
```json
{
  "plan_id": "202605110000_PLAN_old-retired-plan",
  "detail": "Audit file 202605110000_PLAN_old-retired-plan-2.json has no corresponding PLAN in Workbench/."
}
```

**Remediation:** Delete the orphaned audit files or move them alongside the retired PLAN in `Retired/.audit/` (if such a directory exists). Orphaned files do not affect pipeline operation but accumulate over time.

---

### 5. circular_dependencies

**Condition:** A cycle is detected in the `triggers_plans` dependency graph. PLAN A triggers PLAN B which (transitively) triggers PLAN A.

**Severity:** Error

**Check logic:**
```python
# DFS cycle detection on triggers_plans edges
```

**Example output:**
```json
{
  "plan_id": "PLAN-010_plugin-extraction-of-foundry",
  "detail": "Circular dependency detected: PLAN-010_plugin-extraction-of-foundry → PLAN-016_phase-1-core-extraction"
}
```

**Remediation:** Break the cycle by removing one of the `triggers_plans` edges. The orchestrator's children-gate (Step 3 of dispatch.md) would deadlock on a circular dependency — this alert surfaces it before execution begins.

---

### 6. verification_pending_too_long

**Condition:** A PLAN with `pipeline_phase: outcome-verifying` and `verification_state.human_verdict: pending` has been in that state for more than 24 hours (measured from `created` date as an approximation — outcome-verifying start time not tracked separately in v1).

**Severity:** Warning

**Check logic:**
```python
pipeline_phase == "outcome-verifying" and human_verdict == "pending" and age_hours >= 24
```

**Example output:**
```json
{
  "plan_id": "202605050000_PLAN_some-plan",
  "detail": "Awaiting human verification for 28.5 hours (threshold: 24h)."
}
```

**Remediation:** The Human should respond to the outcome-verification prompt with 'all good' or a rejection reason. The orchestrator re-enters on the next reply.

---

### 7. orphaned_threads

**Condition:** A thread ID referenced in a PLAN's `closes_thread` or `advances_thread` does not appear in `ROADMAP.md` (or ROADMAP.md is absent).

**Severity:** Note

**Note:** v1 does not validate against ROADMAP.md content (ROADMAP.md parsing deferred to future dev). This alert category is reserved; no instances will be generated until ROADMAP.md cross-validation is implemented.

**Example output (future):**
```json
{
  "plan_id": "PLAN-022_audit-and-index-v2",
  "detail": "Thread 'T07' referenced in closes_thread not found in ROADMAP.md."
}
```

**Remediation:** Add the thread to ROADMAP.md or remove the `closes_thread` field from the PLAN.

---

### 8. malformed_frontmatter

**Condition:** A PLAN file is missing `schema_version: 2` in its frontmatter, or the value is not `2`. This indicates a pre-v2 PLAN that has not been migrated.

**Severity:** Warning

**Check logic:**
```python
schema_version is None or str(schema_version) != "2"
```

**Example output:**
```json
{
  "plan_id": "PLAN-001_rewrite-roadmap",
  "detail": "Missing schema_version field. Expected schema_version: 2."
}
```

**Remediation:** Add `schema_version: 2` to the PLAN's frontmatter and add the v2 fields (`tags`, `files_touched`, `audit_acknowledgements`, etc.). The clean-break migration decision means no v1 backward-compat code runs — PLANs without `schema_version: 2` are valid but flagged.

---

### 9. executor_hung

**Condition:** A heartbeat file exists in `Workbench/.heartbeat/` with `phase == "running"` AND `now - last_tick_at > 10 minutes`. Indicates the background executor has stopped ticking and may be hung or crashed without writing an exit heartbeat.

**Severity:** Warning

**Check logic:**
```python
# During INDEX build, scan Workbench/.heartbeat/*.json
phase == "running" and (now - last_tick_at).total_seconds() > THRESHOLD_EXECUTOR_HUNG_SECONDS
```

**Example output:**
```json
{
  "plan_id": "PLAN-023_executor-heartbeat",
  "detail": "Executor heartbeat stale for 18.3 min (last tick: 2026-05-13T10:05:00Z). Phase: running, step 4."
}
```

**Remediation:** Check whether the background executor process is still active. If the session was interrupted, re-invoke `plan-pipeline` with the PLAN path — the orchestrator's idempotency check will surface the stale heartbeat warning and allow recovery. If the executor completed but did not write an exit heartbeat, wait for the completion message or manually delete the heartbeat file and re-enter.

---

### 10. orphan_heartbeat

**Condition:** A heartbeat file exists in `Workbench/.heartbeat/` whose `plan_id` does not correspond to any current `*.md` PLAN file in `Workbench/`. This indicates a leftover from a retired or moved PLAN.

**Severity:** Note

**Garbage collection:** The INDEX builder deletes orphaned heartbeat files whose `plan_id` doesn't match any active PLAN. This is the only write action `build_index.py` performs outside of INDEX output files.

**Check logic:**
```python
for hb_file in Workbench/.heartbeat/*.json:
    plan_id = json.load(hb_file).get("plan_id") or hb_file.stem
    if plan_id not in known_plan_ids:
        raise alert; delete hb_file
```

**Example output:**
```json
{
  "plan_id": "202605110000_PLAN_old-retired-plan",
  "detail": "Heartbeat file has no corresponding PLAN in Workbench/. File deleted."
}
```

**Remediation:** No manual action needed — the INDEX builder cleans these up automatically. If the alert appears repeatedly, verify the PLAN retirement flow is deleting heartbeats correctly.

---

---

### 11. stuck_ideation

**Condition:** A PLAN has `ideate_phase` set to a non-terminal value (not `complete` or `exited_early`) AND the last git commit modifying the PLAN file was more than 24 hours ago. Indicates the ideate cadence session has stalled without either completing or explicitly exiting.

**Severity:** Warning

**Check logic:**
```python
ideate_phase not in {complete, exited_early, ""}  # non-terminal, non-empty
AND (now - last_git_commit_touching_plan_file).total_seconds() / 3600 >= 24
```

**Example output:**
```json
{
  "plan_id": "PLAN-025_ideate-cadence-pipeline",
  "detail": "ideate_phase='self_critique' (non-terminal) and last commit was 28.0h ago (threshold: 24h). Ideate may be stalled. Check in or /checkpoint."
}
```

**Remediation:** Resume the ideate session with `resume ideate <plan-id>` to pick up from the saved `ideate_phase`. If the session is abandoned intentionally, set `ideate_phase: exited_early` in the PLAN frontmatter to clear the alert. Use `/checkpoint` to preserve the current conversation state before resuming.

---

## Alert Storage in .index.json

All eleven alert categories are always present in `.index.json`, even if empty:

```json
{
  "alerts": {
    "stuck_audits": [],
    "long_blocked": [],
    "recurring_blockers": [],
    "orphaned_audit_files": [],
    "circular_dependencies": [],
    "verification_pending_too_long": [],
    "orphaned_threads": [],
    "malformed_frontmatter": [],
    "executor_hung": [],
    "orphan_heartbeat": [],
    "stuck_ideation": []
  }
}
```

Each entry is an object with `plan_id` (string) and `detail` (string).
