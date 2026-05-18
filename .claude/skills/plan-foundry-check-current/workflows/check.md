# Check procedure

1. **Resolve bundle path.** Read `--bundle-path <p>` if passed; else `$PLAN_FOUNDRY_BUNDLE_PATH`; else default `~/.claude/plan_foundry/`.
2. **Check the path exists** and contains a `.git/` directory. If not, return `status: no_bundle` with a message pointing at the clone instructions.
3. **Inspect `origin` remote.** Run `git -C <bundle> remote get-url origin`. If the URL does not match `kccastillo/plan_foundry` (HTTPS or SSH form), return `status: wrong_remote` — the human is running the check against the wrong repo (e.g. `plan_foundry_dev`). Exit code 0; this is diagnostic, not failure.
4. **Fetch.** `git -C <bundle> fetch origin main` (silent unless error).
5. **Compare HEADs.**
   - `local = git -C <bundle> rev-parse HEAD`
   - `remote = git -C <bundle> rev-parse origin/main`
   - `behind = git -C <bundle> rev-list --count HEAD..origin/main`
   - `ahead = git -C <bundle> rev-list --count origin/main..HEAD`
6. **Classify.**
   - `behind=0 && ahead=0` → `current`
   - `behind>0 && ahead=0` → `behind`
   - `behind=0 && ahead>0` → `ahead` (rare; only if maintainer is in the bundle dir mid-development)
   - `behind>0 && ahead>0` → `diverged` (very rare; recommend re-clone)
7. **Emit JSON** to stdout and a one-line human message:
   - current: "plan_foundry is up to date."
   - behind: "plan_foundry is behind by N commit(s) — run: cd <bundle> && git pull"
   - ahead: "plan_foundry has N local commit(s) not on origin/main."
   - diverged: "plan_foundry has diverged from origin/main — consider re-cloning."
   - wrong_remote: "Bundle at <bundle> has remote <url>; expected kccastillo/plan_foundry."
   - no_bundle: "plan_foundry bundle not found at <bundle> — clone https://github.com/kccastillo/plan_foundry into ~/.claude/plan_foundry first."
8. **Exit 0** in all states (diagnostic mode; consumers parse the JSON).
