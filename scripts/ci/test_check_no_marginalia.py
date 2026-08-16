#!/usr/bin/env python3
"""
test_check_no_marginalia.py - guard the fenced-block exclusion in check-no-marginalia.py.

The check flags headings such as "## Divergences" as commentary a document makes
about itself. A heading inside a fenced block is not that: it is a template the
document tells its reader to fill in, or quoted material. The check skipped
frontmatter but not fences until 2026-07-31, so
references/risk-criteria-survey-prompt.md failed CI on the "## Divergences"
heading of the report template it asks a surveying agent to produce.

Run: python3 scripts/ci/test_check_no_marginalia.py
"""

from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "scripts" / "ci" / "check-no-marginalia.py"


def load_check():
    spec = importlib.util.spec_from_file_location("check_no_marginalia", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_against(module, tmp_root: Path, body: str) -> int:
    """Point the check at a throwaway tree holding one markdown file.

    The negative cases make the check print its ERROR banner. Capture both
    streams: run-all.sh's loud-fail guard reads an ERROR line on stderr as a
    failure even when the exit code is 0, so a test that lets the banner
    through fails the suite it is meant to protect.
    """
    tmp_root.mkdir(parents=True, exist_ok=True)
    target = tmp_root / "sample.md"
    target.write_text(body, encoding="utf-8")
    module.REPO_ROOT = tmp_root.parent
    module.SCAN_ROOTS = [tmp_root]
    sink_out, sink_err = io.StringIO(), io.StringIO()
    with redirect_stdout(sink_out), redirect_stderr(sink_err):
        return module.main()


def main() -> int:
    import tempfile

    module = load_check()
    failures = []

    cases = [
        (
            "fenced heading passes",
            "# Title\n\nText.\n\n```markdown\n## Divergences\n\n<fill this in>\n```\n",
            0,
        ),
        (
            "unfenced heading fails",
            "# Title\n\n## Divergences\n\nHow this copy differs from the original.\n",
            1,
        ),
        (
            "tilde fence also passes",
            "# Title\n\n~~~\n## Provenance\n~~~\n",
            0,
        ),
        (
            "heading after a closed fence still fails",
            "# Title\n\n```\n## Divergences\n```\n\n## Attribution\n\nFrom elsewhere.\n",
            1,
        ),
        (
            "exempt marker still works outside a fence",
            "# Title\n\n## Divergences <!-- marginalia-ok -->\n",
            0,
        ),
    ]

    for name, body, expected in cases:
        with tempfile.TemporaryDirectory() as td:
            got = run_against(module, Path(td) / "refs", body)
        if got != expected:
            failures.append(f"{name}: expected exit {expected}, got {got}")

    if failures:
        print("check-no-marginalia fence handling: FAILED", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    print("check-no-marginalia: fence handling correct on every case")
    return 0


if __name__ == "__main__":
    sys.exit(main())
