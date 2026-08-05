"""Tests for bundle_semver module (PLAN-AH8)."""

from __future__ import annotations

import pathlib
import sys

_SHARED = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SHARED))

import bundle_semver  # noqa: E402


def test_v1_13_0_ranks_above_v1_9_1():
    """A-1: semver ordering is by integer tuple, not string. v1.13.0 must
    rank above v1.9.1 - a lexical sort would report the opposite."""
    assert bundle_semver.highest(["v1.9.1", "v1.13.0"]) == "v1.13.0"
    assert bundle_semver.parse("v1.13.0") == (1, 13, 0)
    assert bundle_semver.parse("v1.9.1") == (1, 9, 1)
    assert bundle_semver.parse("v1.13.0") > bundle_semver.parse("v1.9.1")


def test_parse_rejects_nonmatching_input():
    assert bundle_semver.parse("nonsense") is None
    assert bundle_semver.parse("") is None
    assert bundle_semver.parse("1.2.3") is None
    assert bundle_semver.parse("v1.2") is None


def test_highest_returns_none_when_nothing_parses():
    assert bundle_semver.highest([]) is None
    assert bundle_semver.highest(["nonsense", "also-nonsense"]) is None


def test_highest_ignores_unparseable_entries():
    assert bundle_semver.highest(["v1.0.0", "nonsense", "v2.0.0"]) == "v2.0.0"


def test_highest_with_single_tag():
    assert bundle_semver.highest(["v0.5.0"]) == "v0.5.0"
