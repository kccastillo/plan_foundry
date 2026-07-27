"""
list_reusable_assets.py - projection primitive for the unified asset registry (PLAN-AD6 / AC2a;
broadened walk + query API added in PLAN-AD9 / AC2b).

Walks ``references/`` and ``.claude/skills/_shared/`` (top-level only),
parses each file's asset frontmatter, and writes:

  - ``references/.registry.json`` - machine-readable projection
    (``{"schema_version": 1, "assets": [...]}``)
  - ``references/INDEX.md``       - human-readable markdown table

The broadened walk (AC2b D1b) discovers any ``.md`` or ``.py`` file in
``.claude/skills/_shared/`` whose parseable frontmatter contains
``asset_id:``.  Sub-directories (e.g. ``lib/``) are excluded because the
walk is non-recursive (top-level files only).

Frontmatter formats supported
-----------------------------
- Markdown files (``.md``): leading ``---``-fenced YAML block.
- Python files (``.py``): a leading-or-near-leading ``# ---`` /
  ``# ---`` block (each line prefixed with ``# `` or ``#``). The
  tolerant parser strips the comment prefix then feeds the body to
  ``yaml.safe_load`` (S3 mitigation).

CLI
---
``python list_reusable_assets.py`` (no args) or
``python list_reusable_assets.py regenerate`` - regenerate from the
discovery walk and any markdown files under ``references/``.

``python list_reusable_assets.py query --tags TAG1,TAG2`` - query by tags.
``python list_reusable_assets.py query --seed-file PATH`` - query by seed text.

The module also exposes ``main()``, ``query_by_tags()``,
``query_by_seed()``, and helper functions so that tests can drive it
directly without spawning a subprocess.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import yaml

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# AC2b D1b - walk scope = β.  Top-level files in _shared/ whose parseable
# frontmatter contains asset_id:.  Sub-directories (lib/) excluded by
# non-recursive iteration.
_SHARED_DIR = pathlib.Path(".claude/skills/_shared")

_REFERENCES_DIR = pathlib.Path("references")

# INDEX.md row fields, in render order.
_INDEX_FIELDS = ("asset_id", "kind", "title", "topic_tags", "last_consulted")


def _read_markdown_frontmatter(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    parts = text.split("---")
    if len(parts) < 3:
        raise ValueError(
            f"{path}: expected leading '---'-fenced YAML frontmatter; "
            f"got {len(parts)} '---' parts"
        )
    parsed = yaml.safe_load(parts[1])
    if not isinstance(parsed, dict):
        raise ValueError(
            f"{path}: frontmatter did not parse as a mapping "
            f"(got {type(parsed).__name__})"
        )
    return parsed


def _read_python_frontmatter(path: pathlib.Path) -> dict:
    """Tolerant '# ---' comment-block parser (S3 mitigation)."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    stripped: list[str] = []
    for line in lines:
        if line.startswith("# "):
            stripped.append(line[2:])
        elif line.startswith("#"):
            stripped.append(line[1:])
    body = "\n".join(stripped)
    parts = body.split("---")
    if len(parts) < 2:
        raise ValueError(
            f"{path}: expected '# ---' comment-block frontmatter; none found"
        )
    # parts[0] is whatever leading comments preceded the first '---';
    # the frontmatter body is parts[1].
    parsed = yaml.safe_load(parts[1])
    if not isinstance(parsed, dict):
        raise ValueError(
            f"{path}: frontmatter did not parse as a mapping "
            f"(got {type(parsed).__name__})"
        )
    return parsed


def _read_frontmatter(path: pathlib.Path) -> dict:
    if path.suffix == ".py":
        return _read_python_frontmatter(path)
    return _read_markdown_frontmatter(path)


def _iter_helper_paths(repo_root: pathlib.Path):
    """Yield top-level _shared/ files whose frontmatter contains asset_id:.

    AC2b D1b walk-scope: non-recursive so lib/ (test scaffolding) is
    automatically excluded.  Files are yielded in sorted-name order for
    determinism.  Silently skips files that do not parse or lack asset_id.
    """
    shared = repo_root / _SHARED_DIR
    if not shared.is_dir():
        return
    for p in sorted(shared.iterdir()):
        if not p.is_file():
            continue
        if p.suffix not in (".md", ".py"):
            continue
        try:
            fm = _read_frontmatter(p)
        except Exception:
            continue
        if "asset_id" in fm:
            yield p


def _iter_reference_paths(repo_root: pathlib.Path):
    refs = repo_root / _REFERENCES_DIR
    if not refs.is_dir():
        return
    for p in sorted(refs.iterdir()):
        if p.is_file() and p.suffix == ".md" and p.name != "INDEX.md":
            yield p


