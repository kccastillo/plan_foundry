"""
test_patch_gate.py - Tests for patch_gate.resolve_patches and
patch_gate.pre_human_bound_reached.

Run: python -m pytest .claude/skills/plan-pipeline/lib/test_patch_gate.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from patch_gate import resolve_patches, pre_human_bound_reached, DefectiveAuditRecord


# ---------------------------------------------------------------------------
# resolve_patches
# ---------------------------------------------------------------------------

def _finding(code, patch=None, location="Step 1"):
    f = {"code": code, "level": "error", "category": "assumptions", "location": location, "message": "m"}
    if patch is not None:
        f["patch"] = patch
    return f


def test_single_applying_patch_lands_in_applicable():
    text = "hello world"
    findings = [_finding("S001", {"old_string": "world", "new_string": "there"})]
    applicable, demoted = resolve_patches(text, findings)
    assert applicable == findings
    assert demoted == []


def test_absent_anchor_demoted_sibling_still_applies():
    text = "hello world"
    absent = _finding("S001", {"old_string": "nowhere", "new_string": "x"})
    sibling = _finding("S002", {"old_string": "world", "new_string": "there"})
    findings = [absent, sibling]
    applicable, demoted = resolve_patches(text, findings)
    assert applicable == [sibling]
    assert len(demoted) == 1
    assert demoted[0]["finding"] == absent
    assert demoted[0]["reason"] == "anchor absent"


def test_anchor_consumed_by_earlier_patch_demoted_not_raised():
    text = "hello world"
    first = _finding("S001", {"old_string": "hello world", "new_string": "goodbye"})
    second = _finding("S002", {"old_string": "world", "new_string": "there"})
    findings = [first, second]
    applicable, demoted = resolve_patches(text, findings)
    assert applicable == [first]
    assert len(demoted) == 1
    assert demoted[0]["finding"] == second
    assert demoted[0]["reason"] == "anchor consumed by an earlier patch in this round"


def test_occurrence_default_mismatch_when_anchor_occurs_twice():
    text = "foo bar foo"
    findings = [_finding("S001", {"old_string": "foo", "new_string": "baz"})]
    applicable, demoted = resolve_patches(text, findings)
    assert applicable == []
    assert len(demoted) == 1
    assert demoted[0]["reason"] == "occurrence mismatch: expected 1, found 2"


def test_occurrence_two_applies_to_both():
    text = "foo bar foo"
    findings = [_finding("S001", {"old_string": "foo", "new_string": "baz", "occurrence": 2})]
    applicable, demoted = resolve_patches(text, findings)
    assert applicable == findings
    assert demoted == []


def test_finding_with_no_patch_key_in_neither_list():
    text = "hello world"
    findings = [_finding("S001", patch=None)]
    applicable, demoted = resolve_patches(text, findings)
    assert applicable == []
    assert demoted == []


def test_applicable_order_matches_input_order():
    text = "aaa bbb ccc"
    f1 = _finding("S001", {"old_string": "aaa", "new_string": "AAA"})
    f2 = _finding("S002", {"old_string": "bbb", "new_string": "BBB"})
    f3 = _finding("S003", {"old_string": "ccc", "new_string": "CCC"})
    findings = [f3, f1, f2]
    applicable, demoted = resolve_patches(text, findings)
    assert applicable == [f3, f1, f2]
    assert demoted == []


# ---------------------------------------------------------------------------
# pre_human_bound_reached
# ---------------------------------------------------------------------------

def _write_round(audit_dir, plan_id, n, triaged_class="mechanically_forced", with_patch=True,
                  omit_triaged=False, malformed_triaged=False, omit_findings=False):
    finding = {
        "code": "S001",
        "level": "error",
        "category": "assumptions",
        "location": "Step 1",
        "message": "m",
    }
    if with_patch:
        finding["patch"] = {"old_string": "x", "new_string": "y", "occurrence": 1}

    payload = {"outcome_subtype": "needs-revision", "review_text": "r"}
    if not omit_triaged:
        if malformed_triaged:
            payload["triaged_human_items"] = [{"class": triaged_class}]  # missing code/location
        else:
            payload["triaged_human_items"] = [
                {"class": triaged_class, "code": "S001", "location": "Step 1"}
            ]

    diagnostics = {"summary": {"error_count": 1, "warning_count": 0, "note_count": 0}}
    if not omit_findings:
        diagnostics["findings"] = [finding]
    data = {
        "outcome": "revision_needed",
        "payload": payload,
        "diagnostics": diagnostics,
    }
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / f"{plan_id}-sufficiency-{n}.json").write_text(json.dumps(data), encoding="utf-8")


def _plan_path(tmp_path, plan_id="PLAN-AJ0"):
    workbench = tmp_path / "Workbench"
    workbench.mkdir(exist_ok=True)
    plan_path = workbench / f"{plan_id}_stub-plan.md"
    plan_path.write_text("---\ntitle: stub\n---\n", encoding="utf-8")
    return plan_path


def test_firing_round(tmp_path):
    plan_path = _plan_path(tmp_path)
    audit_dir = plan_path.parent / ".audit"
    _write_round(audit_dir, "PLAN-AJ0", 1)
    _write_round(audit_dir, "PLAN-AJ0", 2)

    assert pre_human_bound_reached(plan_path, current_iteration=1) is False
    assert pre_human_bound_reached(plan_path, current_iteration=2) is False
    assert pre_human_bound_reached(plan_path, current_iteration=3) is True


def test_broken_trailing_run(tmp_path):
    plan_path = _plan_path(tmp_path)
    audit_dir = plan_path.parent / ".audit"
    _write_round(audit_dir, "PLAN-AJ0", 1)
    _write_round(audit_dir, "PLAN-AJ0", 2)
    _write_round(audit_dir, "PLAN-AJ0", 3, with_patch=False)

    assert pre_human_bound_reached(plan_path, current_iteration=4) is False


def test_gap_in_sequence(tmp_path):
    plan_path = _plan_path(tmp_path)
    audit_dir = plan_path.parent / ".audit"
    _write_round(audit_dir, "PLAN-AJ0", 1)
    _write_round(audit_dir, "PLAN-AJ0", 3)

    assert pre_human_bound_reached(plan_path, current_iteration=4) is False


def test_class_join_is_load_bearing(tmp_path):
    plan_path = _plan_path(tmp_path)
    audit_dir = plan_path.parent / ".audit"
    _write_round(audit_dir, "PLAN-AJ0", 1, triaged_class="real_judgement_call")
    _write_round(audit_dir, "PLAN-AJ0", 2, triaged_class="real_judgement_call")

    assert pre_human_bound_reached(plan_path, current_iteration=3) is False


def test_triaged_items_absent_is_defective_not_silent(tmp_path):
    """
    A round missing triaged_human_items entirely used to read as a silent
    non-count, indistinguishable from a round that never ran. The call
    must now raise, because the record is present and broken rather than
    absent.
    """
    plan_path = _plan_path(tmp_path)
    audit_dir = plan_path.parent / ".audit"
    _write_round(audit_dir, "PLAN-AJ0", 1, omit_triaged=True)

    with pytest.raises(DefectiveAuditRecord):
        pre_human_bound_reached(plan_path, current_iteration=2)


def test_malformed_triaged_entry_is_defective(tmp_path):
    """A triaged_human_items entry missing class/code/location is the same
    class of defect as the array being absent altogether, and must raise
    rather than count as a silent non-count."""
    plan_path = _plan_path(tmp_path)
    audit_dir = plan_path.parent / ".audit"
    _write_round(audit_dir, "PLAN-AJ0", 1, malformed_triaged=True)

    with pytest.raises(DefectiveAuditRecord):
        pre_human_bound_reached(plan_path, current_iteration=2)


def test_unparseable_json_is_defective(tmp_path):
    """A round file present on disk but not valid JSON must raise, not
    terminate the walk as though the round had never been written."""
    plan_path = _plan_path(tmp_path)
    audit_dir = plan_path.parent / ".audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "PLAN-AJ0-sufficiency-1.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(DefectiveAuditRecord):
        pre_human_bound_reached(plan_path, current_iteration=2)


def test_defective_most_recent_round_raises_before_older_rounds_are_read(tmp_path):
    """The historical incident: the round closest to current_iteration was
    written without a well-formed record, which used to silently stop the
    count at zero and let two more repair rounds through. The call must
    now raise before the walk even reaches the older, well-formed rounds."""
    plan_path = _plan_path(tmp_path)
    audit_dir = plan_path.parent / ".audit"
    _write_round(audit_dir, "PLAN-AJ0", 1)
    _write_round(audit_dir, "PLAN-AJ0", 2)
    _write_round(audit_dir, "PLAN-AJ0", 3, omit_triaged=True)

    with pytest.raises(DefectiveAuditRecord):
        pre_human_bound_reached(plan_path, current_iteration=4)


def test_findings_absent_record_is_defective(tmp_path):
    """A well-formed record (valid payload, valid triaged_human_items) whose
    diagnostics.findings array is absent must raise, not silently return False
    and zero the count. The raw record is archived before Repair 2's outcome
    override, so the backward walk reaches it - raising folds this residual into
    the defect path rather than leaving a silent non-count."""
    plan_path = _plan_path(tmp_path)
    audit_dir = plan_path.parent / ".audit"
    _write_round(audit_dir, "PLAN-AJ0", 1, omit_findings=True)

    with pytest.raises(DefectiveAuditRecord):
        pre_human_bound_reached(plan_path, current_iteration=2)


def test_empty_directory(tmp_path):
    plan_path = _plan_path(tmp_path)
    assert pre_human_bound_reached(plan_path, current_iteration=1) is False
