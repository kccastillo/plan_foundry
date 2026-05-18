#!/usr/bin/env python3
"""
next_id.py — compute the next sequential ID for a given PLAN/ADVICE/RESEARCH type.

Design lineage: PLAN-AA0 (id-scheme-overhaul) → PLAN-AA1 (this implementation).
Replaces the legacy max(NNN)+1 filesystem-only allocator.

Usage:
    python next_id.py <TYPE>

where TYPE is one of: PLAN, ADVICE, RESEARCH

For PLAN:
    Allocates IDs in the AA0–ZZ9 scheme (6,760 slots, lexicographic order):
    AA0 → AA1 → … → AA9 → AB0 → … → AZ9 → BA0 → … → ZZ9.

    Source of truth for "used IDs": the LOG Status Table in every monthly LOG
    file found under Workbench/ (glob *_LOG_*.md). The filesystem (Workbench/
    and Retired/) is consulted as a belt-and-braces secondary source.

    LOG-primary + FS-secondary + warn-and-union (M2):
    used = log_ids | fs_ids
    If fs_ids − log_ids is non-empty, a warning is emitted to stderr for each
    orphan, but the orphan is still counted as used. This means the allocator
    never collides with a filesystem PLAN that lacks a LOG row, while also
    surfacing the discrepancy loudly for human inspection.

    Calling-contract (Postgres nextval template, decision C4):
    The allocator is NOT idempotent across calls. Calling `python next_id.py
    PLAN` twice without an intervening PLAN-file write will return the same ID
    both times, because the script reads from LOG + filesystem (neither of which
    changes between calls). Batch callers must write (or at minimum touch) each
    PLAN file before drawing the next ID.

    Disjoint-namespace invariant:
    Numeric IDs (e.g. PLAN-001..PLAN-037, historical) and AA-form IDs
    (PLAN-AA0..ZZ9, active) coexist in the LOG and in the used-ID set. The
    allocator returns from the AA-form space for PLAN; numeric IDs are tracked
    but do not perturb AA-form allocation (they live in separate slot-spaces).

    LOG Status Table column-1 invariant:
    Each data row's first column is expected to be a filename of the form
    PLAN-<id>_<slug>.md. The regex `PLAN-([A-Z]{2}[0-9]|\\d{3,4})` is used to
    extract bare IDs. If the LOG schema drifts (column order changes, header
    row renamed), the regex will stop matching and emit warnings — it fails
    loudly rather than silently under-counting used IDs.

    Expected stdout against the live tree (as of PLAN-AA1 execution):
        AA6
    (Because PLAN-AA0..AA5 exist on disk; AA-form allocation walks AA0..AA5
    and lands on AA6.)

    Expected stderr against the live tree:
        warnings naming AA0, AA1, AA2, AA3, AA4, AA5 as filesystem IDs with
        no LOG row (M2 warn-and-union; these are expected, not a bug, because
        the AA-form PLANs predate this LOG-aware allocator's first run).

For ADVICE / RESEARCH:
    Numeric scheme retained (decision D3). Scans Workbench/ and Retired/ for
    matching filenames, computes max(NNN)+1, returns zero-padded 3-digit
    (4-digit when NNN>999) result.
    No LOG-parsing; ADVICE/RESEARCH have no LOG row in the Status Table format.

Returns:
    Prints the next ID to stdout.
    Exits 1 with a message to stderr on exhaustion or unknown type.
"""

import sys
import re
import pathlib

VALID_TYPES = {"PLAN", "ADVICE", "RESEARCH"}

# Regex to extract bare IDs from LOG Status Table column 1.
# Matches both AA-form (PLAN-AA0) and historic numeric (PLAN-001, PLAN-0029).
# Group 1 is the bare ID portion (e.g. "AA0" or "029").
_LOG_ID_RE = re.compile(r"PLAN-([A-Z]{2}[0-9]|\d{3,4})")

# Regex to match the canonical LOG Status Table header anchor.
_LOG_HEADER = "| Plan File | Title | Assigned | Priority | Status | Due |"

# Total AA-form ID space.
_AA_TOTAL = 26 * 26 * 10  # 6,760


# ---------------------------------------------------------------------------
# Repo-root discovery (preserved from legacy)
# ---------------------------------------------------------------------------

def find_repo_root(start: pathlib.Path) -> pathlib.Path:
    """Walk up from start to find the directory containing Workbench/."""
    current = start.resolve()
    for candidate in [current] + list(current.parents):
        if (candidate / "Workbench").is_dir():
            return candidate
    return pathlib.Path.cwd()


# ---------------------------------------------------------------------------
# AA-form index arithmetic
# ---------------------------------------------------------------------------

def aa_id_to_index(aa: str) -> int:
    """
    Convert an AA-form ID string to its zero-based index.
    "AA0" -> 0, "AA9" -> 9, "AB0" -> 10, "AZ9" -> 259, "BA0" -> 260, "ZZ9" -> 6759.
    """
    letter1 = ord(aa[0]) - ord('A')  # 0..25
    letter2 = ord(aa[1]) - ord('A')  # 0..25
    digit = int(aa[2])               # 0..9
    return letter1 * 260 + letter2 * 10 + digit


def index_to_aa_id(i: int) -> str:
    """
    Convert a zero-based index to an AA-form ID string.
    0 -> "AA0", 9 -> "AA9", 10 -> "AB0", 6759 -> "ZZ9".
    """
    digit = i % 10
    remainder = i // 10
    letter2 = remainder % 26
    letter1 = remainder // 26
    return chr(ord('A') + letter1) + chr(ord('A') + letter2) + str(digit)