def collect_assets(repo_root: pathlib.Path | None = None) -> list[dict]:
    """Walk _shared/ helpers and references/ dir, returning parsed frontmatter.

    AC2b: replaces the hardcoded _HELPER_PATHS tuple with _iter_helper_paths()
    (frontmatter-driven discovery, D1b).
    """
    repo_root = (repo_root or _REPO_ROOT).resolve()
    assets: list[dict] = []

    for helper_path in _iter_helper_paths(repo_root):
        fm = _read_frontmatter(helper_path)
        rel = helper_path.relative_to(repo_root)
        fm["__source_path"] = str(rel).replace("\\", "/")
        assets.append(fm)

    for ref_path in _iter_reference_paths(repo_root):
        fm = _read_frontmatter(ref_path)
        rel = ref_path.relative_to(repo_root)
        fm["__source_path"] = str(rel).replace("\\", "/")
        assets.append(fm)

    assets.sort(key=lambda a: a.get("asset_id", ""))
    return assets


def query_by_tags(
    tags: list[str],
    top_n: int = 5,
    min_overlap: int = 2,
    fallback_overlap: int = 1,
    repo_root: pathlib.Path | None = None,
) -> list[dict]:
    """Return up to top_n AssetPointers whose topic_tags overlap with tags.

    Ranking: overlap_count descending, then asset_id ascending.
    Fallback: if primary set (overlap >= min_overlap) has fewer than top_n
    AND fallback_overlap < min_overlap, top up with assets at fallback
    threshold (not already in primary), capped at top_n total.

    Returns pointers only (no description, no consulted_by, no body) per
    ADVICE-011 C1.  Pure - no writes, no side effects (D7b).

    AssetPointer keys: asset_id, title, topic_tags, last_consulted, path,
    overlap_count.
    """
    assets = collect_assets(repo_root)
    tag_set = set(tags)

    def _overlap(asset: dict) -> int:
        return len(tag_set & set(asset.get("topic_tags", [])))

    def _pointer(asset: dict, overlap_count: int) -> dict:
        return {
            "asset_id": asset.get("asset_id", ""),
            "title": asset.get("title", ""),
            "topic_tags": asset.get("topic_tags", []),
            "last_consulted": asset.get("last_consulted", ""),
            "path": asset.get("__source_path", ""),
            "overlap_count": overlap_count,
        }

    primary: list[dict] = []
    primary_ids: set[str] = set()
    for asset in assets:
        ov = _overlap(asset)
        if ov >= min_overlap:
            primary.append(_pointer(asset, ov))
            primary_ids.add(asset.get("asset_id", ""))

    # Sort primary: overlap desc, asset_id asc.
    primary.sort(key=lambda p: (-p["overlap_count"], p["asset_id"]))

    if len(primary) < top_n and fallback_overlap < min_overlap:
        for asset in assets:
            if asset.get("asset_id", "") in primary_ids:
                continue
            ov = _overlap(asset)
            if ov >= fallback_overlap:
                primary.append(_pointer(asset, ov))
        # Re-sort after extending with fallback entries.
        primary.sort(key=lambda p: (-p["overlap_count"], p["asset_id"]))

    return primary[:top_n]


def query_by_seed(
    seed_text: str,
    top_n: int = 5,
    min_overlap: int = 2,
    fallback_overlap: int = 1,
    repo_root: pathlib.Path | None = None,
) -> list[dict]:
    """Return up to top_n AssetPointers relevant to the seed text.

    Tokenises seed via re.split(r'\\W+', seed.lower()), intersects with the
    union of all known topic_tags across the registry; delegates to
    query_by_tags with the effective tag intersection.

    If the intersection is empty, returns [] - the workflow handles the
    delta-fallback question, not this function (D3b).

    Pure - no writes, no side effects (D7b).
    """
    tokens = {t for t in re.split(r"\W+", seed_text.lower()) if t}
    assets = collect_assets(repo_root)
    known_tags: set[str] = set()
    for asset in assets:
        known_tags.update(asset.get("topic_tags", []))
    effective_tags = list(tokens & known_tags)
    if not effective_tags:
        return []
    return query_by_tags(effective_tags, top_n, min_overlap, fallback_overlap, repo_root)


