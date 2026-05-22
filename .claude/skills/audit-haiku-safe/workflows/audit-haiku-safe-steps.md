# Audit-Haiku-Safe Procedure

## Process

### Step 1: Validate preconditions
- Read the PLAN file at `plan_path`.
  - If unreadable → return `outcome: exception` with diagnostics.
- Confirm `_shared/plan-safe.md` exists and is readable.
  - If missing → `outcome: exception`.
- Check that audit-sufficiency has returned `outcome: success` for this PLAN. Inspect PLAN frontmatter `audit_state.last_stage` and `audit_state.last_outcome`:
  - If `last_stage == sufficiency AND last_outcome == success` (or any later stage with success): preconditions met, proceed.
  - Otherwise → `outcome: exception` with diagnostics: "audit-sufficiency precondition not satisfied; run audit-sufficiency first".

### Step 2: Per-step plan-safety review
For each numbered step in the PLAN's `## Steps` section:

For each step, evaluate against the five plan-safe criteria from `_shared/plan-safe.md`:
1. **Concrete:** specific file paths, exact command syntax, no "likely" / "probably" / "should".
2. **Unambiguous:** no judgement calls; executor runs the steps, doesn't redesign them.
3. **Atomic:** one operation per step; clear success/failure condition.
4. **Safe:** no destructive operations without explicit Human approval; no `--no-verify`/`--force` bypasses.
5. **Testable:** each step has independent, checkable verification criteria.

Classify each finding:
- **Blocker** (decision 14): would cause Haiku to halt, error, or require judgement mid-execution. Examples: "improve X", "audit Y", "if appropriate, Z".
- **Not blocker** (nit): would benefit from sharpening but doesn't block mechanical execution. Examples: line-number anchors instead of text matching; clearer commit message templates.

### Step 3: Cross-step coherence
- Sequencing: do steps reference earlier steps' outputs correctly? Do line-number references account for upstream edits (e.g. step N+1 says "delete lines 23-36" but step N already deleted lines 5-10)?
- File path consistency: do steps reference the same file using the same path style?
- Dependencies: does each step's preconditions hold given prior steps' postconditions?

### Step 4: Verification format check
For each item in the PLAN's `## Verification` section:
- Item must have a shell-runnable annotation directly below the prose:
  - `verify: <shell command>` (state assertion), OR
  - `acceptance: <shell command>` (behavioural check), OR
  - `verify: human` (subjective; surfaced for eyeball).
- At least one `acceptance:` item is required per PLAN (decision 25).
- Items missing the annotation entirely → Blocker.
- Items where the shell command is malformed (e.g. backticks not closed) → Blocker.
- PLAN with zero acceptance: items → Blocker (the Objective cannot be sampled-verified).

### Step 4a: Substrate fidelity check

This check runs after per-step plan-safety review (Step 2) and cross-step coherence (Step 3), before composing the output.

#### 4a.1 — PLANs with declared substrate (`substrate_files` non-empty)

For each PLAN whose frontmatter `substrate_files: [...]` contains at least one path:

1. **Extract named entities** from the PLAN's `## Steps` section matching substrate-grammar patterns:
   - **SQL column refs:** `table.column` dot-notation patterns (e.g. `event_log.description`, `session.name`)
   - **Python imports:** `from <module> import <symbol>` — extract `<symbol>` (and `<module>` for path-check)
   - **Enum string-literal values:** a quoted string literal adjacent to a variable typed as `*.kind`, `*.status`, or an `Enum` class reference (e.g. `kind="item_acquired"`, `improvisation_scope="cautious ally"`)
   - **Third-party API attributes:** `obj.<attr>` where the attribute starts with `_` (underscore) — these are private and must not be authored against

2. **Grep substrate files** for each extracted entity name (literal grep, case-sensitive):
   - For each entity, search all paths listed in `substrate_files`.
   - If the entity has at least one match across any substrate file → no finding.
   - If the entity has **zero matches** across all substrate files → emit a finding:
     ```
     code: SFV001
     level: error
     category: substrate-fidelity
     location: <step number where entity appears>
     message: "substrate-fidelity-violation: '<entity>' referenced in Step N but not found in any declared substrate file ([<substrate_files>])"
     suggested_fix: "Verify the entity name against the substrate file and correct the PLAN Steps."
     ```

