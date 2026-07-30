"""Tests for preflight module (PLAN-AH8, guarantee 2).

conftest.py in this directory puts the real .claude/skills/_shared/ on
sys.path, so `import preflight` (module-level, in most tests here) resolves
to the real, shipped module. test_preflight_resolves_from_clone_not_installed_copy
below is the one exception - it deliberately manipulates sys.path and
sys.modules itself to prove the clone-vs-installed resolution property, and
must delete "preflight" from sys.modules first so an earlier test's import
in this same process cannot contaminate it.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SHARED))

import preflight  # noqa: E402


def _write_pin_file(target_claude: pathlib.Path, tag: str, schema_version) -> None:
    """schema_version pass "__absent__" to omit the key entirely (simulates
    a pin written before PLAN-AH8's Step 3)."""
    target_claude.mkdir(parents=True, exist_ok=True)
    lines = [f"sha={'a' * 40}", f"tag={tag}", "synced=2026-01-01T00:00:00Z"]
    if schema_version != "__absent__":
        lines.append(f"schema_version={schema_version}")
    (target_claude / preflight.PIN_FILENAME).write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _write_contract(bundle_path: pathlib.Path, schema_version) -> None:
    contract_dir = bundle_path / ".claude" / "skills" / "_shared"
    contract_dir.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"schema_version": schema_version, "deprecations": []})
    (contract_dir / preflight.CONTRACT_FILENAME).write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# A-5: verdict combination rule
# ---------------------------------------------------------------------------


def test_verdict_combination_rule(monkeypatch, tmp_path: pathlib.Path):
    """A-5: the verdict combination rule holds - major_step from either
    signal alone, and unavailable only when both are underivable."""
    target_claude = tmp_path / "target" / ".claude"
    bundle_path = tmp_path / "clone"

    # same: pin and clone agree on both signals.
    _write_pin_file(target_claude, tag="v1.2.0", schema_version=2)
    _write_contract(bundle_path, schema_version=2)
    monkeypatch.setattr(preflight, "_run_git", lambda args, cwd: "v1.2.0")
    assert preflight.compare_against_clone(target_claude, bundle_path) == "same"

    # minor_step: non-major tag difference, schema agrees.
    monkeypatch.setattr(preflight, "_run_git", lambda args, cwd: "v1.3.0")
    assert preflight.compare_against_clone(target_claude, bundle_path) == "minor_step"

    # major_step from the tag signal alone.
    monkeypatch.setattr(preflight, "_run_git", lambda args, cwd: "v2.0.0")
    assert preflight.compare_against_clone(target_claude, bundle_path) == "major_step"

    # major_step from the schema_version signal alone (tag agrees).
    monkeypatch.setattr(preflight, "_run_git", lambda args, cwd: "v1.2.0")
    _write_contract(bundle_path, schema_version=3)
    assert preflight.compare_against_clone(target_claude, bundle_path) == "major_step"

    # pin_predates_contract: the pin has no schema_version key at all -
    # the crossing sync that installs this very protection.
    _write_pin_file(target_claude, tag="v1.2.0", schema_version="__absent__")
    _write_contract(bundle_path, schema_version=2)
    assert (
        preflight.compare_against_clone(target_claude, bundle_path)
        == "pin_predates_contract"
    )

    # unavailable: both signals underivable - empty pin tag and schema_version,
    # no clone tag, malformed contract.
    _write_pin_file(target_claude, tag="", schema_version="")
    monkeypatch.setattr(preflight, "_run_git", lambda args, cwd: "")
    contract_dir = bundle_path / ".claude" / "skills" / "_shared"
    (contract_dir / preflight.CONTRACT_FILENAME).write_text("not json", encoding="utf-8")
    assert preflight.compare_against_clone(target_claude, bundle_path) == "unavailable"


def test_empty_schema_version_is_underivable_not_comparable(
    monkeypatch, tmp_path: pathlib.Path
):
    """An empty schema_version must not compare as a difference against a
    real value - it is underivable, and the verdict falls to the tag
    signal."""
    target_claude = tmp_path / "target" / ".claude"
    bundle_path = tmp_path / "clone"

    _write_pin_file(target_claude, tag="v1.0.0", schema_version="")
    _write_contract(bundle_path, schema_version=2)
    monkeypatch.setattr(preflight, "_run_git", lambda args, cwd: "v1.0.0")

    # Tag agrees, schema_version underivable on the pin side - falls to the
    # tag signal, which agrees, so "same" rather than a false major_step.
    assert preflight.compare_against_clone(target_claude, bundle_path) == "same"


