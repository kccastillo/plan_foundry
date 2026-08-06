---
description: Capture conversation summary mid-ideate (phases 1-3) to Workbench/.ideate-checkpoint/<thread-id>.md
---

Write a checkpoint of the current ideate conversation to `Workbench/.ideate-checkpoint/`. Use during Phase 1-3 of the ideate cadence to create a durable forensic trace of the current state - useful for session resumption and cross-session continuity.

Invoke via Bash:

```bash
python .claude/commands/lib/write_checkpoint.py
```

Emit the script's confirmation output verbatim.

The script:
1. Detects whether an active ideate thread exists (scans `Workbench/*.md` for a PLAN with `pipeline_phase: drafting` AND `ideate_phase: ""`).
2. If an active thread is found, uses that PLAN's ID as the thread identifier.
3. If no active thread is found, generates a timestamp-based `<thread-id>` in `YYYYMMDDHHMI` format.
4. Writes `Workbench/.ideate-checkpoint/<thread-id>.md` with sections:
   - **Created:** timestamp
   - **Current phase:** best-guess based on conversation context (human fills in if wrong)
   - **Conversation summary:** placeholder - the invoker fills this in after the checkpoint is written
   - **Open questions:** placeholder list
   - **Decisions captured so far:** placeholder list
5. Prints the path of the written file as confirmation.

After the script runs, the user should edit the written checkpoint file to fill in the placeholders - the script writes the structure; the content is the user's responsibility.

**When to use:**
- Before a long pause in an ideate session (end of working session, context window approaching limit)
- After the human signals "checkpoint this" or "save where we are"
- Before switching to a different conversation context

**Commitment:** The checkpoint file is committed to the repository (not gitignored) and becomes a durable record of the ideation state.
