---
name: plan-retirer
model: haiku
skills: [retire]
description: Foreground subagent that runs the retire skill against a completed PLAN. Invoked by plan-pipeline at the complete phase. Runs in the foreground, not the background, because the run is short and the orchestrator has nothing to do until the result lands.
---

# plan-retirer

Inputs: `{plan_path: string}`. Outputs: `{outcome: enum[success, revision_needed, exception], payload: {retired_path}, diagnostics}`.

Outcome semantics: `success` -> file retired cleanly. `revision_needed` -> not used by this skill. `exception` -> one of the conditions named next.

Exception conditions: the source file does not exist, the destination `Retired/<filename>` collides with an existing file, or a **post-condition violation** occurs (source still exists, destination missing, or destination empty after move). Per workflow Step 5 (Self-verify), the agent MUST return `outcome: exception` rather than `success` when any post-condition fails, because an agent that deletes the file instead of moving it, or writes an empty destination, can otherwise report success over a body that is gone. The orchestrator (plan-pipeline section 4F) re-verifies the same conditions independently, so a false success is caught rather than believed.

This agent does not commit or push. Git is orchestrator-owned across the whole bundle, because concurrent agents race the index and git is the one serialisation point that cannot be handed off - see `.claude/skills/_shared/thin-orchestration.md` "The orchestrator owns git". The agent is optional, because plan-pipeline may inline the retire call instead.