3. **Private-attribute check:** For any `_`-prefixed attribute found in Steps (e.g. `s._tools`, `obj._private`), emit:
   ```
   code: SFV002
   level: error
   category: substrate-fidelity
   location: <step number>
   message: "substrate-fidelity-violation: '<attr>' is a private attribute (underscore-prefixed). The spec MUST author against documented public API surface only."
   suggested_fix: "Check the framework's documented public API for the equivalent public method/attribute."
   ```

#### 4a.2 — PLANs without declared substrate (heuristic detection)

For PLANs where `substrate_files` is empty or absent: apply the heuristic scanner to `## Steps`:

- Scan for substrate signals: SQL keywords (`CREATE TABLE`, `INSERT INTO`, `SELECT`, `ALTER TABLE`), Python imports (`from <module> import`), enum-literal adjacency patterns, third-party attribute access.
- Collect any substrate **file paths** that appear referenced in Steps body (e.g. `schema.py`, `enums.py`, `models.py`).

If any substrate signals are detected AND `substrate_files` is empty/absent → emit a `warn`-severity finding:
```
code: SFV003
level: warning
category: substrate-fidelity
location: "frontmatter"
message: "substrate-files-undeclared: heuristic detected substrate-grammar constructs in Steps (e.g. SQL column refs, Python imports, enum literals) but PLAN frontmatter has no substrate_files declaration. Declare the substrate files or acknowledge that no verification is needed."
suggested_fix: "Add substrate_files: [path/to/schema.py, ...] to PLAN frontmatter, or acknowledge this finding if no substrate ground-truth applies."
```

If no substrate signals detected and `substrate_files` is empty → no finding (no-substrate PLAN).

#### 4a.3 — Finding severity summary

| Code | Level | Trigger |
|------|-------|---------|
| SFV001 | error | Named entity in Steps not found in any declared substrate file |
| SFV002 | error | `_`-prefixed (private) attribute used in Steps against a third-party module |
| SFV003 | warning | Substrate-grammar constructs detected but `substrate_files` not declared |

`error`-level SFV findings are **Blockers** (they would cause the executor to author against non-existent schema/API, silently failing at runtime). `warning`-level SFV findings are **Not blockers** but surface as advisory items in the review output.

### Step 4b: Platform-portability check

This check runs after Step 4a (substrate fidelity) and before composing the output. It calls the `platform_portability.lint_plan()` module (at `lib/platform_portability.py`).

#### 4b.1 — Extract verify/acceptance lines

From the PLAN's `## Verification` section, extract every line that:
- Begins with `verify:` (including `verify: human`)
- Begins with `acceptance:`

These are the shell-runnable annotations below each prose checkbox item.

#### 4b.2 — Annotation check

For each extracted line:
1. Check whether the line ends with `# platform: posix` or `# platform: windows` (trailing comment, case-insensitive).
2. If the annotation is present → skip the portability pattern scan for this line (the author has declared intentional platform scope). Record the annotation as advisory context only.

#### 4b.3 — Forbidden-pattern scan

For each unannotated line, scan for the following forbidden patterns:

| Pattern | Code | Rationale |
|---------|------|-----------|
| `/tmp/` | PPV001 | Linux-only temp path |
| `/dev/null` | PPV002 | POSIX-only null device |
| `bash -c` | PPV003 | Explicitly invokes bash; unavailable on Windows |
| `test -[a-zA-Z]` | PPV004 | POSIX `test` builtin |
| `> /dev/` | PPV005 | Redirect to `/dev/` pseudo-device |
| `2>/dev/null` | PPV006 | POSIX stderr suppression |
| `&&` in compound commands | PPV007 | PowerShell-incompatible; suggest `; if ($?) { ... }` |

For each pattern match, emit a `warn`-severity finding:

```
code: PPV001  (or PPV002–PPV007 per pattern)
level: warning
category: platform-portability
location: "Verification — <verify/acceptance line text (truncated to 80 chars)>"
message: "platform-portability-violation: <pattern> in verify/acceptance line. Either rewrite to a portable form or annotate with # platform: <posix|windows>."
suggested_fix: "<pattern-specific portable alternative>"
```

#### 4b.4 — Finding severity classification

