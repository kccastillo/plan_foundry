# Audit-Haiku-Safe Procedure

## Process

### Step 1: Validate preconditions
- Read the PLAN file at `plan_path`.
  - If unreadable -> return `outcome: exception` with diagnostics.
- Confirm `_shared/plan-safe.md` exists and is readable.
  - If missing -> `outcome: exception`.
- Check that audit-sufficiency has returned `outcome: success` for this PLAN. Inspect PLAN frontmatter `audit_state.last_stage` and `audit_state.last_outcome`:
  - If `last_stage == sufficiency AND last_outcome == success` (or any later stage with success): preconditions met, proceed.
  - Otherwise -> `outcome: exception` with diagnostics: "audit-sufficiency precondition not satisfied; run audit-sufficiency first".

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
- Items missing the annotation entirely -> Blocker.
- Items where the shell command is malformed (e.g. backticks not closed) -> Blocker.
- PLAN with zero acceptance: items -> Blocker (the Objective cannot be sampled-verified).

### Step 4a: Substrate fidelity check

This check runs after per-step plan-safety review (Step 2) and cross-step coherence (Step 3), before composing the output.

#### 4a.1 - PLANs with declared substrate (`substrate_files` non-empty)

For each PLAN whose frontmatter `substrate_files: [...]` contains at least one path:

1. **Extract named entities** from the PLAN's `## Steps` section matching substrate-grammar patterns:
   - **SQL column refs:** `table.column` dot-notation patterns (e.g. `event_log.description`, `session.name`)
   - **Python imports:** `from <module> import <symbol>` - extract `<symbol>` (and `<module>` for path-check)
   - **Enum string-literal values:** a quoted string literal adjacent to a variable typed as `*.kind`, `*.status`, or an `Enum` class reference (e.g. `kind="item_acquired"`, `improvisation_scope="cautious ally"`)
   - **Third-party API attributes:** `obj.<attr>` where the attribute starts with `_` (underscore) - these are private and must not be authored against

2. **Grep substrate files** for each extracted entity name (literal grep, case-sensitive):
   - For each entity, search all paths listed in `substrate_files`.
   - If the entity has at least one match across any substrate file -> no finding.
   - If the entity has **zero matches** across all substrate files -> emit a finding:
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

#### 4a.2 - PLANs without declared substrate (heuristic detection)

For PLANs where `substrate_files` is empty or absent: apply the heuristic scanner to `## Steps`:

- Scan for substrate signals: SQL keywords (`CREATE TABLE`, `INSERT INTO`, `SELECT`, `ALTER TABLE`), Python imports (`from <module> import`), enum-literal adjacency patterns, third-party attribute access.
- Collect any substrate **file paths** that appear referenced in Steps body (e.g. `schema.py`, `enums.py`, `models.py`).

If any substrate signals are detected AND `substrate_files` is empty/absent -> emit a `warn`-severity finding:
```
code: SFV003
level: warning
category: substrate-fidelity
location: "frontmatter"
message: "substrate-files-undeclared: heuristic detected substrate-grammar constructs in Steps (e.g. SQL column refs, Python imports, enum literals) but PLAN frontmatter has no substrate_files declaration. Declare the substrate files or acknowledge that no verification is needed."
suggested_fix: "Add substrate_files: [path/to/schema.py, ...] to PLAN frontmatter, or acknowledge this finding if no substrate ground-truth applies."
```

If no substrate signals detected and `substrate_files` is empty -> no finding (no-substrate PLAN).

#### 4a.3 - Finding severity summary

| Code | Level | Trigger |
|------|-------|---------|
| SFV001 | error | Named entity in Steps not found in any declared substrate file |
| SFV002 | error | `_`-prefixed (private) attribute used in Steps against a third-party module |
| SFV003 | warning | Substrate-grammar constructs detected but `substrate_files` not declared |

`error`-level SFV findings are **Blockers** (they would cause the executor to author against non-existent schema/API, silently failing at runtime). `warning`-level SFV findings are **Not blockers** but surface as advisory items in the review output.

### Step 4b: Platform-portability check

This check runs after Step 4a (substrate fidelity) and before composing the output. It calls the `platform_portability.lint_plan()` module (at `lib/platform_portability.py`).

#### 4b.1 - Extract verify/acceptance lines

From the PLAN's `## Verification` section, extract every line that:
- Begins with `verify:` (including `verify: human`)
- Begins with `acceptance:`

These are the shell-runnable annotations below each prose checkbox item.

