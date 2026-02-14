# SPDX-License-Identifier: MIT
"""Database schema initialization for the cache system."""

from pathlib import Path

from ..enums import AssessmentType, NameType, UpdateStatus, UpdateType
from ..models import VenueType
from .connection_utils import get_configured_connection


# Schema version constants
SCHEMA_VERSION = 2  # Current schema version
MIN_COMPATIBLE_VERSION = 2  # Minimum version this code can work with


class SchemaVersionError(Exception):
    """Raised when database schema version is incompatible."""

    pass


def get_schema_version(db_path: Path) -> int | None:
    """Get current schema version from database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        Version number if found, None if schema_version table doesn't exist
    """
    with get_configured_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        if not cursor.fetchone():
            return None

        cursor.execute("SELECT version FROM schema_version LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else None


def set_schema_version(db_path: Path, version: int, description: str) -> None:
    """Set schema version in database.

    This replaces any existing version entries to ensure only one version is stored.

    Args:
        db_path: Path to the SQLite database file
        version: Version number to set
        description: Description of this schema version
    """
    with get_configured_connection(db_path) as conn:
        # Delete all existing versions first (we only want one version at a time)
        conn.execute("DELETE FROM schema_version")
        # Insert the new version
        conn.execute(
            """
            INSERT INTO schema_version (version, applied_at, description)
            VALUES (?, datetime('now'), ?)
            """,
            (version, description),
        )
        conn.commit()


def validate_schema_version(db_path: Path) -> None:
    """Validate that database schema version is compatible with current code.

    This is a convenience wrapper around check_schema_compatibility that can be
    called to validate the schema before performing operations on the database.

    Args:
        db_path: Path to the SQLite database file

    Raises:
        SchemaVersionError: If schema version is incompatible
    """
    if not db_path.exists():
        # Database doesn't exist yet, nothing to validate
        return

    check_schema_compatibility(db_path)


def check_schema_compatibility(db_path: Path) -> bool:
    """Check if database schema is compatible with current code.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        True if compatible

    Raises:
        SchemaVersionError: If schema version is incompatible
    """
    current_version = get_schema_version(db_path)

    if current_version is None:
        # Legacy database without versioning
        raise SchemaVersionError(
            f"Database schema version is unknown (legacy database detected).\n"
            f"This database needs to be migrated to schema version {SCHEMA_VERSION}.\n\n"
            f"To migrate: aletheia-probe db migrate\n"
            f"To start fresh: aletheia-probe db reset (WARNING: deletes all data)"
        )

    if current_version < MIN_COMPATIBLE_VERSION:
        raise SchemaVersionError(
            f"Database schema version ({current_version}) is too old.\n"
            f"Minimum required version: {MIN_COMPATIBLE_VERSION}\n"
            f"Current code version: {SCHEMA_VERSION}\n\n"
            f"To migrate: aletheia-probe db migrate\n"
            f"To start fresh: aletheia-probe db reset (WARNING: deletes all data)"
        )

    if current_version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"Database was created with a newer version of aletheia-probe.\n"
            f"Database schema version: {current_version}\n"
            f"This code supports up to: {SCHEMA_VERSION}\n\n"
            f"Please upgrade aletheia-probe:\n"
            f"  pip install --upgrade aletheia-probe"
        )

    return True


