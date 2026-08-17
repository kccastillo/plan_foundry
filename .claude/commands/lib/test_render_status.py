"""Unit tests for render_status.py's context-fullness readout (section 3).

Every fixture here is synthetic and lives under tmp_path. Nothing in this
file reads the real ~/.claude directory - compute_context_fullness's
claude_projects_root parameter exists specifically so a test can point it at
a tmp_path tree instead, and every test below does exactly that.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

_LIB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_LIB))

import render_status  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _assistant_line(usage: dict | None) -> str:
    message: dict = {"role": "assistant", "model": "claude-sonnet-5"}
    if usage is not None:
        message["usage"] = usage
    return json.dumps({"message": message})


def _user_line() -> str:
    return json.dumps({"message": {"role": "user", "content": "hi"}})


def _write_transcript(projects_dir: pathlib.Path, session_id: str, lines: list[str]) -> pathlib.Path:
    projects_dir.mkdir(parents=True, exist_ok=True)
    path = projects_dir / f"{session_id}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _projects_dir_for(tmp_path: pathlib.Path, repo_root: pathlib.Path) -> pathlib.Path:
    """Mirror derive_project_slug's own naming so a test's repo_root and its
    fixture's projects_dir agree, the same way the real ~/.claude/projects/
    <slug>/ directory agrees with the repo it was derived from."""
    slug = render_status.derive_project_slug(repo_root)
    return tmp_path / "claude-projects" / slug


# ---------------------------------------------------------------------------
# Scenario 1: latest assistant message carries usage
# ---------------------------------------------------------------------------


def test_latest_message_usage_reported(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    projects_dir = _projects_dir_for(tmp_path, repo_root)
    _write_transcript(
        projects_dir,
        "session-1",
        [
            _user_line(),
            _assistant_line({"input_tokens": 5, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 50}),
        ],
    )

    result = render_status.compute_context_fullness(repo_root, claude_projects_root=projects_dir.parent)

    assert result["available"] is True
    assert result["reason"] is None
    assert result["resident_tokens"] == 1055
    assert result["window_tokens"] is None

    lines = render_status.render_context_fullness(repo_root, claude_projects_root=projects_dir.parent)
    assert len(lines) == 1
    assert "1055" in lines[0]
    assert "unknown" in lines[0]


# ---------------------------------------------------------------------------
# Scenario 2: the regression guard - latest message wins, never a session sum
# ---------------------------------------------------------------------------


def test_reports_latest_message_not_session_sum(tmp_path):
    """The error this readout exists to record: summing cache_read_input_tokens
    across every message re-counts the whole conversation prefix each turn and
    runs far past any real window size. The figure reported here must come
    from the latest assistant message alone."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    projects_dir = _projects_dir_for(tmp_path, repo_root)

    lines = [_user_line()]
    for turn in range(1, 21):
        # Each turn's cache_read grows the way a real transcript's does -
        # re-counting the whole prefix. Summed across 20 turns this passes
        # 100000 tokens even though the last turn alone holds 2000.
        lines.append(
            _assistant_line(
                {
                    "input_tokens": 2,
                    "cache_read_input_tokens": turn * 1000,
                    "cache_creation_input_tokens": 50,
                }
            )
        )
    _write_transcript(projects_dir, "session-2", lines)

    result = render_status.compute_context_fullness(repo_root, claude_projects_root=projects_dir.parent)

    session_sum = sum(
        turn * 1000 + 50 + 2 for turn in range(1, 21)
    )
    assert result["available"] is True
    # The last turn's own usage: input 2 + cache_read 20000 + cache_creation 50.
    assert result["resident_tokens"] == 20052
    assert result["resident_tokens"] < session_sum
    assert session_sum > 100000


# ---------------------------------------------------------------------------
# Scenario 3: no usage on any assistant message
# ---------------------------------------------------------------------------


def test_no_usage_anywhere_reports_unavailable(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    projects_dir = _projects_dir_for(tmp_path, repo_root)
    _write_transcript(
        projects_dir,
        "session-3",
        [_user_line(), _assistant_line(None), _assistant_line(None)],
    )

    result = render_status.compute_context_fullness(repo_root, claude_projects_root=projects_dir.parent)

    assert result["available"] is False
    assert result["resident_tokens"] is None
    assert "no assistant message" in result["reason"]

    lines = render_status.render_context_fullness(repo_root, claude_projects_root=projects_dir.parent)
    assert len(lines) == 1
    assert "unavailable" in lines[0]


# ---------------------------------------------------------------------------
# Scenario 4: missing transcript
# ---------------------------------------------------------------------------


def test_missing_transcript_reports_unavailable(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    projects_dir = _projects_dir_for(tmp_path, repo_root)
    # projects_dir is never created - no session has run for this repo yet.

    result = render_status.compute_context_fullness(repo_root, claude_projects_root=projects_dir.parent)

    assert result["available"] is False
    assert result["resident_tokens"] is None
    assert result["reason"] is not None


# ---------------------------------------------------------------------------
# Scenario 5: malformed JSON line does not crash the read
# ---------------------------------------------------------------------------


def test_malformed_line_skipped_latest_valid_message_used(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    projects_dir = _projects_dir_for(tmp_path, repo_root)
    projects_dir.mkdir(parents=True)
    path = projects_dir / "session-4.jsonl"
    raw_lines = [
        _user_line(),
        _assistant_line({"input_tokens": 1, "cache_read_input_tokens": 10, "cache_creation_input_tokens": 0}),
        "{not valid json",
        _assistant_line({"input_tokens": 3, "cache_read_input_tokens": 200, "cache_creation_input_tokens": 7}),
    ]
    path.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")

    result = render_status.compute_context_fullness(repo_root, claude_projects_root=projects_dir.parent)

    assert result["available"] is True
    # The malformed line sits between two valid assistant messages and is
    # skipped rather than treated as fatal - the later, valid message wins.
    assert result["resident_tokens"] == 210


# ---------------------------------------------------------------------------
# Scenario 6: PLAN_PATTERN matches the live and frozen naming schemes.
# The 2026-08-15 fix - the prior ^\d{12}_PLAN_ pattern was written for the
# pre-migration timestamp-prefixed naming and matched no current PLAN after
# the AA-scheme migration, so render_stalled_audits silently scanned nothing.
# ---------------------------------------------------------------------------


def test_plan_pattern_matches_current_and_legacy_naming():
    assert render_status.PLAN_PATTERN.match("PLAN-AM6_rescope-rolling-board.md")
    assert render_status.PLAN_PATTERN.match("PLAN-AA0_id-scheme-overhaul.md")
    assert render_status.PLAN_PATTERN.match("PLAN-037_some-slug.md")
    assert not render_status.PLAN_PATTERN.match("INDEX.md")
    assert not render_status.PLAN_PATTERN.match("ADVICE-019_surfaces.md")
    assert not render_status.PLAN_PATTERN.match("INPUT-20260804-0200-notes.md")
    # The pre-migration timestamp-prefixed form the stale pattern was written
    # for no longer occurs in Workbench and is not matched by the new pattern.
    assert not render_status.PLAN_PATTERN.match("202605011900_PLAN_old.md")
