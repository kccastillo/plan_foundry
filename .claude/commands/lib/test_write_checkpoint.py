"""Unit tests for write_checkpoint.py's PLAN detection.

The 2026-08-15 fix: PLAN_PATTERN was ^\\d{12}_PLAN_, the pre-migration
timestamp-prefixed naming, so detect_active_ideate_thread matched no current
PLAN and /checkpoint never found an active ideate thread after the AA-scheme
migration. Every fixture here is synthetic and lives under tmp_path.
"""

from __future__ import annotations

import pathlib
import sys

_LIB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_LIB))

import write_checkpoint  # noqa: E402


def _write_plan(workbench_dir, filename, pipeline_phase, ideate_phase):
    """Write a minimal PLAN file. Pass ideate_phase=None to omit the field."""
    workbench_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", "type: plan", f"pipeline_phase: {pipeline_phase}"]
    if ideate_phase is not None:
        lines.append(f"ideate_phase: {ideate_phase}")
    lines.append("---")
    path = workbench_dir / filename
    path.write_text("\n".join(lines) + "\n\n# Body\n", encoding="utf-8")
    return path


def test_plan_pattern_matches_current_and_legacy_naming():
    assert write_checkpoint.PLAN_PATTERN.match("PLAN-AM6_rescope.md")
    assert write_checkpoint.PLAN_PATTERN.match("PLAN-AA0_overhaul.md")
    assert write_checkpoint.PLAN_PATTERN.match("PLAN-037_slug.md")
    assert not write_checkpoint.PLAN_PATTERN.match("INDEX.md")
    # The pre-migration timestamp-prefixed form the stale pattern matched.
    assert not write_checkpoint.PLAN_PATTERN.match("202605011900_PLAN_old.md")


def test_detect_active_ideate_thread_finds_current_scheme_plan(tmp_path):
    workbench = tmp_path / "Workbench"
    # Empty ideate_phase in the quoted form real PLANs use (phases 1-3 are lazy).
    _write_plan(workbench, "PLAN-AM7_some-idea.md", "drafting", '""')
    assert write_checkpoint.detect_active_ideate_thread(workbench) == "PLAN-AM7_some-idea"


def test_detect_active_ideate_thread_finds_plan_with_absent_ideate_phase(tmp_path):
    workbench = tmp_path / "Workbench"
    _write_plan(workbench, "PLAN-AM7_some-idea.md", "drafting", None)
    assert write_checkpoint.detect_active_ideate_thread(workbench) == "PLAN-AM7_some-idea"


def test_detect_ignores_non_drafting_plan(tmp_path):
    workbench = tmp_path / "Workbench"
    _write_plan(workbench, "PLAN-AM8_checked-idea.md", "checked", "complete")
    assert write_checkpoint.detect_active_ideate_thread(workbench) is None


def test_detect_ignores_drafting_plan_with_set_ideate_phase(tmp_path):
    workbench = tmp_path / "Workbench"
    _write_plan(workbench, "PLAN-AM9_mid-ideate.md", "drafting", "converge")
    assert write_checkpoint.detect_active_ideate_thread(workbench) is None