All platform-portability findings are `warn`-severity — **Not blockers** by default. The plan can execute on CI (the canonical baseline); the violation is a portability advisory for Windows consumers. Promote to **Blocker** only if the PLAN's `assigned_to` is `haiku` or `sonnet` and the CI environment is explicitly Windows (rare; annotate in review).

`warn`-severity findings appear in the **Not blockers** subgroup in the review output.

### Step 4c: Falsifiability check

This check runs after Step 4b (platform-portability) and before composing the output. It calls the `falsifiability.lint_plan()` module (at `lib/falsifiability.py`).

#### 4c.1 — What is a falsifiability violation?

A verification assertion is **vacuous** when its passing path requires no real condition — i.e. the expression evaluates to True regardless of implementation state. Vacuous assertions provide false confidence: the PLAN appears verified when nothing meaningful was tested.

Common patterns that make an assertion vacuous (Q1 α blocklist, PLAN-AB5):

| Pattern | Code | Rationale |
|---------|------|-----------|
| `or callable(...)` | FAL001-a | `callable()` is True for any function or class; `or` arm always passes |
| `or True` | FAL001-b | short-circuits to True unconditionally |
| `and True` | FAL001-c | identity; adds no constraint and may signal an incomplete assertion |
| `hasattr(...) or <non-eq-expr>` | FAL001-d | `or` arm means the expression passes even if `hasattr` returns False |
| `any(... True ...)` or `any(callable(...) ...)` | FAL001-e | literal True or always-truthy callable() inside any() guarantees the result is True |
| `or <x> is not None and True` | FAL001-f | `and True` is a no-op; vacuous when `<x> is not None` |

#### 4c.2 — Scope of scan

Only `verify:` and `acceptance:` lines in the PLAN's `## Verification` section are scanned. Body text in `## Steps`, `## Context`, or other sections is NOT flagged — falsifiability only applies to assertions that are actually executed to determine pass/fail.

A line annotated with `# falsifiability: waive` is skipped (the author has declared the pattern is intentional).

#### 4c.3 — Finding format

For each matched pattern, emit a `warn`-severity finding:

```
code: FAL001-<sub>   (a–f per pattern)
level: warning
category: falsifiability
location: "Verification — <verify/acceptance line text (truncated to 80 chars)>"
message: "falsifiability-violation: <pattern rationale>. This assertion may always pass regardless of implementation state."
suggested_fix: "<pattern-specific rewrite hint>"
```

#### 4c.4 — Finding severity classification

All falsifiability findings are `warn`-severity — **Not blockers** by default (per Q2 β, PLAN-AB5). Some vacuous patterns are legitimate (e.g. intentional `or None` for an absent-value check) and an operator needs the opportunity to acknowledge or rewrite. Promote to **Blocker** only if the same finding has recurred across two or more audit iterations without acknowledgement.

`warn`-severity findings appear in the **Not blockers** subgroup in the review output.

### Step 5: Compose review output
Format per CLAUDE.md "Reviews" rule:
1. **Verification preamble** (1-2 sentences): what files were inspected (the PLAN, _shared/plan-safe.md, any referenced source files).
2. **Verdict** (one line): "Mechanically executable" / "N plan-safety blockers — revision needed" / "Pre-condition violation".
3. **Plan-safety section** with two subgroups:
   - `**Blockers**` (numbered, priority-ordered): prose + which plan-safe criterion violated + suggested fix shape (without authoring it).
   - `**Not blockers**`: brief list.
4. **Net verdict**: "ready to advance" / "revise the N blockers and re-audit".
5. **Machine-readable summary**: `Blockers: N` on its own line.

### Step 6: Decision-triage of Human-input items (if any)
If any finding asks the Human for input (rare for plan-safety, common for sufficiency), classify each per parent PLAN 202605011400 decision 15:
- **Already locked** — Human proposed/affirmed earlier; no question.
- **Mechanically forced** — only one alternative; no question.
- **Real judgement call** — surface as a question.

### Step 7: Emit the pipeline-result block
End the agent's response with:
```
<pipeline-result>
```json
{
  "outcome": "success" | "revision_needed" | "exception",
  "payload": {
    "blockers_count": <int>,
    "review_text": "<the formatted review>"
  },
  "diagnostics": { /* if outcome != success */ }
}
```
</pipeline-result>
```

The orchestrator parses this block to drive the audit-loop state machine (decision 21).
