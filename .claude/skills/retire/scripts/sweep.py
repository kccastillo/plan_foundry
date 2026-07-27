#!/usr/bin/env python3
"""
sweep.py - Retire status:done PLANs older than N days.

CLI:
    python sweep.py <workbench_dir> [--age-days N] [--dry-run]

Scans <workbench_dir> for *.md files (excluding INDEX.md, LOG files, .gitkeep,
and dotfiles). For each file with YAML frontmatter containing `status: done`,
checks the last-commit timestamp via `git log`. Falls back to file mtime if git
log returns empty (untracked file). If the file is older than age_days, it is
moved to Retired/ (sibling of <workbench_dir>), or listed if --dry-run.

Exit 0 on success (including zero-eligible case).
"""

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_status(path: Path) -> str:
    """Return the value of the `status:` key in YAML frontmatter, or ''."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    # Must start with ---
    if not text.startswith("---"):
        return ""

    # Find closing ---
    end = text.find("\n---", 3)
    if end == -1:
        return ""

    frontmatter = text[3:end]
    match = re.search(r"^status:\s*(.+)$", frontmatter, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return ""


# ---------------------------------------------------------------------------
# Age checks
# ---------------------------------------------------------------------------

def last_commit_timestamp(path: Path) -> float:
    """
    Return the Unix timestamp of the last git commit touching `path`.
    Returns 0.0 if git log returns empty (untracked) or on error.
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        output = result.stdout.strip()
        if output:
            return float(output)
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 0.0


def effective_timestamp(path: Path) -> float:
    """
    Return the effective age timestamp for path.
    Prefer git log; fall back to file mtime if git log returns 0.
    """
    ts = last_commit_timestamp(path)
    if ts > 0.0:
        return ts
    # Fallback: file mtime
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


# ---------------------------------------------------------------------------
# File filter
# ---------------------------------------------------------------------------

SKIP_PATTERNS = re.compile(
    r"^(INDEX\.md|\.gitkeep)$|^LOG_|_LOG_",
    re.IGNORECASE,
)


def is_candidate(path: Path) -> bool:
    """Return True if the file should be considered for retirement."""
    name = path.name
    if name.startswith("."):
        return False
    if not name.endswith(".md"):
        return False
    if SKIP_PATTERNS.search(name):
        return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retire status:done PLANs older than N days from Workbench/."
    )
    parser.add_argument("workbench_dir", help="Path to Workbench/ directory")
    parser.add_argument(
        "--age-days",
        type=int,
        default=7,
        help="Minimum age in days before a done PLAN is eligible (default: 7)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List eligible files without moving them",
    )
    args = parser.parse_args()

    workbench = Path(args.workbench_dir).resolve()
    if not workbench.is_dir():
        print(f"Error: workbench_dir '{workbench}' does not exist or is not a directory.", file=sys.stderr)
        return 1

    # Retired/ lives as a sibling of Workbench/
    retired = workbench.parent / "Retired"

    cutoff = time.time() - args.age_days * 86400

    eligible = []
    for path in sorted(workbench.glob("*.md")):
        if not is_candidate(path):
            continue
        status = parse_status(path)
        if status != "done":
            continue
        ts = effective_timestamp(path)
        if ts == 0.0 or ts > cutoff:
            continue
        eligible.append(path)

    if not eligible:
        print("No PLANs eligible for retirement.")
        return 0

    if args.dry_run:
        print(f"Dry-run: would retire {len(eligible)} file(s):")
        for p in eligible:
            print(f"  {p.name}")
        return 0

    # Ensure Retired/ exists
    retired.mkdir(parents=False, exist_ok=True)

    moved = []
    errors = []
    for path in eligible:
        dest = retired / path.name
        try:
            shutil.move(str(path), str(dest))
            moved.append(path.name)
        except OSError as exc:
            errors.append(f"  {path.name}: {exc}")

    if moved:
        print(f"Retired {len(moved)} file(s):")
        for name in moved:
            print(f"  {name}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
