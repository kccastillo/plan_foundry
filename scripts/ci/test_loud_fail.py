#!/usr/bin/env python3
"""
test_loud_fail.py - CI must go red when a check fails quietly.

Per PLAN-AC4 D4 (CI-Loud-Fail). run-all.sh's run_check treats a check as failed
if EITHER it exits non-zero OR it emits a line starting with ERROR or Error: on
stderr. The second condition is the one worth guarding: PLAN-AC3 surfaced a
check that printed an error and still exited 0, and CI reported green over it.

This test sources run-all.sh and calls the real run_check with synthetic
commands. It does not run the suite.

Two earlier versions were wrong in different ways, both worth recording:

  - The original copied the repo WITHOUT .git, so two git-dependent checks
    failed on an unmutated tree. It asserted only "exit != 0", so it reported
    PASS whether or not the fault was injected. It was also never registered in
    run-all.sh, so it had never run at all.
  - The replacement ran the whole suite twice inside a git worktree, once for a
    green baseline and once with a crash injected. Correct, but 144 seconds to
    test one property, on every push and every local run.

Sourcing run-all.sh exercises the same run_check the suite uses, in about a
second. Three cases:

  - a command that exits 0 quietly            -> run_check must PASS it
  - a command that exits non-zero             -> run_check must FAIL it
  - a command that exits 0 but prints ERROR:  -> run_check must FAIL it

The first case matters as much as the other two. Without it, a run_check that
failed everything unconditionally would still satisfy this test.

Exit codes:
  0 - all three behaved correctly.
  1 - run_check let something through, or failed something it should not have.
  2 - test infrastructure error.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
RUN_ALL = REPO_ROOT / "scripts" / "ci" / "run-all.sh"

# label, the command run_check is given, whether run_check must report failure
CASES = [
    ("quiet success", "true", False),
    ("non-zero exit", "false", True),
    ("exit 0 but ERROR on stderr", "echo 'ERROR: synthetic silent-pass' >&2; true", True),
]


def shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def run_case(command: str) -> tuple[int, str]:
    """Source run-all.sh, call the real run_check, report the failure count."""
    script = (
        f'source "{RUN_ALL.as_posix()}"\n'
        f'run_check "synthetic" bash -c {shell_quote(command)} >/dev/null 2>&1\n'
        f'echo "failed=$failed"\n'
    )
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )
    return proc.returncode, proc.stdout.strip()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not RUN_ALL.is_file():
        print(f"ERROR: {RUN_ALL} not found", file=sys.stderr)
        return 2

    problems: list[str] = []
    for label, command, must_fail in CASES:
        rc, out = run_case(command)
        if rc != 0 or "failed=" not in out:
            print(f"ERROR: could not evaluate case {label!r}: rc={rc} out={out!r}", file=sys.stderr)
            return 2
        did_fail = out.rsplit("failed=", 1)[1].strip() != "0"
        if did_fail != must_fail:
            expected = "fail" if must_fail else "pass"
            got = "failed" if did_fail else "passed"
            problems.append(f"{label}: run_check should {expected} this, but it {got} it")

    if problems:
        print("FAIL: run_check is not applying the loud-fail rule.", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print("loud-fail: run_check correct on every case "
          "(quiet success, non-zero exit, ERROR-on-stderr-with-exit-0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
