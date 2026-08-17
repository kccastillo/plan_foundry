"""
asset_frontmatter.py - Asset-frontmatter schema validator (PLAN-AD6 / AC2a).

Exposes a single public function:

    validate_asset_frontmatter(path, frontmatter_dict) -> list[dict]

Each returned dict is a finding with fields:
    code       str   AFV001..AFV007
    level      str   "error" | "warning"
    category   str   "asset-frontmatter"
    location   str   the path (string) of the asset under validation
    field      str   the offending frontmatter field (or "" if N/A)
    message    str   human-readable description

Findings:
  AFV001 - Required field missing.
  AFV002 - `kind` is not in {"reference", "helper"}.
  AFV003 - `asset_id` does not match expected prefix for `kind`.
  AFV004 - `schema_version` is not 1.
  AFV005 - `topic_tags` is not a non-empty list of lowercase-hyphenated strings.
  AFV006 - `discoverable_via` is not a non-empty list of strings.
  AFV007 - `created` is not a YYYY-MM-DD string.

Design constraints (per PLAN-AD6):
  - Pure function - no filesystem I/O. Caller parses YAML and passes a dict.
  - `path` is accepted as either a str or a pathlib.Path; coerced to str for
    reporting only.
  - Returns an empty list when the frontmatter is valid.
"""

from __future__ import annotations

import re
from typing import Any

_REQUIRED_FIELDS = (
    "asset_id",
    "kind",
    "title",
    "topic_tags",
    "description",
    "discoverable_via",
    "schema_version",
)

_VALID_KINDS = {"reference", "helper"}
_KIND_PREFIX = {"reference": "ref-", "helper": "help-"}

_TAG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _finding(code: str, level: str, location: str, field: str, message: str) -> dict:
    return {
        "code": code,
        "level": level,
        "category": "asset-frontmatter",
        "location": location,
        "field": field,
        "message": message,
    }


def validate_asset_frontmatter(path: Any, frontmatter_dict: Any) -> list[dict]:
    """Validate an asset frontmatter dict against the AC2a schema.

    Args:
        path: the asset's path (str or pathlib.Path); used only for
            reporting in finding ``location`` fields.
        frontmatter_dict: the parsed YAML frontmatter as a mapping.

    Returns:
        A list of finding dicts. An empty list means the frontmatter
        is valid.
    """
    location = str(path)
    findings: list[dict] = []

    if not isinstance(frontmatter_dict, dict):
        findings.append(
            _finding(
                "AFV001",
                "error",
                location,
                "",
                "frontmatter is not a mapping (got "
                f"{type(frontmatter_dict).__name__})",
            )
        )
        return findings

    # AFV001 - required fields present and non-empty
    for field in _REQUIRED_FIELDS:
        if field not in frontmatter_dict:
            findings.append(
                _finding(
                    "AFV001",
                    "error",
                    location,
                    field,
                    f"required field {field!r} is missing",
                )
            )
            continue
        value = frontmatter_dict[field]
        if value is None or value == "" or value == [] or value == {}:
            findings.append(
                _finding(
                    "AFV001",
                    "error",
                    location,
                    field,
                    f"required field {field!r} is empty",
                )
            )

    # AFV002 - kind enum
    kind = frontmatter_dict.get("kind")
    if kind is not None and kind not in _VALID_KINDS:
        findings.append(
            _finding(
                "AFV002",
                "error",
                location,
                "kind",
                f"kind must be one of {sorted(_VALID_KINDS)}, got {kind!r}",
            )
        )

    # AFV003 - asset_id prefix matches kind
    asset_id = frontmatter_dict.get("asset_id")
    if isinstance(asset_id, str) and kind in _KIND_PREFIX:
        expected_prefix = _KIND_PREFIX[kind]
        if not asset_id.startswith(expected_prefix):
            findings.append(
                _finding(
                    "AFV003",
                    "error",
                    location,
                    "asset_id",
                    f"asset_id {asset_id!r} does not start with "
                    f"expected prefix {expected_prefix!r} for kind={kind!r}",
                )
            )

    # AFV004 - schema_version == 1
    schema_version = frontmatter_dict.get("schema_version")
    if schema_version is not None and schema_version != 1:
        findings.append(
            _finding(
                "AFV004",
                "error",
                location,
                "schema_version",
                f"schema_version must be 1, got {schema_version!r}",
            )
        )

    # AFV005 - topic_tags shape and casing
    topic_tags = frontmatter_dict.get("topic_tags")
    if topic_tags is not None and topic_tags != []:
        if not isinstance(topic_tags, list):
            findings.append(
                _finding(
                    "AFV005",
                    "error",
                    location,
                    "topic_tags",
                    f"topic_tags must be a list, got "
                    f"{type(topic_tags).__name__}",
                )
            )
        else:
            for tag in topic_tags:
                if not isinstance(tag, str) or not _TAG_RE.match(tag):
                    findings.append(
                        _finding(
                            "AFV005",
                            "error",
                            location,
                            "topic_tags",
                            f"topic tag {tag!r} is not lowercase-hyphenated "
                            "(expected pattern: ^[a-z0-9]+(-[a-z0-9]+)*$)",
                        )
                    )

    # AFV006 - discoverable_via shape
    disc = frontmatter_dict.get("discoverable_via")
    if disc is not None and disc != []:
        if not isinstance(disc, list) or not all(
            isinstance(v, str) and v for v in disc
        ):
            findings.append(
                _finding(
                    "AFV006",
                    "error",
                    location,
                    "discoverable_via",
                    "discoverable_via must be a non-empty list of strings",
                )
            )

    # AFV007 - created date format (only if present and non-empty)
    created = frontmatter_dict.get("created")
    if isinstance(created, str) and created and not _DATE_RE.match(created):
        findings.append(
            _finding(
                "AFV007",
                "error",
                location,
                "created",
                f"created {created!r} is not in YYYY-MM-DD format",
            )
        )

    return findings
