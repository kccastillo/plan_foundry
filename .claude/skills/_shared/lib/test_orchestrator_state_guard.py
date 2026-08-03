"""
test_orchestrator_state_guard.py - Unit tests for snapshot_owned_fields() and
restore_owned_fields().

Tests the orchestrator-owned-state guard introduced by PLAN-AF3
(Orchestrator-owned state is never trusted from subagents - BUG 3 forgery defence,
2026-06-20).

Coverage:
  (a) Snapshot returns current owned-field values (including _ABSENT for absent fields).
  (b) Restore reverts subagent-forged owned fields.
  (c) Restore preserves body text and non-owned frontmatter.
  (d) Restore deletes an owned field that the subagent added but snapshot did not have.
  (e) Round-trip with no changes is a no-op on owned fields.

Run: python -m pytest .claude/skills/_shared/lib/test_orchestrator_state_guard.py
"""

import importlib.util
import pathlib
import sys

import yaml

# Make the parent dir importable regardless of cwd.
# conftest.py in this directory inserts _shared/ into sys.path automatically;
# this explicit insert ensures the import works when the file is run directly.
_HERE = pathlib.Path(__file__).resolve().parent
_PARENT = _HERE.parent  # .claude/skills/_shared/
sys.path.insert(0, str(_PARENT))

