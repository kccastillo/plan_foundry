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
_ABSENT = object()


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
    fm_text = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
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
        if value is _ABSENT:
            fm.pop(field, None)
        else:
            fm[field] = value
    _write_frontmatter(plan_path, fm, body)
