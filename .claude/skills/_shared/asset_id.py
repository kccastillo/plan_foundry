"""
asset_id.py - plan_foundry asset-ID allocator (PLAN-AD6 / AC2a).

Exposes:
    next_asset_id(kind, title, existing_ids) -> str

Allocates a stable, slug-derived, prefixed asset ID for the unified
reference/helper registry (per AC2 D2 + AC2a D3a).

Format
------
    <prefix>-<slug>[-<n>]

where:
    prefix = "ref"  if kind == "reference"
           = "help" if kind == "helper"
    slug   = kebab-case lowercase of the human title; non-alphanumerics
             collapsed to single hyphens; leading/trailing hyphens stripped
    -<n>   = appended only on collision with an existing ID; first
             collision -> "-2", next -> "-3", and so on

The slug is intended to be human-readable AND stable across renames at
the file level: once allocated, the ID is checked into a file's
frontmatter and never reissued. Renaming a file does NOT change its
asset_id; renaming the title MAY produce a different slug for new
assets but existing IDs are frozen.

This module is pure: it does not touch the filesystem. Callers are
responsible for persisting the returned ID into the asset's frontmatter
and for supplying the current set of existing IDs.
"""

from __future__ import annotations

import re

_KIND_PREFIX = {
    "reference": "ref",
    "helper": "help",
}

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    lowered = title.lower()
    collapsed = _SLUG_NON_ALNUM.sub("-", lowered)
    return collapsed.strip("-")


def next_asset_id(kind: str, title: str, existing_ids) -> str:
    """Return a stable asset_id for (kind, title), avoiding collisions.

    Args:
        kind: "reference" or "helper".
        title: human-readable asset title; slug derived from this.
        existing_ids: iterable of already-allocated asset IDs; the
            returned ID is guaranteed not to be in this set.

    Returns:
        Allocated asset_id string (e.g. "help-push-policy" or
        "ref-event-sourcing-2" on collision).

    Raises:
        ValueError: if kind is not in {"reference", "helper"} or if
            title slugifies to an empty string.
    """
    if kind not in _KIND_PREFIX:
        raise ValueError(
            f"kind must be 'reference' or 'helper', got {kind!r}"
        )
    slug = _slugify(title)
    if not slug:
        raise ValueError(
            f"title {title!r} produced an empty slug"
        )
    prefix = _KIND_PREFIX[kind]
    base = f"{prefix}-{slug}"
    taken = set(existing_ids)
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"
