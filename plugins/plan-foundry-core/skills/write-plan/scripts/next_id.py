#!/usr/bin/env python3
"""
next_id.py — compute the next sequential ID for a given PLAN/ADVICE/RESEARCH type.

Usage:
    python next_id.py <TYPE>

where TYPE is one of: PLAN, ADVICE, RESEARCH

Scans Workbench/ and Retired/ (relative to this script's repo root, or cwd)
for files matching `<TYPE>-NNN_*.md`, computes max(NNN) + 1,
and prints the zero-padded 3-digit result (e.g. "042") to stdout.

Returns "001" if no existing files of that type are found.
Exits 1 with a message to stderr if TYPE is unknown.
"""

import sys
import re
import pathlib

VALID_TYPES = {"PLAN", "ADVICE", "RESEARCH"}

# Resolve repo root: walk up from this script's location to find Workbench/
def find_repo_root(start: pathlib.Path) -> pathlib.Path:
    current = start.resolve()
    for candidate in [current] + list(current.parents):
        if (candidate / "Workbench").is_dir():
            return candidate
    return pathlib.Path.cwd()


def compute_next_id(type_token: str, repo_root: pathlib.Path) -> str:
    pattern = re.compile(
        rf"^{re.escape(type_token)}-(\d{{3,4}})_",
        re.IGNORECASE,
    )
    max_num = 0
    for directory in ["Workbench", "Retired"]:
        scan_dir = repo_root / directory
        if not scan_dir.is_dir():
            continue
        for f in scan_dir.glob("*.md"):
            m = pattern.match(f.name)
            if m:
                n = int(m.group(1))
                if n > max_num:
                    max_num = n
    next_num = max_num + 1
    # Expand to 4 digits only when count exceeds 999
    width = 4 if next_num > 999 else 3
    return str(next_num).zfill(width)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python next_id.py <TYPE>", file=sys.stderr)
        print("  TYPE must be one of: PLAN, ADVICE, RESEARCH", file=sys.stderr)
        sys.exit(1)

    type_token = sys.argv[1].upper()
    if type_token not in VALID_TYPES:
        print(
            f"Error: unknown type '{sys.argv[1]}'. Must be one of: {', '.join(sorted(VALID_TYPES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root = find_repo_root(pathlib.Path(__file__).parent)
    result = compute_next_id(type_token, repo_root)
    print(result)
