# Corpus Ownership Index

<!-- GENERATED FILE - do not hand-edit. -->
<!-- Source: .claude/skills/_shared/corpus-ownership.toml -->
<!-- Regenerate with: python3 scripts/ci/sync-corpus-ownership.py -->

Realises the Single Canonical Home invariant (see `ARCHITECTURE.md`, Invariants
Register). One row per file in the corpus scope declared in
`corpus-ownership.toml`'s `[scope]` section. `owns_provenance: provisional`
rows are executor-authored one-line paraphrases with no acceptance check;
see the invariant's `Verified by:` clause for what this index does and does
not verify.

| path | owns | owns_provenance | class | points_at | pointed_at_by | synced_from | sync_by |
|---|---|---|---|---|---|---|---|
| `.claude/agents/audit-ceiling-diagnostician.md` | (consumer) audit-ceiling diagnosis system prompt | provisional | dispatch-inline | - | - | .claude/skills/_shared/artefact-register-agent-block.md | scripts/ci/sync-artefact-register.py |
| `.claude/agents/plan-executor-opus.md` | (consumer) executor capability boundary exception prose | seeded | dispatch-inline | `.claude/skills/_shared/executor-capability-boundary.md` | - | .claude/skills/_shared/artefact-register-agent-block.md | scripts/ci/sync-artefact-register.py |
| `.claude/agents/plan-executor-sonnet.md` | (consumer) executor capability boundary exception prose | seeded | dispatch-inline | `.claude/skills/_shared/executor-capability-boundary.md` | - | .claude/skills/_shared/artefact-register-agent-block.md | scripts/ci/sync-artefact-register.py |
| `.claude/agents/plan-executor.md` | (consumer) executor capability boundary exception prose | seeded | dispatch-inline | `.claude/skills/_shared/executor-capability-boundary.md` | - | .claude/skills/_shared/artefact-register-agent-block.md | scripts/ci/sync-artefact-register.py |
| `.claude/agents/plan-retirer.md` | (consumer) retire skill system prompt for the plan-retirer background agent | provisional | dispatch-inline | - | - | - | - |
| `.claude/agents/plan-safety-auditor.md` | (consumer) audit-haiku-safe system prompt for the plan-safety-auditor subagent | provisional | dispatch-inline | - | - | .claude/skills/_shared/artefact-register-agent-block.md | scripts/ci/sync-artefact-register.py |
| `.claude/agents/plan-writer.md` | (consumer) Spec-Draft rigour heuristics H2/H4/H8, injected as system prompt | seeded | dispatch-inline | - | - | .claude/skills/_shared/artefact-register-agent-block.md | scripts/ci/sync-artefact-register.py |
| `.claude/agents/sufficiency-auditor.md` | (consumer) audit-sufficiency system prompt for the sufficiency-auditor subagent | provisional | dispatch-inline | - | - | .claude/skills/_shared/artefact-register-agent-block.md | scripts/ci/sync-artefact-register.py |
| `.claude/agents/survey-researcher.md` | (consumer) research sub-question system prompt for the survey-researcher subagent | provisional | dispatch-inline | - | - | - | - |
| `.claude/skills/_shared/artefact-register-agent-block.md` | (source) artefact writing rules condensed from writing-style.md, spliced into seven agent bodies | seeded | dispatch-inline | - | `.claude/agents/audit-ceiling-diagnostician.md`; `.claude/agents/plan-executor.md`; `.claude/agents/plan-executor-opus.md`; `.claude/agents/plan-executor-sonnet.md`; `.claude/agents/plan-safety-auditor.md`; `.claude/agents/plan-writer.md`; `.claude/agents/sufficiency-auditor.md` | - | scripts/ci/sync-artefact-register.py |
| `.claude/skills/_shared/audit-stages.md` | the three-stage audit distinction: sufficiency, haiku-safe (plan-safe criteria), and plan-safety | seeded | home-pointer-eligible | `.claude/skills/_shared/plan-safe.md` | - | - | - |
| `.claude/skills/_shared/auditor-schema-v3.md` | v3 audit payload JSON schema: level enum, patch/occurrence types, mechanically_forced/real_judgement_call finding disposition | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/_shared/capacity-thresholds.md` | 0.8x capacity-ceiling trigger mechanism referenced by Spec-Draft rigour heuristics | seeded | home-pointer-eligible | - | `.claude/skills/_shared/spec-rigour-heuristics.md` | - | - |
| `.claude/skills/_shared/config-loader.md` | the plan-foundry.config file contract and how a skill reads it | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/_shared/deprecation-policy.md` | deprecation ledger/shim/quarantine mechanism | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/_shared/dispatch-authorisation.md` | dispatch economy: cheapest-capable tier ladder, grant grammar (send it 1-4), carve-outs | seeded | human-edit-only | - | `.claude/skills/_shared/executor-capability-boundary.md`; `.claude/skills/_shared/fable-escalation-policy.md`; `.claude/skills/_shared/thin-orchestration.md` | - | - |
| `.claude/skills/_shared/executor-capability-boundary.md` | what a dispatched executor may touch, derived from the agent file's own skills:/disallowedTools: declarations | seeded | home-pointer-eligible | `.claude/skills/_shared/dispatch-authorisation.md` | `.claude/agents/plan-executor.md`; `.claude/agents/plan-executor-sonnet.md`; `.claude/agents/plan-executor-opus.md`; `.claude/skills/write-plan/references/assigned_to-field.md` | - | - |
| `.claude/skills/_shared/fable-escalation-policy.md` | Fable escalation routing rules, applying the difficulty-not-importance trigger | seeded | home-pointer-eligible | `.claude/skills/_shared/dispatch-authorisation.md` | - | - | - |
| `.claude/skills/_shared/harness-contract.md` | Claude Code harness surfaces, assumptions and workarounds | seeded | home-pointer-eligible | - | `.claude/skills/_shared/questioning-contract.md`; `.claude/skills/_shared/skill-standard.md` | - | - |
| `.claude/skills/_shared/plan-safe.md` | the plan-safe standard: five criteria a PLAN Step must meet, executor t-shirt sizing, PSZ001 | seeded | home-pointer-eligible | - | `.claude/skills/_shared/audit-stages.md`; `.claude/skills/write-plan/references/plan-conventions.md` | - | - |
| `.claude/skills/_shared/platform-portability.md` | CI-baseline portability rule for verify:/acceptance: commands: forbidden shell patterns, # platform: opt-out | seeded | home-pointer-eligible | - | `.claude/skills/write-plan/references/plan-conventions.md` | - | - |
| `.claude/skills/_shared/proportionality-gate.md` | ideate's four-rung proportionality gate: just-do-it / plan-it / audit-it / full-arc | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/_shared/questioning-contract.md` | AskUserQuestion usage rules and the decision-briefing format | seeded | home-pointer-eligible | `.claude/skills/_shared/harness-contract.md` | - | - | - |
| `.claude/skills/_shared/research-prompt-template.md` | mandatory research sub-questions and the survey-researcher dispatch template | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/_shared/skill-standard.md` | the skill standard: required SKILL.md contents, description-health test, retirement-evidence-is-external rule | seeded | home-pointer-eligible | `.claude/skills/_shared/harness-contract.md` | - | - | - |
| `.claude/skills/_shared/spec-rigour-heuristics.md` | Spec-Draft rigour heuristics H2/H4/H8: 0.8x threshold, calling-convention checklist, literal-heading rule | seeded | home-pointer-eligible | `.claude/skills/_shared/capacity-thresholds.md` | - | - | - |
| `.claude/skills/_shared/thin-orchestration.md` | thin-orchestration discipline for fan-out dispatch: orchestrator-owns-git, writable-set, commit-at-milestones | seeded | home-pointer-eligible | `.claude/skills/_shared/dispatch-authorisation.md` | - | - | - |
| `.claude/skills/_shared/writing-style.md` | artefact writing rules: word/verb/sentence/structure discipline for anything written to a file | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/audit-haiku-safe/SKILL.md` | audit-haiku-safe skill entry point: mechanical plan-safety checks, capability-boundary sub-clause citations | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/audit-haiku-safe/references/auditor-codes.md` | audit-haiku-safe finding-code registry: EBV/PPV/SFV codes, D8 capability-boundary derivation rule, forbidden-pattern table | seeded | home-pointer-eligible | - | `.claude/skills/audit-sufficiency/references/auditor-codes.md` | - | - |
| `.claude/skills/audit-haiku-safe/workflows/audit-haiku-safe-steps.md` | audit-haiku-safe step-by-step procedure: capability-boundary checks, Step 4b platform-portability pattern table | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/audit-skills/SKILL.md` | audit-skills skill entry point: skill-corpus audit triggers and workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/audit-skills/references/ownership.md` | bundle-managed versus consumer-owned skill ownership determination for audit-skills | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/audit-sufficiency/SKILL.md` | audit-sufficiency skill entry point; declares the decision-tier triage vocabulary (already_locked/mechanically_forced/real_judgement_call) | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/audit-sufficiency/references/auditor-codes.md` | audit-sufficiency finding-code registry, pointing to audit-haiku-safe's registry for PPV codes | seeded | home-pointer-eligible | `.claude/skills/audit-haiku-safe/references/auditor-codes.md` | - | - | - |
| `.claude/skills/audit-sufficiency/references/sufficiency-audit-exemplar.md` | worked example of a sufficiency-audit pass | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/audit-sufficiency/workflows/audit-sufficiency-steps.md` | audit-sufficiency step-by-step procedure; Step 4 owns the decision-tier triage taxonomy definitions | seeded | home-pointer-eligible | - | `.claude/skills/plan-pipeline/references/phase-state-machine.md` | - | - |
| `.claude/skills/autonomous-loop/SKILL.md` | autonomous-loop skill entry point: unattended drafted-to-complete drive triggers and run-loop workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/autonomous-loop/workflows/run-loop.md` | autonomous-loop drive procedure from drafted to complete | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/execute-plan/SKILL.md` | execute-plan skill entry point: execution workflow trigger, orchestrator-owned frontmatter field list | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/execute-plan/references/heartbeat-spec.md` | heartbeat file schema, tick cadence and lifecycle for executor progress signalling | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/execute-plan/workflows/execute-steps.md` | PLAN execution step-by-step procedure, including the plan-of-plans sync | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/handoff-next-session/SKILL.md` | handoff-next-session skill entry point: session-handoff triggers and write-handoff workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/handoff-next-session/references/claim-carry-gate.md` | which claims a handoff may carry forward versus must re-derive | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/handoff-next-session/references/handoff-naming.md` | handoff filename grammar and scoping rules | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/handoff-next-session/references/readiness-gate.md` | handoff readiness check: reads pipeline_phase, audit_state and status before offering a handoff | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/handoff-next-session/templates/handoff-template.md` | the HANDOFF file content contract template | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/handoff-next-session/workflows/write-handoff.md` | session-handoff authoring procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/ideate/SKILL.md` | ideate skill entry point: eight-phase cadence triggers, decision-tier taxonomy restatement | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/ideate/references/critique-codes.md` | self-critique finding-code registry for the ideate cadence | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/ideate/references/critique-schema.md` | structured schema for ideate self-critique findings | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/ideate/references/phase-transitions.md` | ideate cadence phase-transition rules | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/ideate/workflows/cadence-phases.md` | ideate cadence phase detail, including the F7 decision-tier triage column and research-sub-question dispatch | seeded | home-pointer-eligible | - | `.claude/skills/write-plan/references/plan-conventions.md` | - | - |
| `.claude/skills/ideate/workflows/ideate-arc.md` | ideate's eight-phase cadence procedure | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/ideate/workflows/risk-assess-idea.md` | ideate's idea-stage risk-assessment gate procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/ideate/workflows/risk-assess-spec.md` | ideate's spec-stage risk-assessment gate procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/init-plan-foundry/SKILL.md` | init-plan-foundry skill entry point: bootstrap-install triggers and init-steps workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/init-plan-foundry/operating-rules.md` | (consumer) canonical operating-rules text spliced into a consumer's CLAUDE.md: install procedure, pipeline_phase enum, verify-premise, send it grammar | seeded | consumer-standalone | - | - | - | - |
| `.claude/skills/init-plan-foundry/templates/claude-md-stub.md` | CLAUDE.md stub content for a freshly-bootstrapped consumer project | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/init-plan-foundry/workflows/init-steps.md` | bundle bootstrap-install procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/maintain-project-docs/SKILL.md` | maintain-project-docs skill entry point: durable-doc audit/add/prune triggers and workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/maintain-project-docs/references/anti-patterns.md` | documentation anti-patterns maintain-project-docs checks for | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/maintain-project-docs/references/audit-checklist.md` | checklist maintain-project-docs runs against the durable-doc set | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/maintain-project-docs/templates/add-plan-template.md` | PLAN template for a documentation-addition task | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/maintain-project-docs/templates/audit-plan-template.md` | PLAN template for a documentation-audit task | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/maintain-project-docs/templates/prune-plan-template.md` | PLAN template for a documentation-pruning task | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/maintain-project-docs/workflows/produce-plan.md` | maintain-project-docs PLAN/findings-file production procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/plan-foundry-check-current/SKILL.md` | plan-foundry-check-current skill entry point: currency-check triggers and workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/plan-foundry-check-current/workflows/check.md` | bundle currency-check procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/plan-foundry-sync/SKILL.md` | plan-foundry-sync skill entry point: bundle-sync triggers and workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/plan-foundry-sync/workflows/sync.md` | bundle-sync procedure: copy bundle-managed content, refresh version pin | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/plan-foundry-uninstall/SKILL.md` | plan-foundry-uninstall skill entry point: bundle-removal triggers and workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/plan-foundry-uninstall/workflows/uninstall.md` | bundle-removal procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/plan-pipeline/SKILL.md` | plan-pipeline skill entry point: phase orchestration triggers, orchestrator-owned field names, capability-boundary citation | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/plan-pipeline/references/phase-state-machine.md` | pipeline_phase enum, orchestrator frontmatter mutation cheat sheet, Decision-15 output-format template | seeded | home-pointer-eligible | `.claude/skills/audit-sufficiency/workflows/audit-sufficiency-steps.md` | `.claude/skills/write-plan/references/plan-conventions.md` | - | - |
| `.claude/skills/plan-pipeline/workflows/dispatch.md` | plan-pipeline dispatch procedure: orchestrator-owned field mutation, capability-boundary application sites | seeded | home-pointer-eligible | - | - | - | - |
| `.claude/skills/raise-foundry-request/SKILL.md` | raise-foundry-request skill entry point: FOUNDRYREQ filing triggers and workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/raise-foundry-request/workflows/write-foundry-request.md` | FOUNDRYREQ filing procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/rehydrate-handoff/SKILL.md` | rehydrate-handoff skill entry point: session-start handoff-discovery triggers and read-handoff workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/rehydrate-handoff/workflows/read-handoff.md` | session-start handoff discovery and presentation procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/retire/SKILL.md` | retire skill entry point: artefact-retirement triggers and retire-file workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/retire/workflows/retire-file.md` | artefact-retirement move-and-verify procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/test-foundry/SKILL.md` | test-foundry skill entry point: test-harness triggers and run-tests workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/test-foundry/workflows/run-tests.md` | test-foundry harness run procedure: Python tier plus LLM scenarios | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/write-input/SKILL.md` | write-input skill entry point: INPUT file transcription triggers and workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/write-input/templates/input-template.md` | the INPUT file template | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/write-input/workflows/write-input.md` | INPUT file transcription procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/write-plan/SKILL.md` | write-plan skill entry point: PLAN transcription triggers and workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/write-plan/references/assigned_to-field.md` | the assigned_to frontmatter field: valid executor values and capability-boundary pointer | seeded | home-pointer-eligible | `.claude/skills/_shared/executor-capability-boundary.md` | - | - | - |
| `.claude/skills/write-plan/references/naming-convention.md` | PLAN and INPUT filename convention detail | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/write-plan/references/plan-conventions.md` | PLAN/INPUT file conventions: naming, identity, status enum, frontmatter schema, holding-PLAN pattern | seeded | home-pointer-eligible | `.claude/skills/plan-pipeline/references/phase-state-machine.md`; `.claude/skills/_shared/platform-portability.md`; `.claude/skills/_shared/plan-safe.md`; `.claude/skills/ideate/workflows/cadence-phases.md`; `.claude/skills/write-plan/references/plan-of-plans-authoring.md` | - | - | - |
| `.claude/skills/write-plan/references/plan-of-plans-authoring.md` | authoring discipline for a plan-of-plans: sketch-first placeholder convention, parent-update rules | seeded | home-pointer-eligible | - | `.claude/skills/write-plan/references/plan-conventions.md` | - | - |
| `.claude/skills/write-plan/templates/plan-template.md` | the PLAN file template copied verbatim into every new PLAN, including decision-tier taxonomy boilerplate | seeded | dispatch-inline | - | - | - | - |
| `.claude/skills/write-plan/workflows/write-plan.md` | PLAN file transcription procedure | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/write-skill/SKILL.md` | write-skill skill entry point: skill scaffolding triggers and trigger-proving workflow pointer | provisional | home-pointer-eligible | - | - | - | - |
| `.claude/skills/write-skill/workflows/prove-triggering.md` | skill trigger-proving procedure against must-fire/must-not-fire prompts | provisional | home-pointer-eligible | - | - | - | - |
