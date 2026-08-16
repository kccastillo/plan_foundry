---
title: Platform Portability
description: CI-baseline portability rule for `verify:`/`acceptance:` commands - forbidden shell patterns and the `# platform:` opt-out.
created: 2026-08-17
---

# Platform portability (per PLAN-AB3, H3 hiccup-log 2026-05-16)

Every `verify:` and `acceptance:` command MUST run on the foundry's CI baseline without modification. A command that silently fails or requires rewriting on CI is a plan-safety violation.

**CI baseline (the default platform):** Ubuntu Linux + Python 3.11 + pytest + pyyaml + git + gh + POSIX shell with bash-isms allowed. Commands that rely on this baseline require no annotation.

**Opt-out annotation:** when portability is genuinely impossible, add a trailing comment on the same line:
- `# platform: posix` - command is POSIX-specific; runs only on POSIX platforms during outcome-verify; audit skips the portability check for that item.
- `# platform: windows` - command is Windows-specific; runs only on Windows during outcome-verify; audit skips the portability check for that item.

**Forbidden patterns (when no `# platform:` annotation is present):** unannotated commands containing any of the following patterns will trigger a `warn`-severity finding from `audit-haiku-safe`:

| Pattern | Rationale |
|---------|-----------|
| `/tmp/` | Linux-only temp path; use `tempfile` Python module for portable alternatives |
| `/dev/null` | POSIX-only null device; use `subprocess.DEVNULL` or redirect suppression in Python |
| `bash -c` | Explicitly invokes bash; unavailable or differently-pathed on Windows |
| `test -[a-zA-Z]` | POSIX `test` builtin; use Python `os.path.exists()` / `pathlib` patterns instead |
| `> /dev/` | Redirect to `/dev/` pseudo-device; POSIX-only |
| `2>/dev/null` | POSIX stderr suppression; use Python subprocess or annotate |
| `&&` in compound commands | Works in bash but breaks PowerShell 5.1; split into separate commands or annotate |

**Origin:** H3 from `202605160300_RESEARCH_hiccup-log.md` - Reeve's Plan B used `> /tmp/dump.json && test -s /tmp/dump.json` (POSIX-only on a Windows project); plan-safety audit caught it as a blocker in iteration 1. This section closes the gap at authoring time.

**Audit enforcement:** `audit-haiku-safe` Step 4b extracts every `verify:` and `acceptance:` line from the PLAN's Verification section, checks each for the presence of a `# platform:` annotation, and scans unannotated lines for the forbidden-pattern set. See `audit-haiku-safe/workflows/audit-haiku-safe-steps.md` Step 4b for the full procedure and `audit-haiku-safe/lib/platform_portability.py` for the lint module.

## Boundary with harness-contract.md

This register answers a CI/OS-environment question - what shell and filesystem baseline a
`verify:`/`acceptance:` command may assume. It is not a Claude Code harness surface.
`harness-contract.md` is the sibling register for harness surfaces (skill-listing budgets,
description caps, and similar platform behaviour); the two registers must not be merged.
