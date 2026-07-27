"""
merge_settings.py — shared helper for init-plan-foundry and plan-foundry-sync.

Exposes:
  merge_bundle_settings(target_settings_path, fragment_path) -> dict

Idempotent, non-clobbering deep-merge of a bundle settings fragment into a
consumer project's settings.json. For each list under permissions.* (e.g.
deny, allow), the fragment's entries are appended only if not already present
(order preserved, no duplicates). Any missing keys/objects are created. The
hooks block and all other consumer entries are never touched.

Design rationale: PLAN-AH2. The bundle declares its required settings entries
in a single fragment (bundle-settings.json) under _shared/, and this helper
merges them non-destructively into the consumer's settings.json. Running the
merge twice is a no-op.

Importable as:
  import merge_settings                       (when _shared/ is on sys.path)
  import importlib.util; ...spec_from_file_location(...)  (direct file path)
"""

from __future__ import annotations

import json
import pathlib
from typing import Any


def _deep_merge_permissions(base: dict, fragment: dict) -> tuple[list[str], list[str]]:
    """Merge fragment['permissions'] into base['permissions'] in-place.

    For each key under permissions (e.g. 'deny', 'allow'), union the
    fragment's list into the base's list — append entries that are not
    already present, preserve order, no duplicates.

    Returns (entries_added, entries_already_present).
    """
    entries_added: list[str] = []
    entries_already_present: list[str] = []

    frag_perms = fragment.get("permissions", {})
    if not frag_perms:
        return entries_added, entries_already_present

    if "permissions" not in base:
        base["permissions"] = {}

    base_perms = base["permissions"]

    for key, frag_list in frag_perms.items():
        if not isinstance(frag_list, list):
            continue
        if key not in base_perms:
            base_perms[key] = []
        base_list = base_perms[key]
        if not isinstance(base_list, list):
            # Consumer has a non-list value — skip, do not clobber.
            continue
        existing_set = set(base_list)
        for entry in frag_list:
            if entry in existing_set:
                entries_already_present.append(f"permissions.{key}: {entry}")
            else:
                base_list.append(entry)
                existing_set.add(entry)
                entries_added.append(f"permissions.{key}: {entry}")

    return entries_added, entries_already_present


def merge_bundle_settings(
    target_settings_path: "str | pathlib.Path",
    fragment_path: "str | pathlib.Path",
) -> dict[str, Any]:
    """Merge a bundle settings fragment into the consumer's settings.json.

    Reads target_settings_path as JSON (encoding='utf-8', errors='replace').
    Missing, empty, or unparseable target is treated as {} (logged in the
    returned report — does not raise).

    Reads fragment_path as JSON. For each list under permissions.*, appends
    fragment entries not already in the target list (union, no duplicates,
    order preserved). Never removes, reorders, or mutates pre-existing
    consumer entries or unrelated keys (hooks, etc.).

    Writes the merged result back to target_settings_path with 2-space indent
    and a trailing newline.

    Returns a report dict:
      {
        "target": str(target_settings_path),
        "fragment": str(fragment_path),
        "target_precursor": "present" | "absent" | "empty" | "unparseable",
        "entries_added": [...],
        "entries_already_present": [...],
        "changed": bool,
      }
    """
    target_path = pathlib.Path(target_settings_path)
    fragment_path = pathlib.Path(fragment_path)

    # --- Read fragment (required; let exceptions propagate — misconfigured bundle) ---
    fragment: dict = json.loads(
        fragment_path.read_text(encoding="utf-8", errors="replace")
    )

    # --- Read target (missing/empty/unparseable → {}) ---
    target_precursor = "present"
    base: dict = {}
    if not target_path.exists():
        target_precursor = "absent"
    else:
        raw = target_path.read_text(encoding="utf-8", errors="replace")
        if not raw.strip():
            target_precursor = "empty"
        else:
            try:
                base = json.loads(raw)
            except json.JSONDecodeError:
                target_precursor = "unparseable"

    if not isinstance(base, dict):
        # Malformed root (e.g. JSON array) — treat as {}
        target_precursor = "unparseable"
        base = {}

    # --- Merge ---
    entries_added, entries_already_present = _deep_merge_permissions(base, fragment)

    changed = bool(entries_added)

    # --- Write (always write on first run or when changed; idempotent on re-run) ---
    # We write unconditionally when target was absent/empty/unparseable, or when
    # entries were added; skip the write only when target was already correct.
    if changed or target_precursor in ("absent", "empty", "unparseable"):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(base, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "target": str(target_path),
        "fragment": str(fragment_path),
        "target_precursor": target_precursor,
        "entries_added": entries_added,
        "entries_already_present": entries_already_present,
        "changed": changed,
    }