#### 4b.2 - Annotation check

For each extracted line:
1. Check whether the line ends with `# platform: posix` or `# platform: windows` (trailing comment, case-insensitive).
2. If the annotation is present -> skip the portability pattern scan for this line (the author has declared intentional platform scope). Record the annotation as advisory context only.

#### 4b.3 - Forbidden-pattern scan

For each unannotated line, scan for the following forbidden patterns:

| Pattern | Code | Rationale |
|---------|------|-----------|
| `/tmp/` | PPV001 | Linux-only temp path; use `tempfile` Python module for portable alternatives |
| `/dev/null` | PPV002 | POSIX-only null device; use `subprocess.DEVNULL` or redirect suppression in Python |
| `bash -c` | PPV003 | Explicitly invokes bash; unavailable or differently-pathed on Windows |
| `test -[a-zA-Z]` | PPV004 | POSIX `test` builtin; use Python `os.path.exists()` / `pathlib` patterns instead |
| `> /dev/` | PPV005 | Redirect to `/dev/` pseudo-device; POSIX-only |
| `2>/dev/null` | PPV006 | POSIX stderr suppression; use Python subprocess or annotate |
| `&&` in compound commands | PPV007 | Works in bash but breaks PowerShell 5.1; split into separate commands or annotate |

For each pattern match, emit a `warn`-severity finding:

```
code: PPV001  (or PPV002-PPV007 per pattern)
level: warning
category: platform-portability
location: "Verification - <verify/acceptance line text (truncated to 80 chars)>"
message: "platform-portability-violation: <pattern> in verify/acceptance line. Either rewrite to a portable form or annotate with # platform: <posix|windows>."
suggested_fix: "<pattern-specific portable alternative>"
```

#### 4b.4 - Finding severity classification

All platform-portability findings are `warn`-severity - **Not blockers** by default. The plan can execute on CI (the canonical baseline); the violation is a portability advisory for Windows consumers. Promote to **Blocker** only if the PLAN's `assigned_to` is `haiku` or `sonnet` and the CI environment is explicitly Windows (rare; annotate in review).

`warn`-severity findings appear in the **Not blockers** subgroup in the review output.

### Step 4c: Falsifiability check

This check runs after Step 4b (platform-portability) and before composing the output. It calls the `falsifiability.lint_plan()` module (at `lib/falsifiability.py`).

#### 4c.1 - What is a falsifiability violation?

A verification assertion is **vacuous** when its passing path requires no real condition - i.e. the expression evaluates to True regardless of implementation state. Vacuous assertions provide false confidence: the PLAN appears verified when nothing meaningful was tested.

Common patterns that make an assertion vacuous (Q1 α blocklist, PLAN-AB5):

| Pattern | Code | Rationale |
|---------|------|-----------|
| `or callable(...)` | FAL001-a | `callable()` is True for any function or class; `or` arm always passes |
| `or True` | FAL001-b | short-circuits to True unconditionally |
| `and True` | FAL001-c | identity; adds no constraint and may signal an incomplete assertion |
| `hasattr(...) or <non-eq-expr>` | FAL001-d | `or` arm means the expression passes even if `hasattr` returns False |
| `any(... True ...)` or `any(callable(...) ...)` | FAL001-e | literal True or always-truthy callable() inside any() guarantees the result is True |
| `or <x> is not None and True` | FAL001-f | `and True` is a no-op; vacuous when `<x> is not None` |

#### 4c.2 - Scope of scan

Only `verify:` and `acceptance:` lines in the PLAN's `## Verification` section are scanned. Body text in `## Steps`, `## Context`, or other sections is NOT flagged - falsifiability only applies to assertions that are actually executed to determine pass/fail.

A line annotated with `# falsifiability: waive` is skipped (the author has declared the pattern is intentional).

#### 4c.3 - Finding format

For each matched pattern, emit a `warn`-severity finding:

```
code: FAL001-<sub>   (a-f per pattern)
level: warning
category: falsifiability
location: "Verification - <verify/acceptance line text (truncated to 80 chars)>"
message: "falsifiability-violation: <pattern rationale>. This assertion may always pass regardless of implementation state."
suggested_fix: "<pattern-specific rewrite hint>"
```

#### 4c.4 - Finding severity classification

All falsifiability findings are `warn`-severity - **Not blockers** by default (per Q2 β, PLAN-AB5). Some vacuous patterns are legitimate (e.g. intentional `or None` for an absent-value check) and an operator needs the opportunity to acknowledge or rewrite. Promote to **Blocker** only if the same finding has recurred across two or more audit iterations without acknowledgement.

