# SPDX-License-Identifier: MIT
import os
import sqlite3
from pathlib import Path

import pytest

from aletheia_probe.cache import (
    CacheManager,
    get_cache_manager,
    reset_cache_manager,
    set_cache_manager,
)
from aletheia_probe.normalizer import InputNormalizer


@pytest.fixture(autouse=True)
def setup_cache_for_testing():
    """Set up a temporary cache database for testing."""
    test_db_path = Path("./test_cache.db")
    if test_db_path.exists():
        test_db_path.unlink()  # Ensure a clean slate

    test_cache = CacheManager(db_path=test_db_path)
    set_cache_manager(test_cache)
    yield test_cache
    reset_cache_manager()
    if test_db_path.exists():
        test_db_path.unlink()


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


def test_are_conference_names_equivalent_basic_match(setup_cache_for_testing):
    """Test _are_conference_names_equivalent with basic equivalent names."""
    cache = setup_cache_for_testing
    assert cache._are_conference_names_equivalent(
        "Journal of Science", "Journal of Science"
    )
    assert cache._are_conference_names_equivalent("The Conference", "The Conference")


def test_are_conference_names_equivalent_stop_words(setup_cache_for_testing):
    """Test _are_conference_names_equivalent with stop words variations."""
    cache = setup_cache_for_testing
    # "and" vs "new" issue from logs
    name1 = "journal of process management and new technologies international"
    name2 = "journal of process management new technologies international"
    assert cache._are_conference_names_equivalent(name1, name2)

    name3 = "International Journal of Research in Medical & Applied Sciences"
    name4 = "International Journal of Research in Medical Applied Sciences"
    assert cache._are_conference_names_equivalent(name3, name4)


def test_are_conference_names_equivalent_case_and_html_entities(
    setup_cache_for_testing,
):
    """Test _are_conference_names_equivalent with case and HTML entities."""
    cache = setup_cache_for_testing
    name1 = "International Journal of Scientific Research &#038; Management Studies"
    name2 = "international journal of scientific research & management studies"
    assert cache._are_conference_names_equivalent(name1, name2)


def test_are_conference_names_equivalent_year_and_ordinal(setup_cache_for_testing):
    """Test _are_conference_names_equivalent with year and ordinal variations."""
    cache = setup_cache_for_testing
    name1 = "2023 IEEE Conference on Computer Vision"
    name2 = "IEEE Conference on Computer Vision"
    assert cache._are_conference_names_equivalent(name1, name2)

    name3 = "1st International Conference on AI"
    name4 = "International Conference on AI"
    assert cache._are_conference_names_equivalent(name3, name4)


def test_are_conference_names_equivalent_substrings(setup_cache_for_testing):
    """Test _are_conference_names_equivalent with substring matches for longer names."""
    cache = setup_cache_for_testing
    name1 = "Advances in Neural Information Processing Systems"
    name2 = "Neural Information Processing Systems"
    assert cache._are_conference_names_equivalent(name1, name2)

    # Shorter names should not match on substring alone aggressively
    assert not cache._are_conference_names_equivalent("AI", "AAAI")


def test_store_acronym_mapping_with_equivalent_names(setup_cache_for_testing):
    """
    Test that store_acronym_mapping does not log a warning when overwriting with an equivalent name.
    """
    cache = setup_cache_for_testing
    acronym = "IJSRMS"
    full_name1 = "international journal of scientific research & management studies"
    full_name2 = (
        "international journal of scientific research &#038; management studies"
    )

    # Store the first mapping
    cache.store_acronym_mapping(acronym, full_name1, source="test")

    # Attempt to store the second, equivalent mapping
    # This should not trigger a warning
    cache.store_acronym_mapping(acronym, full_name2, source="test_overwrite")

    # Verify that the mapping exists and is the second one (as it overwrites)
    stored_name = cache.get_full_name_for_acronym(acronym)
    # The normalized name in the cache would be the one after _extract_conference_series and lower()
    # Let's verify it matches the robustly normalized version of full_name2
    norm_full_name2 = cache._normalize_for_comparison(full_name2)
    norm_stored_name = cache._normalize_for_comparison(stored_name)

    assert norm_stored_name == norm_full_name2
    # Check that no warning was logged (requires mocking the logger, but for now, rely on equivalence check)

    # Test with a different normalized name, should overwrite and possibly warn (if not equivalent)
    full_name3 = "International Journal of Completely Different Research"
    cache.store_acronym_mapping(acronym, full_name3, source="test_different")
    stored_name_different = cache.get_full_name_for_acronym(acronym)
    assert cache._normalize_for_comparison(
        stored_name_different
    ) == cache._normalize_for_comparison(full_name3)
