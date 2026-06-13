"""Tests for audit-haiku-safe/lib/asset_frontmatter.py — PLAN-AD6 Step 2."""

from __future__ import annotations

import pathlib
import sys

import pytest

_LIB = pathlib.Path(__file__).resolve().parent
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from asset_frontmatter import validate_asset_frontmatter  # noqa: E402


def _valid_helper(**overrides):
    base = {
        "asset_id": "help-push-policy",
        "kind": "helper",
        "title": "Push Policy",
        "topic_tags": ["push", "policy"],
        "description": "Resolves push-policy for a PLAN.",
        "discoverable_via": ["plan-pipeline", "manual"],
        "created": "2026-05-26",
        "schema_version": 1,
    }
    base.update(overrides)
    return base


def _valid_reference(**overrides):
    base = {
        "asset_id": "ref-event-sourcing",
        "kind": "reference",
        "title": "Event Sourcing — A Primer",
        "topic_tags": ["event-sourcing", "primer"],
        "description": "Background on event sourcing patterns.",
        "discoverable_via": ["ideate-clarify"],
        "created": "2026-05-26",
        "schema_version": 1,
    }
    base.update(overrides)
    return base


class TestHappyPath:
    def test_valid_helper_no_findings(self):
        assert validate_asset_frontmatter("p.py", _valid_helper()) == []

    def test_valid_reference_no_findings(self):
        assert validate_asset_frontmatter("p.md", _valid_reference()) == []

    def test_no_created_field_allowed(self):
        fm = _valid_helper()
        fm.pop("created")
        # created is not in _REQUIRED_FIELDS for this validator;
        # last_consulted and consulted_by are tracked separately
        # but the AC2a required set does not include created. So
        # the only AFV007 check fires when created is present and
        # malformed.
        findings = validate_asset_frontmatter("p.py", fm)
        assert findings == []


class TestRequiredFields:
    @pytest.mark.parametrize(
        "field",
        [
            "asset_id",
            "kind",
            "title",
            "topic_tags",
            "description",
            "discoverable_via",
            "schema_version",
        ],
    )
    def test_missing_each_required_field(self, field):
        fm = _valid_helper()
        del fm[field]
        findings = validate_asset_frontmatter("p.py", fm)
        codes = [f["code"] for f in findings]
        assert "AFV001" in codes
        assert any(f["field"] == field for f in findings if f["code"] == "AFV001")

    def test_empty_string_field_flagged(self):
        fm = _valid_helper(description="")
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(
            f["code"] == "AFV001" and f["field"] == "description" for f in findings
        )

    def test_not_a_dict(self):
        findings = validate_asset_frontmatter("p.py", None)
        assert findings and findings[0]["code"] == "AFV001"


class TestKindEnum:
    def test_bad_kind(self):
        fm = _valid_helper(kind="widget")
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(f["code"] == "AFV002" for f in findings)

    def test_reference_kind_valid(self):
        fm = _valid_reference()
        assert validate_asset_frontmatter("p.md", fm) == []


class TestAssetIdPrefix:
    def test_helper_id_with_ref_prefix(self):
        fm = _valid_helper(asset_id="ref-push-policy")
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(f["code"] == "AFV003" for f in findings)

    def test_reference_id_with_help_prefix(self):
        fm = _valid_reference(asset_id="help-event-sourcing")
        findings = validate_asset_frontmatter("p.md", fm)
        assert any(f["code"] == "AFV003" for f in findings)

    def test_helper_id_with_help_prefix_ok(self):
        fm = _valid_helper(asset_id="help-anything-goes")
        # AFV003 should not fire (prefix matches). Other checks pass.
        findings = validate_asset_frontmatter("p.py", fm)
        assert all(f["code"] != "AFV003" for f in findings)


class TestSchemaVersion:
    def test_schema_version_zero_flagged(self):
        fm = _valid_helper(schema_version=0)
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(f["code"] == "AFV004" for f in findings)

    def test_schema_version_two_flagged(self):
        fm = _valid_helper(schema_version=2)
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(f["code"] == "AFV004" for f in findings)


class TestTopicTags:
    def test_uppercase_tag_flagged(self):
        fm = _valid_helper(topic_tags=["push", "Policy"])
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(f["code"] == "AFV005" for f in findings)

    def test_snake_case_tag_flagged(self):
        fm = _valid_helper(topic_tags=["push_policy"])
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(f["code"] == "AFV005" for f in findings)

    def test_space_in_tag_flagged(self):
        fm = _valid_helper(topic_tags=["push policy"])
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(f["code"] == "AFV005" for f in findings)

    def test_kebab_case_passes(self):
        fm = _valid_helper(topic_tags=["push-policy", "manual-override"])
        findings = validate_asset_frontmatter("p.py", fm)
        assert all(f["code"] != "AFV005" for f in findings)

    def test_topic_tags_must_be_list(self):
        fm = _valid_helper(topic_tags="push")
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(f["code"] == "AFV005" for f in findings)


class TestDiscoverableVia:
    def test_must_be_list_of_strings(self):
        fm = _valid_helper(discoverable_via=[1, 2])
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(f["code"] == "AFV006" for f in findings)


class TestCreatedDate:
    def test_bad_date_format_flagged(self):
        fm = _valid_helper(created="26 May 2026")
        findings = validate_asset_frontmatter("p.py", fm)
        assert any(f["code"] == "AFV007" for f in findings)

    def test_iso_date_passes(self):
        fm = _valid_helper(created="2026-05-26")
        findings = validate_asset_frontmatter("p.py", fm)
        assert all(f["code"] != "AFV007" for f in findings)
