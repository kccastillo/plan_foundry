"""Tests for check_current module (PLAN-AH8 version_compare field).

No conftest.py or __init__.py exists under plan-foundry-check-current/lib/
(unlike _shared/lib/), so this suite inserts its own sys.path entries,
following the pattern at plan-foundry-sync/lib/test_sync.py:17-20.
"""

from __future__ import annotations

import pathlib
import sys

_CHECK_LIB = pathlib.Path(__file__).resolve().parent
_SHARED = _CHECK_LIB.parent.parent / "_shared"  # .claude/skills/_shared
sys.path.insert(0, str(_CHECK_LIB))
sys.path.insert(0, str(_SHARED))

import check_current  # noqa: E402


def _write_pin(target_claude: pathlib.Path, sha: str, tag: str) -> None:
    target_claude.mkdir(parents=True, exist_ok=True)
    (target_claude / check_current.VERSION_FILENAME).write_text(
        f"sha={sha}\ntag={tag}\nsynced=2026-01-01T00:00:00Z\n", encoding="utf-8"
    )


def test_major_gap_reports_behind_major(monkeypatch, tmp_path: pathlib.Path):
    """A-2: a major gap reports behind_major; a patch gap does not."""
    target = tmp_path / "target"
    target_claude = target / ".claude"
    _write_pin(target_claude, sha="a" * 40, tag="v1.9.0")

    monkeypatch.setattr(
        check_current, "fetch_remote_head", lambda url=check_current.BUNDLE_URL: ("b" * 40, "")
    )
    monkeypatch.setattr(
        check_current,
        "fetch_remote_tags",
        lambda url=check_current.BUNDLE_URL: (["v1.9.0", "v2.0.0"], ""),
    )
    result = check_current.check(target)
    assert result["status"] == "behind_or_diverged"
    assert result["version_compare"] == "behind_major"

    # A patch gap does not report behind_major.
    monkeypatch.setattr(
        check_current,
        "fetch_remote_tags",
        lambda url=check_current.BUNDLE_URL: (["v1.9.0", "v1.9.1"], ""),
    )
    result2 = check_current.check(target)
    assert result2["version_compare"] != "behind_major"
    assert result2["version_compare"] == "behind_patch"


def test_unknown_state_never_reports_current(monkeypatch, tmp_path: pathlib.Path):
    """A-3: an unknown version state never reports current, and the
    existing status field is untouched."""
    target = tmp_path / "target"
    target_claude = target / ".claude"

    # Empty pin tag - underivable.
    _write_pin(target_claude, sha="a" * 40, tag="")
    monkeypatch.setattr(
        check_current, "fetch_remote_head", lambda url=check_current.BUNDLE_URL: ("b" * 40, "")
    )
    monkeypatch.setattr(
        check_current, "fetch_remote_tags", lambda url=check_current.BUNDLE_URL: (["v1.0.0"], "")
    )
    result = check_current.check(target)
    assert result["status"] == "behind_or_diverged"
    assert result["version_compare"] == "unavailable"
    assert result["version_compare"] != "current"

    # ls-remote --tags failure.
    _write_pin(target_claude, sha="a" * 40, tag="v1.0.0")
    monkeypatch.setattr(
        check_current,
        "fetch_remote_tags",
        lambda url=check_current.BUNDLE_URL: ([], "network error"),
    )
    result2 = check_current.check(target)
    assert result2["version_compare"] == "unavailable"
    assert result2["version_compare"] != "current"

    # Zero parseable remote tags.
    monkeypatch.setattr(
        check_current,
        "fetch_remote_tags",
        lambda url=check_current.BUNDLE_URL: (["not-a-tag"], ""),
    )
    result3 = check_current.check(target)
    assert result3["version_compare"] == "unavailable"
    assert result3["version_compare"] != "current"


def test_status_field_and_six_values_untouched(monkeypatch, tmp_path: pathlib.Path):
    """The pre-existing status field and its six values are unaffected by
    the version_compare addition."""
    target = tmp_path / "target"
    result = check_current.check(target)
    assert result["status"] == "not_initialised"
    assert result["version_compare"] == "unavailable"


def test_current_status_leaves_version_compare_default(monkeypatch, tmp_path: pathlib.Path):
    """When sha matches remote HEAD (status: current), the tag-compare block
    is never reached and version_compare stays at its unavailable default -
    the insertion point is strictly before the behind_or_diverged return."""
    target = tmp_path / "target"
    target_claude = target / ".claude"
    same_sha = "c" * 40
    _write_pin(target_claude, sha=same_sha, tag="v1.9.0")
    monkeypatch.setattr(
        check_current, "fetch_remote_head", lambda url=check_current.BUNDLE_URL: (same_sha, "")
    )
    result = check_current.check(target)
    assert result["status"] == "current"
    assert result["version_compare"] == "unavailable"
