"""
step_remap.py - Carry a step_renumber.py remap into fingerprint-keyed PLAN records.

PLAN-AJ1. The fingerprint formula (`audit_loop.py:148`, mirrored at
`build_brief.py:214`) concatenates `location` verbatim with no normalisation,
so an ordinal shift in the `## Steps` block moves the fingerprint of every
finding whose `location` was that ordinal - silently invalidating a human
acknowledgement, dispute, or override that pointed at it. This module
rewrites a single `location` string against a remap (`remap_location`), and
walks a PLAN's fingerprint-keyed frontmatter recomputing fingerprints for
every entry whose finding shifted (`remap_plan_fingerprints`).

Scope note: comma-joined ordinal lists in `location` (e.g. "Step 5, Step 6")
are deliberately returned unchanged rather than split, remapped and
re-joined. Splitting them invites re-joining them in a different form (a
different separator, reordering, a different "Step " capitalisation), and
any of those moves the fingerprint by itself - the exact failure mode this
module exists to prevent. A PLAN carrying such a location keeps a stale
fingerprint after a renumber; that is a narrower, already-declared gap, not
a silent one.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# remap_location
# ---------------------------------------------------------------------------

_BARE_ORDINAL_RE = re.compile(r'^(Step\s*)?(\d+)$', re.IGNORECASE)


def remap_location(location: str, remap: list[dict]) -> str:
    """
    Rewrite `location` only when the whole stripped string matches
    `^(?:Step\\s*)?(\\d+)$` (case-insensitive) and that ordinal appears as an
    "old" value in `remap`, preserving the original "Step " prefix and its
    spacing when present. Every other location - prose, a filename, a
    comma-joined list, an empty string - is returned unchanged.
    """
    if not location:
        return location

    match = _BARE_ORDINAL_RE.match(location.strip())
    if not match:
        return location

    prefix = match.group(1) or ""
    old_ordinal = int(match.group(2))

    for entry in remap:
        if entry.get("old") == old_ordinal:
            return f"{prefix}{entry['new']}"

    return location


# ---------------------------------------------------------------------------
# remap_plan_fingerprints
# ---------------------------------------------------------------------------

def _compute_fingerprint(finding: dict) -> str:
    """Same formula as audit_loop.py:148 - sha256(code|level|category|location)[:8]."""
    raw = (
        f"{finding.get('code', '')}|{finding.get('level', '')}|"
        f"{finding.get('category', '')}|{finding.get('location', '')}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


# Frontmatter list field -> the iteration field its entries carry. Only these
# three are fingerprint-keyed with a resolvable iteration. `audit_extracted`
# is deliberately excluded and never read: `apply_actions.py:172-177` writes
# only `fingerprint`, `did`, `extraction_date` and `child_plan_filename` (no
# iteration field), and the second extract write-site at
# `apply_actions.py:398-406` writes no fingerprint at all - there is no
# iteration to resolve an audit JSON from either way.
_ITERATION_FIELD_BY_FRONTMATTER_KEY = {
    "audit_acknowledgements": "ack_iteration",
    "audit_disputes": "dispute_iteration",
    "audit_overrides": "override_iteration",
}


def remap_plan_fingerprints(
    plan_frontmatter: dict,
    remap: list[dict],
    audit_dir: str | Path,
    plan_id: str,
) -> tuple[dict, list[dict]]:
    """
    Walk `audit_acknowledgements`, `audit_disputes` and `audit_overrides` in
    `plan_frontmatter`. For each dict entry carrying a `fingerprint`, resolve
    the audit JSON for the iteration named by its `ack_iteration` /
    `dispute_iteration` / `override_iteration`, find the finding whose
    fingerprint matches, remap its `location`, recompute the fingerprint, and
    write the new value back onto the entry.

    Any of these fields is treated as empty when absent or `null`, rather
    than iterated - `audit_extracted: null` is the plan-template default and
    is the value on every PLAN that has never had an extraction, so iterating
    it unconditionally raises TypeError on the first real call.

    Bare-string entries (a code rather than a fingerprint dict) pass through
    untouched - `audit_loop.py` already tolerates both shapes and this
    function must too.

    Returns (updated_frontmatter, report) where report is a list of
    {"old_fingerprint", "new_fingerprint", "old_location", "new_location",
    "record"} entries for every entry actually rewritten, plus a
    {"record", "old_fingerprint", "skipped": <reason>} entry for every entry
    left untouched because its audit JSON could not be resolved. Never writes
    to disk - the caller writes the returned frontmatter back.
    """
    plan_frontmatter = copy.deepcopy(plan_frontmatter)
    report: list[dict] = []

    if not remap:
        return plan_frontmatter, report

    audit_dir = Path(audit_dir)

    for field_name, iteration_field in _ITERATION_FIELD_BY_FRONTMATTER_KEY.items():
        entries = plan_frontmatter.get(field_name)
        if not isinstance(entries, list):
            continue  # absent or null - nothing to iterate

        for entry in entries:
            if not isinstance(entry, dict):
                continue  # bare-string entry - passes through untouched

            fingerprint = entry.get("fingerprint")
            if not fingerprint:
                continue

            iter_num = entry.get(iteration_field)
            if iter_num is None:
                report.append({
                    "record": field_name,
                    "old_fingerprint": fingerprint,
                    "skipped": "no iteration field",
                })
                continue

            finding = _find_finding(audit_dir, plan_id, iter_num, fingerprint)
            if finding is None:
                report.append({
                    "record": field_name,
                    "old_fingerprint": fingerprint,
                    "skipped": "no matching audit JSON found",
                })
                continue

            old_location = finding.get("location", "")
            new_location = remap_location(old_location, remap)
            if new_location == old_location:
                continue  # this finding's location did not shift

            remapped_finding = dict(finding)
            remapped_finding["location"] = new_location
            new_fingerprint = _compute_fingerprint(remapped_finding)

            entry["fingerprint"] = new_fingerprint
            report.append({
                "record": field_name,
                "old_fingerprint": fingerprint,
                "new_fingerprint": new_fingerprint,
                "old_location": old_location,
                "new_location": new_location,
            })

    return plan_frontmatter, report


def _find_finding(
    audit_dir: Path, plan_id: str, iteration: Any, fingerprint: str
) -> dict | None:
    """
    Glob `audit_dir` for `<plan_id>*-<iteration>.json` rather than
    constructing one name - the corpus carries at least four incompatible
    filename shapes and an acknowledgement records no stage. Scan the
    matched files in sorted order and return the first finding whose
    fingerprint matches; None when no matched file parses and contains it.
    """
    pattern = f"{plan_id}*-{iteration}.json"
    for candidate in sorted(audit_dir.glob(pattern)):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        for finding in data.get("findings", []):
            if finding.get("fingerprint") == fingerprint:
                return finding
    return None
