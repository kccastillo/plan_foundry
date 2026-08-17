---
description: Set the agentic authorisation ceiling for this session (1-4). No argument means 2. Equivalent to typing the `send it` token; the words work everywhere, this command is the discoverable form.
---

The human has set the agentic authorisation ceiling. Read `$ARGUMENTS` as the
requested rung.

- Empty, or `2` -> ceiling rung 2, decision autonomy granted.
- `1` -> ceiling rung 1, decision autonomy revoked. Same as `stand down`.
- `3` -> ceiling rung 3, decision autonomy granted.
- `4` -> ceiling rung 4, decision autonomy granted.
- Anything else -> do not guess. Say what was typed, state that the scale is 1
  to 4, and ask which was meant. Leave the current grant untouched until they
  answer.

Read `.claude/skills/_shared/dispatch-authorisation.md` for what each rung
permits and what the grant never covers. That file is the contract, and this
command only sets the level.

**The number is a ceiling, not a setpoint.** Keep picking the cheapest rung
that fits each piece of work, under the obligations that already apply - a
reason written before any rung 3 dispatch, a failed attempt below before rung
4. Never raise the ceiling yourself. Ask for a higher ceiling if the work
needs one.

**A ceiling is permission, not a budget to spend.** Re-read "Cheapest capable,
rightsized" in the contract before the next dispatch. A raised ceiling makes
these easy to forget. A parallel swarm of cheap Haiku agents is authorised and
encouraged for mechanical fan-out. Effort is a dial separate from tier. The
shape of the work - adversarial verification, an independent panel, running
until a sweep returns nothing new, searching one question several unrelated
ways, a final pass on what is still unchecked - is chosen per stage rather than
defaulted to one agent doing everything.

**Confirm the change in one line**, per "Announcing a change of grant" in the
contract: the level now in force and what it permits. If the new ceiling
lowers or revokes an existing grant, also name anything that was in flight, so
the human can see what stopped.

Then continue the work in front of you at the new ceiling. Do not re-plan, do
not summarise the session, and do not ask what to do next if the current task
is unfinished.
