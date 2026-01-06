# SPDX-License-Identifier: MIT
"""
Framework for fetching, normalizing, and synchronizing journal data sources.

This package provides the infrastructure for maintaining local copies of
authoritative journal lists, which are used by backends to assess publishing
integrity.

Main Components:
- core: DataSource abstraction and synchronization logic.
- sources: Implementations for Beall's List, Retraction Watch, Scopus,
  Algerian Ministry, and Kscien predatory lists.
- utils: Journal name normalization, HTML cleaning, and deduplication tools.
- sync_utils: Database synchronization and update management.
"""

# Import dependencies used by sources and tests
from ..cache import DataSourceManager
from ..normalizer import input_normalizer
from ..validation import validate_issn
from .core import DataSource
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
from .sync_utils import update_source_data
from .utils import (
    clean_html_tags,
    clean_publisher_name,
    deduplicate_journals,
    extract_year_from_text,
    normalize_journal_name,
    parse_date_string,
)


__all__ = [
    # Core classes and functions
    "DataSource",
    "update_source_data",
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
