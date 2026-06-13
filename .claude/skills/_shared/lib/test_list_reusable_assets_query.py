"""Tests for query_by_tags / query_by_seed / CLI (PLAN-AD9 / AC2b).

Adds to the existing stub tests in test_list_reusable_assets_stub.py.
Uses synthetic fixtures (tmp_path) for controlled cases; uses the real
repo_root for integration cases (query_by_seed happy path, zero-known-tags).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from list_reusable_assets import (  # noqa: E402
    _iter_helper_paths,
    collect_assets,
    query_by_seed,
    query_by_tags,
    write_registry,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_MODULE_PATH = _SHARED / "list_reusable_assets.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_registry(tmp_path: pathlib.Path, assets: list[dict]) -> pathlib.Path:
    """Write a minimal .registry.json under tmp_path/references/ and return
    tmp_path so it can be used as repo_root.  Also creates the _shared/ dir
    hierarchy expected by _iter_helper_paths (empty — no helpers added)."""
    refs = tmp_path / "references"
    refs.mkdir(parents=True, exist_ok=True)
    shared = tmp_path / ".claude" / "skills" / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    return tmp_path


def _synthetic_asset(
    asset_id: str,
    title: str,
    tags: list[str],
    last_consulted: str = "",
) -> dict:
    return {
        "asset_id": asset_id,
        "kind": "helper",
        "title": title,
        "topic_tags": tags,
        "last_consulted": last_consulted,
        "__source_path": f"references/{asset_id}.md",
    }


def _write_md_asset(directory: pathlib.Path, asset_id: str, tags: list[str]) -> pathlib.Path:
    """Write a minimal markdown asset file with asset frontmatter."""
    p = directory / f"{asset_id}.md"
    tags_yaml = "\n".join(f"  - {t}" for t in tags)
    p.write_text(
        f"---\nasset_id: {asset_id}\nkind: helper\ntitle: {asset_id}\ntopic_tags:\n{tags_yaml}\nlast_consulted: \"\"\n---\n\nBody.\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# query_by_tags — happy path
# ---------------------------------------------------------------------------


def test_query_by_tags_happy_path(tmp_path):
    """Tags overlapping exactly one asset; returns 1-item list with correct shape."""
    repo_root = _make_registry(tmp_path, [])
    # Write a real helper file so _iter_helper_paths picks it up.
    shared = repo_root / ".claude" / "skills" / "_shared"
    _write_md_asset(shared, "help-alpha", ["alpha", "beta"])

    result = query_by_tags(["alpha", "beta"], min_overlap=2, repo_root=repo_root)
    assert len(result) == 1
    p = result[0]
    assert p["asset_id"] == "help-alpha"
    assert p["overlap_count"] == 2
    # AssetPointer shape — required keys present.
    required = {"asset_id", "title", "topic_tags", "last_consulted", "path", "overlap_count"}
    assert required <= set(p.keys())
    # C1 — no body fields.
    assert "description" not in p
    assert "consulted_by" not in p


# ---------------------------------------------------------------------------
# query_by_tags — zero matches at min_overlap=2
# ---------------------------------------------------------------------------


def test_query_by_tags_zero_matches(tmp_path):
    repo_root = _make_registry(tmp_path, [])
    shared = repo_root / ".claude" / "skills" / "_shared"
    _write_md_asset(shared, "help-alpha", ["alpha"])  # only 1 tag

    result = query_by_tags(["alpha", "nope"], min_overlap=2, fallback_overlap=2, repo_root=repo_root)
    assert result == []


# ---------------------------------------------------------------------------
# query_by_tags — fallback path
# ---------------------------------------------------------------------------


def test_query_by_tags_fallback(tmp_path):
    """min_overlap=2 returns 0 primary; fallback_overlap=1 returns hits."""
    repo_root = _make_registry(tmp_path, [])
    shared = repo_root / ".claude" / "skills" / "_shared"
    _write_md_asset(shared, "help-alpha", ["alpha"])   # 1-tag overlap only
    _write_md_asset(shared, "help-beta", ["beta"])     # 1-tag overlap only

    result = query_by_tags(
        ["alpha", "beta"],
        top_n=5,
        min_overlap=2,
        fallback_overlap=1,
        repo_root=repo_root,
    )
    assert len(result) == 2
    ids = {p["asset_id"] for p in result}
    assert ids == {"help-alpha", "help-beta"}


# ---------------------------------------------------------------------------
# query_by_tags — top_n cap
# ---------------------------------------------------------------------------


def test_query_by_tags_topn_cap(tmp_path):
    """7 high-overlap assets; top_n=5 returns exactly 5."""
    repo_root = _make_registry(tmp_path, [])
    shared = repo_root / ".claude" / "skills" / "_shared"
    for i in range(7):
        _write_md_asset(shared, f"help-item{i:02d}", ["common", "tag"])

    result = query_by_tags(["common", "tag"], top_n=5, min_overlap=2, repo_root=repo_root)
    assert len(result) == 5


# ---------------------------------------------------------------------------
# query_by_tags — C1 enforcement (no body fields)
# ---------------------------------------------------------------------------


def test_query_by_tags_c1_no_body_fields(tmp_path):
    """Returned pointers must NOT contain description, consulted_by, or body."""
    repo_root = _make_registry(tmp_path, [])
    shared = repo_root / ".claude" / "skills" / "_shared"
    _write_md_asset(shared, "help-alpha", ["alpha", "beta"])

    result = query_by_tags(["alpha", "beta"], min_overlap=2, repo_root=repo_root)
    assert len(result) >= 1
    for p in result:
        assert "description" not in p
        assert "consulted_by" not in p
        # No large body text field (anything outside the 6 pointer keys is suspect).
        extra = set(p.keys()) - {"asset_id", "title", "topic_tags", "last_consulted", "path", "overlap_count"}
        assert extra == set(), f"Unexpected keys in AssetPointer: {extra}"


# ---------------------------------------------------------------------------
# query_by_tags — purity (no writes)
# ---------------------------------------------------------------------------


def test_query_by_tags_pure_no_writes():
    """Call twice against real repo; .registry.json mtime must not change."""
    import os
    import time

    registry_path = _REPO_ROOT / "references" / ".registry.json"
    mtime_before = registry_path.stat().st_mtime

    query_by_tags(["push", "git"], repo_root=_REPO_ROOT)
    time.sleep(0.05)  # small buffer
    query_by_tags(["push", "git"], repo_root=_REPO_ROOT)

    mtime_after = registry_path.stat().st_mtime
    assert mtime_before == mtime_after, (
        f"registry mtime changed: {mtime_before} → {mtime_after} — query_by_tags is not pure!"
    )


# ---------------------------------------------------------------------------
# query_by_seed — happy path against real registry
# ---------------------------------------------------------------------------


def test_query_by_seed_happy_path_real_registry():
    """seed 'work on plan-pipeline push policy' must surface help-push-policy.

    Live registry check (2026-05-26): help-push-policy carries
    topic_tags: [push, policy, git, plan-pipeline].
    Seed tokens via re.split: {work, on, plan, pipeline, push, policy}.
    Intersection with known tags: {push, policy} (hyphenated plan-pipeline
    does NOT split into plan+pipeline per D3b / re.split on \\W+).
    overlap_count = 2, which meets min_overlap=2 default.

    If this test fails because topic_tags have drifted from the above,
    the executor MUST surface the drift — do not silently rewrite.
    """
    result = query_by_seed("work on plan-pipeline push policy", repo_root=_REPO_ROOT)
    assert any(p["asset_id"] == "help-push-policy" for p in result), (
        "Expected help-push-policy in results. "
        "Check whether topic_tags on help-push-policy have drifted from "
        "[push, policy, git, plan-pipeline] in references/.registry.json."
    )


# ---------------------------------------------------------------------------
# query_by_seed — hyphenated-tag mismatch (codified expected behaviour D3b)
# ---------------------------------------------------------------------------


def test_query_by_seed_hyphenated_tag_mismatch(tmp_path):
    """Seed 'work on push policy' against asset tagged only [plan-pipeline] returns [].

    This locks re.split-on-\\W+ behaviour as intentional (D3b).
    The token set {work, on, push, policy} does not contain 'plan-pipeline'
    as a whole token, so no intersection with [plan-pipeline].
    A future executor must NOT fix this by adding bigram/substring matching.
    """
    repo_root = _make_registry(tmp_path, [])
    shared = repo_root / ".claude" / "skills" / "_shared"
    _write_md_asset(shared, "help-pp", ["plan-pipeline"])  # only hyphenated tag

    result = query_by_seed(
        "work on push policy",
        min_overlap=1,
        fallback_overlap=1,
        repo_root=repo_root,
    )
    assert result == [], (
        "Expected [] because 'plan-pipeline' is a whole tag and 'plan'/'pipeline' "
        "are separate tokens — no intersection per D3b re.split behaviour."
    )


# ---------------------------------------------------------------------------
# query_by_seed — zero known tags in seed
# ---------------------------------------------------------------------------


def test_query_by_seed_zero_known_tags_in_seed():
    """seed 'hello world foo bar' returns [] — no tokens match any known tag."""
    result = query_by_seed("hello world foo bar", repo_root=_REPO_ROOT)
    assert result == []


# ---------------------------------------------------------------------------
# query_by_seed — ranking
# ---------------------------------------------------------------------------


def test_query_by_seed_ranking(tmp_path):
    """Asset A tagged [push, policy] ranks before asset B tagged [push].

    seed 'push policy' tokenises to {push, policy}; A has overlap 2, B has 1.
    """
    repo_root = _make_registry(tmp_path, [])
    shared = repo_root / ".claude" / "skills" / "_shared"
    _write_md_asset(shared, "help-asset-a", ["push", "policy"])
    _write_md_asset(shared, "help-asset-b", ["push"])

    result = query_by_seed(
        "push policy",
        min_overlap=1,
        fallback_overlap=1,
        repo_root=repo_root,
    )
    assert len(result) >= 2
    ids = [p["asset_id"] for p in result]
    assert ids.index("help-asset-a") < ids.index("help-asset-b"), (
        f"Expected help-asset-a before help-asset-b but got order: {ids}"
    )


# ---------------------------------------------------------------------------
# CLI — query --tags --format json
# ---------------------------------------------------------------------------


def test_cli_query_tags_json():
    """Invoke CLI via subprocess; output parses as JSON with expected shape."""
    result = subprocess.run(
        [sys.executable, str(_MODULE_PATH), "query", "--tags", "push,git", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, f"CLI exited {result.returncode}: {result.stderr}"
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) >= 1
    # Shape check.
    required = {"asset_id", "title", "topic_tags", "last_consulted", "path", "overlap_count"}
    for item in data:
        assert required <= set(item.keys())


# ---------------------------------------------------------------------------
# CLI — silent-on-zero for markdown
# ---------------------------------------------------------------------------


def test_cli_query_silent_on_zero():
    """Non-matching tags produce empty stdout in markdown format."""
    result = subprocess.run(
        [
            sys.executable,
            str(_MODULE_PATH),
            "query",
            "--tags",
            "absolutely-no-such-tag-xyz",
            "--format",
            "markdown",
        ],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0
    assert result.stdout == "", f"Expected empty stdout, got: {repr(result.stdout)}"


# ---------------------------------------------------------------------------
# CLI — regenerate subcommand (backwards compat smoke test)
# ---------------------------------------------------------------------------


def test_cli_regenerate_subcommand():
    """'regenerate' subcommand writes registry and exits 0."""
    result = subprocess.run(
        [sys.executable, str(_MODULE_PATH), "regenerate"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0
    assert "Wrote" in result.stdout
