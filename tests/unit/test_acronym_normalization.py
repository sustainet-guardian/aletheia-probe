# SPDX-License-Identifier: MIT
"""Tests for acronym normalization functionality."""

import logging

import pytest

from aletheia_probe.cache import AcronymCache
from aletheia_probe.normalizer import InputNormalizer, normalize_for_comparison


@pytest.fixture
def normalizer():
    """Fixture for InputNormalizer."""
    return InputNormalizer()


def test_normalize_html_unescape(normalizer):
    """Test normalize with HTML entities."""
    text = "International Journal of Scientific Research &#038; Management Studies"
    cleaned = normalizer.normalize(text).normalized_venue.name
    assert (
        cleaned == "International Journal of Scientific Research & Management Studies"
    )

    text_accent = (
        "revista iberoamericana para la investigaci&oacute;n y el desarrollo educativo"
    )
    cleaned_accent = normalizer.normalize(text_accent).normalized_venue.name
    assert (
        cleaned_accent
        == "Revista Iberoamericana Para La Investigación Y El Desarrollo Educativo"
    )


def test_store_acronym_mapping_with_equivalent_names(isolated_test_cache, caplog):
    """
    Test that store_acronym_mapping does not log a warning for an equivalent name.

    On conflict the first mapping always wins (ON CONFLICT DO NOTHING), so a
    later name never replaces the stored one: an equivalent spelling is
    accepted silently, a genuinely different name is refused with a warning.
    """
    cache = AcronymCache(isolated_test_cache)
    acronym = "IJSRMS"
    entity_type = "journal"
    full_name1 = "international journal of scientific research & management studies"
    full_name2 = (
        "international journal of scientific research &#038; management studies"
    )

    # Store the first mapping
    cache.store_acronym_mapping(acronym, full_name1, entity_type, source="test")

    # Clear previous logs
    caplog.clear()

    # Attempt to store the second, equivalent mapping
    # This should not trigger a warning
    with caplog.at_level(logging.WARNING):
        cache.store_acronym_mapping(
            acronym, full_name2, entity_type, source="test_overwrite"
        )

    # Check that no warning was logged
    assert len(caplog.records) == 0

    # The first mapping is kept. full_name2 is only an equivalent spelling of
    # it, so the stored name matches either one after robust normalization.
    stored_name = cache.get_full_name_for_acronym(acronym, entity_type)
    assert normalize_for_comparison(stored_name) == normalize_for_comparison(full_name1)
    assert normalize_for_comparison(stored_name) == normalize_for_comparison(full_name2)

    # A genuinely different name conflicts and is refused with a warning
    full_name3 = "International Journal of Completely Different Research"

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        cache.store_acronym_mapping(
            acronym, full_name3, entity_type, source="test_different"
        )

    # Should warn now because names are different
    assert len(caplog.records) > 0
    assert "already maps to" in caplog.text

    # ... and the original mapping survives instead of being overwritten.
    stored_name_different = cache.get_full_name_for_acronym(acronym, entity_type)
    assert normalize_for_comparison(stored_name_different) == normalize_for_comparison(
        full_name1
    )
    assert normalize_for_comparison(stored_name_different) != normalize_for_comparison(
        full_name3
    )
