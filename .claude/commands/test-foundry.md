---
description: Run the plan-foundry test harness (Python tier + LLM scenarios) and emit a portable TESTREPORT.
---

Read `.claude/skills/test-foundry/SKILL.md`, follow the workflow it describes, and
report the result. Read the file directly rather than dispatching the Skill tool: the
skill carries `disable-model-invocation: true`, and whether that flag blocks a
Skill-tool call made from a command body is unsettled.

Runs the two-tier test-foundry harness:
- **Python tier** - deterministic / structural tests (INDEX correctness, schema-v2 frontmatter validation, audit-foundry baseline).
- **LLM tier** - scenario walks (lifecycle, audit revision-needed loop, init-plan-foundry idempotency, retire path mechanics).

Emits `Workbench/testreports/TESTREPORT-NNN_<slug>.md` plus the sidecar `Workbench/.testreport-current` (one line: bare ID).

Optional argument: `mode=full` (default) or `mode=llm-tier-only` (reads a pre-run Python-tier result from `Workbench/.python-tier-result.json`).

After invocation, report:
- TESTREPORT path written
- Pass / fail counts per tier
- Any blocking diagnostics
