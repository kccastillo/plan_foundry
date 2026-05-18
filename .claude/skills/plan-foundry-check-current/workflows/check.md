# Check procedure

Two-tier currency report.

## Tier 1: bundle vs upstream

1. **Resolve bundle path.** Read `--bundle-path <p>` if passed; else `$PLAN_FOUNDRY_BUNDLE_PATH`; else default `~/.claude/plan_foundry/`.
2. **Check the path exists** and contains a `.git/` directory. If not, return `status: no_bundle` with a message pointing at the clone instructions.
3. **Inspect `origin` remote.** Run `git -C <bundle> remote get-url origin`. If the URL does not match `kccastillo/plan_foundry` (HTTPS or SSH form), return `status: wrong_remote` — the human is running the check against the wrong repo (e.g. `plan_foundry_dev`). Exit code 0; this is diagnostic, not failure.
4. **Fetch.** `git -C <bundle> fetch origin main` (silent unless error). Falls back to whatever `origin/main` is locally if offline.
5. **Compare HEADs.**
   - `local = git -C <bundle> rev-parse HEAD`
   - `remote = git -C <bundle> rev-parse origin/main`
   - `behind = git -C <bundle> rev-list --count HEAD..origin/main`
   - `ahead = git -C <bundle> rev-list --count origin/main..HEAD`
6. **Classify.**
   - `behind=0 && ahead=0` → `current`
   - `behind>0 && ahead=0` → `behind` — message: `cd <bundle> && git pull`
   - `behind=0 && ahead>0` → `ahead` (rare; only if maintainer is in the bundle dir mid-development)
   - `behind>0 && ahead>0` → `diverged` (very rare; recommend re-clone)

## Tier 2: project vs bundle

Skipped if `--no-target-check` is passed.

1. **Resolve project root.** Read `--target-root <p>` if passed; else use `cwd`.
2. **Check `<target>/.claude/` state.**
   - Absent → `status: not_initialised`. Message: "run /init-plan-foundry first."
   - Symlink → `status: legacy_symlink`. Message: "run /init-plan-foundry to migrate off the symlink layout."
   - Real directory → continue.
3. **Read `.claude/.plan-foundry-bundle-version`.**
   - Absent → `status: not_initialised`. Message: "version pin missing — run /init-plan-foundry first."
   - Empty sha → `status: unknown`. Message: "version pin has empty sha — re-run /plan-foundry-sync."
   - Otherwise → record `project_sha`.
4. **Compare to bundle HEAD.**
   - Equal → `status: current`. Message: "project is in sync with the local bundle."
   - Different, and `git rev-list --count <project_sha>..HEAD` returns a positive integer → `status: behind`. Message: "project is behind the local bundle by N commit(s) — run /plan-foundry-sync."
   - Different, but rev-list cannot compute distance (project_sha not in bundle's history, or rev-list fails) → `status: drift`. Message: "project pin differs from local bundle — run /plan-foundry-sync."

## Output

Emit JSON to stdout with both tiers under `bundle` and `project` keys. Backwards-compat top-level fields mirror the bundle tier so pre-AC5 consumers keep working. Exit 0 in all states.
