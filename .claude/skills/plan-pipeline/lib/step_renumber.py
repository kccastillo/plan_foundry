"""
step_renumber.py - Deterministic renumbering of a PLAN's `## Steps` block.

PLAN-AJ1. A finding's fingerprint is derived in part from its `location`, and
one in five stored locations is a bare Step ordinal (`Step 5`), so an
insertion into the `## Steps` block silently invalidates every fingerprint
that pointed at a shifted Step. This module renumbers the block
deterministically and reports the resulting old->new map; `step_remap.py`
carries that map into the fingerprint-keyed records.

D4 confines the rewrite to the leading `^\\d+\\.` token inside the extracted
`## Steps` block. It never touches prose, never touches text outside that
block, and never rewrites a cross-reference - `Step [0-9]` also matches the
procedure numbering inside unrelated documents, and rewriting those would
corrupt them.

D6 - the refusal predicate - refuses only when the block's ordinal sequence
is not strictly increasing after de-duplicating adjacent repeats, or when
there is no `## Steps` heading. A duplicate ordinal on its own is not a
refusal condition: `resolve_patches` anchors an insertion on the preceding
line, so inserting after Step 4 yields `4, 5, 5, 6` - the duplicate is the
signature of the insertion this module exists to repair, not a sign of
corruption. A restarting sub-run (`1, 2, 3, 1, 2, 3`) is refused, because an
unconditional walk would flatten it into one sequence and corrupt it.

Calling convention (D6, Context "Regex over a Steps block"): counting is done
per line with `.match` over `splitlines()` rather than `re.MULTILINE`
`findall`, because `STEP_LINE_RE` is shared and compiled without flags, and a
flag cannot be added to a precompiled pattern at call time.
"""

from __future__ import annotations

import re
import sys

# ---------------------------------------------------------------------------
# The single shared definition of a Step line. Consumed directly by
# render_status.py and plan_sizing.py so the two previously-drifted
# Step-counting regexes converge on one definition (PLAN-AJ1 Steps 14-15).
# ---------------------------------------------------------------------------
STEP_LINE_RE: re.Pattern[str] = re.compile(r'^(\d+)\.(\s+)')

_STEPS_HEADING_RE: re.Pattern[str] = re.compile(r'^## Steps\s*$', re.MULTILINE)
_NEXT_H2_RE: re.Pattern[str] = re.compile(r'^## ', re.MULTILINE)


class RefusedRenumber(Exception):
    """
    Raised by renumber_steps when the Steps block's ordinal sequence is not
    strictly increasing after de-duplicating adjacent repeats (D6). The
    caller (plan-pipeline dispatch.md section 4B) surfaces this to the human
    rather than repairing it - a restarting sub-run cannot be flattened
    safely.
    """


def extract_steps_block(text: str) -> tuple[str, int, int]:
    """
    Return (block_body, start_offset, end_offset) for the `## Steps` block in
    `text`. The block runs from the line after the `## Steps` heading to the
    character before the next `## ` heading at line start, or to end of text
    when no later heading exists.

    Raises ValueError("no ## Steps heading") when the heading is absent.
    """
    match = _STEPS_HEADING_RE.search(text)
    if match is None:
        raise ValueError("no ## Steps heading")

    heading_end = match.end()
    if text[heading_end:heading_end + 2] == '\r\n':
        block_start = heading_end + 2
    elif text[heading_end:heading_end + 1] == '\n':
        block_start = heading_end + 1
    else:
        block_start = heading_end

    remainder = text[block_start:]
    next_h2 = _NEXT_H2_RE.search(remainder)
    if next_h2 is None:
        block_end = len(text)
    else:
        block_end = block_start + next_h2.start()

    return text[block_start:block_end], block_start, block_end


def may_renumber(ordinals: list[int]) -> bool:
    """
    D6's refusal predicate. De-duplicate adjacent repeats, then return True
    only if every consecutive pair in the result is strictly increasing. An
    empty or single-element sequence returns True.
    """
    if not ordinals:
        return True

    deduped = [ordinals[0]]
    for value in ordinals[1:]:
        if value != deduped[-1]:
            deduped.append(value)

    if len(deduped) <= 1:
        return True

    return all(deduped[i] < deduped[i + 1] for i in range(len(deduped) - 1))


