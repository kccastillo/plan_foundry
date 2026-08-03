"""Tests for _shared/asset_id.py - PLAN-AD6 Step 1."""

from __future__ import annotations

import pathlib
import sys

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from asset_id import next_asset_id  # noqa: E402


class TestSlugDerivation:
    def test_simple_title_kebab_case(self):
        assert next_asset_id("helper", "Push Policy", []) == "help-push-policy"

    def test_lowercases(self):
        assert next_asset_id("helper", "Audit STAGES", []) == "help-audit-stages"

    def test_punctuation_collapses_to_hyphens(self):
        assert (
            next_asset_id("reference", "Event-Sourcing: A Primer!", [])
            == "ref-event-sourcing-a-primer"
        )

    def test_leading_trailing_punctuation_stripped(self):
        assert next_asset_id("helper", "  Hello  ", []) == "help-hello"

    def test_runs_of_non_alnum_collapse(self):
        assert (
            next_asset_id("helper", "foo___---  bar", [])
            == "help-foo-bar"
        )


class TestKindPrefix:
    def test_reference_prefix(self):
        assert next_asset_id("reference", "Foo", []).startswith("ref-")

    def test_helper_prefix(self):
        assert next_asset_id("helper", "Foo", []).startswith("help-")

    def test_invalid_kind_raises(self):
        with pytest.raises(ValueError, match="kind"):
            next_asset_id("widget", "Foo", [])


class TestCollisionResolution:
    def test_no_collision_returns_base(self):
        assert next_asset_id("helper", "Push Policy", []) == "help-push-policy"

    def test_first_collision_appends_2(self):
        existing = ["help-push-policy"]
        assert next_asset_id("helper", "Push Policy", existing) == "help-push-policy-2"

    def test_second_collision_appends_3(self):
        existing = ["help-push-policy", "help-push-policy-2"]
        assert next_asset_id("helper", "Push Policy", existing) == "help-push-policy-3"

    def test_collision_with_set_input(self):
        existing = {"help-foo", "help-foo-2"}
        assert next_asset_id("helper", "Foo", existing) == "help-foo-3"

    def test_existing_ids_other_kind_no_collision(self):
        # ref- and help- prefixes are independent namespaces in practice;
        # but collision detection is over the full id string, so a
        # help- id never collides with a ref- of the same slug.
        existing = ["ref-foo"]
        assert next_asset_id("helper", "Foo", existing) == "help-foo"


class TestIdempotency:
    def test_same_inputs_same_output(self):
        a = next_asset_id("helper", "Audit Stages", ["help-other"])
        b = next_asset_id("helper", "Audit Stages", ["help-other"])
        assert a == b == "help-audit-stages"

    def test_empty_slug_raises(self):
        with pytest.raises(ValueError, match="empty slug"):
            next_asset_id("helper", "   ---   ", [])
