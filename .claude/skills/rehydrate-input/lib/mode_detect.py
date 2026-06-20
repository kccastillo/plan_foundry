"""
mode_detect.py -- Detect rehydrate-input operating mode from asset frontmatter.

Mode detection rules (AC2c D1c):
  - "input"  : frontmatter has `integration_status` field (ADVICE/RESEARCH inputs)
  - "asset"  : frontmatter has `asset_id` field (helpers/references under AD6 schema)
  - ValueError: both fields present (ambiguous frontmatter -- S1 mitigation)
  - ValueError: neither field present (not a recognised rehydrate-input target)
"""


def detect_mode(frontmatter: dict) -> str:
    """Return "input" or "asset" based on discriminator fields in frontmatter.

    Parameters
    ----------
    frontmatter : dict
        Parsed YAML frontmatter of the target file.

    Returns
    -------
    str
        "input" if `integration_status` is present (ADVICE/RESEARCH mode).
        "asset" if `asset_id` is present (helper/reference asset mode).

    Raises
    ------
    ValueError
        If both discriminator fields are present (ambiguous frontmatter).
        If neither discriminator field is present (unrecognised file type).
    """
    has_integration_status = "integration_status" in frontmatter
    has_asset_id = "asset_id" in frontmatter

    if has_integration_status and has_asset_id:
        raise ValueError(
            "ambiguous frontmatter -- both 'integration_status' and 'asset_id' fields "
            "present; cannot determine input vs asset mode. "
            "Remove the field that does not belong to this file type."
        )

    if has_integration_status:
        return "input"

    if has_asset_id:
        return "asset"

    raise ValueError(
        "unrecognised frontmatter -- neither 'integration_status' (ADVICE/RESEARCH input mode) "
        "nor 'asset_id' (helper/reference asset mode) field is present. "
        "Check that the file was authored by write-input or follows the AD6 asset schema."
    )
