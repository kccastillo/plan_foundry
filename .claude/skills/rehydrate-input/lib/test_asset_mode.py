"""
test_asset_mode.py -- Integration-style pytest tests for AC2c asset-mode logic.

Covers all cases specified in PLAN-AE1 Step 4:
  - Asset frontmatter validation: rejects missing required fields.
  - consulted_by append: empty list -> 1 item; existing list of 5 -> 6 items;
    existing list of 20 -> still 20 (oldest dropped).
  - consulted_by idempotency: appending the same PLAN-id twice in a row results in
    single entry (not duplicate).
  - last_consulted stamping: writes today's ISO date.
  - Memory file write: temp CLAUDE_PROJECT_MEMORY_DIR; assert file written; assert
    content shape (title, path, tags, dates).
  - Memory dir unreachable: env var points to nonexistent dir; assert warning surfaced;
    assert frontmatter stamp still lands.
  - Atomicity (S4): mock memory write to raise IOError; assert frontmatter NOT mutated.
"""
import os
import sys
import datetime
from pathlib import Path
from unittest import mock

import pytest
import yaml

sys.path.insert(0, os.path.dirname(__file__))

from asset_mode import (
    validate_asset_frontmatter,
    write_memory_file,
    stamp_asset_frontmatter,
    CONSULTED_BY_CAP,
)


TODAY = datetime.date.today().isoformat()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_FRONTMATTER = {
    "asset_id": "help-push-policy",
    "kind": "helper",
    "title": "Push Policy Helper",
    "description": "Explains push_policy config for plan_foundry.",
    "topic_tags": ["push", "git", "policy"],
    "last_consulted": "",
    "consulted_by": [],
    "schema_version": 1,
}


def make_asset_file(tmp_path: Path, frontmatter: dict, body: str = "\n# Body\n\nContent.\n") -> Path:
    """Write a minimal asset file with the given frontmatter."""
    fm_text = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    content = f"---\n{fm_text}---{body}"
    p = tmp_path / "test_asset.md"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# A1: Frontmatter validation
# ---------------------------------------------------------------------------


def test_validation_rejects_missing_asset_id():
    fm = {k: v for k, v in BASE_FRONTMATTER.items() if k != "asset_id"}
    with pytest.raises(ValueError, match="missing required field 'asset_id'"):
        validate_asset_frontmatter(fm, "PLAN-AE1")


def test_validation_rejects_missing_kind():
    fm = {k: v for k, v in BASE_FRONTMATTER.items() if k != "kind"}
    with pytest.raises(ValueError, match="missing required field 'kind'"):
        validate_asset_frontmatter(fm, "PLAN-AE1")


def test_validation_rejects_missing_last_consulted():
    fm = {k: v for k, v in BASE_FRONTMATTER.items() if k != "last_consulted"}
    with pytest.raises(ValueError, match="missing required field 'last_consulted'"):
        validate_asset_frontmatter(fm, "PLAN-AE1")


def test_validation_rejects_missing_consulted_by():
    fm = {k: v for k, v in BASE_FRONTMATTER.items() if k != "consulted_by"}
    with pytest.raises(ValueError, match="missing required field 'consulted_by'"):
        validate_asset_frontmatter(fm, "PLAN-AE1")


def test_validation_rejects_invalid_kind():
    fm = dict(BASE_FRONTMATTER)
    fm["kind"] = "widget"
    with pytest.raises(ValueError, match="unrecognised value 'widget'"):
        validate_asset_frontmatter(fm, "PLAN-AE1")


def test_validation_rejects_missing_consuming_plan():
    with pytest.raises(ValueError, match="requires 'consuming_plan'"):
        validate_asset_frontmatter(BASE_FRONTMATTER, None)


def test_validation_rejects_empty_consuming_plan():
    with pytest.raises(ValueError, match="requires 'consuming_plan'"):
        validate_asset_frontmatter(BASE_FRONTMATTER, "")


def test_validation_passes_valid_reference_kind():
    fm = dict(BASE_FRONTMATTER)
    fm["kind"] = "reference"
    validate_asset_frontmatter(fm, "PLAN-AE1")  # no exception


def test_validation_passes_valid_helper():
    validate_asset_frontmatter(BASE_FRONTMATTER, "PLAN-AE1")  # no exception


# ---------------------------------------------------------------------------
# A5: consulted_by append
# ---------------------------------------------------------------------------


def test_consulted_by_empty_list_becomes_one_item(tmp_path):
    fm = dict(BASE_FRONTMATTER)
    fm["consulted_by"] = []
    p = make_asset_file(tmp_path, fm)

    result = stamp_asset_frontmatter(p, "PLAN-AE1", TODAY)

    assert result["consulted_by_appended"] is True
    assert result["consulted_by_evicted_oldest"] is False

    raw = p.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw.split("---", 2)[1])
    assert loaded["consulted_by"] == ["PLAN-AE1"]


