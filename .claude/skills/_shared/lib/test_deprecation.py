"""Tests for _shared/preflight.py's deprecation-ledger surface (PLAN-AH9).

preflight.py is stdlib-only and self-contained (see its module docstring);
these tests exercise it directly, not through sync.py's import wrapper.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import preflight  # noqa: E402


def _write_contract(bundle_root: pathlib.Path, deprecations: list) -> None:
    contract_dir = bundle_root / ".claude" / "skills" / "_shared"
    contract_dir.mkdir(parents=True, exist_ok=True)
    (contract_dir / "bundle-contract.json").write_text(
        json.dumps({"schema_version": 2, "deprecations": deprecations}),
        encoding="utf-8",
    )


def test_malformed_entry_skipped_not_fatal(tmp_path):
    """A-1: a malformed ledger entry is skipped individually and does not
    blind the reader to valid entries."""
    good = {
        "path": "bundle_copy.py::_is_under_known_subskill",
        "since": "v1.13.0",
        "removed_in": "v2.0.0",
        "replaced_by": "classify_stale",
        "note": "carries consumers with no receipt yet",
        "kind": "helper",
    }
    malformed_missing_field = {"path": "x", "kind": "helper"}
    malformed_bad_kind = dict(good, kind="not-a-real-kind")
    malformed_not_dict = "not a dict at all"
    malformed_non_string_value = dict(good, since=123)

    _write_contract(
        tmp_path,
        [
            malformed_not_dict,
            malformed_missing_field,
            good,
            malformed_bad_kind,
            malformed_non_string_value,
        ],
    )

    entries = preflight.read_deprecations(tmp_path)
    assert entries == [good]


def test_read_deprecations_empty_when_contract_absent(tmp_path):
    assert preflight.read_deprecations(tmp_path) == []


def test_shim_body_names_replacement_and_removal():
    """A-2: a shim body names the replacement and the removal version, and
    for a skill parses as valid frontmatter."""
    skill_entry = {
        "path": ".claude/skills/old-skill/SKILL.md",
        "since": "v1.13.0",
        "removed_in": "v2.0.0",
        "replaced_by": "new-skill",
        "note": "superseded by new-skill",
        "kind": "skill",
    }
    body = preflight.shim_body(skill_entry)
    assert "new-skill" in body
    assert "v2.0.0" in body
    assert body.startswith("---\n")
    lines = body.splitlines()
    assert lines[0] == "---"
    end_index = lines[1:].index("---") + 1
    frontmatter_lines = lines[1:end_index]
    assert any(line.startswith("name:") for line in frontmatter_lines)
    assert any(line.startswith("description:") for line in frontmatter_lines)

    reference_entry = dict(
        skill_entry, kind="reference", path=".claude/skills/_shared/old-ref.md"
    )
    ref_body = preflight.shim_body(reference_entry)
    assert "new-skill" in ref_body
    assert "v2.0.0" in ref_body
    assert not ref_body.startswith("---\n")


def test_shim_body_rejects_helper_kind():
    helper_entry = {
        "path": "bundle_copy.py::_is_under_known_subskill",
        "since": "v1.13.0",
        "removed_in": "v2.0.0",
        "replaced_by": "classify_stale",
        "note": "carries consumers with no receipt yet",
        "kind": "helper",
    }
    with pytest.raises(ValueError):
        preflight.shim_body(helper_entry)


def test_shipped_ledger_entries_wellformed():
    """A-5: every entry in the shipped ledger reads back well-formed.

    Asserts membership and shape, never a total. `read_deprecations` drops a
    malformed entry silently rather than raising, so the thing worth checking
    is that each named entry survived parsing with its fields intact - and a
    count would additionally go stale the next time anything is deprecated,
    which is operating rule 7.
    """
    repo_root = _SHARED.parent.parent.parent  # .claude/skills/_shared -> repo root
    entries = preflight.read_deprecations(repo_root)
    by_path = {e["path"]: e for e in entries}

    helper_path = ".claude/skills/_shared/bundle_copy.py::_is_under_known_subskill"
    assert helper_path in by_path, sorted(by_path)
    assert by_path[helper_path]["kind"] == "helper"

    for entry in entries:
        assert entry["kind"] in ("skill", "helper", "reference", "hook"), entry
        for field in ("replaced_by", "note", "since", "removed_in"):
            assert entry[field], f"{entry['path']} has empty {field}"


def test_shim_body_names_the_skill_directory_not_the_filename():
    """A skill shim must carry the skill's own name in its frontmatter.

    Regression guard, found on the first real file-level use of this path
    (2026-08-03). A skill ledger entry's path is
    `.claude/skills/<name>/SKILL.md`, so deriving the name from the file stem
    produced the literal "SKILL" for every skill. A release shimming more than
    one skill therefore shipped several skills all claiming the same name, and
    none of them resolvable by the name an operator would invoke.
    """
    for skill in ("convert-pdf", "foundry-research"):
        body = preflight.shim_body({
            "path": f".claude/skills/{skill}/SKILL.md",
            "since": "v1.15.0",
            "removed_in": "v2.0.0",
            "replaced_by": "somewhere else",
            "note": "moved",
            "kind": "skill",
        })
        assert f"name: {skill}\n" in body, (
            f"expected frontmatter 'name: {skill}'; got:\n{body}"
        )
        assert "name: SKILL\n" not in body, (
            f"shim named itself after the filename rather than the skill:\n{body}"
        )
