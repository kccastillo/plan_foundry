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


class DefectiveAuditRecord(Exception):
    """
    Raised by `_round_counts_toward_bound` when an audit JSON file exists on
    disk for the round under inspection but is not a well-formed audit
    record: unreadable, unparseable, carrying a `payload` that is missing or
    not an object, or carrying `triaged_human_items` that is missing, not a
    list, or containing an entry that is not an object or lacks
    `class`/`code`/`location`, or carrying a `findings` array (under
    `diagnostics`, or the top-level fallback) that is missing or not a
    list.

    Absence of the file at that round's index is a different condition -
    the round never ran - and does not raise this. `pre_human_bound_reached`
    still terminates its walk on absence exactly as it did before this
    exception existed. A present, well-formed record that simply carries no
    finding joining to a `mechanically_forced` triaged item is not
    defective either - `_round_counts_toward_bound` returns `False` for that
    case, and must keep doing so.
    """


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
    a well-formed `triaged_human_items` list, and at least one finding joins
    by (code, location) to a `mechanically_forced` triaged item while
    carrying a `patch`.

    Return False when the record is well-formed but simply carries no such
    join - a real, silent non-count, not a defect.

    Raise `DefectiveAuditRecord` when the record is present on disk but is
    not well-formed: unreadable, unparseable, `payload` missing or not an
    object, `triaged_human_items` missing, not a list, or containing a
    malformed entry, or `findings` (under `diagnostics`, or the top-level
    fallback) missing or not a list. A defective record must not read the
    same as a round that never happened - doing so is what let the bound go unenforced on
    2026-08-10, when two audit records were transcribed without their patch
    bodies and neither counted.
    """
    try:
        raw = payload_path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise DefectiveAuditRecord(f"{payload_path}: unreadable or unparseable ({exc})") from exc

    payload = data.get("payload")
    if not isinstance(payload, dict):
        raise DefectiveAuditRecord(f"{payload_path}: payload is missing or not an object")

    triaged_items = payload.get("triaged_human_items")
    if not isinstance(triaged_items, list):
        raise DefectiveAuditRecord(f"{payload_path}: triaged_human_items is missing or not a list")

    # Every entry must at minimum carry class/code/location to be joinable.
    for item in triaged_items:
        if not isinstance(item, dict):
            raise DefectiveAuditRecord(f"{payload_path}: a triaged_human_items entry is not an object")
        if not all(k in item for k in ("class", "code", "location")):
            raise DefectiveAuditRecord(
                f"{payload_path}: a triaged_human_items entry is missing class, code, or location"
            )

    findings = data.get("diagnostics", {}).get("findings")
    if not isinstance(findings, list):
        findings = data.get("findings")
    if not isinstance(findings, list):
        raise DefectiveAuditRecord(
            f"{payload_path}: diagnostics.findings is missing or not a list"
        )

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
    own bound). The walk terminates at the first index whose file is absent
    from disk, or whose record is well-formed but carries no finding that
    joins by (code, location) to a `mechanically_forced` triaged item while
    carrying a patch. A gap in the sequence terminates the run rather than
    being skipped over.

    Returns True once the trailing count reaches `bound`. Raises
    `DefectiveAuditRecord`, and does not return, when a file within the
    trailing walk is present on disk but is not a well-formed audit record -
    see `_round_counts_toward_bound`. Never writes.
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
