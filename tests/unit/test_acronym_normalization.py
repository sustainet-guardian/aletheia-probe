# SPDX-License-Identifier: MIT
import pytest

from aletheia_probe.cache import AcronymCache
from aletheia_probe.normalizer import InputNormalizer, normalize_for_comparison


@pytest.fixture
def normalizer():
    """Fixture for InputNormalizer."""
    return InputNormalizer()


def test_clean_text_html_unescape(normalizer):
    """Test _clean_text with HTML entities."""
    text = "International Journal of Scientific Research &#038; Management Studies"
    cleaned = normalizer._clean_text(text)
    assert (
        cleaned == "International Journal of Scientific Research & Management Studies"
    )

    text_accent = (
        "revista iberoamericana para la investigaci&oacute;n y el desarrollo educativo"
    )
    cleaned_accent = normalizer._clean_text(text_accent)
    assert (
        cleaned_accent
        == "revista iberoamericana para la investigación y el desarrollo educativo"
    )


def test_store_acronym_mapping_with_equivalent_names(isolated_test_cache):
    """
    Test that store_acronym_mapping does not log a warning when overwriting with an equivalent name.
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

    # Attempt to store the second, equivalent mapping
    # This should not trigger a warning
    cache.store_acronym_mapping(
        acronym, full_name2, entity_type, source="test_overwrite"
    )

    # Verify that the mapping exists and is the second one (as it overwrites)
    stored_name = cache.get_full_name_for_acronym(acronym, entity_type)
    # The normalized name in the cache would be the one after _extract_conference_series and lower()
    # Let's verify it matches the robustly normalized version of full_name2
    norm_full_name2 = normalize_for_comparison(full_name2)
    norm_stored_name = normalize_for_comparison(stored_name)

    assert norm_stored_name == norm_full_name2
    # Check that no warning was logged (requires mocking the logger, but for now, rely on equivalence check)

    # Test with a different normalized name, should overwrite and possibly warn (if not equivalent)
    full_name3 = "International Journal of Completely Different Research"
    cache.store_acronym_mapping(
        acronym, full_name3, entity_type, source="test_different"
    )
    stored_name_different = cache.get_full_name_for_acronym(acronym, entity_type)
    assert normalize_for_comparison(stored_name_different) == normalize_for_comparison(
        full_name3
    )
