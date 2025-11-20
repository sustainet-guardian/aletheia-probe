# SPDX-License-Identifier: MIT
"""Data updater for downloading and processing journal lists."""

# Import dependencies used by sources and tests
from ..cache import get_cache_manager
from ..normalizer import input_normalizer
from ..validation import extract_issn_from_text, validate_issn
from .core import DataSource, DataUpdater
from .sources import (
    AlgerianMinistrySource,
    BeallsListSource,
    CustomListSource,
    KscienHijackedJournalsSource,
    KscienPredatoryConferencesSource,
    KscienPublishersSource,
    KscienStandaloneJournalsSource,
    PredatoryJournalsSource,
    RetractionWatchSource,
    ScopusSource,
)
from .utils import (
    calculate_risk_level,
    clean_html_tags,
    clean_publisher_name,
    deduplicate_journals,
    extract_year_from_text,
    normalize_journal_name,
    parse_date_string,
)

# Global data updater instance
data_updater = DataUpdater()

# Register default sources
data_updater.add_source(BeallsListSource())
data_updater.add_source(AlgerianMinistrySource())
data_updater.add_source(PredatoryJournalsSource())
data_updater.add_source(KscienPredatoryConferencesSource())
data_updater.add_source(KscienStandaloneJournalsSource())
data_updater.add_source(KscienHijackedJournalsSource())
data_updater.add_source(KscienPublishersSource())
data_updater.add_source(RetractionWatchSource())
data_updater.add_source(ScopusSource())  # Optional - only active if file exists

__all__ = [
    # Core classes
    "DataSource",
    "DataUpdater",
    "data_updater",
    # Source implementations
    "AlgerianMinistrySource",
    "BeallsListSource",
    "CustomListSource",
    "KscienHijackedJournalsSource",
    "KscienPredatoryConferencesSource",
    "KscienPublishersSource",
    "KscienStandaloneJournalsSource",
    "PredatoryJournalsSource",
    "RetractionWatchSource",
    "ScopusSource",
    # Utility functions
    "calculate_risk_level",
    "clean_html_tags",
    "clean_publisher_name",
    "deduplicate_journals",
    "extract_issn_from_text",
    "extract_year_from_text",
    "normalize_journal_name",
    "parse_date_string",
    "validate_issn",
    # Dependencies used by sources and tests
    "get_cache_manager",
    "input_normalizer",
]
