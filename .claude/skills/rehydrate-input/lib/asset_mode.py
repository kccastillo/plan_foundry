"""
asset_mode.py -- Asset-mode helpers for rehydrate-input (AC2c).

Implements the A1-A5 logic:
  A1. Validate asset frontmatter.
  A4. Write per-asset memory pointer file.
  A5. Stamp asset frontmatter (last_consulted + consulted_by append).

These are pure functions + file-writing utilities; the calling workflow
(rehydrate-input.md Step 1.a-asset) orchestrates them in order.

S4 atomicity ordering: A4 (memory write) runs BEFORE A5 (frontmatter mutation).
If A4 raises, A5 is never called -- clean-retry property preserved.
"""
import os
import re
import datetime
from pathlib import Path
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_ASSET_FIELDS = ("asset_id", "kind", "last_consulted", "consulted_by")
VALID_KINDS = {"reference", "helper"}
CONSULTED_BY_CAP = 20


# ---------------------------------------------------------------------------
# A1: Frontmatter validation
# ---------------------------------------------------------------------------


def validate_asset_frontmatter(frontmatter: dict, consuming_plan: Optional[str]) -> None:
    """Validate that an asset frontmatter dict meets the AC2c contract.

    Parameters
    ----------
    frontmatter : dict
        Parsed YAML frontmatter from the asset file.
    consuming_plan : str or None
        The PLAN-id supplied by the caller. Must not be None/empty in asset mode.

    Raises
    ------
    ValueError
        If any required field is missing, `kind` is invalid, or
        `consuming_plan` was not supplied.
    """
    for field in REQUIRED_ASSET_FIELDS:
        if field not in frontmatter:
            raise ValueError(
                f"asset frontmatter missing required field '{field}'. "
                "Check that the file follows the AD6 schema."
            )

    kind = frontmatter["kind"]
    if kind not in VALID_KINDS:
        raise ValueError(
            f"asset frontmatter 'kind' has unrecognised value '{kind}'. "
            f"Must be one of: {sorted(VALID_KINDS)}."
        )

    if not consuming_plan:
        raise ValueError(
            "asset mode requires 'consuming_plan'; supply via skill argument. "
            "Example: rehydrate asset <path> consuming_plan=PLAN-AE1"
        )


# ---------------------------------------------------------------------------
# Memory directory resolution
# ---------------------------------------------------------------------------


def resolve_memory_dir() -> Path:
    """Return the Claude auto-memory directory Path.

    Reads CLAUDE_PROJECT_MEMORY_DIR env var first (per S2/D3c).
    Falls back to the dev-only hardcoded path if not set.
    """
    env_val = os.environ.get("CLAUDE_PROJECT_MEMORY_DIR")
    if env_val:
        return Path(env_val)
    return Path(os.path.expanduser(
        "~/.claude/projects/D--projects-plan-foundry-dev/memory"
    ))


# ---------------------------------------------------------------------------
# A4: Write per-asset memory pointer file
# ---------------------------------------------------------------------------


def write_memory_file(
    asset_path: str,
    frontmatter: dict,
    consuming_plan: str,
    today: str,
    memory_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Write the per-asset memory pointer file to the Claude auto-memory dir.

    Parameters
    ----------
    asset_path : str
        Relative path to the asset from the repo root (used in the pointer).
    frontmatter : dict
        Parsed frontmatter of the asset file.
    consuming_plan : str
        The consuming PLAN-id (appended to consulted_by in the memory file).
    today : str
        ISO date string (YYYY-MM-DD) for Last consulted.
    memory_dir : Path or None
        Override memory directory (used in tests via CLAUDE_PROJECT_MEMORY_DIR).
        If None, resolved via resolve_memory_dir().

    Returns
    -------
    Path or None
        The absolute path to the written memory file, or None if the memory
        directory was unreachable (S2 degraded path -- caller surfaces warning).

    Raises
    ------
    IOError / OSError
        If the memory directory exists but the write fails. Caller must NOT
        proceed to A5 frontmatter mutation on this exception (S4 atomicity).
    """
    if memory_dir is None:
        memory_dir = resolve_memory_dir()

    if not memory_dir.exists():
        return None  # S2 degraded path -- caller surfaces warning

    asset_id = frontmatter.get("asset_id", "unknown")
    kind = frontmatter.get("kind", "unknown")
    title = frontmatter.get("title", asset_id)
    description = frontmatter.get("description", "")
    topic_tags = frontmatter.get("topic_tags", [])
    if isinstance(topic_tags, list):
        tags_str = ", ".join(str(t) for t in topic_tags)
    else:
        tags_str = str(topic_tags)

    # Build consulted_by list with the new consuming_plan appended (preview)
    existing = list(frontmatter.get("consulted_by") or [])
    if not existing or existing[-1] != consuming_plan:
        preview_consulted = existing + [consuming_plan]
    else:
        preview_consulted = existing
    consulted_str = ", ".join(str(x) for x in preview_consulted[-CONSULTED_BY_CAP:])

    memory_filename = f"reference_{asset_id}.md"
    memory_file = memory_dir / memory_filename

    content = (
        f"# {title} ({asset_id})\n"
        f"Path: {asset_path}\n"
        f"Kind: {kind}\n"
        f"Topic tags: {tags_str}\n"
        f"Last consulted: {today}\n"
        f"Consulted by (last 20): {consulted_str}\n"
        "\n"
        "---\n"
        "\n"
        f"Description: {description}\n"
    )

    memory_file.write_text(content, encoding="utf-8")
    return memory_file.resolve()


# ---------------------------------------------------------------------------
# A5: Stamp asset frontmatter
# ---------------------------------------------------------------------------


def stamp_asset_frontmatter(
    file_path: Path,
    consuming_plan: str,
    today: str,
) -> dict:
    """Update last_consulted and consulted_by on the asset file in-place.

    Parameters
    ----------
    file_path : Path
        Absolute path to the asset file.
    consuming_plan : str
        The PLAN-id to append to consulted_by.
    today : str
        ISO date string (YYYY-MM-DD) for last_consulted.

    Returns
    -------
    dict
        A dict with keys:
          - 'consulted_by_appended': bool -- whether consuming_plan was appended
          - 'consulted_by_evicted_oldest': bool -- whether FIFO eviction occurred

    Raises
    ------
    ValueError
        If the file cannot be parsed or frontmatter is missing.
    """
    raw = file_path.read_text(encoding="utf-8")

    # Split frontmatter from body
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Cannot parse frontmatter from {file_path}")

    fm_text = parts[1]
    body = parts[2]
    fm = yaml.safe_load(fm_text)

    if not isinstance(fm, dict):
        raise ValueError(f"Frontmatter is not a mapping in {file_path}")

    # Update last_consulted
    fm["last_consulted"] = today

    # Update consulted_by with idempotency + cap
    existing = list(fm.get("consulted_by") or [])
    appended = False
    evicted = False

    if not existing or existing[-1] != consuming_plan:
        existing.append(consuming_plan)
        appended = True
        if len(existing) > CONSULTED_BY_CAP:
            existing.pop(0)  # FIFO eviction of oldest
            evicted = True

    fm["consulted_by"] = existing

    # Reconstruct the file with updated frontmatter
    new_fm_text = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    new_raw = f"---\n{new_fm_text}---{body}"
    file_path.write_text(new_raw, encoding="utf-8")

    return {
        "consulted_by_appended": appended,
        "consulted_by_evicted_oldest": evicted,
    }
