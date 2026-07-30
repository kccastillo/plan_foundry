"""Tests for _shared/ascii_git.py -- ASCII guard at the git boundary (PLAN-AD2 D9 / W0.7).

Covers: each named substitution, the NFKD accented-Latin fallback,
idempotency, empty string, pure-ASCII passthrough (byte-identical), a
realistic multi-line commit message, and the invariant that output always
satisfies s.encode("ascii") without error.
"""
# ascii-exempt (D18): this file deliberately contains non-ASCII.
# It is the ASCII sanitiser and its fixtures - the characters below ARE
# the test data. Sweeping them would break the guard that protects the
# rule. Do not remove this marker to 'tidy' the file.

from __future__ import annotations

import pathlib
import sys

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from ascii_git import has_non_ascii, to_ascii  # noqa: E402


# ---------------------------------------------------------------------------
# Named substitutions
# ---------------------------------------------------------------------------


class TestNamedSubstitutions:
    def test_right_arrow(self):
        assert to_ascii("checked → executing") == "checked -> executing"

    def test_left_arrow(self):
        assert to_ascii("executing ← checked") == "executing <- checked"

    def test_em_dash(self):
        assert to_ascii("a—b") == "a - b"

    def test_en_dash(self):
        assert to_ascii("a–b") == "a - b"

    def test_em_dash_collapses_double_space(self):
        # An em-dash already surrounded by spaces must not produce "a  -  b".
        assert to_ascii("a — b") == "a - b"

    def test_less_than_or_equal(self):
        assert to_ascii("x ≤ 5") == "x <= 5"

    def test_greater_than_or_equal(self):
        assert to_ascii("x ≥ 5") == "x >= 5"

    def test_left_single_quote(self):
        assert to_ascii("‘hello") == "'hello"

    def test_right_single_quote(self):
        assert to_ascii("don’t") == "don't"

    def test_left_double_quote(self):
        assert to_ascii("“hello”") == '"hello"'

    def test_right_double_quote_alone(self):
        assert to_ascii("hello”") == 'hello"'

    def test_ellipsis(self):
        assert to_ascii("wait…") == "wait..."

    def test_section_sign(self):
        assert to_ascii("§ 3.2") == "Sec. 3.2"

    def test_middle_dot(self):
        assert to_ascii("a·b") == "a-b"

    def test_non_breaking_space(self):
        assert to_ascii("a b") == "a b"
        assert not has_non_ascii(to_ascii("a b"))


# ---------------------------------------------------------------------------
# NFKD fallback for accented Latin
# ---------------------------------------------------------------------------


class TestNfkdFallback:
    def test_accented_word_degrades_to_base_letters(self):
        assert to_ascii("café") == "cafe"

    def test_accented_uppercase(self):
        assert to_ascii("Señor") == "Senor"

    def test_combining_diacritics_stripped(self):
        # "naive" with combining diaeresis over the i
        combining = "naïve"
        assert to_ascii(combining) == "naive"

    def test_truly_unencodable_becomes_question_mark(self):
        # A character with no ASCII-reachable decomposition (e.g. CJK)
        # must fall back to "?" rather than raise or vanish silently.
        result = to_ascii("plan 中文 test")
        result.encode("ascii")  # must not raise
        assert "?" in result


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    @pytest.mark.parametrize(
        "text",
        [
            "",
            "plain ascii commit message",
            "checked → executing — done",
            "café ‘quoted’ “text” …",
            "x ≤ 5 · y ≥ 3",
            "中文 test",
        ],
    )
    def test_double_application_equals_single(self, text):
        once = to_ascii(text)
        twice = to_ascii(once)
        assert once == twice


# ---------------------------------------------------------------------------
# Empty string / pure-ASCII passthrough
# ---------------------------------------------------------------------------


class TestPassthrough:
    def test_empty_string(self):
        assert to_ascii("") == ""

    def test_none_treated_as_empty(self):
        assert to_ascii(None) == ""

    def test_pure_ascii_byte_identical(self):
        text = "fix: tidy up the commit-msg hook wiring for consumers\n\nSee PLAN-AD2 W0.7.\n"
        result = to_ascii(text)
        assert result == text
        assert result.encode("ascii") == text.encode("ascii")

    def test_has_non_ascii_false_for_pure_ascii(self):
        assert has_non_ascii("plain text 123 !@#$%^&*()") is False

    def test_has_non_ascii_true(self):
        assert has_non_ascii("café") is True

    def test_has_non_ascii_empty_string(self):
        assert has_non_ascii("") is False


# ---------------------------------------------------------------------------
# Realistic multi-line commit message
# ---------------------------------------------------------------------------


class TestRealisticCommitMessage:
    def test_multiline_message_with_em_dash_subject(self):
        message = (
            "plan-pipeline: fix phase transition — checked to executing\n"
            "\n"
            "The auditor previously returned revision_needed even after the\n"
            "human’s override was recorded. This closes that gap — see\n"
            "PLAN-AD2 § W0.7 for the D9 rationale.\n"
            "\n"
            "# Please enter the commit message for your changes. Lines starting\n"
            "# with '#' will be ignored, and an empty message aborts the commit.\n"
        )
        result = to_ascii(message)

        result.encode("ascii")  # must not raise
        assert "—" not in result
        assert "’" not in result
        assert "§" not in result

        # Structure preserved: same number of lines, comment lines still present
        # and still start with "#".
        original_lines = message.splitlines()
        result_lines = result.splitlines()
        assert len(original_lines) == len(result_lines)
        for orig_line, res_line in zip(original_lines, result_lines):
            if orig_line.startswith("#"):
                assert res_line.startswith("#")

        assert "fix phase transition - checked to executing" in result
        assert "human's override" in result
        assert "Sec. W0.7" in result


# ---------------------------------------------------------------------------
# Global invariant: output always encodable as ASCII
# ---------------------------------------------------------------------------


class TestAsciiInvariant:
    @pytest.mark.parametrize(
        "text",
        [
            "",
            "plain",
            "→←—–≤≥‘’“”…§· ",
            "café naïve résumé",
            "中文あいう",
            "mixed ascii and — unicode 中文 together",
        ],
    )
    def test_output_always_ascii_encodable(self, text):
        result = to_ascii(text)
        # Must not raise.
        encoded = result.encode("ascii")
        assert isinstance(encoded, bytes)
