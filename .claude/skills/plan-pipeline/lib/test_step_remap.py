"""
test_step_remap.py - Tests for step_remap.py (PLAN-AJ1).

Run: python -m pytest .claude/skills/plan-pipeline/lib/test_step_remap.py -q
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from step_remap import remap_location, remap_plan_fingerprints
from step_renumber import renumber_steps


def _fingerprint(code: str, level: str, category: str, location: str) -> str:
    raw = f"{code}|{level}|{category}|{location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


def test_remap_location_variants() -> None:
    remap = [{"old": 5, "new": 6}]
    assert remap_location("Step 5", remap) == "Step 6"
    assert remap_location("step 5", remap) == "step 6"
    assert remap_location("5", remap) == "6"
    assert remap_location("Step 5, Step 6", remap) == "Step 5, Step 6"
    assert remap_location("Verification", remap) == "Verification"
    assert remap_location("", remap) == ""
    assert remap_location(".claude/skills/plan-pipeline/lib/step_remap.py", remap) == (
        ".claude/skills/plan-pipeline/lib/step_remap.py"
    )


def test_acceptance_insertion_preserves_acknowledgement(tmp_path) -> None:
    # 12-Step block with an insertion after Step 5 - the same signature D6
    # exists to renumber rather than refuse.
    ordinals = [1, 2, 3, 4, 5, 5, 6, 7, 8, 9, 10, 11, 12]
    body = "\n".join(f"{n}. step body" for n in ordinals)
    text = f"## Steps\n\n{body}\n\n## Verification\n"
    _, remap = renumber_steps(text)
    assert {"old": 6, "new": 7} in remap

    plan_id = "PLAN-TEST"
    original_location = "Step 6"
    old_fingerprint = _fingerprint("S001", "warning", "assumptions", original_location)

    audit_json = {
        "schema_version": 3,
        "auditor": "sufficiency",
        "plan_id": plan_id,
        "iteration": 1,
        "findings": [
            {
                "code": "S001",
                "level": "warning",
                "category": "assumptions",
                "location": original_location,
                "message": "example finding",
                "fingerprint": old_fingerprint,
            }
        ],
        "summary": {"error_count": 0, "warning_count": 1, "note_count": 0},
    }
    (tmp_path / f"{plan_id}-sufficiency-1.json").write_text(
        json.dumps(audit_json), encoding="utf-8"
    )

    plan_frontmatter = {
        "audit_acknowledgements": [
            {
                "fingerprint": old_fingerprint,
                "rationale": "accepted as-is",
                "ack_date": "2026-07-31",
                "ack_iteration": 1,
            }
        ],
    }

    updated, report = remap_plan_fingerprints(
        plan_frontmatter, remap, tmp_path, plan_id
    )

    new_location = "Step 7"
    expected_new_fingerprint = _fingerprint("S001", "warning", "assumptions", new_location)

    assert updated["audit_acknowledgements"][0]["fingerprint"] == expected_new_fingerprint
    assert report == [
        {
            "record": "audit_acknowledgements",
            "old_fingerprint": old_fingerprint,
            "new_fingerprint": expected_new_fingerprint,
            "old_location": original_location,
            "new_location": new_location,
        }
    ]


def test_missing_audit_json_leaves_entry_unchanged_and_reports_skip(tmp_path) -> None:
    remap = [{"old": 5, "new": 6}]
    plan_frontmatter = {
        "audit_acknowledgements": [
            {
                "fingerprint": "deadbeef",
                "rationale": "x",
                "ack_date": "2026-07-31",
                "ack_iteration": 1,
            }
        ],
    }

    updated, report = remap_plan_fingerprints(
        plan_frontmatter, remap, tmp_path, "PLAN-MISSING"
    )

    assert updated["audit_acknowledgements"][0]["fingerprint"] == "deadbeef"
    assert len(report) == 1
    assert report[0]["skipped"] == "no matching audit JSON found"


def test_bare_string_entry_passes_through_untouched(tmp_path) -> None:
    remap = [{"old": 5, "new": 6}]
    plan_frontmatter = {"audit_acknowledgements": ["PSZ001"]}

    updated, report = remap_plan_fingerprints(plan_frontmatter, remap, tmp_path, "PLAN-X")

    assert updated["audit_acknowledgements"] == ["PSZ001"]
    assert report == []


def test_empty_remap_no_changes_and_no_file_read(tmp_path) -> None:
    plan_frontmatter = {
        "audit_acknowledgements": [
            {
                "fingerprint": "abc12345",
                "rationale": "x",
                "ack_date": "2026-07-31",
                "ack_iteration": 1,
            }
        ],
    }
    # A directory that does not exist - proves no glob/read was attempted,
    # since remap_plan_fingerprints returns before touching audit_dir.
    nonexistent_dir = tmp_path / "does-not-exist"

    updated, report = remap_plan_fingerprints(
        plan_frontmatter, [], nonexistent_dir, "PLAN-X"
    )

    assert updated == plan_frontmatter
    assert report == []


def test_null_audit_extracted_does_not_raise(tmp_path) -> None:
    remap = [{"old": 5, "new": 6}]
    plan_frontmatter = {
        "audit_acknowledgements": [],
        "audit_disputes": [],
        "audit_overrides": [],
        "audit_extracted": None,
    }

    updated, report = remap_plan_fingerprints(plan_frontmatter, remap, tmp_path, "PLAN-X")

    assert updated["audit_extracted"] is None
    assert report == []