`warn`-severity findings appear in the **Not blockers** subgroup in the review output.

### Step 4d: Step-count check (PSZ001)

This check runs after Step 4c (falsifiability) and before composing the output. It implements
the D4 algorithm from PLAN-AC7 to detect oversized PLANs.

#### 4d.1 - Count top-level Steps (D4 algorithm)

1. Locate the `## Steps` heading in the PLAN body.
2. Extract the text between that heading and the next line that begins with `## ` (or end of file
   if no subsequent heading exists).
3. Count lines in that extracted block that match the regex `^\d+\.\s+` (one or more digits,
   followed by a literal period, followed by one or more whitespace characters, followed by
   content). These are top-level Step lines.
4. Lines starting with leading whitespace before the digit (sub-items) and letter-prefixed items
   (e.g. `a.`, `b.`) are **not** counted.

#### 4d.2 - Check threshold and acknowledgement

- If the Step count is <= 12 -> **no finding**. Proceed to Step 5.
- If the Step count is > 12:
  - Read the PLAN's frontmatter `audit_acknowledgements:` list.
  - If `PSZ001` appears in the list -> **no finding** (acknowledgement suppresses the advisory).
  - If `PSZ001` does NOT appear in the list -> emit a Not-blocker advisory finding:

```
code: PSZ001
level: warning
category: plan-sizing
location: "## Steps"
message: "oversized-plan: PLAN has <N> top-level Steps (ceiling is 12, per D1 - PLAN-AC7).
          Decompose into a plan-of-plans or sequential PLANs, or add PSZ001 to
          audit_acknowledgements with a rationale in the Context section."
suggested_fix: "Split into a plan-of-plans (parent PLAN with triggers_plans: [...]) or
               sequential PLANs. If decomposition is genuinely impractical, add PSZ001 to
               audit_acknowledgements and document the rationale in Context."
```

#### 4d.3 - Finding severity classification

PSZ001 is always `warn`-severity - **Not blocker**. The ceiling is a heuristic; a genuinely
atomic large PLAN must be allowed to pass with a recorded acknowledgement. PSZ001 MUST NOT be
promoted to Blocker by the auditor.

`warn`-severity findings appear in the **Not blockers** subgroup in the review output.

### Step 4e: Executor-capability-boundary check (EBV001)

This check runs after Step 4d (step-count) and before composing the output. It calls the `capability_boundary.lint_plan()` module (at `lib/capability_boundary.py`).

#### 4e.1 - What is a capability-boundary violation?

The PLAN's `assigned_to` resolves to an executor agent file, and an operation is excluded when it is absent from that file's `skills:` list or denied by its `disallowedTools:`. The rule is derived from the dispatched agent's own declarations, not from a maintained list of skill names (D8, PLAN-AK1).

| Operation | executor-capability-boundary.md clause | Why it falls out of the derived rule |
|---|---|---|
| `retire` | (b) | Absent from every executor agent's `skills:` list |
| `write-input`, `plan-pipeline` | (d) | Absent from every executor agent's `skills:` list |
| `ideate` | (c), plus: no agent file exists for it at all | Absent from every executor agent's `skills:` list, and unreachable at a more basic level - there is nothing to dispatch to |
| raw `bash`/`sh` | (a) | A `disallowedTools:` fact, not a `skills:` fact |

This table is illustrative, not the rule - a skill absent from the resolved agent's preload list is a violation whether or not it appears in this table. A Step directing the executor to run `write-skill` or `audit-skills` end to end is caught for the same reason: neither name is in this table, a hard-coded name-list check would pass both, and the derived rule catches them because neither is in `plan-executor`'s preloaded `skills:` list. The worked case is the fixture `test_unlisted_skill_outside_the_four_names_is_flagged` in `lib/test_capability_boundary.py`, not a live PLAN. An example naming a live file's current content is a claim with an expiry date: this paragraph previously cited PLAN-AJ8's Steps 3-5, and AJ8's own plan-safety audit had moved those runs to the orchestrator seventeen minutes after the observation was written.

#### 4e.2 - Scope of scan

The `## Steps` section only. Fenced code blocks inside it are skipped, including fences indented under a numbered step (they carry literal content to be written, not instructions to the executor). The Verification section is excluded - `H401`-`H405` cover it, and its `verify:`/`acceptance:` commands run in the orchestrator's parent context, where these operations are legitimate (`executor-capability-boundary.md` clause (a)).

