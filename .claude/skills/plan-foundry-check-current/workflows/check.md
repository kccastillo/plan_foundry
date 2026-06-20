# Check procedure (AC6)

Single-tier currency report: project pin vs remote HEAD.

## Step 1: Resolve project root

Read `--target-root <p>` if passed; else use `cwd`.

## Step 2: Read project state

Check `<target>/.claude/`:
- Absent → `status: not_initialised`. Message: "run /init-plan-foundry first."
- Symlink → `status: legacy_symlink`. Message: "run /init-plan-foundry to migrate off the symlink layout."
- Real directory → continue.

Read `<target>/.claude/.plan-foundry-bundle-version`:
- Absent → `status: not_initialised`. Message: "version pin missing — run /init-plan-foundry first."
- Empty sha → `status: unknown`. Message: "version pin has empty sha — run /plan-foundry-sync."
- Otherwise → record `project_sha`.

## Step 3: Query remote HEAD

Run `git ls-remote https://github.com/kccastillo/plan_foundry HEAD`. Parse the first whitespace-separated field of the first line as `remote_sha`.

- **Network/auth failure** → `status: remote_unreachable`. Message: "could not query remote: <err>. You are pinned at <project_sha[:8]>; run /plan-foundry-sync when network is available."

## Step 4: Compare

- `project_sha == remote_sha` → `status: current`. Message: "project is up to date (pinned at <project_sha[:8]>)."
- Different → `status: behind_or_diverged`. Message: "project pin <project_sha[:8]> differs from remote HEAD <remote_sha[:8]> — run /plan-foundry-sync to update."

## Output

Emit JSON to stdout with `status`, `project_sha`, `remote_sha`, `ref`, `message`. Exit 0 in all states.
