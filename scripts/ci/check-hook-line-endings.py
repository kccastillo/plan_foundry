#!/usr/bin/env python3
"""
check-hook-line-endings.py - assert every bundle git hook is CRLF-free.

Why this is a mechanical check rather than a convention
------------------------------------------------------
Git executes hooks via their shebang. A CRLF-terminated shebang makes the
kernel look for an interpreter literally named `sh\\r`, and the hook dies:

    .git/hooks/commit-msg: /usr/bin/env: 'sh\\r': No such file or directory

This defect is invisible to review - the file reads correctly in an editor, in
a diff, and on GitHub. Worse, `.claude/hooks/commit-msg` exits 0 on every
failure path by design so it can never stall a pipeline, which means a hook
broken this way is outwardly indistinguishable from a working one. Nothing
short of a byte-level assertion catches it, so this is that assertion.

Two things are checked, because either alone is insufficient:

  1. **The committed blob has no CR bytes.** This is the ground truth. What is
     in the object database is what every consumer clones.
  2. **A matching `eol=lf` attribute is declared.** The blob being clean today
     does not stop a future commit from a Windows working tree reintroducing
     CRs; the attribute is what keeps it clean.

Per FOUNDRYREQ-plan_foundry_dev-20260727-1350 item 4, and PLAN-AD2 D9/D10.
"""

import pathlib
import subprocess
import sys

HOOKS_DIR = ".claude/hooks"


def _run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout


def main() -> int:
    # See check-invariants.py: cp1252 consoles mangle this script's em dashes
    # on Windows. PLAN-AF2 guard.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    rc, root_out = _run(["git", "rev-parse", "--show-toplevel"])
    if rc != 0:
        print("ERROR: not a git working tree", file=sys.stderr)
        return 1
    root = pathlib.Path(root_out.strip())

    rc, listing = _run(["git", "ls-files", "--", HOOKS_DIR])
    if rc != 0:
        print(f"ERROR: git ls-files failed for {HOOKS_DIR}", file=sys.stderr)
        return 1

    tracked = [line for line in listing.splitlines() if line.strip()]
    if not tracked:
        print(f"ERROR: no tracked files under {HOOKS_DIR} - expected at least the commit-msg hook", file=sys.stderr)
        return 1

    failures: list[str] = []

    for path in tracked:
        # 1. Committed blob must contain zero CR bytes.
        proc = subprocess.run(
            ["git", "show", f"HEAD:{path}"], capture_output=True
        )
        if proc.returncode != 0:
            # New file not yet committed - check the working tree instead.
            blob = (root / path).read_bytes()
            source = "working tree (uncommitted)"
        else:
            blob = proc.stdout
            source = "HEAD blob"
        cr_count = blob.count(b"\r")
        if cr_count:
            failures.append(
                f"{path}: {cr_count} CR byte(s) in {source} - a CRLF shebang "
                f"makes this hook fail silently on every Windows consumer"
            )

        # 2. An eol=lf attribute must be declared for it.
        rc, attr_out = _run(["git", "check-attr", "eol", "--", path])
        declared = attr_out.strip().rsplit(":", 1)[-1].strip() if attr_out else ""
        if declared != "lf":
            failures.append(
                f"{path}: eol attribute is {declared or 'unspecified'!r}, expected 'lf' - "
                f"add a pin to .gitattributes (see _shared/gitattributes_pin.py)"
            )

    if failures:
        for f in failures:
            print(f"ERROR: {f}", file=sys.stderr)
        return 1

    print(f"hook line endings: every tracked file under {HOOKS_DIR} is LF with eol=lf pinned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
