#!/usr/bin/env python3
"""
migrate_plan_ids.py - one-shot migration from timestamp-prefixed plan IDs
to type-prefixed sequential IDs (TYPE-NNN_slug.md).

Usage:
    python migrate_plan_ids.py [--dry-run | --apply] [--workbench DIR] [--retired DIR]

Modes:
    --dry-run   (default) print planned moves and content-change counts; no filesystem changes.
    --apply     execute renames and content rewrites.

Order of operations (strict):
    (a) Scan all files, parse frontmatter, build rename map + friendly-form map.
    (b) Build sibling-file move list (.audit/, .ideate-critique/).
    (c) Perform ALL content rewrites (passes 1-4).
    (d) Perform ALL os.rename calls last (PLAN files + sibling files).

Four rewrite passes:
    Pass 1: full stems (\d{12}_(PLAN|ADVICE|RESEARCH)_slug) in all .md files
    Pass 2: LOG status-table bare 12-digit cells (LOG files only)
    Pass 3: friendly forms "PLAN 202605121430" in all .md files (excl. naming-convention.md)
    Pass 4: JSON sibling file internals (.audit/*.json, .ideate-critique/*.json)

Idempotency: re-running --apply on already-migrated files is a no-op.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Matches old-format stems: 202604191430_PLAN_slug-here
OLD_STEM_RE = re.compile(r"\b(\d{12})_(PLAN|ADVICE|RESEARCH)_([a-zA-Z0-9-]+)\b")

# Matches new-format filenames (already migrated)
NEW_FORMAT_RE = re.compile(r"^(PLAN|ADVICE|RESEARCH)-\d{3,4}_")

# Matches LOG filenames
LOG_RE = re.compile(r"_LOG_")

# Matches "PLAN 202605121430" style friendly forms
FRIENDLY_RE = re.compile(r"\b(PLAN|ADVICE|RESEARCH)\s+(\d{12})\b")

# Bare 12-digit number for LOG table cell detection
BARE_12_DIGIT_RE = re.compile(r"^\s*(\d{12})\s*$")

# LOG header keywords that indicate an ID column
LOG_ID_HEADER_KEYWORDS = {"id", "plan id", "plan", "plan-id"}

# FILES to skip for pass 3 (naming-convention.md at any path)
NAMING_CONVENTION_BASENAME = "naming-convention.md"


# ---------------------------------------------------------------------------
# Scanning and map building
# ---------------------------------------------------------------------------

def parse_frontmatter_type(text: str) -> str | None:
    """Extract 'type:' field from YAML frontmatter. Returns lowercase string or None."""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    for line in m.group(1).splitlines():
        if line.startswith("type:"):
            val = line.split(":", 1)[1].strip().strip('"').strip("'").lower()
            return val
    return None


def is_migratable(path: Path) -> bool:
    """True if this file should be considered for renaming (old timestamp-format PLAN/ADVICE/RESEARCH)."""
    name = path.name
    # Skip LOG files
    if LOG_RE.search(name):
        return False
    # Skip already new-format
    if NEW_FORMAT_RE.match(name):
        return False
    # Skip gitkeep, INDEX, etc.
    if name in (".gitkeep", "INDEX.md"):
        return False
    # Must match old timestamp pattern
    m = re.match(r"^(\d{12})_(PLAN|ADVICE|RESEARCH)_[a-zA-Z0-9-]+\.md$", name)
    return m is not None


def build_rename_map(workbench: Path, retired: Path):
    """
    Scan both dirs, collect migratable files, assign sequential IDs per type
    (chronological by timestamp prefix), and return:
      - rename_map: {old_stem: new_stem}
      - friendly_map: {12-digit-ts: "TYPE-NNN"}  (for pass-3 lookups)
      - files_by_type_count: for summary
    """
    # Collect all migratable files across both dirs
    all_files = []
    for directory in [workbench, retired]:
        if not directory.is_dir():
            continue
        for p in directory.glob("*.md"):
            if is_migratable(p):
                all_files.append(p)

    # Parse type from frontmatter (fallback: from filename)
    def get_type(p: Path) -> str:
        text = p.read_text(encoding="utf-8", errors="replace")
        fm_type = parse_frontmatter_type(text)
        if fm_type in ("plan", "advice", "research"):
            return fm_type.upper()
        # Fallback: extract from filename
        m = re.match(r"^\d{12}_(PLAN|ADVICE|RESEARCH)_", p.name)
        if m:
            return m.group(1)
        return "PLAN"

    # Group by type, sort chronologically by timestamp prefix
    by_type: dict[str, list[Path]] = {"PLAN": [], "ADVICE": [], "RESEARCH": []}
    for p in all_files:
        t = get_type(p)
        if t in by_type:
            by_type[t].append(p)
        else:
            by_type["PLAN"].append(p)

    for t in by_type:
        by_type[t].sort(key=lambda p: p.name)  # lexicographic = chronological for timestamp prefix

    rename_map: dict[str, str] = {}   # old_stem -> new_stem
    friendly_map: dict[str, str] = {}  # "202605121430" -> "PLAN-005"

    for t, files in by_type.items():
        for idx, p in enumerate(files, start=1):
            width = 4 if idx > 999 else 3
            num_str = str(idx).zfill(width)
            old_m = re.match(r"^(\d{12})_(PLAN|ADVICE|RESEARCH)_([a-zA-Z0-9-]+)\.md$", p.name)
            if not old_m:
                continue
            timestamp = old_m.group(1)
            slug = old_m.group(3)
            old_stem = f"{timestamp}_{t}_{slug}"
            new_stem = f"{t}-{num_str}_{slug}"
            rename_map[old_stem] = new_stem
            # Build friendly map: "202605121430" -> "PLAN-005"
            friendly_map[timestamp] = f"{t}-{num_str}"

    return rename_map, friendly_map


# ---------------------------------------------------------------------------
# Sibling-file discovery
# ---------------------------------------------------------------------------

def build_sibling_moves(workbench: Path, rename_map: dict[str, str]) -> list[tuple[Path, Path]]:
    """
    Find .audit/ and .ideate-critique/ JSON files whose stem prefix matches an old stem.
    Returns list of (old_path, new_path) tuples.
    """
    moves = []
    for subdir_name in [".audit", ".ideate-critique"]:
        subdir = workbench / subdir_name
        if not subdir.is_dir():
            continue
        for json_file in subdir.glob("*.json"):
            for old_stem, new_stem in rename_map.items():
                # sibling name pattern: <old_stem>-N.json
                prefix = old_stem + "-"
                if json_file.name.startswith(prefix):
                    suffix = json_file.name[len(prefix):]  # e.g. "1.json"
                    new_name = f"{new_stem}-{suffix}"
                    new_path = subdir / new_name
                    moves.append((json_file, new_path))
                    break
    return moves


# ---------------------------------------------------------------------------
# Rewrite helpers
# ---------------------------------------------------------------------------

def apply_pass1(text: str, rename_map: dict[str, str]) -> tuple[str, int]:
    """Pass 1: replace full old stems in .md content."""
    count = 0

    def replacer(m: re.Match) -> str:
        nonlocal count
        ts = m.group(1)
        t = m.group(2)
        slug = m.group(3)
        old_stem = f"{ts}_{t}_{slug}"
        new_stem = rename_map.get(old_stem)
        if new_stem:
            count += 1
            return new_stem
        return m.group(0)

    new_text = OLD_STEM_RE.sub(replacer, text)
    return new_text, count


def find_id_column_index(header_line: str) -> int | None:
    """Given a pipe-delimited header row, find the column index (0-based) of the ID column."""
    cells = [c.strip().lower() for c in header_line.split("|")]
    for i, cell in enumerate(cells):
        if cell in LOG_ID_HEADER_KEYWORDS:
            return i
    return None


def apply_pass2(text: str, friendly_map: dict[str, str]) -> tuple[str, int]:
    """
    Pass 2: update LOG status-table cells containing bare 12-digit IDs.
    Only runs on text from LOG files.
    """
    count = 0
    lines = text.splitlines(keepends=True)
    new_lines = []
    id_col_idx: int | None = None
    in_table = False

    for line in lines:
        stripped = line.rstrip("\n").rstrip("\r")
        if stripped.startswith("|"):
            if not in_table:
                # Potential header row
                col_idx = find_id_column_index(stripped)
                if col_idx is not None:
                    id_col_idx = col_idx
                    in_table = True
                new_lines.append(line)
                continue
            # We're in a table with a known ID column
            if id_col_idx is None:
                new_lines.append(line)
                continue
            # Parse cells
            cells = stripped.split("|")
            if id_col_idx < len(cells):
                cell = cells[id_col_idx]
                m = BARE_12_DIGIT_RE.match(cell)
                if m:
                    ts = m.group(1)
                    new_id = friendly_map.get(ts)
                    if new_id:
                        # Preserve surrounding whitespace
                        leading = len(cell) - len(cell.lstrip())
                        trailing = len(cell) - len(cell.rstrip())
                        cells[id_col_idx] = " " * leading + new_id + " " * trailing
                        count += 1
            new_lines.append("|".join(cells) + ("\n" if line.endswith("\n") else ""))
            continue
        else:
            if in_table:
                in_table = False
                id_col_idx = None
            new_lines.append(line)

    return "".join(new_lines), count


def apply_pass3(text: str, friendly_map: dict[str, str]) -> tuple[str, int]:
    """
    Pass 3: replace friendly forms "PLAN 202605121430" with "PLAN-005" etc.
    """
    count = 0

    def replacer(m: re.Match) -> str:
        nonlocal count
        t = m.group(1)
        ts = m.group(2)
        new_id = friendly_map.get(ts)
        if new_id:
            # new_id is already "TYPE-NNN"; the leading TYPE from friendly_map matches
            count += 1
            return new_id
        return m.group(0)

    new_text = FRIENDLY_RE.sub(replacer, text)
    return new_text, count


def apply_pass4_json(json_path: Path, rename_map: dict[str, str], dry_run: bool) -> int:
    """
    Pass 4: update string fields inside a JSON sibling file that contain old-format stems.
    Returns number of fields updated.
    """
    try:
        raw = json_path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw)
    except Exception as e:
        print(f"  [pass-4] WARN: could not parse {json_path}: {e}", file=sys.stderr)
        return 0

    count = 0

    def update_value(v):
        nonlocal count
        if not isinstance(v, str):
            return v
        new_v = OLD_STEM_RE.sub(
            lambda m: (
                rename_map.get(f"{m.group(1)}_{m.group(2)}_{m.group(3)}", m.group(0))
            ),
            v,
        )
        if new_v != v:
            count += 1
        return new_v

    def walk_obj(obj):
        if isinstance(obj, dict):
            return {k: walk_obj(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [walk_obj(item) for item in obj]
        elif isinstance(obj, str):
            return update_value(obj)
        return obj

    new_data = walk_obj(data)
    if count > 0 and not dry_run:
        json_path.write_text(json.dumps(new_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return count


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def find_repo_root_from_workbench(workbench: Path) -> Path:
    """
    Derive repo root from the workbench path.
    The workbench dir itself is expected to be named 'Workbench' inside the repo root,
    or its parent is the repo root.
    Falls back to walking up from the script location.
    """
    # If workbench is named "Workbench", its parent is the repo root
    if workbench.name == "Workbench" and workbench.is_dir():
        return workbench.parent
    # Try walking up from the script
    script_dir = Path(__file__).resolve().parent
    for candidate in [script_dir] + list(script_dir.parents):
        if (candidate / "Workbench").is_dir():
            return candidate
    return workbench.parent


def collect_md_files(workbench: Path, retired: Path, repo_root: Path | None = None) -> list[Path]:
    """
    Collect all .md files across the repo for content rewriting.
    If repo_root is provided, use it directly. Otherwise derive from workbench path.
    Excludes .git/, .audit/ directories.
    """
    if repo_root is None:
        repo_root = find_repo_root_from_workbench(workbench)

    files = set()
    for p in repo_root.rglob("*.md"):
        if ".git" in p.parts:
            continue
        if ".audit" in p.parts:
            continue
        files.add(p)
    return sorted(files)


def run_migration(workbench: Path, retired: Path, dry_run: bool, repo_root: Path | None = None):
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
    print(f"Workbench: {workbench}")
    print(f"Retired:   {retired}")
    print()

    # Derive repo root for broad .md content scan
    if repo_root is None:
        repo_root = find_repo_root_from_workbench(workbench)

    # ---------------------------------------------------------------------------
    # (a) Scan and build maps
    # ---------------------------------------------------------------------------
    print("Scanning files and building rename map...")
    rename_map, friendly_map = build_rename_map(workbench, retired)

    if not rename_map:
        print("No files to migrate (all files already in new format or no PLAN/ADVICE/RESEARCH found).")
        print("Migration complete (no-op).")
        return

    print(f"  Found {len(rename_map)} file(s) to rename:")
    for old_stem, new_stem in sorted(rename_map.items()):
        print(f"    {old_stem}  ->  {new_stem}")
    print()

    # ---------------------------------------------------------------------------
    # (b) Build sibling-file move list
    # ---------------------------------------------------------------------------
    sibling_moves = build_sibling_moves(workbench, rename_map)
    if sibling_moves:
        print(f"Sibling files to rename ({len(sibling_moves)}):")
        for old_p, new_p in sibling_moves:
            print(f"    {old_p.name}  ->  {new_p.name}")
        print()

    # ---------------------------------------------------------------------------
    # (c) Content rewrites
    # ---------------------------------------------------------------------------
    all_md_files = collect_md_files(workbench, retired, repo_root=repo_root)

    pass1_total = 0
    pass2_total = 0
    pass3_total = 0
    pass4_total = 0

    print("Pass 1: rewriting full stems in .md files...")
    for md_file in all_md_files:
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  WARN: could not read {md_file}: {e}", file=sys.stderr)
            continue
        new_text, n = apply_pass1(text, rename_map)
        if n > 0:
            pass1_total += n
            print(f"  [{n} replacements] {md_file}")
            if not dry_run:
                md_file.write_text(new_text, encoding="utf-8")

    print(f"  Pass 1 total: {pass1_total} replacement(s)")
    print()

    print("Pass 2: rewriting LOG status-table cells (LOG files only)...")
    for md_file in all_md_files:
        if not LOG_RE.search(md_file.name):
            continue
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  WARN: could not read {md_file}: {e}", file=sys.stderr)
            continue
        new_text, n = apply_pass2(text, friendly_map)
        if n > 0:
            pass2_total += n
            print(f"  [{n} cells] {md_file}")
            if not dry_run:
                md_file.write_text(new_text, encoding="utf-8")
        else:
            # Check if LOG has no recognised ID header - emit warning
            lines = text.splitlines()
            has_table = any(l.startswith("|") for l in lines)
            if has_table:
                # Try to find header
                found_header = False
                for l in lines:
                    if l.startswith("|"):
                        if find_id_column_index(l) is not None:
                            found_header = True
                            break
                if not found_header:
                    print(f"  WARN: {md_file.name}: table found but no recognised ID header column - skipping pass 2", file=sys.stderr)

    print(f"  Pass 2 total: {pass2_total} cell(s)")
    print()

    print("Pass 3: rewriting friendly forms 'TYPE TIMESTAMP' in .md files...")
    for md_file in all_md_files:
        if md_file.name == NAMING_CONVENTION_BASENAME:
            print(f"  [SKIP] {md_file} (naming-convention.md excluded from pass 3)")
            continue
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  WARN: could not read {md_file}: {e}", file=sys.stderr)
            continue
        new_text, n = apply_pass3(text, friendly_map)
        if n > 0:
            pass3_total += n
            print(f"  [{n} replacements] {md_file}")
            if not dry_run:
                md_file.write_text(new_text, encoding="utf-8")

    print(f"  Pass 3 total: {pass3_total} replacement(s)")
    print()

    print("Pass 4: rewriting JSON sibling file internals...")
    for subdir_name in [".audit", ".ideate-critique"]:
        subdir = workbench / subdir_name
        if not subdir.is_dir():
            continue
        for json_file in sorted(subdir.glob("*.json")):
            n = apply_pass4_json(json_file, rename_map, dry_run)
            if n > 0:
                pass4_total += n
                print(f"  [{n} field(s)] {json_file}")

    print(f"  Pass 4 total: {pass4_total} field(s)")
    print()

    # ---------------------------------------------------------------------------
    # (d) Rename files (LAST)
    # ---------------------------------------------------------------------------
    renamed = 0
    print("Renaming PLAN/ADVICE/RESEARCH files...")
    for old_stem, new_stem in sorted(rename_map.items()):
        # Find the actual file (could be in workbench or retired)
        for directory in [workbench, retired]:
            old_path = directory / f"{old_stem}.md"
            if old_path.exists():
                new_path = directory / f"{new_stem}.md"
                print(f"  {old_path.name}  ->  {new_path.name}")
                if not dry_run:
                    os.rename(old_path, new_path)
                renamed += 1
                break

    print()
    print("Renaming sibling files...")
    for old_p, new_p in sibling_moves:
        if old_p.exists():
            print(f"  {old_p.name}  ->  {new_p.name}")
            if not dry_run:
                os.rename(old_p, new_p)
        else:
            print(f"  SKIP (not found): {old_p}")

    print()
    print("=" * 60)
    print(f"Pass 1: rewrote {pass1_total} stem match(es).")
    print(f"Pass 2: rewrote {pass2_total} LOG table cell(s).")
    print(f"Pass 3: rewrote {pass3_total} friendly form(s).")
    print(f"Pass 4: rewrote {pass4_total} JSON field(s).")
    print(f"Renamed {renamed} plan file(s) + {len(sibling_moves)} sibling file(s).")
    if dry_run:
        print("DRY RUN - no filesystem changes made.")
    else:
        print("Migration complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Workbench/Retired plan IDs from timestamp-prefix to TYPE-NNN format."
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run", dest="dry_run", action="store_true", default=True,
        help="Print planned moves and change counts without modifying files (default)."
    )
    mode_group.add_argument(
        "--apply", dest="dry_run", action="store_false",
        help="Execute renames and content rewrites."
    )
    parser.add_argument(
        "--workbench", default="Workbench",
        help="Path to Workbench directory (default: Workbench)."
    )
    parser.add_argument(
        "--retired", default="Retired",
        help="Path to Retired directory (default: Retired)."
    )
    args = parser.parse_args()

    # Resolve paths relative to cwd
    workbench = Path(args.workbench).resolve()
    retired = Path(args.retired).resolve()

    if not workbench.is_dir():
        print(f"Error: Workbench directory not found: {workbench}", file=sys.stderr)
        sys.exit(1)

    run_migration(workbench, retired, dry_run=args.dry_run)
    sys.exit(0)


if __name__ == "__main__":
    main()