#### 4e.3 - Attribution discrimination

**Sentence-scoped subject attribution (D2).** Split each top-level Step's prose into sentences. For each sentence containing an excluded-operation match, scan that same sentence for a non-executor attribution marker: `orchestrator`, `parent session`, `parent-session`, `the parent`, `the human`, `the operator`, `[Human]`. If a marker is present, suppress the finding; otherwise carry on to the run-versus-record rules below.

Two recorded failure modes: a compound sentence naming both the executor and the orchestrator can false-negative (accepted - it degrades to the pre-mechanisation status quo, where the auditing model still reads the Step under `H302`); an unattributed Step body correctly fires, since the default reading of an unattributed Step is that the executor performs it.

#### 4e.3a - Run-versus-record discrimination

A Step may name a skill because the executor is to run it, or because the executor is to write the name down - as documentation prose for another skill's `SKILL.md`, as a slash-command's or child skill's specified body, as a test fixture or assertion string, or inside an Edit's `old_string`/`new_string`. Only the first is a crossing.

This is the dominant failure mode, measured rather than predicted. The sweep of 2026-08-05 over every PLAN in `Workbench/` and `Retired/` fired 59 times; of the 46 findings that were not self-acknowledged, 40 were wrong, and 38 of those 40 were this. Lead-line attribution, the failure mode D2 names and reasons about, accounted for the other 2.

Three rules, applied after the attribution scan:

- **A `Skill(...)` literal counts only when an invocation verb or preposition governs it** - `invoke`, `call`, `run`, `use`, `execute`, `dispatch`, `fire`, or `via`, `with`, `through`, `by`, within sixty characters before the mention. There is no allowance for a bare mention at the head of its sentence: `The Skill("write-plan") invocation pattern must work` is a sentence about a call. The two prose patterns have always required an invocation verb; the literal branch requiring none was an inconsistency rather than a decision.
- **A `Skill(...)` literal counts only when the name resolves to `.claude/skills/<name>/SKILL.md`** - the same existence filter the prose branches already apply. A name resolving to nothing is a fixture or a negative-test plant, not a crossing. The cost is that a Step naming a since-deleted skill goes unflagged; two genuine historical crossings in the corpus are invisible for this reason.
- **An authoring verb earlier in the containing step suppresses the finding**, and so does an Edit diff block in the same paragraph. `write`, `author`, `create`, `add`, `specify`, `document`, `implement` and their kin frame everything after them as content being produced. The frame is evaluated over the whole step, because a step routinely sets it in a heading and uses it four lines down; it is bounded by the step, because many PLANs pack their numbered steps with no blank line and an unbounded frame let step 1 suppress a crossing in step 3. The diff-block rule alone is paragraph-scoped, since a step may legitimately both edit a file and instruct an invocation.

The bias is deliberate and matches D2's: a false negative degrades to the auditing model reading the Step under `H302`, and a false positive blocks a correct PLAN. The known false-negative cost is a step that both authors a file and separately instructs an invocation.

Do not repair a future false positive by widening a marker list. That is the move the pre-fix heuristic already made and the sweep already failed.

#### 4e.3b - Measured accuracy

Re-swept after the rules above landed, over the same corpus with acknowledgements disabled: 4 findings, all four genuine crossings, no false positives. The two historical crossings named in the existence-filter bullet are not recoverable from this corpus.

The measurement's own weakness: the rules were tuned against the corpus they were then measured on, so the zero is a fit to that corpus rather than an estimate of accuracy on PLANs not yet written. The tests in `lib/test_capability_boundary.py` pin each rule to the named shape that motivated it, so a regression is caught by name; a novel shape is not, and `audit_acknowledgements: [EBV001]` remains the escape hatch (D3).

Re-derive the sweep with:

```
python -c "import sys, glob; sys.path.insert(0, '.claude/skills/audit-haiku-safe/lib'); from capability_boundary import lint_plan; [print(p, f) for p in sorted(glob.glob('Retired/PLAN-*.md')) + sorted(glob.glob('Workbench/PLAN-*.md')) for f in lint_plan(p, ack_codes=[])]"
```

#### 4e.4 - Finding format and severity classification

