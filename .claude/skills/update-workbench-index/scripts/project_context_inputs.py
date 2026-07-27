#!/usr/bin/env python3
"""
project_context_inputs.py - Context Inputs projector for the monthly LOG.

Computes the correct set of Input-filename rows for the LOG's
'## Context Inputs This Month' section by reading on-disk ADVICE-*.md and
RESEARCH-*.md files filtered to the LOG's own month (derived from the LOG
filename, NOT from date.today()).

Only the Input-filename SET is deterministically projectable.  The Advises
and Notes columns are authored routing narrative - this projector preserves
them verbatim for surviving rows, and seeds Advises from frontmatter only for
newly-appended missing rows (blocker S202).

Out-of-month on-disk inputs are excluded from the missing-row set (blocker
S002): each file's frontmatter `created` date determines its month.

Modes
-----
--check (default)
    Report dangling / missing rows; exit 0 if no drift, 1 if there is drift.
    Writes nothing.
--write
    Reconcile the LOG's Context Inputs table in place.  Preserves authored
    Advises + Notes on surviving rows.  Drops dangling rows.  Appends missing
    rows with Advises seeded from frontmatter advises_plan / feeds_plan.
    Idempotent: only writes the file when content actually changes.

Usage
-----
    python project_context_inputs.py [workbench_dir] [--check | --write] \\
        [--log-path PATH]

    workbench_dir defaults to "Workbench" relative to the current working
    directory.  --log-path overrides the LOG file used (for tests - the month
    filter follows the fixture's filename, not today's date).

Reuses _parse_frontmatter from the co-located build_index.py.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Import _parse_frontmatter from the sibling scripts/ directory.
# This script lives in scripts/, so the directory is already the parent.
# The explicit path-insert is belt-and-braces (mirrors how tests import us).
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from build_index import _parse_frontmatter  # noqa: E402

# Guard stdout for UTF-8 to avoid encode errors on non-ASCII output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Month derivation from LOG filename
# ---------------------------------------------------------------------------


def _month_from_log_path(log_path: Path) -> str:
    """
    Derive the YYYYMM month string from the LOG filename.

    Expects a filename token matching _LOG_(\\d{6}), e.g.
    202607010000_LOG_202607.md -> "202607".

    Raises ValueError if the token is absent.
    """
    m = re.search(r"_LOG_(\d{6})", log_path.name)
    if not m:
        raise ValueError(
            f"Cannot derive month from LOG filename: {log_path.name!r} "
            "(expected pattern _LOG_YYYYMM)"
        )
    return m.group(1)


# ---------------------------------------------------------------------------
# LOG locator
# ---------------------------------------------------------------------------


def _locate_log(workbench_dir: Path, log_path_override: Path | None = None) -> Path:
    """
    Locate the current-month LOG file.

    If log_path_override is given, return it directly (test / explicit path).
    Otherwise construct {YYYYMM}010000_LOG_{YYYYMM}.md from today's date,
    and fall back to the lexicographically-latest *_LOG_*.md if the exact
    name is absent.
    """
    if log_path_override is not None:
        return log_path_override

    today = date.today()
    month_str = today.strftime("%Y%m")
    exact = workbench_dir / f"{month_str}010000_LOG_{month_str}.md"
    if exact.exists():
        return exact

    # Fallback: lexicographically latest *_LOG_*.md
    candidates = sorted(workbench_dir.glob("*_LOG_*.md"))
    if not candidates:
        raise FileNotFoundError(f"No LOG file found in {workbench_dir}")
    return candidates[-1]


# ---------------------------------------------------------------------------
# compute_rows: month-scoped on-disk input set
# ---------------------------------------------------------------------------


def compute_rows(workbench_dir: Path, month: str) -> list[dict]:
    """
    Glob ADVICE-*.md and RESEARCH-*.md at the top level of workbench_dir
    (not subdirectories; not .audit/), filter to files whose frontmatter
    `created` month equals `month` (YYYYMM), and return a sorted list of dicts.

    Each dict has:
      input            - the filename (not the full path)
      advises_fallback - the advises_plan value (type: advice) or feeds_plan
                         value (type: research), or "-" when empty / absent.
                         Used ONLY to seed the Advises cell of a newly-appended
                         missing row; surviving rows always use their authored
                         cell instead.

    Sorted deterministically by filename.
    """
    rows: list[dict] = []

    for pattern in ("ADVICE-*.md", "RESEARCH-*.md"):
        for p in workbench_dir.glob(pattern):
            if not p.is_file():
                continue
            # Top-level only: glob() on a plain Path is already top-level-only,
            # but we double-check that the parent is workbench_dir.
            if p.parent.resolve() != workbench_dir.resolve():
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            fm = _parse_frontmatter(text)

            # Month filter (blocker S002): compare frontmatter `created` month to
            # the LOG's own month.  `created` is e.g. "2026-07-12"; extract YYYYMM.
            created = fm.get("created") or ""
            if isinstance(created, str) and len(created) >= 7:
                file_month = created[:7].replace("-", "")
            else:
                file_month = ""
            if file_month != month:
                continue

            # Determine the advises_fallback for a potential new row.
            file_type = fm.get("type") or ""
            if file_type == "advice":
                fallback = fm.get("advises_plan") or ""
            else:
                # research (or unknown type)
                fallback = fm.get("feeds_plan") or ""

            # Normalise: None, empty string, or the literal "None" -> "-"
            if not fallback or fallback == "None":
                fallback = "-"

            rows.append({"input": p.name, "advises_fallback": fallback})

    rows.sort(key=lambda r: r["input"])
    return rows


# ---------------------------------------------------------------------------
# Table parsing: find the section and extract data rows
# ---------------------------------------------------------------------------

_TABLE_ROW_RE = re.compile(r"^\|.*\|")
_SECTION_HEADING_RE = re.compile(r"^##\s+Context Inputs This Month\s*$")
_NEXT_HEADING_RE = re.compile(r"^##")
_SEPARATOR_RE = re.compile(r"^\|[-| :]+\|$")


def _find_section_and_table(
    content: str,
) -> tuple | None:
    """
    Locate the '## Context Inputs This Month' section and its markdown table.

    Returns
    -------
    None
        Section heading not found.
    (section_idx, None, None, [], [])
        Heading found but no table follows (before the next ## heading or EOF).
    (section_idx, table_start, table_end, [header_line, sep_line], data_rows)
        Heading and table found.  table_start / table_end are line indices into
        content.splitlines(keepends=True).  data_rows is a list of
        [input_cell, advises_cell, notes_cell] string lists (cells stripped).
    """
    lines = content.splitlines(keepends=True)

    # 1. Find section heading.
    section_idx = None
    for i, line in enumerate(lines):
        if _SECTION_HEADING_RE.match(line.rstrip()):
            section_idx = i
            break
    if section_idx is None:
        return None

    # 2. State-machine scan for the table.
    #    States: looking -> header -> data
    phase = "looking"
    table_start: int | None = None
    table_end: int | None = None
    header_lines: list[str] = []
    data_rows: list[list[str]] = []

    for i in range(section_idx + 1, len(lines)):
        stripped = lines[i].rstrip()

        is_table_row = bool(_TABLE_ROW_RE.match(stripped))

        if phase == "looking":
            # Stop if we hit another section heading.
            if _NEXT_HEADING_RE.match(stripped):
                break
            if is_table_row:
                table_start = i
                header_lines.append(stripped)
                phase = "separator"
        elif phase == "separator":
            if is_table_row:
                # This is the separator row (|---|---|---|).
                header_lines.append(stripped)
                phase = "data"
            else:
                # Unexpected non-table line after header - end of table.
                table_end = i
                break
        elif phase == "data":
            if is_table_row:
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                # Pad to at least 3 cells.
                while len(cells) < 3:
                    cells.append("")
                data_rows.append(cells)
            else:
                # Non-table line ends the data block.
                table_end = i
                break
    else:
        # Reached EOF while scanning.
        if table_start is not None:
            table_end = len(lines)

    if table_start is None:
        return (section_idx, None, None, [], [])

    return (section_idx, table_start, table_end, header_lines, data_rows)


# ---------------------------------------------------------------------------
# diff: detect dangling and missing rows
# ---------------------------------------------------------------------------


def diff(log_path: Path, workbench_dir: Path) -> dict:
    """
    Compare the existing Context Inputs table against the on-disk input set.

    Returns
    -------
    {
        'dangling': [filename, ...],   # in table but no file on disk
        'missing':  [filename, ...],   # in-month on-disk input not in table
    }

    Out-of-month on-disk inputs are EXCLUDED from `missing` (blocker S002).
    If the '## Context Inputs This Month' heading is absent, the existing table
    is treated as zero rows (dangling: [], missing: all in-month on-disk inputs).
    """
    month = _month_from_log_path(log_path)
    on_disk = compute_rows(workbench_dir, month)
    on_disk_names = {r["input"] for r in on_disk}

    content = log_path.read_text(encoding="utf-8", errors="replace")
    result = _find_section_and_table(content)

    if result is None:
        # Heading absent - treat as zero existing rows.
        table_names: set[str] = set()
    else:
        _, table_start, table_end, _header_lines, data_rows = result
        if table_start is None:
            # Heading present, no table.
            table_names = set()
        else:
            table_names = {row[0] for row in data_rows if row[0]}

    dangling = sorted(table_names - on_disk_names)
    missing = sorted(on_disk_names - table_names)

    return {"dangling": dangling, "missing": missing}


# ---------------------------------------------------------------------------
# render_write: reconcile the table in place
# ---------------------------------------------------------------------------


def _build_table_lines(all_rows: list[list[str]]) -> list[str]:
    """Build standard markdown table lines (header + separator + data rows)."""
    lines = [
        "| Input | Advises | Notes |",
        "|---|---|---|",
    ]
    for row in all_rows:
        # Ensure 3 cells.
        while len(row) < 3:
            row.append("")
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} |")
    return lines


def render_write(log_path: Path, workbench_dir: Path) -> bool:
    """
    Reconcile the LOG's Context Inputs table in place.

    Contract
    --------
    - Dangling rows (Input cell in table, no such file on disk) are REMOVED.
    - Surviving rows (file IS on disk) keep BOTH their authored Advises and
      Notes cells verbatim - do NOT recompute from frontmatter (blocker S202).
    - Missing rows (in-month file on disk, no table row) are APPENDED with
      Advises seeded from frontmatter advises_plan / feeds_plan (or "-") and an
      empty Notes cell ("-").
    - Section heading and any prose above the table are preserved verbatim.
    - Idempotent: the LOG file is only written when content actually changes.

    Returns True if the file was rewritten, False if no change was needed.

    Graceful absent-section handling
    ---------------------------------
    - Heading absent -> print a notice, make no change, return False.
    - Heading present, no table -> insert a fresh table under the heading.
    """
    month = _month_from_log_path(log_path)
    on_disk = compute_rows(workbench_dir, month)
    on_disk_by_name = {r["input"]: r for r in on_disk}

    content = log_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines(keepends=True)

    result = _find_section_and_table(content)

    if result is None:
        # Heading absent - do not fabricate section placement.
        print(
            f"Notice: '## Context Inputs This Month' heading not found in "
            f"{log_path.name}; no change made."
        )
        return False

    section_idx, table_start, table_end, _header_lines, data_rows = result

    if table_start is None:
        # Heading present but no table - insert a fresh table.
        # Find the insertion point: right after the heading line's trailing blank lines.
        insert_idx = section_idx + 1
        for i in range(section_idx + 1, len(lines)):
            stripped = lines[i].strip()
            if stripped == "":
                insert_idx = i + 1
            elif stripped.startswith("|") or stripped.startswith("#"):
                break
            else:
                insert_idx = i + 1

        new_rows = [[r["input"], r["advises_fallback"], "-"] for r in on_disk]
        table_lines = _build_table_lines(new_rows)
        new_lines = (
            lines[:insert_idx]
            + [l + "\n" for l in table_lines]
            + ["\n"]
            + lines[insert_idx:]
        )
        new_content = "".join(new_lines)
        if new_content == content:
            return False
        log_path.write_text(new_content, encoding="utf-8")
        return True

    # Table present - reconcile in place.

    # Surviving rows: Input cell in table AND file on disk -> preserve authored cells.
    surviving: list[list[str]] = []
    for row in data_rows:
        input_name = row[0]
        if input_name in on_disk_by_name:
            surviving.append(row)
        # else: dangling - omit (dropped).

    # Missing rows: on-disk file not represented in surviving.
    surviving_names = {r[0] for r in surviving}
    missing_rows: list[list[str]] = []
    for r in on_disk:  # already sorted by filename
        if r["input"] not in surviving_names:
            missing_rows.append([r["input"], r["advises_fallback"], "-"])

    all_new_rows = surviving + missing_rows

    # Build the replacement table.
    table_lines = _build_table_lines(all_new_rows)

    # Reconstruct file: preserve everything before and after the table block.
    new_lines = (
        lines[:table_start]
        + [l + "\n" for l in table_lines]
        + lines[table_end:]
    )
    new_content = "".join(new_lines)

    # Idempotent write: only touch the file when content actually changed.
    if new_content == content:
        return False

    log_path.write_text(new_content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Context Inputs projector for the monthly LOG. "
            "Detects dangling / missing rows in the '## Context Inputs This Month' "
            "table (--check, default) or reconciles them in place (--write)."
        )
    )
    parser.add_argument(
        "workbench_dir",
        nargs="?",
        default="Workbench",
        help="Path to the Workbench directory (default: Workbench)",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Report drift without modifying the LOG (default when neither flag given)",
    )
    mode_group.add_argument(
        "--write",
        action="store_true",
        help="Reconcile the LOG Context Inputs table in place",
    )
    parser.add_argument(
        "--log-path",
        default=None,
        metavar="PATH",
        help=(
            "Override the LOG file path (for tests; month filter follows "
            "the fixture filename, not today's date)"
        ),
    )
    args = parser.parse_args(argv)

    workbench = Path(args.workbench_dir).resolve()
    log_path_override = Path(args.log_path).resolve() if args.log_path else None
    log_path = _locate_log(workbench, log_path_override)

    if args.write:
        changed = render_write(log_path, workbench)
        if changed:
            print(f"Context Inputs table reconciled in {log_path.name}.")
        else:
            print(f"Context Inputs table already up to date in {log_path.name}.")
        sys.exit(0)
    else:
        # --check mode (default when neither flag given).
        report = diff(log_path, workbench)
        dangling = report["dangling"]
        missing = report["missing"]
        if not dangling and not missing:
            print(
                f"Context Inputs table in {log_path.name}: no drift detected."
            )
            sys.exit(0)
        else:
            print(f"Context Inputs drift detected in {log_path.name}:")
            if dangling:
                print("  Dangling rows (in table, file not on disk):")
                for name in dangling:
                    print(f"    - {name}")
            if missing:
                print("  Missing rows (in-month on-disk input, not in table):")
                for name in missing:
                    print(f"    - {name}")
            sys.exit(1)


if __name__ == "__main__":
    main()
