#!/usr/bin/env python3
"""
next_testreport_id.py — sequential ID allocator for TESTREPORT files.

Scan-and-resume algorithm:
    1. Glob `Workbench/testreports/*.md`.
    2. Filter filenames matching `^TESTREPORT-(\\d{3})_.*\\.md$`.
    3. Take the max integer.
    4. Allocate `max + 1`, zero-padded to 3 digits.
    5. Refuse to write if the target path already exists (caller's responsibility
       to call `would_collide(path)` before writing).

If no matching files exist, return `001`.

Rationale (per PLAN-AA8 Mechanically-forced section): the existing
`.claude/skills/write-plan/scripts/next_id.py` only scans
`Workbench/` and misses LOG-archived retired IDs (documented allocator bug).
Keeping the TESTREPORT allocator independent avoids inheriting that bug class
and lets each evolve at its own pace.
"""

from __future__ import annotations

import pathlib
import re
import sys


_TESTREPORT_RE = re.compile(r"^TESTREPORT-(\d{3})_.*\.md$")


def find_repo_root(start: pathlib.Path) -> pathlib.Path:
    current = start.resolve()
    for candidate in [current] + list(current.parents):
        if (candidate / "Workbench").is_dir():
            return candidate
    return pathlib.Path.cwd()


def allocate(testreports_dir: pathlib.Path | None = None) -> str:
    """Allocate the next TESTREPORT ID (zero-padded 3-digit string).

    Args:
        testreports_dir: optional override; defaults to `<repo_root>/Workbench/testreports`.

    Returns:
        e.g. "003"
    """
    if testreports_dir is None:
        repo_root = find_repo_root(pathlib.Path(__file__).parent)
        testreports_dir = repo_root / "Workbench" / "testreports"
    max_seen = 0
    if testreports_dir.is_dir():
        for path in testreports_dir.glob("*.md"):
            m = _TESTREPORT_RE.match(path.name)
            if m:
                n = int(m.group(1))
                if n > max_seen:
                    max_seen = n
    return f"{max_seen + 1:03d}"


def would_collide(target_path: pathlib.Path) -> bool:
    """Return True if the target path already exists.

    Callers MUST check this before writing — the allocator refuses to overwrite.
    """
    return target_path.exists()


if __name__ == "__main__":
    print(allocate())