def _serialise_asset(asset: dict) -> dict:
    """Coerce non-JSON types (datetime.date) to strings for the registry."""
    out: dict = {}
    for k, v in asset.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def write_registry(assets: list[dict], repo_root: pathlib.Path | None = None) -> pathlib.Path:
    repo_root = (repo_root or _REPO_ROOT).resolve()
    path = repo_root / _REFERENCES_DIR / ".registry.json"
    payload = {
        "schema_version": 1,
        "assets": [_serialise_asset(a) for a in assets],
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def write_index(assets: list[dict], repo_root: pathlib.Path | None = None) -> pathlib.Path:
    repo_root = (repo_root or _REPO_ROOT).resolve()
    path = repo_root / _REFERENCES_DIR / "INDEX.md"
    lines = [
        "# Reusable Asset Index",
        "",
        "This file is regenerated by `.claude/skills/_shared/list_reusable_assets.py`. Do not hand-edit.",
        "",
        "| " + " | ".join(_INDEX_FIELDS) + " |",
        "|" + "|".join("---" for _ in _INDEX_FIELDS) + "|",
    ]
    if not assets:
        lines.append("| " + " | ".join("" for _ in _INDEX_FIELDS) + " |")
    for a in assets:
        cells = []
        for field in _INDEX_FIELDS:
            v = a.get(field, "")
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            elif hasattr(v, "isoformat"):
                v = v.isoformat()
            cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _format_markdown(pointers: list[dict]) -> str:
    """Format AssetPointers as a markdown table block.

    Returns empty string (silent-on-zero per D5b) when pointers is empty.
    """
    if not pointers:
        return ""
    n = len(pointers)
    header = f"### Possibly relevant reusable assets ({n} match{'es' if n != 1 else ''})\n"
    sep = "\n"
    col_header = "| asset_id | title | topic_tags | last_consulted | path |"
    col_sep = "|---|---|---|---|---|"
    rows = []
    for p in pointers:
        tags_str = ", ".join(p.get("topic_tags") or [])
        rows.append(
            f"| {p['asset_id']} | {p['title']} | {tags_str} | {p['last_consulted']} | {p['path']} |"
        )
    return header + sep + col_header + "\n" + col_sep + "\n" + "\n".join(rows) + "\n"


def main(repo_root: pathlib.Path | None = None) -> int:
    """Default regenerate action (backwards-compatible entry point)."""
    assets = collect_assets(repo_root)
    write_registry(assets, repo_root)
    write_index(assets, repo_root)
    print(f"Wrote {len(assets)} assets to references/.registry.json and INDEX.md")
    return 0


def _cli_main(argv: list[str] | None = None) -> int:  # noqa: C901
    """Full argparse CLI entry point (AC2b Step 5).

    Subcommands:
      regenerate  - rebuild registry + INDEX (existing behaviour).
      query       - query by tags or seed file.

    Backwards compat: calling with no args defaults to regenerate.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import argparse

    parser = argparse.ArgumentParser(
        prog="list_reusable_assets",
        description="Reusable-asset registry tool (plan_foundry AC2b).",
    )
    sub = parser.add_subparsers(dest="subcommand")

    # regenerate subcommand
    sub.add_parser("regenerate", help="Rebuild .registry.json and INDEX.md (default).")

    # query subcommand
    qp = sub.add_parser("query", help="Query the registry by tags or seed file.")
    mx = qp.add_mutually_exclusive_group(required=True)
    mx.add_argument(
        "--tags",
        metavar="TAG1,TAG2,...",
        help="Comma-separated tags to match.",
    )
    mx.add_argument(
        "--seed-file",
        metavar="PATH",
        help="Path to a file containing seed text; avoids shell quoting hazards (S5).",
    )
    qp.add_argument("--top-n", type=int, default=5, metavar="N", help="Max results (default 5).")
    qp.add_argument(
        "--min-overlap", type=int, default=2, metavar="N", help="Min tag-overlap threshold (default 2)."
    )
    qp.add_argument(
        "--fallback-overlap",
        type=int,
        default=1,
        metavar="N",
        help="Fallback overlap threshold when primary set < top-n (default 1).",
    )
    qp.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown).",
    )

    args = parser.parse_args(argv)

    # Default: no subcommand -> regenerate.
    if args.subcommand is None or args.subcommand == "regenerate":
        return main()

    # query subcommand
    if args.subcommand == "query":
        if args.tags is not None:
            tag_list = [t.strip() for t in args.tags.split(",") if t.strip()]
            pointers = query_by_tags(
                tag_list,
                top_n=args.top_n,
                min_overlap=args.min_overlap,
                fallback_overlap=args.fallback_overlap,
            )
        else:
            seed_path = pathlib.Path(args.seed_file)
            seed_text = seed_path.read_text(encoding="utf-8", errors="replace")
            pointers = query_by_seed(
                seed_text,
                top_n=args.top_n,
                min_overlap=args.min_overlap,
                fallback_overlap=args.fallback_overlap,
            )

        if args.format == "json":
            print(json.dumps(pointers, indent=2))
        else:
            # markdown: silent-on-zero (D5b).
            output = _format_markdown(pointers)
            if output:
                print(output, end="")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())
