# SPDX-License-Identifier: MIT
"""Database schema initialization for the cache system."""

import sqlite3
from pathlib import Path


def init_database(db_path: Path) -> None:
    """Initialize normalized database schema.

    Args:
        db_path: Path to the SQLite database file
    """
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
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
                UNIQUE(journal_id, name)
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
                UNIQUE(journal_id, url)
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                PRIMARY KEY (acronym, entity_type)
            );
            CREATE INDEX IF NOT EXISTS idx_venue_acronyms_normalized_name ON venue_acronyms(normalized_name);
            CREATE INDEX IF NOT EXISTS idx_venue_acronyms_entity_type ON venue_acronyms(entity_type);

            -- Source metadata (replaces JSON metadata)
            CREATE TABLE IF NOT EXISTS source_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                metadata_key TEXT NOT NULL,
                metadata_value TEXT,
                data_type TEXT DEFAULT 'string',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
                FOREIGN KEY (source_id) REFERENCES data_sources(id) ON DELETE CASCADE,
                UNIQUE(journal_id, source_id, metadata_key)
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
                FOREIGN KEY (source_id) REFERENCES data_sources(id)
            );

            -- Assessment result cache
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
                metadata TEXT,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );

            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_journals_normalized_name ON journals(normalized_name);
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
            CREATE INDEX IF NOT EXISTS idx_source_assessments_source_id ON source_assessments(source_id);
            CREATE INDEX IF NOT EXISTS idx_source_assessments_composite ON source_assessments(source_id, assessment);
            CREATE INDEX IF NOT EXISTS idx_source_metadata_journal_source ON source_metadata(journal_id, source_id);
            CREATE INDEX IF NOT EXISTS idx_assessment_cache_expires ON assessment_cache(expires_at);
            CREATE INDEX IF NOT EXISTS idx_article_retractions_doi ON article_retractions(doi);
            CREATE INDEX IF NOT EXISTS idx_article_retractions_expires ON article_retractions(expires_at);
        """
        )
