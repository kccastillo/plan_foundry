"""
push_policy.py - plan_foundry push-policy resolver.

Exposes get_push_policy(plan_path, repo_root=None) -> str
returning "auto" or "manual".

Resolution order (first match wins):
  1. PLAN frontmatter field `push_policy` (per-PLAN override).
  2. Hard-coded default: "manual".

Valid values: "auto", "manual".
Any other value produces a warning on stderr, and resolution falls through
to "manual".

History (PLAN-AC4, D6/D6a): a project-default layer used to read a
top-level `push_policy` from the per-project marketplace config file that
PLAN-AC3 deleted during the bundle pivot. A git-log check on 2026-05-18
confirmed that the project-default field had only ever been set to
"manual" in tree, so the entire reader layer was collapsed into the
hard-coded default. The per-PLAN frontmatter override remains the only
escape hatch for individual PLANs that need automatic push.
"""

# ---
# asset_id: help-push-policy
# kind: helper
# title: Push Policy
# topic_tags: [push, policy, git, plan-pipeline]
# description: Push-policy resolver returning "auto" or "manual" for a given PLAN, consulted by plan-pipeline before pushing milestone commits.
# discoverable_via: [plan-pipeline, manual]
# created: 2026-05-26
# last_consulted: ""
# consulted_by: []
# schema_version: 1
# ---

import pathlib
import sys

_VALID = {"auto", "manual"}
_DEFAULT = "manual"


def _warn(msg: str) -> None:
    print(f"[push_policy] WARNING: {msg}", file=sys.stderr)


def _resolve_repo_root(plan_path: str, repo_root=None) -> pathlib.Path:
    """Return the repo root as a Path.

    When the caller supplies repo_root, return that path unchanged. Otherwise
    walk up from plan_path looking for a .git directory, and when no .git
    directory is found, return the directory containing plan_path.
    """
    if repo_root is not None:
        return pathlib.Path(repo_root)
    candidate = pathlib.Path(plan_path).resolve().parent
    while True:
        if (candidate / ".git").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            return pathlib.Path(plan_path).resolve().parent
        candidate = parent


def _read_frontmatter_field(plan_path: str, field: str):
    """Extract a scalar YAML frontmatter field value from a PLAN file.

    Returns the raw string value (stripped), or None when the field is absent
    or the read fails. Handles simple scalar fields only, not nested mappings
    or lists. Uses errors='replace' to handle non-UTF-8 bytes.
    """
    try:
        text = pathlib.Path(plan_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith(field + ":"):
            value = line[len(field) + 1:].strip()
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            return value if value else None
    return None


def get_push_policy(plan_path: str, repo_root=None) -> str:
    """Return the effective push policy for the given PLAN file.

    Args:
        plan_path: Absolute or relative path to the PLAN markdown file.
        repo_root: Optional repo root. When not supplied, detected by walking up
            to the nearest .git directory.

    Returns:
        "auto" or "manual".
    """
    _resolve_repo_root(plan_path, repo_root)

    # 1. Per-PLAN frontmatter override
    plan_value = _read_frontmatter_field(plan_path, "push_policy")
    if plan_value is not None:
        if plan_value in _VALID:
            return plan_value
        _warn(
            f"PLAN frontmatter push_policy={plan_value!r} is not a valid value "
            f"(expected one of {sorted(_VALID)}), so the default applies."
        )

    # 2. Hard-coded default
    return _DEFAULT
