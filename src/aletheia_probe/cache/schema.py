# SPDX-License-Identifier: MIT
"""Database schema initialization for the cache system."""

import sqlite3
from pathlib import Path

from ..enums import AssessmentType, NameType, UpdateStatus, UpdateType
from ..models import VenueType


def init_database(db_path: Path) -> None:
    """Initialize normalized database schema.

    Args:
        db_path: Path to the SQLite database file
    """
    # Generate CHECK constraint strings from enums
    source_type_values = ", ".join(f"'{t.value}'" for t in AssessmentType)
    entity_type_values = ", ".join(f"'{t.value}'" for t in VenueType)
    update_status_values = ", ".join(f"'{s.value}'" for s in UpdateStatus)
    update_type_values = ", ".join(f"'{t.value}'" for t in UpdateType)
    name_type_values = ", ".join(f"'{t.value}'" for t in NameType)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            f"""
            -- Core journals table (normalized, one entry per unique journal)
            CREATE TABLE IF NOT EXISTS journals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                normalized_name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                issn TEXT,
                eissn TEXT,
                publisher TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Journal name variants and aliases
            CREATE TABLE IF NOT EXISTS journal_names (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                name_type TEXT DEFAULT 'alias',
                source_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
                UNIQUE(journal_id, name),
                CHECK (name_type IN ({name_type_values}))
            );

            -- Journal URLs (one-to-many with journals)
            CREATE TABLE IF NOT EXISTS journal_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                url_type TEXT DEFAULT 'website',
                is_active BOOLEAN DEFAULT TRUE,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
                UNIQUE(journal_id, url),
                CHECK (url_type IN ('website'))
            );

            -- Data sources registry
            CREATE TABLE IF NOT EXISTS data_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                authority_level INTEGER DEFAULT 5,
                base_url TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (source_type IN ({source_type_values}))
            );

            -- Source assessments (many-to-many: journals <-> sources)
            CREATE TABLE IF NOT EXISTS source_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                assessment TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                first_listed_at TIMESTAMP,
                last_confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
                FOREIGN KEY (source_id) REFERENCES data_sources(id) ON DELETE CASCADE,
                UNIQUE(journal_id, source_id)
            );

            -- Venue acronym mappings (self-learning cache)
            -- Tracks acronym-to-name mappings for journals, conferences, and other venue types
            CREATE TABLE IF NOT EXISTS venue_acronyms (
                acronym TEXT NOT NULL COLLATE NOCASE,
                normalized_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (acronym, entity_type),
                CHECK (entity_type IN ({entity_type_values}))
            );
            CREATE INDEX IF NOT EXISTS idx_venue_acronyms_normalized_name ON venue_acronyms(normalized_name);
            CREATE INDEX IF NOT EXISTS idx_venue_acronyms_entity_type ON venue_acronyms(entity_type);

            -- Retraction statistics (purpose-built for RetractionWatch data)
            CREATE TABLE IF NOT EXISTS retraction_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal_id INTEGER NOT NULL,
                total_retractions INTEGER NOT NULL DEFAULT 0,
                recent_retractions INTEGER NOT NULL DEFAULT 0,
                very_recent_retractions INTEGER NOT NULL DEFAULT 0,
                retraction_types TEXT,
                top_reasons TEXT,
                publishers TEXT,
                first_retraction_date TEXT,
                last_retraction_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
                UNIQUE(journal_id)
            );

            -- Source updates tracking
            CREATE TABLE IF NOT EXISTS source_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                update_type TEXT NOT NULL,
                status TEXT NOT NULL,
                records_added INTEGER DEFAULT 0,
                records_updated INTEGER DEFAULT 0,
                records_removed INTEGER DEFAULT 0,
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES data_sources(id),
                CHECK (update_type IN ({update_type_values})),
                CHECK (status IN ({update_status_values}))
            );

            -- Assessment result cache
            -- Purpose: Domain-specific caching for structured journal/conference assessment results
            -- Stores AssessmentResult objects as JSON with associated query metadata
            -- Key structure: MD5 hash (32 hex chars) of normalized query parameters
            -- Use this for: Caching complete assessment operations and their results
            CREATE TABLE IF NOT EXISTS assessment_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash TEXT UNIQUE NOT NULL,
                query_input TEXT NOT NULL,
                assessment_result TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );

            -- Article retraction cache (for DOI-level retraction checking)
            CREATE TABLE IF NOT EXISTS article_retractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doi TEXT UNIQUE NOT NULL,
                is_retracted BOOLEAN NOT NULL DEFAULT FALSE,
                retraction_type TEXT,
                retraction_date TEXT,
                retraction_doi TEXT,
                retraction_reason TEXT,
                source TEXT NOT NULL,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );

            -- OpenAlex publication statistics cache
            -- Purpose: Structured caching for OpenAlex API responses with publication metrics
            -- Replaces generic key_value_cache usage for OpenAlex data
            -- Provides queryable columns instead of JSON strings
            CREATE TABLE IF NOT EXISTS openalex_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issn TEXT,
                normalized_journal_name TEXT,
                openalex_id TEXT,
                openalex_url TEXT,
                display_name TEXT,
                source_type TEXT,
                issn_l TEXT,
                issns TEXT,
                total_publications INTEGER DEFAULT 0,
                recent_publications INTEGER DEFAULT 0,
                recent_publications_by_year TEXT,
                publisher TEXT,
                first_publication_year INTEGER,
                last_publication_year INTEGER,
                cited_by_count INTEGER DEFAULT 0,
                is_in_doaj BOOLEAN DEFAULT FALSE,
                fetched_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                CHECK (issn IS NOT NULL OR normalized_journal_name IS NOT NULL),
                UNIQUE(issn, normalized_journal_name)
            );

            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_journals_display_name ON journals(display_name);
            CREATE INDEX IF NOT EXISTS idx_journals_normalized_name_lower ON journals(LOWER(normalized_name));
            CREATE INDEX IF NOT EXISTS idx_journals_display_name_lower ON journals(LOWER(display_name));
            CREATE INDEX IF NOT EXISTS idx_journals_issn ON journals(issn);
            CREATE INDEX IF NOT EXISTS idx_journals_eissn ON journals(eissn);
            CREATE INDEX IF NOT EXISTS idx_journal_names_name ON journal_names(name);
            CREATE INDEX IF NOT EXISTS idx_journal_names_journal_id ON journal_names(journal_id);
            CREATE INDEX IF NOT EXISTS idx_journal_urls_journal_id ON journal_urls(journal_id);
            CREATE INDEX IF NOT EXISTS idx_journal_urls_url ON journal_urls(url);
            CREATE INDEX IF NOT EXISTS idx_source_assessments_journal_id ON source_assessments(journal_id);
            CREATE INDEX IF NOT EXISTS idx_source_assessments_composite ON source_assessments(source_id, assessment);
            CREATE INDEX IF NOT EXISTS idx_retraction_statistics_journal_id ON retraction_statistics(journal_id);
            CREATE INDEX IF NOT EXISTS idx_assessment_cache_expires ON assessment_cache(expires_at);
            CREATE INDEX IF NOT EXISTS idx_article_retractions_doi ON article_retractions(doi);
            CREATE INDEX IF NOT EXISTS idx_article_retractions_expires ON article_retractions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_openalex_cache_issn ON openalex_cache(issn);
            CREATE INDEX IF NOT EXISTS idx_openalex_cache_journal_name ON openalex_cache(normalized_journal_name);
            CREATE INDEX IF NOT EXISTS idx_openalex_cache_expires ON openalex_cache(expires_at);
        """
        )
