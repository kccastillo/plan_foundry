"""
bundle_semver.py - integer-tuple semver ordering for bundle tags.

PLAN-AH8. This module is named bundle_semver rather than semver because a
PyPI package named "semver" is installed on at least one developer machine,
and a bare "import semver" resolves to that package whenever _shared/ is not
first on sys.path. Running this PLAN's own V-2 before this module existed
exposed the collision, because the import succeeded and returned the wrong
module.

Semver ordering is required for correctness. Measured in this repo,
`git tag --list` ranks v1.9.1 above v1.13.0 lexically, so any string sort
reports a consumer four minors behind as current, and the fault stays
invisible until the minor version reaches double digits. Comparison in this
module is on parsed integer tuples only, and a lexical comparison anywhere
here is a defect.
"""

from __future__ import annotations

import re
from typing import Optional

_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def parse(tag: str) -> Optional[tuple[int, int, int]]:
    """Parse a tag like "v1.13.0" into (1, 13, 0). Returns None for anything
    not matching ^v(\\d+)\\.(\\d+)\\.(\\d+)$.
    """
    if not tag:
        return None
    match = _TAG_RE.match(tag)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def highest(tags: list[str]) -> Optional[str]:
    """Return the greatest tag string by integer-tuple comparison, or None
    when no tag in `tags` parses.
    """
    best_tag: Optional[str] = None
    best_tuple: Optional[tuple[int, int, int]] = None
    for tag in tags:
        parsed = parse(tag)
        if parsed is None:
            continue
        if best_tuple is None or parsed > best_tuple:
            best_tuple = parsed
            best_tag = tag
    return best_tag
