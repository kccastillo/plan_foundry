#!/usr/bin/env python3
"""
next_id.py — compute the next sequential ID for a given PLAN/ADVICE/RESEARCH type.

Design lineage: PLAN-AA0 (id-scheme-overhaul) → PLAN-AA1 (this implementation).
Replaces the legacy max(NNN)+1 filesystem-only allocator.

Usage:
    python next_id.py <TYPE> [--explain]

where TYPE is one of: PLAN, ADVICE, RESEARCH

    --explain (optional, boolean): in addition to the normal next-ID stdout
    line, write one line per used ID to stderr in the format
    `<ID>\t<source>` where `<source>` is one of `Workbench`, `Retired`, or
    `LOG-only`. Lines are emitted in lexicographic order by ID and are
    followed by a single trailing blank line. The stdout next-ID print
    and exit code are unchanged. Useful for diagnosing the
    defence-in-depth LOG-scan fallback path (any `LOG-only` line names an
    ID that appears in a LOG but is missing from both Workbench/ and
    Retired/ — a signal worth human attention post-D2-A).

For PLAN:
    Allocates IDs in the AA0–ZZ9 scheme (6,760 slots, lexicographic order):
    AA0 → AA1 → … → AA9 → AB0 → … → AZ9 → BA0 → … → ZZ9.

    Source of truth for "used IDs" (post-PLAN-AB9 D2, 2026-05-23):
    **filesystem-primary** — Workbench/ + Retired/ (scanned recursively) are
    authoritative. Rolled-over LOGs and PLANs nest in per-month subdirectories
    of Retired/, so Retired/ is always scanned recursively. The LOG Status
    Table is consulted only as a non-authoritative defence-in-depth fallback
    for any pre-D2-A archive state (Retired/ became a tracked directory under
    PLAN-AD0 D2-A on 2026-05-22; before that, the LOG was the only durable
    cross-clone record of used IDs).

    FS-primary + LOG-fallback + warn-and-union (M2):
    used = fs_ids ∪ log_ids
    If log_ids − fs_ids is non-empty, the orphan IDs (present in a LOG but
    missing from both Workbench/ and Retired/) are still counted as used —
    the allocator never re-issues them — and a warning is emitted to stderr
    for each. These warnings are the residual signal of the legacy
    LOG-primary regime; under the post-D2-A model they should be rare and
    each one is worth human inspection.

    Symmetrically, fs_ids − log_ids (filesystem IDs with no LOG row) still
    emits a stderr warning. Under the slim-LOG contract (AB9 D1, effective
    2026-06-01) these are expected for new-month PLANs that no longer get
    Status Table rows; the warning is retained for diagnostic transparency
    but is not a defect signal for `log_month ≥ 202606` PLANs.

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

    Expected stdout against the live tree (as of PLAN-AD0 backfill,
    2026-05-22; assumes PR #42's recursive-scan fix is merged):
        AD1
    (All earlier AA-form IDs through AD0 are in use — AA0..AB3 in Retired/,
    AA6..AC9 + AD0 active in Workbench/. AA-form allocation walks the union
    of LOG rows + filesystem and lands on AD1.)

    Expected stderr against the live tree (post-PLAN-AD0):
        warnings naming AA0, AA4, AA5 as filesystem IDs with no LOG row
        (M2 warn-and-union). These are expected, not a bug: per PLAN-AD0
        D1 (shipped-behaviour criterion) those three retired PLANs do
        not have LOG rows — AA0 was a plan-of-plans coordinator, AA4
        was audit-only, AA5 was doc-only. Their IDs remain visible to
        the allocator via the recursive Retired/ scan (PR #42), so the
        allocator does not re-issue them; the orphan warning is the
        intended audit-trail signal.

        Under PLAN-AD0 D2-A (2026-05-22), Retired/ is a tracked
        directory, so the recursive scan sees these IDs in every
        clone — not just operator-local working trees. AA2, AA3, AB2,
        AB3 have LOG rows backfilled per PLAN-AD0 D1 and no longer
        produce orphan warnings.

For ADVICE / RESEARCH:
    Numeric scheme retained (decision D3). Scans Workbench/ and Retired/ for
    matching filenames, computes max(NNN)+1, returns zero-padded 3-digit
    (4-digit when NNN>999) result.
    No LOG-parsing; ADVICE/RESEARCH have no LOG row in the Status Table format.

Returns:
    Prints the next ID to stdout.
    Exits 1 with a message to stderr on exhaustion or unknown type.
"""

