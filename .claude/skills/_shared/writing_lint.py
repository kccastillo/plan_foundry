"""writing_lint.py -- mechanically checkable subset of writing-style.md.

FOUNDRYREQ-horse-chestnut-brickhouse-20260805-1702: nothing in this repo
checks a PLAN, a handoff or other Workbench prose against the rules
writing-style.md itself calls checkable rather than judgement-based.
ascii_git.py is scoped to the git commit-message boundary only, and
check-shipped-ascii.py checks the shipped bundle surface, not authored
Workbench prose.

This is a callable script, not a CI gate. A blind sweep over all of
Workbench/ would false-positive on conversation-register content and on
legitimate non-ASCII in retired documentation (PLAN-AD2 D9 note: 968 prose
lines of intentional non-ASCII exist by design), so nothing in
scripts/ci/run-all.sh invokes this against Workbench/ as a blocking check.
A skill or a human runs it directly against a chosen path.

Checks four rules from the Sentence-level rules section of
.claude/skills/_shared/writing-style.md:
    ascii            - character outside the ASCII range (line 116 range).
    semicolon        - "No semicolons. Write two sentences."
    it-boundary      - "Never open a sentence on 'it', never close one on it."
    persisted-count  - "Never write down a count of things that exist
                        elsewhere."

A fifth check is project-local and optional. writing-style.md's "Project-local
supplement" section names `.claude/writing-style-local.md` as the one file a
project may add its own rule to. When that file exists under the resolved
supplement root (the current working directory by default), its "Additional
banned words or phrases" list is folded in as a fifth check,
supplement-banned-phrase. The parser only ever reads that one list, so a
supplement can add a banned phrase and cannot touch, weaken or disable any of
the four checks above - there is no input path for that.

The judgement-based prose tells in writing-style.md (elegant variation,
uniform hedging, and so on) are out of scope. Those need a reader, not a
regular expression.

Usage:
    python writing_lint.py <path-or-glob> [<path-or-glob> ...]

Prints one line per finding: "<path>:<line>: <check> - <message>". Exits 1
if any file has a finding, 0 if every file is clean.

A file carrying the "ascii-exempt" marker (the same convention
check-shipped-ascii.py uses) skips the ascii check only for that file. A
semicolon or a persisted count is not made acceptable by the file also
holding legitimate non-ASCII prose, so the other three checks still run.
"""
from __future__ import annotations

import glob
import re
import sys
from dataclasses import dataclass
from pathlib import Path

EXEMPT_MARKER = "ascii-exempt"

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[A-Za-z']+")

# A double-quoted span (straight or curly) is a quotation, not an assertion -
# writing-style.md itself names the tell "It is not just X, it is Y" and
# names the banned persisted-count pattern by quoting the exact phrase it
# forbids. Stripped before the it-boundary check tokenises a sentence, so a
# mention of the construct is not mistaken for a use of it.
# Single quotes are left alone - they double as apostrophes and stripping
# them would mangle contractions and possessives.
_DOUBLE_QUOTE_RE = re.compile(r'"[^"]*"|“[^”]*”')


def _strip_quoted_spans(text: str) -> str:
    return _DOUBLE_QUOTE_RE.sub(" ", text)

# A digit or digit-comma-digit group next to a plural count noun ("24
# open items"), or the noun leading the number ("a tally of 12").
_PERSISTED_COUNT_RE = re.compile(
    r"\b\d[\d,]*\s+(?:tally|tallies|count|counts|skills|checks|files|plans|"
    r"items|tests|entries|reports|steps)\b"
    r"|\b(?:tally|count)\s+of\s+\d[\d,]*\b",
    re.IGNORECASE,
)


@dataclass
class Finding:
    path: str
    line: int
    check: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.check} - {self.message}"


def check_ascii(text: str) -> list[tuple[int, str]]:
    """Flag the first non-ASCII character on each offending line."""
    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        for ch in line:
            if ord(ch) > 127:
                findings.append((lineno, f"non-ASCII character U+{ord(ch):04X}"))
                break
    return findings


def check_semicolons(text: str) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        if ";" in line:
            findings.append((lineno, "semicolon found - write two sentences"))
    return findings