```
code: EBV001
level: error
category: capability-boundary
location: "Step <n>"
message: "capability-boundary-violation: Step <n> asks the executor to invoke '<name>', which is not in <agent_name>'s preloaded skills (<comma-separated skills:>). Skill() from a subagent fails as a silent no-op, so route this to the orchestrator (parent session)."
suggested_fix: "Re-author the Step to name the orchestrator as the actor (e.g. \"the orchestrator retires <target>\"), or move the operation out of executor scope entirely."
```

```
code: EBV002
level: warning
category: capability-boundary
location: "<agent_path>"
message: "capability-boundary-unresolved: could not read a skills: declaration from <agent_path> (assigned_to: '<value>'), so no executor-capability check ran for this PLAN."
suggested_fix: "Repair <agent_path> so it declares a skills: list (and disallowedTools: where relevant), or correct this PLAN's assigned_to value."
```

`EBV001` is `error`-severity and therefore a **Blocker**, unlike the warn-severity `PPV`/`FAL`/`PSZ` families - a capability-boundary crossing produces a silent no-op at execution time, with the executor reporting success over work that never happened. `EBV002` is `warn` and reports that the check could not run rather than that the PLAN is unsafe (D9). Either code in `audit_acknowledgements` suppresses that code alone.

The error severity is held on the measurement in 4e.3b, not on a judgement by the party the check binds. Before the run-versus-record rules landed the same severity was indefensible on the same evidence, and the correct response to a future sweep showing the same thing is to fix the heuristic or pull this step from the workflow, not to demote the code and leave a check nobody reads.

Per D7, the module reads `audit_acknowledgements` from the PLAN itself, so the acknowledgement takes effect through the invocation below without the auditing model extracting or passing anything - unlike Step 4d, where 4d.2 asks the model to read the field first.

Run from the repository root (the module resolves `.claude/agents` relative to the working directory):

```
python -c "import sys; sys.path.insert(0, '.claude/skills/audit-haiku-safe/lib'); from capability_boundary import lint_plan; [print(f) for f in lint_plan('<plan_path>')]"
```

with `<plan_path>` replaced by the PLAN under review.

### Step 5: Compose review output
Format per CLAUDE.md "Reviews" rule:
1. **Verification preamble** (1-2 sentences): what files were inspected (the PLAN, _shared/plan-safe.md, any referenced source files).
2. **Verdict** (one line): "Mechanically executable" / "N plan-safety blockers - revision needed" / "Pre-condition violation".
3. **Plan-safety section** with two subgroups:
   - `**Blockers**` (numbered, priority-ordered): prose + which plan-safe criterion violated + suggested fix shape (without authoring it).
   - `**Not blockers**`: brief list.
4. **Net verdict**: "ready to advance" / "revise the N blockers and re-audit".
5. **Machine-readable summary**: `Blockers: N` on its own line.

### Step 6: Decision-triage of Human-input items (if any)
If any finding asks the Human for input (rare for plan-safety, common for sufficiency), classify each per parent PLAN 202605011400 decision 15:
- **`already_locked`** - Human proposed/affirmed earlier; no question.
- **`mechanically_forced`** - only one alternative; no question.
- **`real_judgement_call`** - surface as a question.

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
  "diagnostics": {
    "findings": [
      {
        "code": "H302",
        "level": "error",
        "category": "concreteness",
        "location": "Step 4",
        "message": "<what is wrong>"
      }
    ]
  }
}
```
</pipeline-result>
```

**`diagnostics.findings` is mandatory and is emitted on every return, including
`outcome: success` (where it is an empty array).** One entry per finding, blockers
and not-blockers alike. Field shapes are defined in
[../../_shared/auditor-schema-v3.md](../../_shared/auditor-schema-v3.md).

This array is what the orchestrator fingerprints. `audit_loop.py` hashes
`code|level|category|location` to detect a finding recurring across iterations,
and `build_brief.py` renders the prior round's findings into the next round's
brief. Omitting the array silently disables recurrence detection and stops the
`[STUCK xN]` badge from firing.

Keep `location` stable across iterations for a finding that has not moved. The
fingerprint depends on it, and a finding relocated by an edit reads as new
rather than recurring.

The orchestrator parses this block to drive the audit-loop state machine (decision 21).

**`blockers_count` is a handoff value, never a stored source of truth.** It travels in the live `<pipeline-result>` for this dispatch and is persisted only as part of the audit record. Nothing reads it back off disk, and nothing should start: `diagnostics.findings` is the list, and any later reader wanting a blocker count derives it from that array. A count read back from a file is a claim about findings the reader has not looked at.
