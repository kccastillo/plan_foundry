"""Unit tests for dispatch_audit.py - the compliance-join audit.

Every fixture here is synthetic and is written under tmp_path. Nothing in
this file reads the real ~/.claude directory, because audit_project's
claude_projects_root parameter exists so that a test can point
claude_projects_root at a tmp_path tree instead, and every test below does
exactly that.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_SHARED))

import dispatch_audit  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _write_meta(subagents_dir: pathlib.Path, agent_id: str, meta: dict) -> None:
    (subagents_dir / f"agent-{agent_id}.meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )


def _write_jsonl_lines(subagents_dir: pathlib.Path, agent_id: str, lines: list[str]) -> None:
    (subagents_dir / f"agent-{agent_id}.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


_BASE_TS = datetime(2026, 1, 1, 0, 0, 0)


def _iso(offset_seconds: float) -> str:
    """Return a deterministic ISO-8601 UTC timestamp, offset_seconds after a
    fixed base instant, matching the "timestamp" field shape written on
    every real subagent transcript line."""
    stamp = _BASE_TS + timedelta(seconds=offset_seconds)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _assistant_line(model: str, timestamp: str | None = None) -> str:
    obj: dict = {"message": {"role": "assistant", "model": model}}
    if timestamp is not None:
        obj["timestamp"] = timestamp
    return json.dumps(obj)


def _timestamp_only_line(timestamp: str) -> str:
    """Return a line carrying no model, mimicking the initiating user turn
    that opens every real subagent transcript and sets the start of the
    agent's span."""
    return json.dumps({"timestamp": timestamp, "message": {"role": "user"}})


def _make_session(tmp_path: pathlib.Path, session_id: str = "session-1") -> pathlib.Path:
    session_dir = tmp_path / session_id
    (session_dir / "subagents").mkdir(parents=True)
    return session_dir


