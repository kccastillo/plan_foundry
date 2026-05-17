"""
push_policy.py — Plan-foundry push-policy resolver.

Exposes get_push_policy(plan_path, repo_root=None) -> str
returning "auto" or "manual".

Resolution order (first match wins):
  1. PLAN frontmatter field `push_policy` (per-PLAN override).
  2. `.claude-plugin/marketplace.json` top-level field `push_policy` (project default).
  3. Hard-coded default: "manual".

Valid values: "auto", "manual".
Any other value triggers a stderr warning and falls through to "manual".
"""

import json
import pathlib
import sys

_VALID = {"auto", "manual"}
_DEFAULT = "manual"


def _warn(msg: str) -> None:
    print(f"[push_policy] WARNING: {msg}", file=sys.stderr)


def _resolve_repo_root(plan_path: str, repo_root=None) -> pathlib.Path:
    """Return the repo root as a Path.

    If repo_root is supplied, use it directly.
    Otherwise, walk up from plan_path looking for a .git directory.
    Falls back to the directory of plan_path if no .git found.
    """
    if repo_root is not None:
        return pathlib.Path(repo_root)
    candidate = pathlib.Path(plan_path).resolve().parent
    while True:
        if (candidate / ".git").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            # Reached filesystem root — fall back to plan's directory
            return pathlib.Path(plan_path).resolve().parent
        candidate = parent


def _read_frontmatter_field(plan_path: str, field: str):
    """Extract a scalar YAML frontmatter field value from a PLAN file.

    Returns the raw string value (stripped), or None if not found or on error.
    Only handles simple scalar fields (not nested mappings or lists).
    Uses errors='replace' when opening the file to handle non-UTF-8 bytes.
    """
    try:
        text = pathlib.Path(plan_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Frontmatter is between the first pair of '---' lines.
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    in_front = False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith(field + ":"):
            value = line[len(field) + 1:].strip()
            # Strip surrounding quotes if present
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            return value if value else None
    return None


def _read_marketplace_field(repo_root: pathlib.Path, field: str):
    """Read a top-level field from .claude-plugin/marketplace.json.

    Returns the string value, or None if the file is missing, malformed,
    or the field is absent.
    Uses errors='replace' to handle non-UTF-8 bytes.
    """
    mp_path = repo_root / ".claude-plugin" / "marketplace.json"
    try:
        text = mp_path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(text)
        value = data.get(field)
        return str(value).strip() if value is not None else None
    except (OSError, json.JSONDecodeError):
        return None


def get_push_policy(plan_path: str, repo_root=None) -> str:
    """Return the effective push policy for the given PLAN file.

    Args:
        plan_path: Absolute or relative path to the PLAN markdown file.
        repo_root: Optional repo root (pathlib.Path or str).
                   Auto-detected via .git walk if not supplied.

    Returns:
        "auto" or "manual".
    """
    root = _resolve_repo_root(plan_path, repo_root)

    # 1. Per-PLAN frontmatter override
    plan_value = _read_frontmatter_field(plan_path, "push_policy")
    if plan_value is not None:
        if plan_value in _VALID:
            return plan_value
        _warn(
            f"PLAN frontmatter push_policy={plan_value!r} is not a valid value "
            f"(expected one of {sorted(_VALID)}). Falling through to marketplace.json."
        )

    # 2. Project default from marketplace.json
    mp_value = _read_marketplace_field(root, "push_policy")
    if mp_value is not None:
        if mp_value in _VALID:
            return mp_value
        _warn(
            f"marketplace.json push_policy={mp_value!r} is not a valid value "
            f"(expected one of {sorted(_VALID)}). Using default."
        )

    # 3. Hard-coded default
    return _DEFAULT