import argparse
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
# Repo file discovery
# ---------------------------------------------------------------------------

def iter_repo_files(repo_root: pathlib.Path, pattern: str) -> "list[pathlib.Path]":
    """
    Return files matching `pattern` under Workbench/ and Retired/.

    Workbench/ is flat. Retired/ nests rolled-over artefacts — PLAN files and
    month-end LOGs — in per-month subdirectories, so it is scanned recursively.
    A non-recursive glob over Retired/ silently under-counts used IDs, after
    which the allocator hands back an ID that is already taken.
    """
    found: list[pathlib.Path] = []
    for directory, recursive in (("Workbench", False), ("Retired", True)):
        scan_dir = repo_root / directory
        if not scan_dir.is_dir():
            continue
        matcher = scan_dir.rglob if recursive else scan_dir.glob
        found.extend(matcher(pattern))
    return found


# ---------------------------------------------------------------------------
# LOG parsing
# ---------------------------------------------------------------------------

def parse_log_ids(repo_root: pathlib.Path) -> "set[str]":
    """
    Discover all monthly LOG files under Workbench/ and Retired/ (Retired/
    scanned recursively, since rolled-over LOGs nest in per-month subdirs).
    For each file, locate the Status Table by anchoring on the canonical
    header row. Parse subsequent rows until the table ends. Extract bare
    PLAN IDs via regex from column 1.

    Tolerates: malformed rows (skip + stderr warn), missing anchor (skip
    file + stderr warn), unreadable files (skip + stderr warn).

    Returns a set of bare IDs, e.g. {"AA0", "029", "030"}.
    """
    ids: set[str] = set()
    log_files = iter_repo_files(repo_root, "*_LOG_*.md")
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
    Glob PLAN-*.md under Workbench/ and Retired/ (Retired/ recursively).
    Extract bare IDs via the same regex.
    Returns a set of bare IDs.
    """
    ids: set[str] = set()
    for f in iter_repo_files(repo_root, "PLAN-*.md"):
        m = _LOG_ID_RE.search(f.name)
        if m:
            ids.add(m.group(1))
    return ids


def glob_filesystem_ids_by_source(repo_root: pathlib.Path) -> "tuple[set[str], set[str]]":
    """
    Return (workbench_ids, retired_ids) — disjoint PLAN-ID sets keyed by
    discovery directory. Workbench/ is scanned flat; Retired/ recursively.
    Used by `--explain` to label each ID's authoritative source.
    """
    workbench_ids: set[str] = set()
    retired_ids: set[str] = set()
    for directory, recursive, target in (
        ("Workbench", False, workbench_ids),
        ("Retired", True, retired_ids),
    ):
        scan_dir = repo_root / directory
        if not scan_dir.is_dir():
            continue
        matcher = scan_dir.rglob if recursive else scan_dir.glob
        for f in matcher("PLAN-*.md"):
            m = _LOG_ID_RE.search(f.name)
            if m:
                target.add(m.group(1))
    return workbench_ids, retired_ids


def compute_used_ids(repo_root: pathlib.Path) -> "set[str]":
    """
    Return fs_ids ∪ log_ids (FS-primary + LOG-fallback + warn-and-union, M2).

    Post-PLAN-AB9 D2 (2026-05-23): filesystem (Workbench/ + Retired/) is the
    authoritative source. LOG-scan is retained as a non-authoritative
    defence-in-depth fallback — any ID found only in a LOG (and not on the
    filesystem) is still counted as used so the allocator never re-issues
    it, and a warning is emitted to stderr for human attention.

    Symmetric warn-path: fs_ids − log_ids (filesystem PLAN with no LOG row)
    also emits a stderr warning; under the slim-LOG contract this is expected
    for new-month PLANs and the warning is diagnostic rather than defect-class.
    """
    log_ids = parse_log_ids(repo_root)
    fs_ids = glob_filesystem_ids(repo_root)
    orphans = fs_ids - log_ids
    for orphan in sorted(orphans):
        print(
            f"warning: filesystem ID PLAN-{orphan} has no LOG row; treating as used",
            file=sys.stderr,
        )
    log_only = log_ids - fs_ids
    for stray in sorted(log_only):
        print(
            f"warning: LOG-only ID PLAN-{stray} not present in Workbench/ or Retired/; "
            f"treating as used (non-authoritative fallback, AB9 D2)",
            file=sys.stderr,
        )
    return fs_ids | log_ids


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
    Scans Workbench/ and Retired/ (Retired/ recursively) for files matching
    <TYPE>-NNN_*.md, computes max(NNN)+1, returns zero-padded 3-digit
    (4-digit if >999) result.
    Returns "001" if no existing files of that type are found.
    No LOG-parsing — ADVICE/RESEARCH do not appear in the PLAN Status Table.
    """
    pattern = re.compile(
        rf"^{re.escape(type_token)}-(\d{{3,4}})_",
        re.IGNORECASE,
    )
    max_num = 0
    for f in iter_repo_files(repo_root, "*.md"):
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

