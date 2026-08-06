"""Tests for _shared/writing_lint.py -- the mechanical prose-rule checker.

Covers: each of the four checks fires on a fixture built to trip it, and a
clean fixture passes all four. Also covers the ascii-exempt marker skipping
only the ascii check, and the CLI glob resolution.
"""
from __future__ import annotations

import pathlib
import sys

_SHARED = pathlib.Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from writing_lint import (  # noqa: E402
    check_ascii,
    check_it_boundary,
    check_persisted_count,
    check_semicolons,
    check_supplement_banned,
    find_supplement,
    lint_file,
    lint_text,
    parse_supplement_banned_phrases,
)


class TestIndividualChecks:
    def test_semicolon_fires(self):
        findings = check_semicolons("The file carries the date; the count.")
        assert findings == [(1, "semicolon found - write two sentences")]

    def test_semicolon_clean(self):
        assert check_semicolons("The file carries the date. It has no fault.") == []

    def test_ascii_fires_on_non_ascii_character(self):
        findings = check_ascii("The report notes a café nearby.")
        assert len(findings) == 1
        assert findings[0][0] == 1
        assert "non-ASCII" in findings[0][1]

    def test_ascii_clean_on_pure_ascii(self):
        assert check_ascii("Nothing here is outside the ASCII range.") == []

    def test_it_boundary_fires_on_opening(self):
        findings = check_it_boundary("It carries the date and the author.")
        assert len(findings) == 1
        assert "opens on 'it'" in findings[0][1]

    def test_it_boundary_fires_on_closing(self):
        findings = check_it_boundary("The file carries it.")
        assert len(findings) == 1
        assert "closes on 'it'" in findings[0][1]

    def test_it_boundary_clean_on_named_subject(self):
        assert check_it_boundary("The file carries the date and the author.") == []

    def test_it_boundary_ignores_possessive_its(self):
        # "Its" is a different word to the bare pronoun "it" the rule targets.
        assert check_it_boundary("Its scope stays narrow by design.") == []

    def test_persisted_count_fires_on_number_before_noun(self):
        findings = check_persisted_count("The board tracks the 24 items today.")
        assert len(findings) == 1
        assert "persisted count pattern" in findings[0][1]

    def test_persisted_count_fires_on_tally_of_number(self):
        findings = check_persisted_count("Keep a tally of 12 open items.")
        assert len(findings) == 1

    def test_persisted_count_clean_on_cap_or_threshold(self):
        # A cap or a bound is not a count of things that exist elsewhere,
        # per writing-style.md's Structure section - it is the fact itself.
        assert check_persisted_count("CLAUDE.md has a hard line-cap of 175.") == []

    def test_it_boundary_ignores_quoted_illustration(self):
        # A double-quoted mention of the banned construct is not a use of it.
        # writing-style.md itself names the tell this way: '"It is not just
        # X, it is Y."'
        quoted = '- **"It is not just X, it is Y."** Also "this is about it".'
        assert check_it_boundary(quoted) == []

    def test_it_boundary_ignores_blockquote_illustration(self):
        # A markdown blockquote is this repo's convention for a Before/After
        # example the document discusses rather than asserts.
        blockquote = "> It is important to note that this closes on it."
        assert check_it_boundary(blockquote) == []

    def test_it_boundary_still_fires_inside_a_quote_bearing_sentence(self):
        # Quote-stripping must not blind the check to a real violation that
        # merely sits near a quotation.
        mixed = 'The report says "the count is high" and ends flat on it.'
        findings = check_it_boundary(mixed)
        assert len(findings) == 1
        assert "closes on 'it'" in findings[0][1]


class TestLintText:
    def test_clean_fixture_passes_all_four(self):
        clean = (
            "The file carries the date and the author.\n"
            "The check re-derives the list on demand.\n"
        )
        assert lint_text(clean) == []

    def test_dirty_fixture_fails_all_four(self):
        dirty = (
            "It carries the date; the café note; and the 24 items.\n"
        )
        findings = lint_text(dirty)
        checks_fired = {f.check for f in findings}
        assert checks_fired == {"ascii", "semicolon", "it-boundary", "persisted-count"}

    def test_skip_ascii_flag_suppresses_only_ascii_check(self):
        dirty = "The café note has a semicolon; right here.\n"
        findings = lint_text(dirty, skip_ascii=True)
        checks_fired = {f.check for f in findings}
        assert checks_fired == {"semicolon"}


class TestSupplement:
    """FOUNDRYREQ-horse-chestnut-brickhouse-20260805-1715: a project may add
    a rule at .claude/writing-style-local.md. These cover the parser, the
    check it feeds, and the file-discovery path lint_file uses."""

    def test_parse_supplement_reads_only_the_named_section(self):
        text = (
            "# Project writing-style-local.md\n"
            "\n"
            "## Additional banned words or phrases\n"
            "- utilise\n"
            "- going forward\n"
            "\n"
            "## Some other section\n"
            "- not a banned phrase\n"
        )
        assert parse_supplement_banned_phrases(text) == ["utilise", "going forward"]

    def test_parse_supplement_empty_without_the_heading(self):
        text = "## Notes\n- utilise\n"
        assert parse_supplement_banned_phrases(text) == []

    def test_check_supplement_banned_fires_case_insensitively(self):
        findings = check_supplement_banned(
            "We should Utilise the existing helper.\n", ["utilise"]
        )
        assert len(findings) == 1
        assert "project-local banned phrase" in findings[0][1]

    def test_check_supplement_banned_no_phrases_is_a_no_op(self):
        assert check_supplement_banned("Utilise this.\n", []) == []

    def test_find_supplement_absent_by_default(self, tmp_path):
        assert find_supplement(tmp_path) is None

    def test_find_supplement_found_when_present(self, tmp_path):
        claude = tmp_path / ".claude"
        claude.mkdir()
        supplement = claude / "writing-style-local.md"
        supplement.write_text("## Additional banned words or phrases\n- utilise\n")
        assert find_supplement(tmp_path) == supplement

    def test_lint_file_folds_in_supplement_banned_phrase(self, tmp_path):
        claude = tmp_path / ".claude"
        claude.mkdir()
        (claude / "writing-style-local.md").write_text(
            "## Additional banned words or phrases\n- utilise\n"
        )
        target = tmp_path / "doc.md"
        target.write_text("We should utilise the helper.\n")

        findings = lint_file(target, supplement_root=tmp_path)

        assert any(f.check == "supplement-banned-phrase" for f in findings)

    def test_lint_file_clean_without_a_supplement(self, tmp_path):
        target = tmp_path / "doc.md"
        target.write_text("We should use the helper.\n")
        findings = lint_file(target, supplement_root=tmp_path)
        assert findings == []

    def test_lint_file_does_not_lint_the_supplement_against_itself(self, tmp_path):
        # A supplement whose own text contains one of its own banned phrases
        # is not double-counted as a target file finding when it is the file
        # being linted directly with itself as the discovered supplement.
        claude = tmp_path / ".claude"
        claude.mkdir()
        supplement = claude / "writing-style-local.md"
        supplement.write_text(
            "## Additional banned words or phrases\n- utilise\n"
        )
        findings = lint_file(supplement, supplement_root=tmp_path)
        assert not any(f.check == "supplement-banned-phrase" for f in findings)
