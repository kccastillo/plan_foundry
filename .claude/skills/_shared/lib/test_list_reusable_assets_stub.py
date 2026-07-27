"""Tests for _shared/list_reusable_assets.py - PLAN-AD6 Step 5 stub."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from list_reusable_assets import (  # noqa: E402
    collect_assets,
    main,
    write_index,
    write_registry,
)


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]


def test_collect_finds_four_helpers():
    assets = collect_assets(_REPO_ROOT)
    asset_ids = [a["asset_id"] for a in assets]
    assert "help-capacity-thresholds" in asset_ids
    assert "help-audit-stages" in asset_ids
    assert "help-research-prompt-template" in asset_ids
    assert "help-push-policy" in asset_ids


def test_all_collected_are_helpers():
    assets = collect_assets(_REPO_ROOT)
    # AC2a migrated zero references; only helpers.
    assert all(a["kind"] == "helper" for a in assets)


def test_main_writes_registry_and_index(tmp_path, monkeypatch):
    # Use the real repo for asset collection but write outputs to tmp.
    # We patch the module's _REFERENCES_DIR to point under tmp_path.
    import list_reusable_assets as mod

    # Mirror the real repo's references/ contents into tmp so the
    # function can write there. We point repo_root at tmp_path but
    # also need the helper files present at tmp_path/.claude/...,
    # which is not realistic for an isolated unit test. Instead,
    # test the writers directly with a synthetic asset list.
    fake_assets = [
        {
            "asset_id": "help-foo",
            "kind": "helper",
            "title": "Foo",
            "topic_tags": ["foo"],
            "last_consulted": "",
            "__source_path": "x.py",
        },
        {
            "asset_id": "ref-bar",
            "kind": "reference",
            "title": "Bar",
            "topic_tags": ["bar", "baz"],
            "last_consulted": "2026-05-26",
            "__source_path": "references/bar.md",
        },
    ]
    (tmp_path / "references").mkdir()
    reg_path = write_registry(fake_assets, repo_root=tmp_path)
    idx_path = write_index(fake_assets, repo_root=tmp_path)

    assert reg_path.is_file()
    assert idx_path.is_file()

    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    assert reg["schema_version"] == 1
    assert len(reg["assets"]) == 2
    assert {a["asset_id"] for a in reg["assets"]} == {"help-foo", "ref-bar"}

    idx_text = idx_path.read_text(encoding="utf-8")
    assert "help-foo" in idx_text
    assert "ref-bar" in idx_text
    assert "| asset_id | kind | title | topic_tags | last_consulted |" in idx_text


def test_main_returns_zero_on_real_repo():
    rc = main(_REPO_ROOT)
    assert rc == 0
    reg = json.loads(
        (_REPO_ROOT / "references" / ".registry.json").read_text(encoding="utf-8")
    )
    assert reg["schema_version"] == 1

    # This assertion used to be `len(reg["assets"]) == 4`. It had been failing
    # since two assets landed on 2026-07-27 (fable-escalation-policy,
    # writing-style), and CI never caught it because run-all.sh enumerated its
    # test files by hand while its own header claimed to run everything under
    # .claude/skills/*/lib/. A hardcoded corpus count is the hand-asserted fact
    # D13 says must be derived or deleted.
    #
    # Deriving it by re-globbing was tried and rejected: reproducing the
    # walker's collection rules inside its own test duplicates the logic under
    # test, and the duplicate drifts (the first attempt miscounted push_policy.py,
    # the second miscounted the walker's own source, which contains the literal
    # string "asset_id:"). Assert structural invariants instead - they hold at
    # any corpus size and cannot go stale.
    assert reg["assets"], "registry collected no assets"
    for asset in reg["assets"]:
        src = _REPO_ROOT / asset["__source_path"]
        assert src.exists(), f"registry names a source that does not exist: {src}"
        assert asset["asset_id"], f"asset with no asset_id: {asset['__source_path']}"
    ids = [a["asset_id"] for a in reg["assets"]]
    assert len(ids) == len(set(ids)), f"duplicate asset_ids in registry: {ids}"


def test_index_rows_match_collected_assets():
    main(_REPO_ROOT)
    idx = (_REPO_ROOT / "references" / "INDEX.md").read_text(encoding="utf-8")
    for asset_id in (
        "help-capacity-thresholds",
        "help-audit-stages",
        "help-research-prompt-template",
        "help-push-policy",
    ):
        assert asset_id in idx, f"INDEX.md missing row for {asset_id}"