def renumber_steps(text: str) -> tuple[str, list[dict]]:
    """
    Extract the `## Steps` block, collect the ordinals of every line matching
    STEP_LINE_RE, and renumber them from 1 in order, preserving each line's
    captured whitespace verbatim.

    Raises RefusedRenumber when may_renumber(ordinals) is False - it does not
    return a partial result. A duplicate ordinal is not itself a refusal
    condition; it is the signature of the insertion this function repairs.

    Returns (new_text, remap) where remap is a list of {"old": int, "new":
    int} entries covering only the lines whose ordinal changed. When no
    ordinal changed, new_text is identical to text and remap is [].
    """
    block, start, end = extract_steps_block(text)
    lines = block.splitlines(keepends=True)

    step_line_indices: list[int] = []
    ordinals: list[int] = []
    for i, line in enumerate(lines):
        m = STEP_LINE_RE.match(line)
        if m:
            step_line_indices.append(i)
            ordinals.append(int(m.group(1)))

    if not may_renumber(ordinals):
        seq = ", ".join(str(o) for o in ordinals)
        raise RefusedRenumber(
            "ordinals are not strictly increasing after de-duplicating "
            f"adjacent repeats: {seq}"
        )

    remap: list[dict] = []
    next_ordinal = 1
    for line_idx, old_ordinal in zip(step_line_indices, ordinals):
        new_ordinal = next_ordinal
        if new_ordinal != old_ordinal:
            remap.append({"old": old_ordinal, "new": new_ordinal})
            line = lines[line_idx]
            m = STEP_LINE_RE.match(line)
            whitespace = m.group(2)
            rest = line[m.end():]
            lines[line_idx] = f"{new_ordinal}.{whitespace}{rest}"
        next_ordinal += 1

    new_block = "".join(lines)
    new_text = text[:start] + new_block + text[end:]
    return new_text, remap


def renumber_report(remap: list[dict]) -> str:
    """
    Return a one-line-per-entry human-readable report of the form
    "Step <old> -> Step <new>", or "no ordinal changes" for an empty remap.
    """
    if not remap:
        return "no ordinal changes"
    return "\n".join(f"Step {e['old']} -> Step {e['new']}" for e in remap)


def _ordinal_sequence(text: str) -> list[int]:
    """Best-effort ordinal sequence for --check reporting, after extraction succeeded."""
    block, _, _ = extract_steps_block(text)
    ordinals = []
    for line in block.splitlines():
        m = STEP_LINE_RE.match(line)
        if m:
            ordinals.append(int(m.group(1)))
    return ordinals


if __name__ == "__main__":
    import argparse
    import pathlib

    parser = argparse.ArgumentParser(
        description="Report (and optionally assert) which PLAN-*.md files under "
        "the given directories would be renumbered, refused, or left clean. "
        "Never writes."
    )
    parser.add_argument("--check", nargs="+", required=True, metavar="DIR")
    parser.add_argument("--expect-refused", default="", metavar="basename,...")
    parser.add_argument("--expect-renumber", default="", metavar="basename,...")
    parser.add_argument("--assert-no-other-changes", action="store_true")
    args = parser.parse_args()

    buckets: dict[str, list[str]] = {
        "no-steps-block": [],
        "refused": [],
        "would-renumber": [],
        "clean": [],
    }
    ordinal_seqs: dict[str, list[int]] = {}

    for directory in args.check:
        for path in sorted(pathlib.Path(directory).rglob("PLAN-*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            try:
                _, remap = renumber_steps(text)
            except ValueError:
                buckets["no-steps-block"].append(path.name)
                continue
            except RefusedRenumber:
                buckets["refused"].append(path.name)
                ordinal_seqs[path.name] = _ordinal_sequence(text)
                continue

            if remap:
                buckets["would-renumber"].append(path.name)
                ordinal_seqs[path.name] = _ordinal_sequence(text)
            else:
                buckets["clean"].append(path.name)

    for bucket_name in ("no-steps-block", "refused", "would-renumber", "clean"):
        print(f"{bucket_name}: {len(buckets[bucket_name])}")

    for bucket_name in ("would-renumber", "refused"):
        for fname in buckets[bucket_name]:
            seq = ", ".join(str(o) for o in ordinal_seqs.get(fname, []))
            print(f"  {fname}: {seq}")

    exit_code = 0

    if args.expect_refused:
        expected = set(args.expect_refused.split(","))
        actual = set(buckets["refused"])
        if expected != actual:
            print(f"expect-refused mismatch: expected {sorted(expected)}, got {sorted(actual)}")
            exit_code = 1

    if args.expect_renumber:
        expected = set(args.expect_renumber.split(","))
        actual = set(buckets["would-renumber"])
        if expected != actual:
            print(f"expect-renumber mismatch: expected {sorted(expected)}, got {sorted(actual)}")
            exit_code = 1

    if args.assert_no_other_changes:
        allowed = set(args.expect_refused.split(",") if args.expect_refused else [])
        allowed |= set(args.expect_renumber.split(",") if args.expect_renumber else [])
        other = (set(buckets["would-renumber"]) | set(buckets["refused"])) - allowed
        if other:
            print(f"unexpected changes outside named sets: {sorted(other)}")
            exit_code = 1

    sys.exit(exit_code)
