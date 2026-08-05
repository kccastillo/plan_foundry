"""
patch_gate.py - Deciding which auditor-supplied patches apply, and deriving the
pre-human repair bound from disk.

Written for PLAN-AJ0 (auditor supplies the repair, orchestrator applies it).
This module decides; the orchestrator applies. It never writes to disk and it
never issues an Edit itself - `resolve_patches` simulates the patch sequence
in memory and returns which findings' patches survive, in the order the
orchestrator should apply them; the orchestrator issues one Edit per surviving
patch.

A patch's target file is always the PLAN under audit. Nothing in this module
targets, or is passed, any other file.

Import policy: this module imports only the standard library, with exactly
one exception - it imports `extract_plan_id` from `audit_loop`, so the
plan id is derived by the same code that wrote the audit JSON filenames
rather than by a second, independently-drifting regex.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from audit_loop import extract_plan_id

_ITER_RE = re.compile(r"-sufficiency-(\d+)$")


def resolve_patches(text: str, findings: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Simulate applying each finding's patch, in array order, against `text`.

    Returns (applicable, demoted):
      - applicable: findings (in input order) whose patch's old_string occurred
        in the simulated text exactly `occurrence` times (default 1) at the
        point the finding was considered. The simulated text is updated by
        replacing all occurrences before moving to the next finding.
      - demoted: [{"finding": <finding>, "reason": <str>}] for findings that
        carried a patch but did not apply. Reasons:
          "anchor absent" - the anchor was already absent from the text this
              function was given.
          "anchor consumed by an earlier patch in this round" - the anchor
              was present in the original `text` but is absent from the
              simulated text at the point this patch is considered (D6).
          "occurrence mismatch: expected N, found M" - otherwise.

    A finding with no "patch" key is ignored by both lists.

    This function never writes to disk.
    """
    applicable: list[dict] = []
    demoted: list[dict] = []
    simulated = text

    for finding in findings:
        patch = finding.get("patch")
        if not patch:
            continue

        old_string = patch["old_string"]
        new_string = patch["new_string"]
        occurrence = patch.get("occurrence", 1)

        count = simulated.count(old_string)

        if count == occurrence:
            simulated = simulated.replace(old_string, new_string)
            applicable.append(finding)
            continue

        if count == 0:
            if old_string in text:
                reason = "anchor consumed by an earlier patch in this round"
            else:
                reason = "anchor absent"
        else:
            reason = f"occurrence mismatch: expected {occurrence}, found {count}"

        demoted.append({"finding": finding, "reason": reason})

    return applicable, demoted


def _triaged_class_for(finding: dict, triaged_items: list[dict]) -> str | None:
    """Return the `class` of the triaged item joining to `finding` on
    (code, location), or None if no item joins, per D3's join key."""
    code = finding.get("code")
    location = finding.get("location")
    joined = None
    for item in triaged_items:
        if item.get("code") == code and item.get("location") == location:
            joined = item.get("class")
    return joined


def _round_counts_toward_bound(payload_path: Path) -> bool:
    """
    Return True if the audit JSON at `payload_path` represents a round whose
    trailing membership counts toward the pre-human bound: it parses, carries
    a joinable `triaged_human_items` list, and at least one finding joins by
    (code, location) to a `mechanically_forced` triaged item while carrying a
    `patch`. Any other shape (unreadable, unparseable, missing/malformed
    triaged items, no qualifying finding) returns False.
    """
    try:
        raw = payload_path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return False

    payload = data.get("payload")
    if not isinstance(payload, dict):
        return False

    triaged_items = payload.get("triaged_human_items")
    if not isinstance(triaged_items, list):
        return False

    # Every entry must at minimum carry class/code/location to be joinable.
    for item in triaged_items:
        if not isinstance(item, dict):
            return False
        if not all(k in item for k in ("class", "code", "location")):
            return False

    findings = data.get("diagnostics", {}).get("findings")
    if not isinstance(findings, list):
        findings = data.get("findings")
    if not isinstance(findings, list):
        return False

    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if not finding.get("patch"):
            continue
        joined_class = _triaged_class_for(finding, triaged_items)
        if joined_class == "mechanically_forced":
            return True

    return False


def pre_human_bound_reached(plan_path: str | Path, current_iteration: int, bound: int = 2) -> bool:
    """
    Derive the pre-human repair bound (D8) from the audit JSONs on disk.

    Walks sufficiency-audit iteration indices in descending order starting at
    `current_iteration - 1` (the round under audit is never counted toward its
    own bound). The walk terminates at the first index that does not count
    toward the trailing run: the index is not on disk, the file does not read
    or parse, it carries no joinable `triaged_human_items`, or no finding in
    it joins by (code, location) to a `mechanically_forced` triaged item while
    carrying a patch. A gap in the sequence terminates the run rather than
    being skipped over.

    Returns True once the trailing count reaches `bound`. Never raises and
    never writes.
    """
    plan_path = Path(plan_path)
    plan_id = extract_plan_id(plan_path)
    audit_dir = plan_path.parent / ".audit"

    round_files: dict[int, Path] = {}
    if audit_dir.is_dir():
        for path in audit_dir.glob(f"{plan_id}-sufficiency-*.json"):
            match = _ITER_RE.search(path.stem)
            if match:
                round_files[int(match.group(1))] = path

    count = 0
    idx = current_iteration - 1
    while idx in round_files:
        if not _round_counts_toward_bound(round_files[idx]):
            break
        count += 1
        idx -= 1

    return count >= bound
