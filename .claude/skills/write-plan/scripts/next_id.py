#!/usr/bin/env python3
"""
next_id.py - compute the next sequential ID for a given PLAN/ADVICE/RESEARCH type.

Design lineage: PLAN-AA0 (id-scheme-overhaul) -> PLAN-AA1 (this implementation).
Replaces the legacy max(NNN)+1 filesystem-only allocator.

Usage:
    python next_id.py <TYPE> [--explain]

where TYPE is one of: PLAN, ADVICE, RESEARCH

    --explain (optional, boolean): in addition to the normal next-ID stdout
    line, write one line per used ID to stderr in the format
    `<ID>	<source>` where `<source>` is `Workbench`, `Retired` or `Burned`.
    Lines are emitted in lexicographic order by ID and are followed by a single
    trailing blank line. The stdout next-ID print and exit code are unchanged.

    Burning an ID: write a tombstone `Retired/PLAN-<ID>_BURNED_<slug>.md`
    carrying the reason. The allocator refuses the ID by the ordinary filename
    scan, with no special case; the marker only changes how `--explain` labels
    it. See `_BURNED_RE` below and the PLAN Identity Policy in
    write-plan/references/plan-conventions.md.

For PLAN:
    Allocates IDs in the AA0-ZZ9 scheme (6,760 slots, lexicographic order):
    AA0 -> AA1 -> ... -> AA9 -> AB0 -> ... -> AZ9 -> BA0 -> ... -> ZZ9.

    Source of truth for "used IDs": **the filesystem, and only the filesystem**
    - Workbench/ (flat) + Retired/ (recursive, since rolled-over PLANs nest in
    per-month subdirectories). Authoritative since PLAN-AB9 D2 (2026-05-23);
    sole source since PLAN-AD2 W0.2 (2026-07-27), which removed the LOG Status
    Table fallback scan. See the note above _AA_TOTAL for why that scan could
    not affect allocation and was not replaced by a literal.

    used = fs_ids

    Silent on success. `--explain` is the only path that writes per-ID lines
    to stderr. Before W0.2 this module emitted 48 stderr lines on a routine
    invocation of the live tree, 46 of which described expected conditions;
    that volume is what made the two real ones invisible.

    Calling-contract (Postgres nextval template, decision C4):
    The allocator is NOT idempotent across calls. Calling `python next_id.py
    PLAN` twice without an intervening PLAN-file write returns the same ID both
    times, because the filesystem does not change between calls. Batch callers
    must write (or at minimum touch) each PLAN file before drawing the next ID.

    Disjoint-namespace invariant:
    Numeric IDs (PLAN-001..PLAN-037, historical and frozen) and AA-form IDs
    (PLAN-AA0..ZZ9, active) coexist in the used-ID set. The allocator returns
    from the AA-form space for PLAN; numeric IDs are counted but cannot perturb
    AA-form allocation, since the two occupy separate slot-spaces. This is why
    dropping the LOG scan is safe: everything it contributed was numeric-form.

For ADVICE / RESEARCH:
    Numeric scheme retained (decision D3). Scans Workbench/ and Retired/ for
    matching filenames, computes max(NNN)+1, returns zero-padded 3-digit
    (4-digit when NNN>999) result. Independent of the PLAN path throughout.

Returns:
    Prints the next ID to stdout.
    Exits 1 with a message to stderr on exhaustion or unknown type.
"""

import argparse
import sys
import re
import pathlib

VALID_TYPES = {"PLAN", "ADVICE", "RESEARCH"}

# Regex to extract bare IDs from PLAN filenames.
# Matches both AA-form (PLAN-AA0) and historic numeric (PLAN-001, PLAN-0029).
# Group 1 is the bare ID portion (e.g. "AA0" or "029").
_LOG_ID_RE = re.compile(r"PLAN-([A-Z]{2}[0-9]|\d{3,4})")

# Tombstone marker. A PLAN ID can be retired without ever owning a file - the
# work it named was reverted, or the ID was drawn and abandoned. Prose recording
# the burn is invisible to a filename-derived allocator, so the burn is recorded
# as a file instead: `Retired/PLAN-<ID>_BURNED_<slug>.md`, carrying the reason.
#
# The allocator needs no special case to honour it. The tombstone matches the
# same `PLAN-*.md` glob and the same ID regex as any retired PLAN, so the ID is
# already in the used set. The marker exists so `--explain` can say *why* an ID
# is skipped, which is the difference between an operator trusting the table and
# re-deriving it by hand.
_BURNED_RE = re.compile(r"_BURNED(?:_|\.)")