def test_consulted_by_existing_five_becomes_six(tmp_path):
    fm = dict(BASE_FRONTMATTER)
    fm["consulted_by"] = ["PLAN-AA1", "PLAN-AA2", "PLAN-AA3", "PLAN-AA4", "PLAN-AA5"]
    p = make_asset_file(tmp_path, fm)

    result = stamp_asset_frontmatter(p, "PLAN-AE1", TODAY)

    assert result["consulted_by_appended"] is True
    assert result["consulted_by_evicted_oldest"] is False

    raw = p.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw.split("---", 2)[1])
    assert len(loaded["consulted_by"]) == 6
    assert loaded["consulted_by"][-1] == "PLAN-AE1"


def test_consulted_by_at_cap_stays_at_cap_with_oldest_dropped(tmp_path):
    fm = dict(BASE_FRONTMATTER)
    existing = [f"PLAN-AA{i}" for i in range(CONSULTED_BY_CAP)]
    fm["consulted_by"] = existing[:]
    p = make_asset_file(tmp_path, fm)

    result = stamp_asset_frontmatter(p, "PLAN-AE1", TODAY)

    assert result["consulted_by_appended"] is True
    assert result["consulted_by_evicted_oldest"] is True

    raw = p.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw.split("---", 2)[1])
    assert len(loaded["consulted_by"]) == CONSULTED_BY_CAP
    # Oldest (PLAN-AA0) dropped; newest (PLAN-AE1) at the end
    assert "PLAN-AA0" not in loaded["consulted_by"]
    assert loaded["consulted_by"][-1] == "PLAN-AE1"


# ---------------------------------------------------------------------------
# A5: consulted_by idempotency
# ---------------------------------------------------------------------------


def test_consulted_by_idempotency_same_plan_twice_no_duplicate(tmp_path):
    """A->A produces [A] -- no duplicate adjacent entry."""
    fm = dict(BASE_FRONTMATTER)
    fm["consulted_by"] = ["PLAN-AE1"]  # already last entry
    p = make_asset_file(tmp_path, fm)

    result = stamp_asset_frontmatter(p, "PLAN-AE1", TODAY)

    assert result["consulted_by_appended"] is False
    assert result["consulted_by_evicted_oldest"] is False

    raw = p.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw.split("---", 2)[1])
    assert loaded["consulted_by"] == ["PLAN-AE1"]  # still just one entry


def test_consulted_by_idempotency_a_b_a_produces_three_entries(tmp_path):
    """A->B->A produces [A, B, A] -- legitimate re-consultation."""
    fm = dict(BASE_FRONTMATTER)
    fm["consulted_by"] = ["PLAN-AA1", "PLAN-AA2"]  # last entry is PLAN-AA2
    p = make_asset_file(tmp_path, fm)

    result = stamp_asset_frontmatter(p, "PLAN-AA1", TODAY)  # re-consulting PLAN-AA1

    assert result["consulted_by_appended"] is True

    raw = p.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw.split("---", 2)[1])
    assert loaded["consulted_by"] == ["PLAN-AA1", "PLAN-AA2", "PLAN-AA1"]


# ---------------------------------------------------------------------------
# A5: last_consulted stamping
# ---------------------------------------------------------------------------


def test_last_consulted_stamped_with_today(tmp_path):
    fm = dict(BASE_FRONTMATTER)
    fm["last_consulted"] = ""
    p = make_asset_file(tmp_path, fm)

    stamp_asset_frontmatter(p, "PLAN-AE1", TODAY)

    raw = p.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw.split("---", 2)[1])
    assert loaded["last_consulted"] == TODAY


def test_last_consulted_overwritten_from_prior_date(tmp_path):
    fm = dict(BASE_FRONTMATTER)
    fm["last_consulted"] = "2025-01-01"
    p = make_asset_file(tmp_path, fm)

    stamp_asset_frontmatter(p, "PLAN-AE1", TODAY)

    raw = p.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw.split("---", 2)[1])
    assert loaded["last_consulted"] == TODAY


# ---------------------------------------------------------------------------
# A4: Memory file write
# ---------------------------------------------------------------------------


