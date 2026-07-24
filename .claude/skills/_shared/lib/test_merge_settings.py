"""Tests for merge_settings.py (PLAN-AH2).

Uses conftest.py convention: _shared/ is on sys.path (added by conftest.py
in this directory). Run with:
    python -m pytest .claude/skills/_shared/lib/test_merge_settings.py -q
"""

from __future__ import annotations

import json
import pathlib

import pytest

import merge_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _make_fragment(tmp_path: pathlib.Path, data: dict | None = None) -> pathlib.Path:
    if data is None:
        data = {"permissions": {"deny": ["AskUserQuestion"]}}
    frag = tmp_path / "bundle-settings.json"
    _write_json(frag, data)
    return frag


# ---------------------------------------------------------------------------
# Case (a): absent target file → created with permissions.deny == ["AskUserQuestion"]
# ---------------------------------------------------------------------------

def test_absent_target_creates_with_deny(tmp_path):
    target = tmp_path / ".claude" / "settings.json"
    frag = _make_fragment(tmp_path)

    report = merge_settings.merge_bundle_settings(target, frag)

    assert target.exists()
    result = _read_json(target)
    assert result["permissions"]["deny"] == ["AskUserQuestion"]
    assert report["target_precursor"] == "absent"
    assert "permissions.deny: AskUserQuestion" in report["entries_added"]
    assert report["changed"] is True


# ---------------------------------------------------------------------------
# Case (b): target with pre-existing permissions.allow and unrelated deny
#           → deny unioned, allow + unrelated deny entry preserved, hooks untouched
# ---------------------------------------------------------------------------

def test_preserve_allow_and_unrelated_deny_and_hooks(tmp_path):
    target = tmp_path / "settings.json"
    frag = _make_fragment(tmp_path)

    existing = {
        "permissions": {
            "allow": ["Bash(git *)"],
            "deny": ["SomethingElse"],
        },
        "hooks": {
            "PostToolUse": [{"type": "command", "command": "my-hook"}]
        },
    }
    _write_json(target, existing)

    report = merge_settings.merge_bundle_settings(target, frag)

    result = _read_json(target)
    # AskUserQuestion merged in
    assert "AskUserQuestion" in result["permissions"]["deny"]
    # SomethingElse preserved (not removed)
    assert "SomethingElse" in result["permissions"]["deny"]
    # allow preserved
    assert result["permissions"]["allow"] == ["Bash(git *)"]
    # hooks preserved (not touched)
    assert result["hooks"]["PostToolUse"][0]["command"] == "my-hook"

    assert "permissions.deny: AskUserQuestion" in report["entries_added"]
    assert report["changed"] is True


# ---------------------------------------------------------------------------
# Case (c): target already containing AskUserQuestion in deny → no duplicate
# ---------------------------------------------------------------------------

def test_no_duplicate_when_already_present(tmp_path):
    target = tmp_path / "settings.json"
    frag = _make_fragment(tmp_path)

    existing = {"permissions": {"deny": ["AskUserQuestion"]}}
    _write_json(target, existing)

    report = merge_settings.merge_bundle_settings(target, frag)

    result = _read_json(target)
    assert result["permissions"]["deny"].count("AskUserQuestion") == 1
    assert report["entries_added"] == []
    assert "permissions.deny: AskUserQuestion" in report["entries_already_present"]
    assert report["changed"] is False


# ---------------------------------------------------------------------------
# Case (d): idempotency — running the merge twice yields byte-identical output
# ---------------------------------------------------------------------------

def test_idempotent_double_run(tmp_path):
    target = tmp_path / "settings.json"
    frag = _make_fragment(tmp_path)

    merge_settings.merge_bundle_settings(target, frag)
    first_bytes = target.read_bytes()

    merge_settings.merge_bundle_settings(target, frag)
    second_bytes = target.read_bytes()

    assert first_bytes == second_bytes


# ---------------------------------------------------------------------------
# Case (e): empty/malformed target file → treated as {}, no raise
# ---------------------------------------------------------------------------

def test_empty_target_treated_as_empty_dict(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text("", encoding="utf-8")
    frag = _make_fragment(tmp_path)

    report = merge_settings.merge_bundle_settings(target, frag)

    assert target.exists()
    result = _read_json(target)
    assert result["permissions"]["deny"] == ["AskUserQuestion"]
    assert report["target_precursor"] == "empty"
    assert report["changed"] is True


def test_malformed_target_treated_as_empty_dict(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text("this is not json {{{ broken", encoding="utf-8")
    frag = _make_fragment(tmp_path)

    # Must not raise
    report = merge_settings.merge_bundle_settings(target, frag)

    assert report["target_precursor"] == "unparseable"
    result = _read_json(target)
    assert result["permissions"]["deny"] == ["AskUserQuestion"]


# ---------------------------------------------------------------------------
# Case (f): target with permissions present but NO deny key (current dev
#           settings.json shape — permissions.allow only) → deny created
#           and populated, allow preserved
# ---------------------------------------------------------------------------

def test_no_deny_key_creates_deny_and_preserves_allow(tmp_path):
    target = tmp_path / "settings.json"
    frag = _make_fragment(tmp_path)

    existing = {
        "permissions": {
            "allow": [
                "Bash(git *)",
                "Bash(grep *)",
            ]
        },
        "hooks": {
            "PostToolUse": [{"type": "command", "command": "my-hook"}]
        },
    }
    _write_json(target, existing)

    report = merge_settings.merge_bundle_settings(target, frag)

    result = _read_json(target)
    # deny key created
    assert "deny" in result["permissions"]
    assert "AskUserQuestion" in result["permissions"]["deny"]
    # allow preserved exactly
    assert result["permissions"]["allow"] == ["Bash(git *)", "Bash(grep *)"]
    # hooks preserved
    assert "hooks" in result
    assert result["hooks"]["PostToolUse"][0]["command"] == "my-hook"

    assert report["changed"] is True
    assert "permissions.deny: AskUserQuestion" in report["entries_added"]
