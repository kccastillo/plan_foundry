---
title: Platform Portability
description: CI-baseline portability rule for `verify:`/`acceptance:` commands - forbidden shell patterns and the `# platform:` opt-out.
created: 2026-08-17
---

# Platform portability (per PLAN-AB3, H3 hiccup-log 2026-05-16)

Every `verify:` and `acceptance:` command MUST run on the foundry's CI baseline without modification. A command that silently fails or requires rewriting on CI is a plan-safety violation.

**CI baseline (the default platform):** Ubuntu Linux + Python 3.11 + pytest + pyyaml + git + POSIX shell with bash-isms allowed. Commands that rely on this baseline require no annotation. Every element of that list is supplied by the foundry repo's `.github/workflows/checks.yml`, which runs on `ubuntu-latest`, installs Python 3.11 with `actions/setup-python`, installs `pytest` and `PyYAML`, sets a git identity, and then shells out to `scripts/ci/run-all.sh`.

**`gh` is not in the baseline.** The GitHub-hosted Ubuntu runner ships the `gh` binary, but `checks.yml` declares `permissions: contents: read`, exports no token, and never authenticates the CLI, and GitHub's documentation requires a `GH_TOKEN` environment variable on every workflow step that uses `gh`. A `verify:` or `acceptance:` command calling `gh` would fail on the first authenticated call, so it needs the same treatment as any other off-baseline dependency. `gh` remains available in a maintainer's local session, and the one helper that uses it, `_shared/resume_preflight.py`, calls `gh pr list` fail-open and treats an absent or erroring CLI as an unavailable axis rather than a failure.

**Opt-out annotation:** when portability is genuinely impossible, add a trailing comment on the same line:
- `# platform: posix` - the author declares the command POSIX-specific. Audit skips the portability check for that item.
- `# platform: windows` - the author declares the command Windows-specific. Audit skips the portability check for that item.

The annotation is read only by the portability lint. Nothing gates execution on it: the orchestrator's `outcome-verifying` phase re-runs an annotated `verify:`/`acceptance:` line the same way it runs any other, so the annotation records the author's declared scope rather than confining the command to a platform.

**Forbidden patterns (when no `# platform:` annotation is present):** an unannotated command is scanned against every pattern below, and each pattern it matches produces its own `level: warning` finding from `audit-haiku-safe`. The codes are the ones the lint module emits:

| Code | Pattern | Rationale |
|------|---------|-----------|
| `PPV001` | `/tmp/` | Linux-only temp path. Use the `tempfile` Python module for a portable alternative |
| `PPV002` | `/dev/null` | POSIX-only null device. Use `subprocess.DEVNULL` or redirect suppression in Python |
| `PPV003` | `bash -c` | Explicitly invokes bash, which is unavailable or differently-pathed on Windows |
| `PPV004` | `test -[a-zA-Z]` | POSIX `test` builtin. Use Python `os.path.exists()` or `pathlib` patterns instead |
| `PPV005` | `> /dev/` | Redirect to a `/dev/` pseudo-device, which is POSIX-only |
| `PPV006` | `2>/dev/null` | POSIX stderr suppression. Use Python subprocess or annotate the line |
| `PPV007` | `&&` in compound commands | Works in bash but breaks PowerShell 5.1. Split into separate commands or annotate the line |

The `/dev/` patterns overlap: a line containing `2>/dev/null` matches `PPV002`, `PPV005` and `PPV006`, so that one line carries three findings.

**Origin:** H3 from `Retired/202605160300_RESEARCH_hiccup-log.md` - Reeve's Plan B used `> /tmp/dump.json && test -s /tmp/dump.json`, which is POSIX-only on a Windows project, and the plan-safety audit caught the command as a blocker in iteration 1. This section closes the gap at authoring time.

**Audit enforcement:** `audit-haiku-safe` Step 4b extracts every `verify:` and `acceptance:` line from the PLAN's Verification section, checks each for the presence of a `# platform:` annotation, and scans unannotated lines for the forbidden-pattern set. See `audit-haiku-safe/workflows/audit-haiku-safe-steps.md` Step 4b for the full procedure and `audit-haiku-safe/lib/platform_portability.py` for the lint module.

## Boundary with harness-contract.md

This register answers a CI/OS-environment question - what shell and filesystem baseline a
`verify:`/`acceptance:` command may assume. That baseline is not a Claude Code harness
surface. `harness-contract.md` is the sibling register for harness surfaces (skill-listing
budgets, description caps, and similar platform behaviour), and the two registers must not
be merged.
