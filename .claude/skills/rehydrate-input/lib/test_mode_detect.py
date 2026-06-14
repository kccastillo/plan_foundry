"""
test_mode_detect.py -- Unit tests for mode_detect.detect_mode().

Four cases per PLAN-AE1 Step 1:
  1. input-only frontmatter -> "input"
  2. asset-only frontmatter -> "asset"
  3. both fields present   -> raises ValueError
  4. neither field present -> raises ValueError
"""
import pytest

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from mode_detect import detect_mode


def test_input_mode_from_integration_status():
    """A frontmatter with only integration_status returns 'input'."""
    fm = {"integration_status": "pending", "title": "Some advice"}
    assert detect_mode(fm) == "input"


def test_input_mode_integrated():
    """integration_status: integrated is also recognised as input mode."""
    fm = {"integration_status": "integrated", "title": "Some research"}
    assert detect_mode(fm) == "input"


def test_asset_mode_from_asset_id():
    """A frontmatter with only asset_id returns 'asset'."""
    fm = {
        "asset_id": "help-push-policy",
        "kind": "helper",
        "title": "Push Policy Helper",
    }
    assert detect_mode(fm) == "asset"


def test_both_fields_raises_value_error():
    """Frontmatter with both integration_status and asset_id raises ValueError (S1 mitigation)."""
    fm = {
        "integration_status": "pending",
        "asset_id": "help-something",
        "title": "Ambiguous file",
    }
    with pytest.raises(ValueError, match="ambiguous frontmatter"):
        detect_mode(fm)


def test_neither_field_raises_value_error():
    """Frontmatter with neither discriminator field raises ValueError."""
    fm = {"title": "Random file", "status": "open"}
    with pytest.raises(ValueError, match="unrecognised frontmatter"):
        detect_mode(fm)


def test_empty_frontmatter_raises_value_error():
    """Empty frontmatter dict raises ValueError."""
    with pytest.raises(ValueError, match="unrecognised frontmatter"):
        detect_mode({})
