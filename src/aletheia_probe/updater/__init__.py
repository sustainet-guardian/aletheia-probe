# SPDX-License-Identifier: MIT
"""Data updater for downloading and processing journal lists."""

# Import dependencies used by sources and tests
from ..cache import DataSourceManager
from ..normalizer import input_normalizer
from ..validation import validate_issn
from .core import DataSource, DataUpdater, get_update_source_registry
from .sources import (
    AlgerianMinistrySource,
    BeallsListSource,
    CustomListSource,
    KscienGenericSource,
    KscienHijackedJournalsSource,
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


# Register KscienGenericSource with specific configuration for predatory-conferences
# This is registered here because it requires a specific publication_type parameter
get_update_source_registry().register_factory(
    "kscien_predatory_conferences",
    lambda: KscienGenericSource(publication_type="predatory-conferences"),
    default_config={},
)

# Global data updater instance
data_updater = DataUpdater()

# Register default sources from the registry
for source in get_update_source_registry().get_all_sources():
    data_updater.add_source(source)

__all__ = [
    # Core classes
    "DataSource",
    "DataUpdater",
    "data_updater",
    "get_update_source_registry",
    # Source implementations
    "AlgerianMinistrySource",
    "BeallsListSource",
    "CustomListSource",
    "KscienGenericSource",
    "KscienHijackedJournalsSource",
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
    "extract_year_from_text",
    "normalize_journal_name",
    "parse_date_string",
    "validate_issn",
    # Dependencies used by sources and tests
    "DataSourceManager",
    "input_normalizer",
]
