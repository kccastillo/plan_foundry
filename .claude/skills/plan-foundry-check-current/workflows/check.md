# Check procedure (AC6)

Single-tier currency report: project pin vs remote HEAD.

## Step 1: Resolve project root

Read `--target-root <p>` if passed; else use `cwd`.

## Step 2: Read project state

Check `<target>/.claude/`:
- Absent -> `status: not_initialised`. Message: "run /init-plan-foundry first."
- Symlink -> `status: legacy_symlink`. Message: "run /init-plan-foundry to migrate off the symlink layout."
- Real directory -> continue.

Read `<target>/.claude/.plan-foundry-bundle-version`:
- Absent -> `status: not_initialised`. Message: "version pin missing - run /init-plan-foundry first."
- Empty sha -> `status: unknown`. Message: "version pin has empty sha - run /plan-foundry-sync."
- Otherwise -> record `project_sha`.

## Step 3: Query remote HEAD

Run `git ls-remote https://github.com/kccastillo/plan_foundry HEAD`. Parse the first whitespace-separated field of the first line as `remote_sha`.

- **Network/auth failure** -> `status: remote_unreachable`. Message: "could not query remote: <err>. You are pinned at <project_sha[:8]>; run /plan-foundry-sync when network is available."

## Step 4: Compare

- `project_sha == remote_sha` -> `status: current`. Message: "project is up to date (pinned at <project_sha[:8]>)."
- Different -> `status: behind_or_diverged`. Message: "project pin <project_sha[:8]> differs from remote HEAD <remote_sha[:8]> - run /plan-foundry-sync to update."

## Step 5: The pre-sync break signal (PLAN-AH8, guarantee 1)

A separate field, `version_compare`, answers "would syncing now cross a breaking version boundary" - distinct from `status` above, which stays sha-based and untouched.

Immediately before the `behind_or_diverged` return in Step 4 (so the `current` early return is unaffected):

- Run `git ls-remote --tags <url>`. Parse each `refs/tags/<tag>` line (stripping a trailing `^{}` dereference marker) into a tag list.
- Select the highest tag via `bundle_semver.highest(tags)` - integer-tuple comparison, never lexical.
- Compare the pin's `tag` field against the highest remote tag:
  - Pin tag empty, or no remote tag parses -> `version_compare: unavailable`.
  - Highest remote tag's major is greater -> `behind_major`.
  - Same major, minor greater -> `behind_minor`.
  - Same major and minor, patch greater -> `behind_patch`.
  - Otherwise -> `current`.
- `version_compare` must never report `current` from an underivable state - empty, absent, or unparseable inputs always fall to `unavailable`, never to a comparable value.

## Output

Emit JSON to stdout with `status`, `project_sha`, `remote_sha`, `ref`, `message`, `version_compare`. Exit 0 in all states.
