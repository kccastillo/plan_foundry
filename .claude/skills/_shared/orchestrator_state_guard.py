"""
orchestrator_state_guard.py — Snapshot/restore helper for orchestrator-owned PLAN frontmatter fields.

PLAN-AF3 (2026-06-20): Closes BUG 3. A subagent (plan-writer, sufficiency-auditor,
plan-safety-auditor) must not be trusted to write orchestrator-owned frontmatter
fields. The orchestrator snapshots owned fields before dispatch and restores them
after, so any subagent-forged state is wiped before the orchestrator reads or acts
on frontmatter.

Owned-field set (D1 — "No-Trust-Subagent-State"):
    pipeline_phase, audit_state, last_executor_outcome, verification_state

Note: `status` is intentionally excluded from the guard — it is legitimately
executor-written and outside the BUG-3 forgery surface. Guarding it would risk
reverting a legitimate executor-set status.

D1a carve-out ("Orchestrator-Directed-Writes"): when the orchestrator deliberately
directs an owned-field value as part of the dispatch (e.g. plan-writer's
`target_phase` parameter), it MUST set that field in the snapshot dict to its
intended post-dispatch value *before* calling `restore_owned_fields`, so the restore
preserves the directed change while still wiping any other undirected owned-field
write.

No cross-skill imports (D2 — partial-install rationale).
"""

from __future__ import annotations

from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OWNED_FIELDS = (
    "pipeline_phase",
    "audit_state",
    "last_executor_outcome",
    "verification_state",
)

# Sentinel: distinguishes "field absent from frontmatter" from "field present with value None".
#
# RESEARCH-005 fix: this MUST be a value-stable, YAML-safe token, NOT a bare
# `object()`. A bare-object sentinel encodes its meaning purely in Python object
# identity, which does not survive a serialisation or module-reimport boundary.
# When the snapshot crossed such a boundary, `restore_owned_fields`'s `is`-check
# missed, the sentinel object was written into frontmatter, and `yaml.dump`
# serialised it as `!!python/object:builtins.object {}` — breaking the next
# helper's `safe_load`. A namespaced string survives persistence (round-trips
# through JSON/YAML) and reimport (compared by value), so restore always deletes
# an absent field instead of poisoning the file. Compared via `_is_absent` (==),
# never `is`.
_ABSENT = "__orchestrator_state_guard::ABSENT__"


def _is_absent(value: object) -> bool:
    """True when `value` is the absent-marker, compared by value (boundary-stable)."""
    return isinstance(value, str) and value == _ABSENT


# RESEARCH-005 direction 3 (belt-and-braces): the only owned-field value types
# that may be written back into frontmatter. Anything else (e.g. a stray
# object() sentinel that survived a boundary) is treated as absent/unknown and
# popped by restore_owned_fields, so it can never reach _write_frontmatter.
# safe_dump remains the loud backstop if a non-safe value somehow slips through.
_ALLOWED_OWNED_TYPES = (str, int, float, bool, dict, list)


def _is_yaml_safe_owned_value(value: object) -> bool:
    """True when `value` is None or one of the plain YAML-safe owned types."""
    return value is None or isinstance(value, _ALLOWED_OWNED_TYPES)


# ---------------------------------------------------------------------------
# Helpers: frontmatter read/write (mirrors audit_loop.py patterns exactly)
# ---------------------------------------------------------------------------

def _read_frontmatter_raw(plan_path: Path) -> tuple[str, str, str]:
    """
    Split a PLAN file into (pre_marker, frontmatter_text, body).
    pre_marker is '' (empty string before the first ---), frontmatter_text is
    between the two --- markers, body is the rest.
    Raises ValueError if frontmatter is missing or malformed.
    """
    text = plan_path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        raise ValueError(f"PLAN file has no frontmatter: {plan_path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"PLAN file frontmatter is malformed: {plan_path}")
    # parts[0] is empty string (before the first ---), parts[1] is the YAML, parts[2] is body
    return parts[0], parts[1], parts[2]


def _write_frontmatter(plan_path: Path, fm: dict, body: str) -> None:
    """Write updated frontmatter back to the PLAN file."""
    # safe_dump (not dump): refuses non-standard Python objects, so a stray
    # sentinel or object can never be serialised as a `!!python/object` tag that
    # would break the next safe_load (RESEARCH-005 defence-in-depth). For plain
    # scalars/dicts/lists the output is identical to yaml.dump.
    fm_text = yaml.safe_dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    new_text = f"---\n{fm_text}---{body}"
    plan_path.write_text(new_text, encoding="utf-8")


def _load_frontmatter(plan_path: Path) -> tuple[dict, str]:
    """
    Load PLAN frontmatter as a dict and return (fm_dict, body_text).
    body_text includes the leading newline after '---'.
    """
    _, fm_text, body = _read_frontmatter_raw(plan_path)
    fm = yaml.safe_load(fm_text) or {}
    return fm, body


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def snapshot_owned_fields(plan_path: str | Path) -> dict:
    """
    Read the PLAN file and return a snapshot dict mapping each name in
    OWNED_FIELDS to its current value, or to the sentinel _ABSENT when the
    field is not present in frontmatter.

    Args:
        plan_path: Path to the PLAN .md file.

    Returns:
        dict with exactly the keys in OWNED_FIELDS. Values are the current
        frontmatter value, or _ABSENT if the field is missing.

    Raises:
        ValueError: if the file has no frontmatter or malformed frontmatter.
    """
    plan_path = Path(plan_path)
    fm, _ = _load_frontmatter(plan_path)
    snapshot: dict = {}
    for field in OWNED_FIELDS:
        if field in fm:
            snapshot[field] = fm[field]
        else:
            snapshot[field] = _ABSENT
    return snapshot


def restore_owned_fields(plan_path: str | Path, snapshot: dict) -> None:
    """
    Re-read the current frontmatter of the PLAN file and overwrite ONLY the
    owned fields with the values from `snapshot`. For each key in OWNED_FIELDS:
    - If snapshot[key] is _ABSENT: delete the key from frontmatter (if present).
    - If snapshot[key] is present but not a YAML-safe owned value (not None/str/int/float/bool/dict/list): delete the key (treated as absent/unknown — RESEARCH-005 direction 3).
    - Otherwise: set frontmatter[key] = snapshot[key].

    All non-owned frontmatter fields and the body are preserved verbatim.

    Args:
        plan_path: Path to the PLAN .md file.
        snapshot:  dict returned by snapshot_owned_fields (keys = OWNED_FIELDS).

    Raises:
        ValueError: if the file has no frontmatter or malformed frontmatter.
    """
    plan_path = Path(plan_path)
    fm, body = _load_frontmatter(plan_path)
    for field in OWNED_FIELDS:
        value = snapshot.get(field, _ABSENT)
        # Pop when the value is the absent-marker OR is not a plain YAML-safe
        # scalar/container (RESEARCH-005 direction 3). Directed owned-field
        # writes (D1a) are always str/dict/list/scalar, so they pass unchanged;
        # only genuinely non-serialisable junk is dropped.
        if _is_absent(value) or not _is_yaml_safe_owned_value(value):
            fm.pop(field, None)
        else:
            fm[field] = value
    _write_frontmatter(plan_path, fm, body)
