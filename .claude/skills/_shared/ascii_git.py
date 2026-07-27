"""ascii_git.py -- ASCII sanitiser for the git boundary (PLAN-AD2 D9 / W0.7).

Scope, deliberately narrow: commit messages and tag annotations ONLY.
Never file contents -- W0.1 preserved 968 prose lines of non-ASCII (em-dashes,
arrows) in this repo's documentation on purpose, and this helper must never
undo that. It exists to be invoked at the single point where non-ASCII text
actually causes harm on the git boundary (some Windows terminals / tools
mangle it), not as a repo-wide lint.

Public surface:
    to_ascii(text: str) -> str
        Pure function. Deterministic, no I/O, no side effects. Idempotent:
        to_ascii(to_ascii(x)) == to_ascii(x) always holds.
    has_non_ascii(text: str) -> bool
        True if `text` contains any character outside the ASCII range.
    main()
        CLI entry point: `python ascii_git.py <file>` rewrites that file
        in place (read/write with encoding="utf-8", errors="replace").

Strategy:
    1. Named substitutions first, so the common cases degrade to readable
       ASCII rather than mangled fallback text.
    2. NFKD-normalise whatever remains and drop combining marks, so
       accented Latin (e.g. "cafe" from "café") degrades to plain letters.
    3. Anything still unable to encode as ASCII is replaced with "?".
Never raises.
"""
# ascii-exempt (D18): this file deliberately contains non-ASCII.
# It is the ASCII sanitiser and its fixtures - the characters below ARE
# the test data. Sweeping them would break the guard that protects the
# rule. Do not remove this marker to 'tidy' the file.

from __future__ import annotations

import sys
import unicodedata

# Named substitutions, applied first for readable (not mangled) output.
# Order matters only where overlaps could occur; none do here.
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

    Only touches the space character itself (not tabs/newlines), since the
    em/en-dash substitution above (" - ") is the source of the doubling this
    guards against (e.g. "a -- b" style sequences, or dash adjacent to an
    existing space).
    """
    while "  " in text:
        text = text.replace("  ", " ")
    return text


def to_ascii(text: str) -> str:
    """Sanitise `text` to pure ASCII. Deterministic, no I/O, never raises.

    1. Apply named substitutions (readable output for common punctuation).
    2. NFKD-normalise and drop combining marks (accented Latin -> base letter).
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

    # NFKD-normalise; drop combining marks so accented Latin degrades to
    # its base letter (e.g. "e" from "é").
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
    bytes never raise. Returns 0 on success, non-zero only for usage errors
    (missing argument) -- callers that must never fail (e.g. the commit-msg
    hook) should not rely on this exit code and should treat any error as
    "leave the file untouched".
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
