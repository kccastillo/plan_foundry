# Changelog

Versioned migration and cleanup notes for plan_foundry releases.

## What changed, and what to clean up after updating

Read this before your first sync onto a new version. It lists only changes that
leave something behind in your project, or that change a habit. Everything else
is in the commit history.

### v1.14.0 (2026-07-31)

**Two skills, one agent and one hook were removed.** They are gone from the
bundle and nothing calls them any more:

| Removed | What it did | What it leaves in your project |
|---|---|---|
| `foundry-log` skill | Managed a unified operation log | `.claude/_foundry_log.jsonl`, and any `foundry-log-export-*.jsonl` in your project root |
| `.claude/hooks/foundry-log.py` | Wrote that log automatically | Nothing, once the file itself is gone |
| `foundry-log-summariser` agent | Summarised the log | Nothing |
| `lessons-learned` skill | Appended lessons to the monthly LOG | Whatever it wrote into your `Workbench/` LOG files |

Nine further scripts, references and templates went with them - migration and
one-shot tooling that had served its purpose. The full list is in the v1.14.0
tag's diff.

**Your first sync will not remove them for you, and this is the one thing worth
knowing.** Quarantine works from an install receipt at
`.claude/.bundle-receipts/plan_foundry.files` (a legacy `.claude/.plan-foundry-bundle-files`
is read and adopted where it can be proven to be this bundle's own), which records
what the bundle put in your tree. Receipts are new. If your project was installed or
last synced before receipts existed, the sync that brings you to v1.14.0 *writes* your
first receipt and quarantines nothing - it has no record of what it previously
installed, and it will not guess. Removed files stay where they are.

From your **second** sync onwards this is automatic: a file in the receipt that
upstream no longer ships is moved to
`.claude/.plan-foundry-quarantine/<UTC-timestamp>/`, left there for 30 days in
case you need it back, then swept.

**To clean up now rather than waiting**, delete these if present. All are safe -
nothing in the current bundle reads any of them:

```
.claude/skills/foundry-log/
.claude/skills/lessons-learned/
.claude/agents/foundry-log-summariser.md
.claude/hooks/foundry-log.py
.claude/skills/execute-plan/references/log-rules.md
.claude/skills/write-plan/templates/log-template.md
.claude/skills/write-plan/scripts/migrate_plan_ids.py
.claude/skills/write-plan/scripts/test_migrate_plan_ids.py
.claude/skills/update-workbench-index/scripts/project_context_inputs.py
.claude/skills/update-workbench-index/scripts/regenerate_state.py
.claude/skills/update-workbench-index/lib/test_project_context_inputs.py
```

`.claude/_foundry_log.jsonl` and any LOG files in `Workbench/` are **your data,
not bundle code**. Nothing reads them now. Keep or delete them as you see fit -
the uninstall path deliberately leaves operator data alone.

**If you had a `SessionStart` hook pointed at `foundry-log.py`**, remove that
entry from your `.claude/settings.json`. Sync will not touch your settings
hooks, and a hook pointing at a deleted script fails on every session start.

**Update:** `plan-foundry-sync` now performs the `foundry-log` half of this
cleanup for you - it quarantines the three paths above (recoverable from
`.claude/.plan-foundry-quarantine/`, same as everything else it removes) and
strips the matching hook entry out of `.claude/settings.json`, on every sync,
whether or not the files are still on disk. The manual steps above are only
needed if you want the cleanup before your next sync.

**Monthly LOG files are no longer part of the model.** `Workbench/` is the
authority for what exists - a directory listing plus PLAN frontmatter reads.
Install no longer seeds a LOG, and no skill writes one. Existing LOG files in
your `Workbench/` are inert - retire them when convenient.

**Pipeline commits now stage named paths.** The orchestrator previously ran
`git add -A` on every commit, which staged your whole working tree and could
publish work the phase did not author. It now stages an explicit list per
commit template. The visible consequence: a file the orchestrator cannot
attribute to the phase is left unstaged, so you may see a dirty tree after a
pipeline run where previously everything was swept in. That is the fix working -
the dirt is visible instead of silently committed.