# NOTE (PLAN-AD2 W0.2, 2026-07-27): there is deliberately no LOG scan here.
#
# Until 2026-07-27 this module walked every monthly LOG, anchored on the Status
# Table header, and unioned any ID found there into the used set as a
# defence-in-depth fallback. That scan was removed because it could not affect
# allocation. The only IDs it contributed beyond the filesystem were numeric-form
# historical ones (PLAN-001 .. PLAN-037); `next_aa_id` issues AA-form only
# (AA0-ZZ9) and `next_numeric_id` scans the filesystem directly for ADVICE and
# RESEARCH, so the two ID spaces are disjoint by construction. No protection is
# lost by removing it, and none needs to be re-added as a literal - a constant
# listing this repo's history would be inert here and wrong in a consumer's
# clone, since next_id.py ships in the bundle.
#
# The scan also could not begin to matter: it read only the Status Table, which
# was removed from the monthly LOG on 2026-06-01 (PLAN-AB9 D3), so its input is
# closed. Historical numeric IDs remain frozen per the PLAN Identity Policy -
# that policy is enforced by their files existing under Retired/, not by a scan.

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

    Workbench/ is flat. Retired/ nests rolled-over artefacts - PLAN files and
    month-end LOGs - in per-month subdirectories, so it is scanned recursively.
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
    Return (workbench_ids, retired_ids) - disjoint PLAN-ID sets keyed by
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


def glob_burned_ids(repo_root: pathlib.Path) -> "set[str]":
    """
    Return the set of PLAN IDs whose only file is a burn tombstone.

    A tombstone is any `PLAN-*.md` under Workbench/ or Retired/ whose filename
    carries the `_BURNED` marker. These IDs are already in the used set by the
    ordinary filename scan; this function exists only so `--explain` can label
    them, so it never widens what the allocator refuses.
    """
    ids: set[str] = set()
    for f in iter_repo_files(repo_root, "PLAN-*.md"):
        if not _BURNED_RE.search(f.name):
            continue
        m = _LOG_ID_RE.search(f.name)
        if m:
            ids.add(m.group(1))
    return ids


def compute_used_ids(repo_root: pathlib.Path, verbose: bool = False) -> "set[str]":
    """
    Return the set of used PLAN IDs, read from the filesystem alone.

    Post-PLAN-AB9 D2 (2026-05-23) the filesystem (Workbench/ + Retired/,
    the latter scanned recursively) is the authoritative source. Post-PLAN-AD2
    W0.2 (2026-07-27) it is the *only* source - see the module-level note on
    why the LOG scan was removed rather than replaced.

    Silent by default. The former warn-and-union paths emitted 46 stderr lines
    per invocation, which buried genuine warnings, and both described conditions
    that are normal rather than exceptional:

      - fs_ids - log_ids ("filesystem PLAN with no LOG row") is the *expected*
        state for every PLAN authored since the slim-LOG cutover, because slim
        LOGs carry no Status Table row. 36 of 48 lines.
      - log_ids - fs_ids named historical numeric IDs that cannot be re-issued
        in any case. 10 of 48 lines.

    Pass verbose=True (wired to `--explain`) for a per-ID breakdown.
    """
    fs_ids = glob_filesystem_ids(repo_root)
    if verbose:
        print(
            f"note: {len(fs_ids)} PLAN ID(s) in use, all discovered on the filesystem "
            f"(Workbench/ + Retired/); no LOG is consulted",
            file=sys.stderr,
        )
    return fs_ids


# ---------------------------------------------------------------------------
# AA-form ID allocation
# ---------------------------------------------------------------------------

def next_aa_id(used: "set[str]") -> str:
    """
    Walk AA0, AA1, ..., ZZ9 and return the first ID not in used.
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
# Numeric allocation (ADVICE / RESEARCH - legacy behaviour preserved)
# ---------------------------------------------------------------------------

def next_numeric_id(type_token: str, repo_root: pathlib.Path) -> str:
    """
    Compute the next sequential numeric ID for ADVICE or RESEARCH.
    Scans Workbench/ and Retired/ (Retired/ recursively) for files matching
    <TYPE>-NNN_*.md, computes max(NNN)+1, returns zero-padded 3-digit
    (4-digit if >999) result.
    Returns "001" if no existing files of that type are found.
    No LOG-parsing - ADVICE/RESEARCH do not appear in the PLAN Status Table.
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
      Workbench - ID discovered in the flat Workbench/ scan.
      Retired   - ID discovered in the recursive Retired/ scan.
      Burned    - ID whose file is a `_BURNED` tombstone. Deliberately unused;
                  the ID is refused because the tombstone is on disk, not
                  because a PLAN ever owned it.
    Workbench takes precedence over Retired for any ID that appears in both
    (an unusual state - would indicate a half-retired PLAN). Burned takes
    precedence over either, since a tombstone is the more specific fact.
    """
    workbench_ids, retired_ids = glob_filesystem_ids_by_source(repo_root)
    burned_ids = glob_burned_ids(repo_root)

    labelled: list[tuple[str, str]] = []
    for plan_id in burned_ids:
        labelled.append((plan_id, "Burned"))
    for plan_id in workbench_ids - burned_ids:
        labelled.append((plan_id, "Workbench"))
    for plan_id in retired_ids - workbench_ids - burned_ids:
        labelled.append((plan_id, "Retired"))

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
             "source is one of: Workbench, Retired, Burned.",
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
            used = compute_used_ids(repo_root, verbose=args.explain)
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