def check_it_boundary(text: str) -> list[tuple[int, str]]:
    """Flag a sentence that opens or closes on the bare word 'it'.

    Sentences are split per line, which is enough for a single-line fixture
    or a single-line prose paragraph and matches how the other checks here
    already operate line by line.
    """
    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            # Markdown blockquote: this repo's convention (writing-style.md's
            # own Before/After examples) for quoting illustrative prose the
            # document is discussing rather than asserting.
            continue
        scrubbed = _strip_quoted_spans(stripped)
        for sentence in _SENTENCE_SPLIT_RE.split(scrubbed):
            sentence = sentence.strip()
            if not sentence:
                continue
            words = _WORD_RE.findall(sentence)
            if not words:
                continue
            if words[0].lower() == "it":
                findings.append((lineno, f"sentence opens on 'it': {sentence!r}"))
            elif words[-1].lower() == "it":
                findings.append((lineno, f"sentence closes on 'it': {sentence!r}"))
    return findings


def check_persisted_count(text: str) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        match = _PERSISTED_COUNT_RE.search(line)
        if match:
            findings.append((lineno, f"persisted count pattern: {match.group(0)!r}"))
    return findings


CHECKS = {
    "ascii": check_ascii,
    "semicolon": check_semicolons,
    "it-boundary": check_it_boundary,
    "persisted-count": check_persisted_count,
}

# Project-local supplement (writing-style.md, "Project-local supplement").
SUPPLEMENT_RELPATH = Path(".claude") / "writing-style-local.md"
_SUPPLEMENT_HEADING_RE = re.compile(
    r"^#{1,6}\s*Additional banned words or phrases\s*$", re.IGNORECASE
)
_SUPPLEMENT_ITEM_RE = re.compile(r"^-\s+(.+?)\s*$")


def find_supplement(root: Path | None = None) -> Path | None:
    """Return the project's writing-style-local.md if it exists under root.

    root defaults to the current working directory, so a caller that knows
    the project root (the CI check does) should pass it explicitly rather
    than rely on cwd.
    """
    base = root if root is not None else Path.cwd()
    candidate = base / SUPPLEMENT_RELPATH
    return candidate if candidate.is_file() else None


def parse_supplement_banned_phrases(text: str) -> list[str]:
    """Read only the "Additional banned words or phrases" list.

    This is the entire read surface of a supplement file. No other heading
    or content in the file is parsed, which is what keeps a supplement to
    "add or tighten" - there is no field it could set to relax, disable or
    override one of the four checks above.
    """
    phrases: list[str] = []
    in_section = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            in_section = bool(_SUPPLEMENT_HEADING_RE.match(stripped))
            continue
        if in_section:
            match = _SUPPLEMENT_ITEM_RE.match(stripped)
            if match:
                phrases.append(match.group(1))
    return phrases


def check_supplement_banned(text: str, phrases: list[str]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    if not phrases:
        return findings
    for lineno, line in enumerate(text.split("\n"), start=1):
        low = line.lower()
        for phrase in phrases:
            if phrase.lower() in low:
                findings.append(
                    (lineno, f"project-local banned phrase: {phrase!r}")
                )
    return findings


def lint_text(
    text: str,
    path: str = "<text>",
    skip_ascii: bool = False,
    supplement_banned: list[str] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    for name, fn in CHECKS.items():
        if name == "ascii" and skip_ascii:
            continue
        for lineno, message in fn(text):
            findings.append(Finding(path=path, line=lineno, check=name, message=message))
    if supplement_banned:
        for lineno, message in check_supplement_banned(text, supplement_banned):
            findings.append(
                Finding(path=path, line=lineno, check="supplement-banned-phrase", message=message)
            )
    return sorted(findings, key=lambda f: (f.line, f.check))


def lint_file(path: Path, supplement_root: Path | None = None) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [Finding(path=str(path), line=0, check="read-error", message=str(exc))]
    skip_ascii = EXEMPT_MARKER in text
    supplement_banned: list[str] = []
    supplement = find_supplement(supplement_root)
    if supplement is not None and supplement.resolve() != path.resolve():
        supplement_banned = parse_supplement_banned_phrases(
            supplement.read_text(encoding="utf-8", errors="replace")
        )
    return lint_text(
        text, path=str(path), skip_ascii=skip_ascii, supplement_banned=supplement_banned
    )


def resolve_paths(args: list[str]) -> list[Path]:
    paths: list[Path] = []
    for arg in args:
        matches = glob.glob(arg, recursive=True)
        if matches:
            for m in matches:
                p = Path(m)
                if p.is_file():
                    paths.append(p)
        else:
            p = Path(arg)
            if p.is_file():
                paths.append(p)
    return paths


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        sys.stderr.write("usage: python writing_lint.py <path-or-glob> [...]\n")
        return 2

    paths = resolve_paths(args)
    if not paths:
        sys.stderr.write(f"writing_lint: no files matched {args!r}\n")
        return 2

    all_findings: list[Finding] = []
    for path in paths:
        all_findings.extend(lint_file(path))

    for finding in all_findings:
        print(str(finding))

    if all_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
