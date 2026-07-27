"""Tests for the widened findings[].code pattern in auditor-schema-v2.md (PLAN-AG2).

The pattern is read directly out of the schema markdown file (not hard-coded
here) so this test stays coupled to whatever the schema actually declares.
"""

from __future__ import annotations

import json
import pathlib
import re

_SCHEMA_PATH = pathlib.Path(__file__).resolve().parent.parent / "auditor-schema-v2.md"


def _extract_code_pattern() -> str:
    text = _SCHEMA_PATH.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r'"code":\s*\{[^}]*?"pattern":\s*"((?:[^"\\]|\\.)*)"',
        text,
        re.DOTALL,
    )
    assert match, "could not find findings[].code pattern in auditor-schema-v2.md"
    # The pattern is stored JSON-escaped (double backslashes) in the markdown's
    # fenced ```json block; decode it the same way json.loads would.
    return json.loads(f'"{match.group(1)}"')


CODE_PATTERN = re.compile(_extract_code_pattern())


class TestWidenedCodesValidate:
    """Representative codes from every admitted family must validate."""

    def test_sufficiency_code_validates(self):
        assert CODE_PATTERN.match("S001")

    def test_plan_safety_code_validates(self):
        assert CODE_PATTERN.match("H302")

    def test_substrate_fidelity_code_validates(self):
        assert CODE_PATTERN.match("SFV001")

    def test_platform_portability_code_validates(self):
        assert CODE_PATTERN.match("PPV003")

    def test_plan_sizing_code_validates(self):
        assert CODE_PATTERN.match("PSZ001")

    def test_falsifiability_code_with_suffix_validates(self):
        assert CODE_PATTERN.match("FAL001-a")

    def test_falsifiability_code_without_suffix_validates(self):
        assert CODE_PATTERN.match("FAL001")


class TestMalformedCodesRejected:
    """Genuinely malformed codes must still fail the widened pattern."""

    def test_unknown_family_rejected(self):
        assert not CODE_PATTERN.match("ZZZ42")

    def test_falsifiability_uppercase_suffix_rejected(self):
        assert not CODE_PATTERN.match("FAL001-A")

    def test_substrate_fidelity_short_digits_rejected(self):
        assert not CODE_PATTERN.match("SFV1")