from orchestrator_state_guard import (  # noqa: E402
    OWNED_FIELDS,
    _ABSENT,
    restore_owned_fields,
    snapshot_owned_fields,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE_BASIC = """\
---
id: PLAN-TEST
title: Test plan
status: ready
pipeline_phase: drafted
audit_state:
  last_stage: none
  last_outcome: none
---

## Objective

Test body text.
"""

_FIXTURE_NO_EXECUTOR_OUTCOME = """\
---
id: PLAN-TEST2
title: Test plan 2
status: ready
pipeline_phase: drafted
audit_state:
  last_stage: none
  last_outcome: none
---

## Objective

Another test body.
"""


def _write_plan(tmp_path: pathlib.Path, content: str, name: str = "PLAN-TEST_test.md") -> pathlib.Path:
    """Write a PLAN fixture to tmp_path with UTF-8 encoding."""
    plan_path = tmp_path / name
    plan_path.write_text(content, encoding="utf-8")
    return plan_path


# ---------------------------------------------------------------------------
# (a) Snapshot returns current owned-field values
# ---------------------------------------------------------------------------

def test_snapshot_returns_owned_field_values(tmp_path):
    """(a) snapshot_owned_fields returns current values for present fields and _ABSENT for absent ones."""
    plan_path = _write_plan(tmp_path, _FIXTURE_BASIC)

    result = snapshot_owned_fields(plan_path)

    # Keys are exactly OWNED_FIELDS
    assert set(result.keys()) == set(OWNED_FIELDS), (
        f"snapshot keys should be exactly OWNED_FIELDS; got {set(result.keys())}"
    )

    # pipeline_phase is present
    assert result["pipeline_phase"] == "drafted", (
        f"expected pipeline_phase='drafted', got {result['pipeline_phase']!r}"
    )

    # audit_state is present
    assert result["audit_state"] == {"last_stage": "none", "last_outcome": "none"}, (
        f"audit_state mismatch: {result['audit_state']!r}"
    )

    # last_executor_outcome and verification_state are absent in the fixture
    assert result["last_executor_outcome"] is _ABSENT, (
        "last_executor_outcome should be _ABSENT (not in fixture)"
    )
    assert result["verification_state"] is _ABSENT, (
        "verification_state should be _ABSENT (not in fixture)"
    )


# ---------------------------------------------------------------------------
# (b) Restore reverts subagent-forged owned fields
# ---------------------------------------------------------------------------

def test_restore_reverts_forged_owned_fields(tmp_path):
    """(b) restore_owned_fields reverts fields a subagent forged after the snapshot."""
    plan_path = _write_plan(tmp_path, _FIXTURE_BASIC)

    # Take snapshot before forgery
    snapshot = snapshot_owned_fields(plan_path)
    assert snapshot["pipeline_phase"] == "drafted"

    # Simulate subagent forgery: flip pipeline_phase and inject a false audit_state
    forged_content = _FIXTURE_BASIC.replace(
        "pipeline_phase: drafted",
        "pipeline_phase: checked",
    ).replace(
        "audit_state:\n  last_stage: none\n  last_outcome: none",
        "audit_state:\n  last_stage: plan_safety\n  last_outcome: success\n  last_audit_commit: abc12345",
    )
    plan_path.write_text(forged_content, encoding="utf-8")

    # Verify forgery is on disk
    forged_snap = snapshot_owned_fields(plan_path)
    assert forged_snap["pipeline_phase"] == "checked"
    assert forged_snap["audit_state"]["last_outcome"] == "success"

    # Restore
    restore_owned_fields(plan_path, snapshot)

    # Re-read and assert owned fields are back to pre-forgery values
    restored = snapshot_owned_fields(plan_path)
    assert restored["pipeline_phase"] == "drafted", (
        f"pipeline_phase should be 'drafted' after restore; got {restored['pipeline_phase']!r}"
    )
    assert restored["audit_state"] == {"last_stage": "none", "last_outcome": "none"}, (
        f"audit_state should be pre-forgery value; got {restored['audit_state']!r}"
    )


# ---------------------------------------------------------------------------
# (c) Restore preserves body text and non-owned frontmatter
# ---------------------------------------------------------------------------

def test_restore_preserves_body_and_non_owned_frontmatter(tmp_path):
    """(c) restore_owned_fields leaves body text and non-owned frontmatter unchanged."""
    plan_path = _write_plan(tmp_path, _FIXTURE_BASIC)

    # Take snapshot
    snapshot = snapshot_owned_fields(plan_path)

    # Edit the file: change body text and add a non-owned frontmatter entry
    modified_content = plan_path.read_text(encoding="utf-8")
    # Add linked_inputs (non-owned) to frontmatter
    modified_content = modified_content.replace(
        "status: ready\n",
        "status: ready\nlinked_inputs:\n- ADVICE-001.md\n",
    )
    # Change the Objective body text
    modified_content = modified_content.replace(
        "Test body text.",
        "Updated body text after subagent edit.",
    )
    plan_path.write_text(modified_content, encoding="utf-8")

    # Restore owned fields (owned fields themselves were not changed in this edit,
    # so restore is essentially a no-op on owned fields, but MUST preserve
    # body + non-owned frontmatter)
    restore_owned_fields(plan_path, snapshot)

    # Read back
    result_text = plan_path.read_text(encoding="utf-8")

    # Body change survives
    assert "Updated body text after subagent edit." in result_text, (
        "body text change should survive restore"
    )

    # linked_inputs (non-owned) survives
    assert "linked_inputs" in result_text, (
        "linked_inputs (non-owned frontmatter) should survive restore"
    )
    assert "ADVICE-001.md" in result_text, (
        "linked_inputs content should survive restore"
    )

    # Owned fields are back to snapshot values
    restored_snap = snapshot_owned_fields(plan_path)
    assert restored_snap["pipeline_phase"] == "drafted"
    assert restored_snap["audit_state"] == {"last_stage": "none", "last_outcome": "none"}


# ---------------------------------------------------------------------------
# (d) Restore deletes an owned field that the subagent added but snapshot did not have
# ---------------------------------------------------------------------------

def test_restore_deletes_subagent_added_owned_field(tmp_path):
    """(d) restore_owned_fields removes an owned field that was absent in the snapshot."""
    # Use fixture without last_executor_outcome
    plan_path = _write_plan(tmp_path, _FIXTURE_NO_EXECUTOR_OUTCOME, name="PLAN-TEST2_test.md")

    # Snapshot - last_executor_outcome is absent
    snapshot = snapshot_owned_fields(plan_path)
    assert snapshot["last_executor_outcome"] is _ABSENT, (
        "last_executor_outcome should be _ABSENT in snapshot"
    )

    # Simulate subagent injecting last_executor_outcome
    injected_content = plan_path.read_text(encoding="utf-8").replace(
        "pipeline_phase: drafted\n",
        "pipeline_phase: drafted\nlast_executor_outcome:\n  outcome: success\n",
    )
    plan_path.write_text(injected_content, encoding="utf-8")

    # Verify injection is on disk
    from_disk = snapshot_owned_fields(plan_path)
    assert from_disk["last_executor_outcome"] is not _ABSENT, (
        "last_executor_outcome should be present after injection"
    )
    assert from_disk["last_executor_outcome"]["outcome"] == "success"

    # Restore
    restore_owned_fields(plan_path, snapshot)

    # Re-read: last_executor_outcome must be gone
    after_restore = snapshot_owned_fields(plan_path)
    assert after_restore["last_executor_outcome"] is _ABSENT, (
        "last_executor_outcome should be absent after restore (was absent in snapshot)"
    )


# ---------------------------------------------------------------------------
# (e) Round-trip with no changes is a no-op on owned fields
# ---------------------------------------------------------------------------

def test_roundtrip_no_changes_is_noop(tmp_path):
    """(e) snapshot then immediate restore leaves owned fields identical."""
    plan_path = _write_plan(tmp_path, _FIXTURE_BASIC)

    # Record pre-snapshot owned fields via direct read
    pre = snapshot_owned_fields(plan_path)

    # Snapshot then immediately restore (no disk changes in between)
    snapshot = snapshot_owned_fields(plan_path)
    restore_owned_fields(plan_path, snapshot)

    # Post-restore values must match pre values
    post = snapshot_owned_fields(plan_path)
    for field in OWNED_FIELDS:
        pre_val = pre[field]
        post_val = post[field]
        if pre_val is _ABSENT:
            assert post_val is _ABSENT, (
                f"field {field!r}: was _ABSENT before, should still be _ABSENT after round-trip"
            )
        else:
            assert post_val == pre_val, (
                f"field {field!r}: expected {pre_val!r}, got {post_val!r} after round-trip"
            )


# ---------------------------------------------------------------------------
# (f) RESEARCH-005 regression: the absent-marker survives a module-reimport /
#     serialisation boundary - restore deletes the absent field, never writes the
#     sentinel as a !!python/object YAML tag that breaks the next safe_load.
# ---------------------------------------------------------------------------

def test_absent_marker_survives_import_boundary(tmp_path):
    """(f) RESEARCH-005 regression. Snapshot under one import of the guard and
    restore under a second, independent import - so producer._ABSENT and
    consumer._ABSENT are DIFFERENT objects (the double-import boundary that broke
    the old `is`-checked object() sentinel). The absent last_executor_outcome must
    be deleted, the frontmatter must contain no `!!python/object` tag, and the
    next helper's safe_load must not raise.
    """
    guard_path = _PARENT / "orchestrator_state_guard.py"

    def _load(modname):
        spec = importlib.util.spec_from_file_location(modname, guard_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    producer = _load("guard_producer_f")
    consumer = _load("guard_consumer_f")

    plan_path = _write_plan(tmp_path, _FIXTURE_NO_EXECUTOR_OUTCOME, name="PLAN-TESTF_test.md")

    # Snapshot under producer (last_executor_outcome + verification_state absent).
    snapshot = producer.snapshot_owned_fields(plan_path)

    # Restore under consumer - its _ABSENT is a different object than producer's.
    consumer.restore_owned_fields(plan_path, snapshot)

    text = plan_path.read_text(encoding="utf-8")
    assert "!!python/object" not in text, (
        "RESEARCH-005 regression: sentinel leaked into frontmatter as a python/object tag:\n"
        + text
    )

    # The next helper does a plain safe_load - it must not raise.
    fm_text = text.split("---", 2)[1]
    fm = yaml.safe_load(fm_text)

    assert "last_executor_outcome" not in fm, (
        "absent field should be DELETED across the boundary, not written back"
    )
    assert "verification_state" not in fm, (
        "absent field should be DELETED across the boundary, not written back"
    )


# ---------------------------------------------------------------------------
# (g) RESEARCH-005 direction 3 regression: a stray non-YAML-safe owned-field
#     value (a bare object()) reaching restore must be treated as absent and
#     POPPED - never written - so the frontmatter has no !!python/object tag and
#     the next safe_load succeeds.
# ---------------------------------------------------------------------------

def test_restore_pops_non_serialisable_owned_value(tmp_path):
    """(g) A non-YAML-safe owned value in the snapshot is popped, not written."""
    plan_path = _write_plan(
        tmp_path, _FIXTURE_NO_EXECUTOR_OUTCOME, name="PLAN-TESTG_test.md"
    )

    snapshot = snapshot_owned_fields(plan_path)
    # Simulate a stray, non-YAML-safe sentinel reaching restore for an owned field.
    snapshot["last_executor_outcome"] = object()

    restore_owned_fields(plan_path, snapshot)

    text = plan_path.read_text(encoding="utf-8")
    assert "!!python/object" not in text, (
        "RESEARCH-005 direction 3: non-serialisable owned value leaked into "
        "frontmatter as a python/object tag:\n" + text
    )

    # The next helper does a plain safe_load - it must not raise.
    fm_text = text.split("---", 2)[1]
    fm = yaml.safe_load(fm_text)
    assert "last_executor_outcome" not in fm, (
        "non-serialisable owned value should be POPPED, not written back"
    )


if __name__ == "__main__":
    import tempfile

    tests = [
        test_snapshot_returns_owned_field_values,
        test_restore_reverts_forged_owned_fields,
        test_restore_preserves_body_and_non_owned_frontmatter,
        test_restore_deletes_subagent_added_owned_field,
        test_roundtrip_no_changes_is_noop,
        test_absent_marker_survives_import_boundary,
        test_restore_pops_non_serialisable_owned_value,
    ]
    failures = 0
    for t in tests:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = pathlib.Path(tmp)
            try:
                t(tmp_p)
                print(f"PASS: {t.__name__}")
            except AssertionError as e:
                print(f"FAIL: {t.__name__}: {e}")
                failures += 1
    import sys as _sys
    _sys.exit(0 if failures == 0 else 1)
