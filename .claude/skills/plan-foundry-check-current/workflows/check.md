# Check procedure (AC6)

Single-tier currency report: project pin vs remote HEAD.

## Step 1: Resolve project root

Read `--target-root <p>` if passed; else use `cwd`.

## Step 2: Read project state

First, read `<target>/.claude/skills/_shared/bundle-contract.json`'s top-level `bundle` key inline, importing nothing from `_shared/`. If it names a bundle other than `plan_foundry`, record it as `shared_dir_owner` and append a note to whatever `message` the steps below produce: two bundles from this lineage are installed here and are overwriting each other's shared helpers, and `/plan-foundry-sync` reclaims the directory. This does not change `status` - the pin this check reads is plan_foundry's own file and stays readable, so the currency answer is still worth giving. What it cannot promise is that the helpers under `_shared/` are the ones that pin describes. An absent, malformed, or key-less contract is the pre-identity state and is trusted. See ARCHITECTURE.md, Invariant: Bundle Namespace Ownership.

Check `<target>/.claude/`:
- Absent -> `status: not_initialised`. Message: "run /init-plan-foundry first."
- Symlink -> `status: legacy_symlink`. Message: "run /init-plan-foundry to migrate off the symlink layout."
- Real directory -> continue.

Read `<target>/.claude/.plan-foundry-bundle-version`:
- Absent -> `status: not_initialised`. Message: "version pin missing - run /init-plan-foundry first."
- Empty sha -> `status: unknown`. Message: "version pin has empty sha - run /plan-foundry-sync."
- Otherwise -> record `project_sha`.

## Step 2a: Check for an incomplete-sync marker (PLAN-AK6 D6)

Immediately after Step 2's pin read, before Step 3's network call. Read `<target>/.claude/.plan-foundry-sync-incomplete` inline, matching Step 2's own practice of reading the pin inline. Absent or unreadable -> continue to Step 3 unaffected.

Present -> `status: sync_incomplete`. `sync_incomplete` carries the parsed marker (`previous_sha`, `target_sha`, `started`). Message names the sha the interrupted run was moving to, states that the target holds a partly applied bundle, and instructs the operator to run `/plan-foundry-sync` again. Return immediately - `remote_sha` and `version_compare` stay at their unavailable defaults, and the network is never queried. This is deliberate: a target part-way through a failed sync must not be told `current` or merely `behind_or_diverged`, whatever its pin says, and the answer must survive an offline consumer.

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

Emit JSON to stdout with `status`, `project_sha`, `remote_sha`, `ref`, `message`, `version_compare`, `shared_dir_owner`, `sync_incomplete`. Exit 0 in all states.

`sync_incomplete` (PLAN-AK6) is `null` except when `status == "sync_incomplete"`, in which case it carries the marker dict Step 2a read.