# ---------------------------------------------------------------------------
# LOG parsing
# ---------------------------------------------------------------------------

def parse_log_ids(workbench_dir: pathlib.Path) -> "set[str]":
    """
    Discover all monthly LOG files via workbench_dir.glob("*_LOG_*.md").
    For each file, locate the Status Table by anchoring on the canonical
    header row. Parse subsequent rows until the table ends. Extract bare
    PLAN IDs via regex from column 1.

    Tolerates: malformed rows (skip + stderr warn), missing anchor (skip
    file + stderr warn), unreadable files (skip + stderr warn).

    Returns a set of bare IDs, e.g. {"AA0", "029", "030"}.
    """
    ids: set[str] = set()
    log_files = list(workbench_dir.glob("*_LOG_*.md"))
    if not log_files:
        return ids

    for log_path in log_files:
        try:
            # errors='replace' tolerates stray non-UTF-8 bytes (e.g. smart-quote
            # bytes from a Windows-pasted Status Table cell) by substituting
            # U+FFFD rather than dropping the whole file's data. The PLAN spec
            # requires graceful degradation on malformed input — a single bad
            # byte must not cause the file's PLAN IDs to be lost.
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            print(
                f"warning: could not read LOG file {log_path.name}: {exc}",
                file=sys.stderr,
            )
            continue

        # Anchor on canonical header row.
        header_pos = text.find(_LOG_HEADER)
        if header_pos == -1:
            print(
                f"warning: {log_path.name} has no Status Table header row; skipping",
                file=sys.stderr,
            )
            continue

        # Parse from the character after the header line.
        after_header = text[header_pos + len(_LOG_HEADER):]
        for line in after_header.splitlines():
            stripped = line.strip()
            if not stripped:
                # Blank line — table may have ended.
                continue
            if stripped.startswith("#"):
                # Section header — table ended.
                break
            if not stripped.startswith("|"):
                # Separator row or non-table content.
                continue
            # Column 1 is between the first and second pipes.
            parts = stripped.split("|")
            if len(parts) < 3:
                print(
                    f"warning: malformed row in {log_path.name}: {stripped!r}; skipping",
                    file=sys.stderr,
                )
                continue
            cell = parts[1].strip()
            m = _LOG_ID_RE.search(cell)
            if m:
                ids.add(m.group(1))

    return ids


# ---------------------------------------------------------------------------
# Filesystem scanning
# ---------------------------------------------------------------------------

def glob_filesystem_ids(repo_root: pathlib.Path) -> "set[str]":
    """
    Glob Workbench/PLAN-*.md and Retired/PLAN-*.md.
    Extract bare IDs via the same regex.
    Returns a set of bare IDs.
    """
    ids: set[str] = set()
    for directory in ("Workbench", "Retired"):
        scan_dir = repo_root / directory
        if not scan_dir.is_dir():
            continue
        for f in scan_dir.glob("PLAN-*.md"):
            m = _LOG_ID_RE.search(f.name)
            if m:
                ids.add(m.group(1))
    return ids


def compute_used_ids(workbench_dir: pathlib.Path, repo_root: pathlib.Path) -> "set[str]":
    """
    Return log_ids | fs_ids (warn-and-union, M2).
    Emits a stderr warning for each filesystem ID with no LOG row (orphan),
    but still includes it in the returned set so the allocator does not collide.
    """
    log_ids = parse_log_ids(workbench_dir)
    fs_ids = glob_filesystem_ids(repo_root)
    orphans = fs_ids - log_ids
    for orphan in sorted(orphans):
        print(
            f"warning: filesystem ID PLAN-{orphan} has no LOG row; treating as used",
            file=sys.stderr,
        )
    return log_ids | fs_ids


# ---------------------------------------------------------------------------
# AA-form ID allocation
# ---------------------------------------------------------------------------

def next_aa_id(used: "set[str]") -> str:
    """
    Walk AA0, AA1, …, ZZ9 and return the first ID not in used.
    Raises RuntimeError if all 6,760 slots are taken.
    """
    for i in range(_AA_TOTAL):
        candidate = index_to_aa_id(i)
        if candidate not in used:
            return candidate
    raise RuntimeError(
        f"AA-form ID space exhausted ({_AA_TOTAL} slots used)"
    )


# ---------------------------------------------------------------------------
# Numeric allocation (ADVICE / RESEARCH — legacy behaviour preserved)
# ---------------------------------------------------------------------------

def next_numeric_id(type_token: str, repo_root: pathlib.Path) -> str:
    """
    Compute the next sequential numeric ID for ADVICE or RESEARCH.
    Scans Workbench/ and Retired/ for files matching <TYPE>-NNN_*.md,
    computes max(NNN)+1, returns zero-padded 3-digit (4-digit if >999) result.
    Returns "001" if no existing files of that type are found.
    No LOG-parsing — ADVICE/RESEARCH do not appear in the PLAN Status Table.
    """
    pattern = re.compile(
        rf"^{re.escape(type_token)}-(\d{{3,4}})_",
        re.IGNORECASE,
    )
    max_num = 0
    for directory in ("Workbench", "Retired"):
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
    width = 4 if next_num > 999 else 3
    return str(next_num).zfill(width)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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

    if type_token == "PLAN":
        workbench_dir = repo_root / "Workbench"
        try:
            used = compute_used_ids(workbench_dir, repo_root)
            result = next_aa_id(used)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
    else:
        result = next_numeric_id(type_token, repo_root)

    print(result)