def _make_agents_dir(tmp_path: pathlib.Path, agents: dict[str, str]) -> pathlib.Path:
    """agents: {agent name: pinned model string}."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    for name, model in agents.items():
        (agents_dir / f"{name}.md").write_text(
            f"---\nname: {name}\nmodel: {model}\ndescription: synthetic test agent\n---\n\n# {name}\n",
            encoding="utf-8",
        )
    return agents_dir


_EMPTY_AGENTS_DIR_NAME = "no-agents-here"


# ---------------------------------------------------------------------------
# Scenario 1: a clean session
# ---------------------------------------------------------------------------


def test_clean_session_haiku_matches(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents,
        "clean1",
        {"agentType": "general-purpose", "description": "grep a thing", "toolUseId": "tu1", "spawnDepth": 1, "model": "haiku"},
    )
    _write_jsonl_lines(
        subagents,
        "clean1",
        [
            _timestamp_only_line(_iso(0)),
            _assistant_line("claude-haiku-4-5-20251001", _iso(5)),
        ],
    )

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    assert len(report.records) == 1
    rec = report.records[0]
    assert rec.agent_id == "clean1"
    assert rec.requested_tier == "haiku"
    assert rec.actual_tier == "haiku"
    assert rec.tier_mismatch is False
    assert rec.rung == "rung 1"
    assert rec.gaps == []


# ---------------------------------------------------------------------------
# Scenario 2: a tier mismatch between meta.json and the jsonl
# ---------------------------------------------------------------------------


def test_tier_mismatch_between_meta_and_jsonl(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents,
        "mismatch1",
        {"agentType": "general-purpose", "description": "should be sonnet", "toolUseId": "tu2", "spawnDepth": 1, "model": "sonnet"},
    )
    _write_jsonl_lines(subagents, "mismatch1", [_assistant_line("claude-opus-5")])

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    rec = report.records[0]
    assert rec.requested_tier == "sonnet"
    assert rec.actual_tier == "opus"
    assert rec.tier_mismatch is True
    assert any("does not match" in g for g in rec.gaps)


# ---------------------------------------------------------------------------
# Scenario 3: a missing sibling .jsonl
# ---------------------------------------------------------------------------


def test_missing_sibling_jsonl_reports_gap_not_exception(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents,
        "nojsonl1",
        {"agentType": "general-purpose", "description": "no jsonl written", "toolUseId": "tu3", "spawnDepth": 1, "model": "haiku"},
    )
    # No sibling .jsonl written at all.

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    rec = report.records[0]
    assert rec.actual_tier == "unknown"
    assert rec.actual_model_raw is None
    assert rec.tier_mismatch is None
    assert any("not found" in g for g in rec.gaps)
    assert rec.rung == "unavailable (actual tier unknown)"


# ---------------------------------------------------------------------------
# Scenario 4: a malformed JSON line in the .jsonl
# ---------------------------------------------------------------------------


def test_malformed_jsonl_line_is_skipped_not_fatal(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents,
        "malformed1",
        {"agentType": "general-purpose", "description": "one bad line then a good one", "toolUseId": "tu4", "spawnDepth": 1, "model": "opus"},
    )
    _write_jsonl_lines(
        subagents,
        "malformed1",
        ["{not valid json at all", _assistant_line("claude-opus-5")],
    )

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    rec = report.records[0]
    assert rec.actual_tier == "opus"
    assert rec.actual_model_raw == "claude-opus-5"
    assert any("malformed" in g for g in rec.gaps)


def test_malformed_jsonl_with_no_recoverable_model_reports_unknown(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents,
        "allbad1",
        {"agentType": "general-purpose", "description": "every line is broken", "toolUseId": "tu5", "spawnDepth": 1},
    )
    _write_jsonl_lines(subagents, "allbad1", ["{broken", "]] also broken"])

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    rec = report.records[0]
    assert rec.actual_tier == "unknown"
    assert any("malformed" in g for g in rec.gaps)


# ---------------------------------------------------------------------------
# Malformed meta.json itself
# ---------------------------------------------------------------------------


def test_malformed_meta_json_reports_gap_not_exception(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    (subagents / "agent-badmeta1.meta.json").write_text("{not json", encoding="utf-8")
    _write_jsonl_lines(subagents, "badmeta1", [_assistant_line("claude-sonnet-5")])

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    rec = report.records[0]
    assert rec.agent_type is None
    assert any("not valid JSON" in g for g in rec.gaps)


# ---------------------------------------------------------------------------
# Pipeline-fixed exemption
# ---------------------------------------------------------------------------


def test_pipeline_fixed_agent_is_exempt_from_the_ladder(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents,
        "pipe1",
        {"agentType": "sufficiency-auditor", "description": "opus-grade review", "toolUseId": "tu6", "spawnDepth": 1},
    )
    _write_jsonl_lines(subagents, "pipe1", [_assistant_line("claude-opus-5")])

    agents_dir = _make_agents_dir(tmp_path, {"sufficiency-auditor": "opus"})
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    rec = report.records[0]
    assert rec.pipeline_fixed is True
    assert rec.requested_tier == "opus"
    assert rec.requested_tier_source == "pinned in .claude/agents/sufficiency-auditor.md"
    assert "exempt" in rec.rung


def test_non_pipeline_agent_is_not_exempt(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents,
        "discretionary1",
        {"agentType": "general-purpose", "description": "an ordinary fan-out task", "toolUseId": "tu7", "spawnDepth": 1},
    )
    _write_jsonl_lines(
        subagents,
        "discretionary1",
        [
            _timestamp_only_line(_iso(0)),
            _assistant_line("claude-opus-5", _iso(5)),
        ],
    )

    agents_dir = _make_agents_dir(tmp_path, {"sufficiency-auditor": "opus"})
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    rec = report.records[0]
    assert rec.pipeline_fixed is False
    assert rec.requested_tier == "unspecified"
    assert rec.rung == "rung 3"  # a solo Opus dispatch, with no override, that is not pipeline-fixed


# ---------------------------------------------------------------------------
# Fable is outside the ladder
# ---------------------------------------------------------------------------


def test_fable_dispatch_reports_outside_the_ladder(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents,
        "fable1",
        {"agentType": "general-purpose", "description": "an escalation", "toolUseId": "tu8", "spawnDepth": 1, "model": "fable"},
    )
    _write_jsonl_lines(subagents, "fable1", [_assistant_line("claude-fable-5")])

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    rec = report.records[0]
    assert rec.actual_tier == "fable"
    assert "outside the ladder" in rec.rung


# ---------------------------------------------------------------------------
# Concurrency: derived from span overlap between agents' own timestamps,
# never from message grouping in a parent transcript (the harness writes
# one assistant message per Agent dispatch, so that grouping is always 1
# and would silently under-report every concurrent batch).
# ---------------------------------------------------------------------------


def test_concurrency_overlapping_spans_report_the_overlap(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    # conc1 runs [0, 20] and conc2 runs [5, 25], so the two spans overlap
    # throughout [5, 20].
    _write_meta(
        subagents, "conc1", {"agentType": "general-purpose", "toolUseId": "tuA", "spawnDepth": 1, "model": "sonnet"}
    )
    _write_jsonl_lines(
        subagents,
        "conc1",
        [_timestamp_only_line(_iso(0)), _assistant_line("claude-sonnet-5", _iso(20))],
    )
    _write_meta(
        subagents, "conc2", {"agentType": "general-purpose", "toolUseId": "tuB", "spawnDepth": 1, "model": "sonnet"}
    )
    _write_jsonl_lines(
        subagents,
        "conc2",
        [_timestamp_only_line(_iso(5)), _assistant_line("claude-sonnet-5", _iso(25))],
    )

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    assert report.concurrency_available is True
    by_id = {rec.agent_id: rec for rec in report.records}
    assert by_id["conc1"].concurrency_group_size == 2
    assert by_id["conc2"].concurrency_group_size == 2
    assert by_id["conc1"].rung == "rung 3"
    assert by_id["conc2"].rung == "rung 3"


def test_concurrency_disjoint_spans_each_report_one(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    # early1 runs [0, 10] and late1 runs [100, 110], so the two spans do not
    # overlap.
    _write_meta(
        subagents, "early1", {"agentType": "general-purpose", "toolUseId": "tuE", "spawnDepth": 1, "model": "sonnet"}
    )
    _write_jsonl_lines(
        subagents,
        "early1",
        [_timestamp_only_line(_iso(0)), _assistant_line("claude-sonnet-5", _iso(10))],
    )
    _write_meta(
        subagents, "late1", {"agentType": "general-purpose", "toolUseId": "tuL", "spawnDepth": 1, "model": "sonnet"}
    )
    _write_jsonl_lines(
        subagents,
        "late1",
        [_timestamp_only_line(_iso(100)), _assistant_line("claude-sonnet-5", _iso(110))],
    )

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    assert report.concurrency_available is True
    by_id = {rec.agent_id: rec for rec in report.records}
    assert by_id["early1"].concurrency_group_size == 1
    assert by_id["late1"].concurrency_group_size == 1
    assert by_id["early1"].rung == "rung 2"
    assert by_id["late1"].rung == "rung 2"


def test_concurrency_unavailable_for_agent_with_no_timestamps_siblings_still_resolve(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    # notime1 carries a jsonl with no "timestamp" field on any line at all.
    _write_meta(
        subagents, "notime1", {"agentType": "general-purpose", "toolUseId": "tuN", "spawnDepth": 1, "model": "sonnet"}
    )
    _write_jsonl_lines(subagents, "notime1", [_assistant_line("claude-sonnet-5")])
    # dated1 carries a normal timestamped span.
    _write_meta(
        subagents, "dated1", {"agentType": "general-purpose", "toolUseId": "tuD", "spawnDepth": 1, "model": "sonnet"}
    )
    _write_jsonl_lines(
        subagents,
        "dated1",
        [_timestamp_only_line(_iso(0)), _assistant_line("claude-sonnet-5", _iso(10))],
    )

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    # dated1 has a usable span, so the session as a whole reports concurrency
    # as available.
    assert report.concurrency_available is True
    by_id = {rec.agent_id: rec for rec in report.records}

    notime = by_id["notime1"]
    assert notime.concurrency_group_size is None
    assert any("concurrency unavailable" in g for g in notime.gaps)
    assert "unavailable" in notime.rung

    dated = by_id["dated1"]
    assert dated.concurrency_group_size == 1
    assert dated.rung == "rung 2"


def test_concurrency_unavailable_at_session_level_when_nothing_has_a_usable_span(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents, "notime2", {"agentType": "general-purpose", "toolUseId": "tuN2", "spawnDepth": 1, "model": "opus"}
    )
    _write_jsonl_lines(subagents, "notime2", [_assistant_line("claude-opus-5")])

    agents_dir = tmp_path / _EMPTY_AGENTS_DIR_NAME
    agents_dir.mkdir()
    report = dispatch_audit.audit_session(session_dir, agents_dir=agents_dir)

    assert report.concurrency_available is False
    assert any("concurrency unavailable for this session" in g for g in report.session_gaps)
    rec = report.records[0]
    assert rec.concurrency_group_size is None
    assert "unavailable" in rec.rung

    table = dispatch_audit._format_table(report)
    assert "UNAVAILABLE for this session" in table


# ---------------------------------------------------------------------------
# Project slug and session selection
# ---------------------------------------------------------------------------


def test_derive_project_slug_replaces_separators_and_underscores():
    slug = dispatch_audit.derive_project_slug(pathlib.Path("D:/projects/plan_foundry_dev"))
    assert slug == "D--projects-plan-foundry-dev"


def test_find_latest_session_dir_picks_most_recently_modified(tmp_path):
    older = tmp_path / "session-old"
    (older / "subagents").mkdir(parents=True)
    newer = tmp_path / "session-new"
    (newer / "subagents").mkdir(parents=True)
    # Force a distinct, ordered mtime rather than relying on write timing.
    import os
    import time

    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))

    chosen, notes = dispatch_audit.find_latest_session_dir(tmp_path)
    assert chosen == newer
    assert notes == []


def test_find_latest_session_dir_ignores_memory_directory(tmp_path):
    (tmp_path / "memory").mkdir()
    only_real = tmp_path / "session-real"
    (only_real / "subagents").mkdir(parents=True)

    chosen, notes = dispatch_audit.find_latest_session_dir(tmp_path)
    assert chosen == only_real


def test_find_latest_session_dir_reports_gap_when_absent(tmp_path):
    missing = tmp_path / "does-not-exist"
    chosen, notes = dispatch_audit.find_latest_session_dir(missing)
    assert chosen is None
    assert any("not found" in n for n in notes)


def test_audit_project_never_touches_real_home(tmp_path):
    """claude_projects_root is injected, so this test must not read the real
    ~/.claude directory, whatever is on the machine running the test."""
    session_dir = _make_session(tmp_path / "D--fake-project-slug", session_id="session-only")
    subagents = session_dir / "subagents"
    _write_meta(
        subagents, "iso1", {"agentType": "general-purpose", "toolUseId": "tuIso", "spawnDepth": 1, "model": "haiku"}
    )
    _write_jsonl_lines(subagents, "iso1", [_assistant_line("claude-haiku-4-5-20251001")])

    report = dispatch_audit.audit_project(
        project_root=pathlib.Path("/fake/project"),
        claude_projects_root=tmp_path,
        agents_dir=tmp_path / _EMPTY_AGENTS_DIR_NAME,
    )
    # The derived slug for "/fake/project" will not match "D--fake-project-slug",
    # so this exercises the "no session found" path without touching real home.
    assert report.session_dir is None
    assert report.records == []
    assert report.session_gaps


def test_audit_project_with_explicit_session_dir_bypasses_slug_lookup(tmp_path):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents, "explicit1", {"agentType": "general-purpose", "toolUseId": "tuE", "spawnDepth": 1, "model": "haiku"}
    )
    _write_jsonl_lines(subagents, "explicit1", [_assistant_line("claude-haiku-4-5-20251001")])

    report = dispatch_audit.audit_project(
        session_dir=session_dir,
        agents_dir=tmp_path / _EMPTY_AGENTS_DIR_NAME,
        claude_projects_root=tmp_path / "unused-projects-root",
    )
    assert len(report.records) == 1
    assert report.records[0].agent_id == "explicit1"


# ---------------------------------------------------------------------------
# CLI: reports rather than enforces
# ---------------------------------------------------------------------------


def test_main_returns_zero_even_with_a_tier_mismatch(tmp_path, capsys):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents,
        "cli_mismatch",
        {"agentType": "general-purpose", "toolUseId": "tuCli", "spawnDepth": 1, "model": "haiku"},
    )
    _write_jsonl_lines(subagents, "cli_mismatch", [_assistant_line("claude-opus-5")])

    exit_code = dispatch_audit.main(["--session-dir", str(session_dir)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "cli_mismatch" in out


def test_main_json_output_is_parseable(tmp_path, capsys):
    session_dir = _make_session(tmp_path)
    subagents = session_dir / "subagents"
    _write_meta(
        subagents, "cli_json", {"agentType": "general-purpose", "toolUseId": "tuJson", "spawnDepth": 1, "model": "haiku"}
    )
    _write_jsonl_lines(subagents, "cli_json", [_assistant_line("claude-haiku-4-5-20251001")])

    exit_code = dispatch_audit.main(["--session-dir", str(session_dir), "--json"])
    assert exit_code == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["records"][0]["agent_id"] == "cli_json"


def test_main_never_fails_when_session_dir_is_absent(tmp_path, capsys):
    missing = tmp_path / "no-such-session"
    exit_code = dispatch_audit.main(["--session-dir", str(missing)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "no subagents/ directory" in out


def test_cli_subprocess_exits_zero_on_a_missing_session(tmp_path):
    """Exercises the real __main__ entry point as a subprocess, matching how
    CI or a human would actually invoke this script."""
    missing = tmp_path / "no-such-session-either"
    result = subprocess.run(
        [sys.executable, str(_SHARED / "dispatch_audit.py"), "--session-dir", str(missing)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "no subagents/ directory" in result.stdout


# ---------------------------------------------------------------------------
# Rung classification, tested directly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pipeline_fixed,actual_tier,concurrency,expected_prefix",
    [
        (False, "haiku", 1, "rung 1"),
        (False, "haiku", 5, "rung 1"),
        (False, "sonnet", 1, "rung 2"),
        (False, "sonnet", 2, "rung 3"),
        (False, "opus", 1, "rung 3"),
        (False, "opus", 2, "rung 4"),
        (False, "opus", None, "unavailable"),
        (False, "unknown", 1, "unavailable"),
        (True, "opus", 2, "exempt"),
        (False, "fable", 1, "n/a"),
    ],
)
def test_rung_for_matches_the_ladder(pipeline_fixed, actual_tier, concurrency, expected_prefix):
    rung = dispatch_audit._rung_for(pipeline_fixed, actual_tier, concurrency)
    assert rung.startswith(expected_prefix)


# ---------------------------------------------------------------------------
# Pipeline-fixed agent loading
# ---------------------------------------------------------------------------


def test_load_pipeline_fixed_agents_reads_name_and_model(tmp_path):
    agents_dir = _make_agents_dir(tmp_path, {"plan-writer": "opus", "plan-retirer": "haiku"})
    fixed = dispatch_audit.load_pipeline_fixed_agents(agents_dir)
    assert fixed == {"plan-writer": "opus", "plan-retirer": "haiku"}


def test_load_pipeline_fixed_agents_absent_dir_returns_empty(tmp_path):
    fixed = dispatch_audit.load_pipeline_fixed_agents(tmp_path / "does-not-exist")
    assert fixed == {}