def init_database(db_path: Path, check_version: bool = False) -> None:
    """Initialize normalized database schema with version tracking.

    Args:
        db_path: Path to the SQLite database file
        check_version: If True, check schema compatibility for existing databases.
                      If False (default), skip version check during initialization.

    Raises:
        SchemaVersionError: If check_version=True and existing database has incompatible schema version
    """
    # Generate CHECK constraint strings from enums
    source_type_values = ", ".join(f"'{t.value}'" for t in AssessmentType)
    entity_type_values = ", ".join(f"'{t.value}'" for t in VenueType)
    update_status_values = ", ".join(f"'{s.value}'" for s in UpdateStatus)
    update_type_values = ", ".join(f"'{t.value}'" for t in UpdateType)
    name_type_values = ", ".join(f"'{t.value}'" for t in NameType)

    with get_configured_connection(db_path) as conn:
        cursor = conn.cursor()

        # Check if database already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        is_new_db = cursor.fetchone() is None

        if not is_new_db:
            # Existing database: drop obsolete legacy tables, then check compatibility
            cursor.execute("DROP TABLE IF EXISTS learned_abbreviations")
            # Detect old JSON-column schema (issn/variants as JSON) and drop it so
            # CREATE IF NOT EXISTS below rebuilds cleanly. Data must be re-imported.
            cursor.execute("PRAGMA table_info(venue_acronyms)")
            old_cols = {row[1] for row in cursor.fetchall()}
            if "issn" in old_cols or "variants" in old_cols:
                cursor.execute("DROP TABLE IF EXISTS venue_acronym_issns")
                cursor.execute("DROP TABLE IF EXISTS venue_acronym_variants")
                cursor.execute("DROP TABLE IF EXISTS venue_acronyms")
            conn.commit()
            if check_version:
                check_schema_compatibility(db_path)
            return

        # New database - create with current schema
        # Drop old venue_acronyms table if it exists (clean replacement)
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='venue_acronyms'"
        )
        if cursor.fetchone():
            cursor.execute("DROP TABLE venue_acronyms")
            conn.commit()


        conn.executescript(
            f"""
            -- Schema version tracking table
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                description TEXT NOT NULL
            );

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

            -- Venue acronyms: one row per (acronym, entity_type) pair.
            -- Canonical name and confidence imported from venue-acronyms-2025 pipeline.
            -- ISSNs and name variants are stored in dedicated child tables.
            CREATE TABLE IF NOT EXISTS venue_acronyms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acronym TEXT NOT NULL COLLATE NOCASE,
                entity_type TEXT NOT NULL,
                canonical TEXT NOT NULL,
                confidence_score REAL DEFAULT 0.0,
                source_file TEXT,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(acronym, entity_type),
                CHECK (entity_type IN ({entity_type_values}))
            );
            CREATE INDEX IF NOT EXISTS idx_venue_acronyms_acronym
                ON venue_acronyms(acronym);
            CREATE INDEX IF NOT EXISTS idx_venue_acronyms_canonical
                ON venue_acronyms(canonical);

            -- Venue name variants: all observed forms (expanded and abbreviated).
            -- One row per variant string, FK to venue_acronyms.
            CREATE TABLE IF NOT EXISTS venue_acronym_variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_acronym_id INTEGER NOT NULL,
                variant TEXT NOT NULL COLLATE NOCASE,
                FOREIGN KEY (venue_acronym_id)
                    REFERENCES venue_acronyms(id) ON DELETE CASCADE,
                UNIQUE(venue_acronym_id, variant)
            );
            CREATE INDEX IF NOT EXISTS idx_venue_acronym_variants_variant
                ON venue_acronym_variants(variant);
            CREATE INDEX IF NOT EXISTS idx_venue_acronym_variants_acronym_id
                ON venue_acronym_variants(venue_acronym_id);

            -- Venue ISSNs: known ISSN values for a venue.
            -- One row per ISSN, FK to venue_acronyms.
            CREATE TABLE IF NOT EXISTS venue_acronym_issns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_acronym_id INTEGER NOT NULL,
                issn TEXT NOT NULL,
                FOREIGN KEY (venue_acronym_id)
                    REFERENCES venue_acronyms(id) ON DELETE CASCADE,
                UNIQUE(venue_acronym_id, issn)
            );
            CREATE INDEX IF NOT EXISTS idx_venue_acronym_issns_issn
                ON venue_acronym_issns(issn);

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

            -- Custom journal lists (user-provided CSV/JSON files)
            -- Purpose: Persistent storage for custom list registrations
            -- Stores metadata about user-added journal lists to survive process restarts
            CREATE TABLE IF NOT EXISTS custom_lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_name TEXT UNIQUE NOT NULL,
                file_path TEXT NOT NULL,
                list_type TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (list_type IN ({source_type_values}))
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
            CREATE INDEX IF NOT EXISTS idx_custom_lists_list_name ON custom_lists(list_name);
            CREATE INDEX IF NOT EXISTS idx_custom_lists_enabled ON custom_lists(enabled);
        """
        )

        # Set initial schema version for new database
        set_schema_version(
            db_path,
            SCHEMA_VERSION,
            "Initial schema v2 with venue_acronym_variants and learned_abbreviations",
        )