def _emit_explain(repo_root: pathlib.Path) -> None:
    """
    Emit `<ID>\\t<source>` lines to stderr for every used PLAN ID, in
    lexicographic order, followed by one trailing blank line. `source` is:
      Workbench — ID discovered in the flat Workbench/ scan.
      Retired   — ID discovered in the recursive Retired/ scan.
      LOG-only  — ID found ONLY in a LOG, missing from both Workbench/
                  and Retired/ (defence-in-depth fallback signal).
    Workbench takes precedence over Retired for any ID that appears in both
    (an unusual state — would indicate a half-retired PLAN).
    """
    workbench_ids, retired_ids = glob_filesystem_ids_by_source(repo_root)
    log_ids = parse_log_ids(repo_root)
    fs_ids = workbench_ids | retired_ids
    log_only = log_ids - fs_ids

    labelled: list[tuple[str, str]] = []
    for plan_id in workbench_ids:
        labelled.append((plan_id, "Workbench"))
    for plan_id in retired_ids - workbench_ids:
        labelled.append((plan_id, "Retired"))
    for plan_id in log_only:
        labelled.append((plan_id, "LOG-only"))

    for plan_id, source in sorted(labelled, key=lambda pair: pair[0]):
        print(f"{plan_id}\t{source}", file=sys.stderr)
    print("", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="next_id.py",
        description="Compute the next sequential ID for PLAN/ADVICE/RESEARCH.",
    )
    parser.add_argument(
        "type",
        metavar="TYPE",
        help="One of: PLAN, ADVICE, RESEARCH (case-insensitive).",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        default=False,
        help="Emit `<ID>\\t<source>` lines to stderr (PLAN only). "
             "source ∈ {Workbench, Retired, LOG-only}.",
    )
    args = parser.parse_args()

    type_token = args.type.upper()
    if type_token not in VALID_TYPES:
        print(
            f"Error: unknown type '{args.type}'. Must be one of: {', '.join(sorted(VALID_TYPES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root = find_repo_root(pathlib.Path(__file__).parent)

    if type_token == "PLAN":
        try:
            used = compute_used_ids(repo_root)
            result = next_aa_id(used)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        if args.explain:
            _emit_explain(repo_root)
    else:
        result = next_numeric_id(type_token, repo_root)
        # --explain is a no-op for ADVICE/RESEARCH (no LOG-vs-FS distinction).

    print(result)