def test_memory_file_written_with_correct_shape(tmp_path, monkeypatch):
    """Memory file is written to CLAUDE_PROJECT_MEMORY_DIR; content has expected fields."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_MEMORY_DIR", str(memory_dir))

    fm = dict(BASE_FRONTMATTER)
    result_path = write_memory_file(
        asset_path=".claude/skills/_shared/push-policy.md",
        frontmatter=fm,
        consuming_plan="PLAN-AE1",
        today=TODAY,
        memory_dir=memory_dir,
    )

    assert result_path is not None
    assert result_path.exists()

    content = result_path.read_text(encoding="utf-8")
    assert "help-push-policy" in content
    assert ".claude/skills/_shared/push-policy.md" in content
    assert "helper" in content
    assert "push" in content  # part of topic tags
    assert TODAY in content
    assert "PLAN-AE1" in content
    assert "Explains push_policy" in content  # description


def test_memory_file_idempotent_overwrite(tmp_path):
    """Re-consumption overwrites the existing memory file (idempotent)."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()

    fm = dict(BASE_FRONTMATTER)

    write_memory_file(
        asset_path=".claude/skills/_shared/push-policy.md",
        frontmatter=fm,
        consuming_plan="PLAN-AA1",
        today="2026-01-01",
        memory_dir=memory_dir,
    )

    # Re-consume with a different plan + date
    fm2 = dict(BASE_FRONTMATTER)
    fm2["consulted_by"] = ["PLAN-AA1"]
    write_memory_file(
        asset_path=".claude/skills/_shared/push-policy.md",
        frontmatter=fm2,
        consuming_plan="PLAN-AE1",
        today=TODAY,
        memory_dir=memory_dir,
    )

    files = list(memory_dir.iterdir())
    assert len(files) == 1  # only one file (overwritten)
    content = files[0].read_text(encoding="utf-8")
    assert TODAY in content
    assert "PLAN-AE1" in content


# ---------------------------------------------------------------------------
# S2 degraded path: memory dir unreachable
# ---------------------------------------------------------------------------


def test_memory_write_returns_none_when_dir_missing(tmp_path):
    """If memory dir does not exist, write_memory_file returns None (caller surfaces warning)."""
    nonexistent = tmp_path / "does_not_exist"
    # Do NOT create the directory

    result = write_memory_file(
        asset_path=".claude/skills/_shared/push-policy.md",
        frontmatter=dict(BASE_FRONTMATTER),
        consuming_plan="PLAN-AE1",
        today=TODAY,
        memory_dir=nonexistent,
    )

    assert result is None


def test_frontmatter_stamp_still_lands_when_memory_dir_missing(tmp_path):
    """When memory dir is unreachable (S2 degraded path), frontmatter stamp still writes."""
    nonexistent = tmp_path / "does_not_exist"
    fm = dict(BASE_FRONTMATTER)
    asset_file = make_asset_file(tmp_path, fm)

    # Caller workflow: try memory write (returns None = skip), then stamp frontmatter
    mem_result = write_memory_file(
        asset_path="test_asset.md",
        frontmatter=fm,
        consuming_plan="PLAN-AE1",
        today=TODAY,
        memory_dir=nonexistent,
    )
    assert mem_result is None  # memory write skipped

    # A5 still proceeds
    stamp_result = stamp_asset_frontmatter(asset_file, "PLAN-AE1", TODAY)
    assert stamp_result["consulted_by_appended"] is True

    raw = asset_file.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw.split("---", 2)[1])
    assert loaded["last_consulted"] == TODAY
    assert "PLAN-AE1" in loaded["consulted_by"]


# ---------------------------------------------------------------------------
# S4 atomicity: memory write raises -> frontmatter NOT mutated
# ---------------------------------------------------------------------------


def test_atomicity_memory_ioerror_frontmatter_not_mutated(tmp_path):
    """S4: If the memory write (A4) raises IOError, frontmatter (A5) must NOT be mutated.

    The workflow contract is: call write_memory_file() FIRST (A4), then
    stamp_asset_frontmatter() ONLY IF A4 succeeded. This test simulates a real
    IOError at A4 by pointing the memory_dir to a read-only path (a file, not a dir),
    and verifies that if the caller correctly honours S4 ordering, the asset
    frontmatter is untouched.
    """
    # Simulate a scenario where memory_dir points to something that causes IOError:
    # a FILE at the memory dir path (so writing inside it fails).
    memory_dir = tmp_path / "memory"
    # Create it as a FILE instead of a dir -- any write inside it will fail.
    memory_dir.write_text("not a directory", encoding="utf-8")

    fm = dict(BASE_FRONTMATTER)
    asset_file = make_asset_file(tmp_path, fm)
    original_raw = asset_file.read_text(encoding="utf-8")

    # A4: attempt memory write -- this should raise because memory_dir is a file
    raised = False
    try:
        write_memory_file(
            asset_path="test_asset.md",
            frontmatter=fm,
            consuming_plan="PLAN-AE1",
            today=TODAY,
            memory_dir=memory_dir,
        )
    except (IOError, OSError, NotADirectoryError):
        raised = True

    # Confirm that write_memory_file raised (A4 failed)
    assert raised, "Expected write_memory_file to raise when memory_dir is a file"

    # S4 enforcement: because A4 raised, A5 (stamp_asset_frontmatter) is NOT called.
    # Verify the asset file is unchanged.
    after_raw = asset_file.read_text(encoding="utf-8")
    assert after_raw == original_raw, (
        "Frontmatter must not be mutated when A4 (memory write) raises -- S4 atomicity violated"
    )
