"""
test_patch_gate.py - Tests for patch_gate.resolve_patches and
patch_gate.pre_human_bound_reached.

Run: python -m pytest .claude/skills/plan-pipeline/lib/test_patch_gate.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from patch_gate import resolve_patches, pre_human_bound_reached


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
                  omit_triaged=False, malformed_triaged=False):
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

    data = {
        "outcome": "revision_needed",
        "payload": payload,
        "diagnostics": {"findings": [finding], "summary": {"error_count": 1, "warning_count": 0, "note_count": 0}},
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


def test_triaged_items_absent(tmp_path):
    plan_path = _plan_path(tmp_path)
    audit_dir = plan_path.parent / ".audit"
    _write_round(audit_dir, "PLAN-AJ0", 1, omit_triaged=True)
    _write_round(audit_dir, "PLAN-AJ0", 2, omit_triaged=True)

    assert pre_human_bound_reached(plan_path, current_iteration=3) is False


def test_empty_directory(tmp_path):
    plan_path = _plan_path(tmp_path)
    assert pre_human_bound_reached(plan_path, current_iteration=1) is False