def test_compare_against_clone_no_pin_is_unavailable(tmp_path: pathlib.Path):
    target_claude = tmp_path / "target" / ".claude"
    bundle_path = tmp_path / "clone"
    _write_contract(bundle_path, schema_version=2)
    assert preflight.compare_against_clone(target_claude, bundle_path) == "unavailable"


# ---------------------------------------------------------------------------
# A-4: resolves from the clone, not the installed copy
# ---------------------------------------------------------------------------


def test_preflight_resolves_from_clone_not_installed_copy(
    monkeypatch, tmp_path: pathlib.Path
):
    """A-4: the pre-flight resolves from the clone, not the consumer's
    installed copy. The fixture's installed _shared must genuinely predate
    preflight.py - the sanity import below must fail with ImportError, or
    this test could pass vacuously without exercising the resolution it
    claims to test."""
    monkeypatch.delitem(sys.modules, "preflight", raising=False)

    installed_shared = tmp_path / "installed" / "_shared"
    installed_shared.mkdir(parents=True)
    # Deliberately no preflight.py here - the installed copy predates the
    # helper (this is the crossing consumer's actual state).

    clone_shared = tmp_path / "clone" / "_shared"
    clone_shared.mkdir(parents=True)
    (clone_shared / "preflight.py").write_text(
        (_SHARED / "preflight.py").read_text(encoding="utf-8"), encoding="utf-8"
    )

    old_path = list(sys.path)
    try:
        # Remove the real _shared/ (inserted by this directory's conftest.py)
        # for the duration of this test - otherwise it would silently
        # satisfy the "import preflight" below regardless of what this test
        # is trying to isolate, defeating the sanity check.
        sys.path[:] = [
            p for p in sys.path if pathlib.Path(p).resolve() != _SHARED.resolve()
        ]
        sys.path.insert(0, str(installed_shared))

        with pytest.raises(ImportError):
            import preflight  # noqa: F401

        # The clone's _shared/ is inserted ahead of the installed one -
        # mirrors sync.py's bundle_shared sys.path.insert(0, ...) pattern.
        sys.path.insert(0, str(clone_shared))
        monkeypatch.delitem(sys.modules, "preflight", raising=False)
        import preflight as resolved  # noqa: F811

        assert hasattr(resolved, "compare_against_clone")
        assert pathlib.Path(resolved.__file__).resolve() == (
            clone_shared / "preflight.py"
        ).resolve()
    finally:
        sys.path[:] = old_path
        monkeypatch.delitem(sys.modules, "preflight", raising=False)


# ---------------------------------------------------------------------------
# A-10: imports no bundle_copy
# ---------------------------------------------------------------------------


def test_preflight_does_not_import_bundle_copy():
    """A-10: preflight.py imports no bundle_copy - the whole of blocker 1's
    fix, and the one property a later tidy-up is most likely to undo."""
    assert not hasattr(preflight, "bundle_copy")
    source = pathlib.Path(preflight.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+bundle_copy", source, re.M)


# ---------------------------------------------------------------------------
# scan_in_flight_plans
# ---------------------------------------------------------------------------


def _write_plan(workbench: pathlib.Path, name: str, pipeline_phase) -> None:
    workbench.mkdir(parents=True, exist_ok=True)
    if pipeline_phase is None:
        body = "no frontmatter here\n"
    else:
        body = f'---\npipeline_phase: "{pipeline_phase}"\n---\n\nbody\n'
    (workbench / name).write_text(body, encoding="utf-8")


def test_scan_in_flight_plans_filters_by_phase(tmp_path: pathlib.Path):
    workbench = tmp_path / "Workbench"
    _write_plan(workbench, "PLAN-A.md", "executing")
    _write_plan(workbench, "PLAN-B.md", "complete")
    _write_plan(workbench, "PLAN-C.md", "checked")
    _write_plan(workbench, "PLAN-D.md", None)  # malformed - no frontmatter

    found = preflight.scan_in_flight_plans(tmp_path)
    assert "Workbench/PLAN-A.md" in found
    assert "Workbench/PLAN-C.md" in found
    assert "Workbench/PLAN-B.md" not in found
    assert "Workbench/PLAN-D.md" not in found


def test_scan_in_flight_plans_no_workbench_returns_empty(tmp_path: pathlib.Path):
    assert preflight.scan_in_flight_plans(tmp_path / "nowhere") == []
