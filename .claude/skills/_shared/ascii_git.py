"""ascii_git.py -- ASCII sanitiser for the git boundary (PLAN-AD2 D9 / W0.7).

The scope is deliberately narrow, covering commit messages and tag
annotations ONLY and never file contents, because W0.1 preserved 968 prose
lines of non-ASCII (em-dashes, arrows) in this repository's documentation on
purpose and this helper must never undo that preservation. Callers invoke
this sanitiser at the single point where non-ASCII text actually causes harm,
the git boundary, where some Windows terminals and tools mangle such text.
This module is not a repository-wide lint.

Public surface:
    to_ascii(text: str) -> str
        A pure function that is deterministic, performs no I/O, and has no
        side effects. Idempotent, because to_ascii(to_ascii(x)) ==
        to_ascii(x) always holds.
    has_non_ascii(text: str) -> bool
        Returns True when `text` contains any character outside the ASCII
        range.
    main()
        The CLI entry point, where `python ascii_git.py <file>` rewrites
        that file in place, reading and writing with encoding="utf-8" and
        errors="replace".

Strategy:
    1. Named substitutions run first, so the common cases degrade to
       readable ASCII rather than mangled fallback text.
    2. Whatever remains is NFKD-normalised and stripped of combining marks,
       so accented Latin (e.g. "cafe" from "café") degrades to plain letters.
    3. Anything still unable to encode as ASCII is replaced with "?".
Sanitising never raises.
"""
# ascii-exempt (D18): this file deliberately contains non-ASCII.
# This module is the ASCII sanitiser and its fixtures, so the characters
# below ARE the test data. Sweeping them would break the guard that
# enforces the rule. Do not remove this marker to 'tidy' the file.

from __future__ import annotations

import sys
import unicodedata

# Named substitutions, applied first so the output is readable rather than
# mangled. Order matters only where overlaps could occur, and no two entries
# below overlap.
_NAMED_SUBSTITUTIONS: list[tuple[str, str]] = [
    ("→", "->"),      # RIGHTWARDS ARROW
    ("←", "<-"),      # LEFTWARDS ARROW
    ("—", " - "),     # EM DASH
    ("–", " - "),     # EN DASH
    ("≤", "<="),      # LESS-THAN OR EQUAL TO
    ("≥", ">="),      # GREATER-THAN OR EQUAL TO
    ("‘", "'"),       # LEFT SINGLE QUOTATION MARK
    ("’", "'"),       # RIGHT SINGLE QUOTATION MARK
    ("“", '"'),       # LEFT DOUBLE QUOTATION MARK
    ("”", '"'),       # RIGHT DOUBLE QUOTATION MARK
    ("…", "..."),     # HORIZONTAL ELLIPSIS
    ("§", "Sec."),    # SECTION SIGN
    ("·", "-"),       # MIDDLE DOT
    (" ", " "),       # NO-BREAK SPACE -> ordinary space
]


def has_non_ascii(text: str) -> bool:
    """Return True if `text` contains any character outside the ASCII range."""
    if not text:
        return False
    try:
        text.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def _collapse_double_spaces(text: str) -> str:
    """Collapse runs of 2+ ordinary spaces into one.

    Only the ordinary space character is affected, and never tabs or
    newlines, because the em-dash and en-dash substitutions above (" - ")
    are the source of the doubling being collapsed here, as in "a -- b"
    style sequences or a dash adjacent to an existing space.
    """
    while "  " in text:
        text = text.replace("  ", " ")
    return text


def to_ascii(text: str) -> str:
    """Sanitise `text` to pure ASCII. Deterministic, no I/O, never raises.

    1. Apply named substitutions, which give readable output for common
       punctuation.
    2. NFKD-normalise and drop combining marks, so accented Latin degrades
       to its base letter.
    3. Replace anything still non-ASCII with "?".

    Idempotent: to_ascii(to_ascii(x)) == to_ascii(x).
    """
    if text is None:
        return ""
    if text == "":
        return text

    result = text
    for src, dst in _NAMED_SUBSTITUTIONS:
        if src in result:
            result = result.replace(src, dst)

    result = _collapse_double_spaces(result)

    if not has_non_ascii(result):
        return result

    # NFKD-normalise, then drop combining marks so that accented Latin
    # degrades to its base letter (e.g. "e" from "é").
    normalised = unicodedata.normalize("NFKD", result)
    stripped = "".join(ch for ch in normalised if not unicodedata.combining(ch))

    # Final fallback: anything still unable to encode as ASCII becomes "?".
    out_chars = []
    for ch in stripped:
        if ord(ch) < 128:
            out_chars.append(ch)
        else:
            out_chars.append("?")
    final = "".join(out_chars)

    return _collapse_double_spaces(final)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: `python ascii_git.py <file>` rewrites `<file>` in place.

    Reads and writes with encoding="utf-8", errors="replace" so malformed
    bytes never raise. Returns 0 on success and non-zero only for a usage
    error such as a missing argument. A caller that must never fail, such as
    the commit-msg hook, should not rely on this exit code and should treat
    any error as "leave the file untouched".
    """
    args = sys.argv[1:] if argv is None else argv
    if not args:
        sys.stderr.write("usage: python ascii_git.py <file>\n")
        return 2

    path = args[0]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            original = fh.read()
    except OSError as exc:
        sys.stderr.write(f"ascii_git: could not read {path}: {exc}\n")
        return 1

    sanitised = to_ascii(original)

    if sanitised == original:
        return 0

    try:
        with open(path, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(sanitised)
    except OSError as exc:
        sys.stderr.write(f"ascii_git: could not write {path}: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
