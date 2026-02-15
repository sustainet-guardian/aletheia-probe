# SPDX-License-Identifier: MIT
"""Database schema initialization for the cache system."""

from pathlib import Path

from ..enums import AssessmentType, NameType, UpdateStatus, UpdateType
from ..models import VenueType
from .connection_utils import get_configured_connection


# Schema version constants
SCHEMA_VERSION = 5  # Current schema version
MIN_COMPATIBLE_VERSION = 5  # Minimum version this code can work with


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
            f"Database schema is from an old version of aletheia-probe (pre-1.0) "
            f"and cannot be used with this version (requires schema {SCHEMA_VERSION}).\n\n"
            f"Please delete the database and run sync again:\n"
            f"  rm {db_path}\n"
            f"  aletheia-probe sync"
        )

    if current_version < MIN_COMPATIBLE_VERSION:
        raise SchemaVersionError(
            f"Database schema version ({current_version}) is too old "
            f"(requires {SCHEMA_VERSION}).\n\n"
            f"Please delete the database and run sync again:\n"
            f"  rm {db_path}\n"
            f"  aletheia-probe sync"
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


def init_database(db_path: Path) -> None:
    """Initialize normalized database schema with version tracking.

    For existing databases, the schema version must match SCHEMA_VERSION exactly.
    Pre-1.0: no migration support — if the schema is outdated, delete the database
    and run sync again.

    Args:
        db_path: Path to the SQLite database file

    Raises:
        SchemaVersionError: If existing database has an incompatible schema version
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
            # Existing database: version must match. No migration in pre-1.0.
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

            -- ROR snapshot metadata for local identity registry imports
            CREATE TABLE IF NOT EXISTS ror_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ror_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                release_date TEXT NOT NULL,
                source_url TEXT NOT NULL,
                sha256 TEXT,
                record_count INTEGER NOT NULL,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN NOT NULL DEFAULT FALSE
            );

            -- Core ROR organization records
            CREATE TABLE IF NOT EXISTS ror_organizations (
                ror_id TEXT PRIMARY KEY,
                snapshot_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                established INTEGER,
                country_code TEXT,
                city TEXT,
                lat REAL,
                lng REAL,
                org_types_json TEXT NOT NULL,
                FOREIGN KEY (snapshot_id) REFERENCES ror_snapshots(id)
            );

            -- All names/aliases/acronyms for each organization
            CREATE TABLE IF NOT EXISTS ror_names (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ror_id TEXT NOT NULL,
                value TEXT NOT NULL,
                value_normalized TEXT NOT NULL,
                lang TEXT,
                name_types_json TEXT NOT NULL,
                FOREIGN KEY (ror_id) REFERENCES ror_organizations(ror_id) ON DELETE CASCADE
            );

            -- Organization domains for fast domain-based lookups
            CREATE TABLE IF NOT EXISTS ror_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ror_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                domain_normalized TEXT NOT NULL,
                FOREIGN KEY (ror_id) REFERENCES ror_organizations(ror_id) ON DELETE CASCADE,
                UNIQUE(ror_id, domain_normalized)
            );

            -- Organization links (website, wikipedia, etc.)
            CREATE TABLE IF NOT EXISTS ror_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ror_id TEXT NOT NULL,
                link_type TEXT NOT NULL,
                url TEXT NOT NULL,
                host_normalized TEXT,
                FOREIGN KEY (ror_id) REFERENCES ror_organizations(ror_id) ON DELETE CASCADE
            );

            -- External identifiers (wikidata, isni, fundref, ...)
            CREATE TABLE IF NOT EXISTS ror_external_ids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ror_id TEXT NOT NULL,
                id_type TEXT NOT NULL,
                preferred_value TEXT,
                all_values_json TEXT NOT NULL,
                FOREIGN KEY (ror_id) REFERENCES ror_organizations(ror_id) ON DELETE CASCADE
            );

            -- Parent/child/related relationships between organizations
            CREATE TABLE IF NOT EXISTS ror_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ror_id TEXT NOT NULL,
                related_ror_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                related_label TEXT,
                FOREIGN KEY (ror_id) REFERENCES ror_organizations(ror_id) ON DELETE CASCADE
            );

            -- Journal-to-ROR link evidence (references journals.id)
            CREATE TABLE IF NOT EXISTS journal_ror_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal_id INTEGER NOT NULL,
                ror_id TEXT NOT NULL,
                match_status TEXT NOT NULL,
                confidence REAL NOT NULL,
                matching_method TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                snapshot_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
                FOREIGN KEY (ror_id) REFERENCES ror_organizations(ror_id),
                FOREIGN KEY (snapshot_id) REFERENCES ror_snapshots(id),
                UNIQUE(journal_id, ror_id, snapshot_id)
            );

            -- Conference-to-ROR link evidence (references journals.id for now)
            CREATE TABLE IF NOT EXISTS conference_ror_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conference_id INTEGER NOT NULL,
                ror_id TEXT NOT NULL,
                match_status TEXT NOT NULL,
                confidence REAL NOT NULL,
                matching_method TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                snapshot_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conference_id) REFERENCES journals(id) ON DELETE CASCADE,
                FOREIGN KEY (ror_id) REFERENCES ror_organizations(ror_id),
                FOREIGN KEY (snapshot_id) REFERENCES ror_snapshots(id),
                UNIQUE(conference_id, ror_id, snapshot_id)
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
            CREATE INDEX IF NOT EXISTS idx_ror_snapshots_active ON ror_snapshots(is_active);
            CREATE INDEX IF NOT EXISTS idx_ror_org_snapshot ON ror_organizations(snapshot_id);
            CREATE INDEX IF NOT EXISTS idx_ror_names_normalized ON ror_names(value_normalized);
            CREATE INDEX IF NOT EXISTS idx_ror_names_ror_id ON ror_names(ror_id);
            CREATE INDEX IF NOT EXISTS idx_ror_domains_normalized ON ror_domains(domain_normalized);
            CREATE INDEX IF NOT EXISTS idx_ror_domains_ror_id ON ror_domains(ror_id);
            CREATE INDEX IF NOT EXISTS idx_ror_links_host ON ror_links(host_normalized);
            CREATE INDEX IF NOT EXISTS idx_ror_external_ids_type ON ror_external_ids(id_type);
            CREATE INDEX IF NOT EXISTS idx_ror_relationships_ror_id ON ror_relationships(ror_id);
            CREATE INDEX IF NOT EXISTS idx_ror_relationships_related ON ror_relationships(related_ror_id);
            CREATE INDEX IF NOT EXISTS idx_journal_ror_links_journal ON journal_ror_links(journal_id);
            CREATE INDEX IF NOT EXISTS idx_journal_ror_links_confidence ON journal_ror_links(confidence);
            CREATE INDEX IF NOT EXISTS idx_conference_ror_links_conference ON conference_ror_links(conference_id);
            CREATE INDEX IF NOT EXISTS idx_conference_ror_links_confidence ON conference_ror_links(confidence);
        """
        )

        # Set initial schema version for new database
        set_schema_version(
            db_path,
            SCHEMA_VERSION,
            "Schema v5: removes ror_organizations.raw_json from ROR cache schema",
        )
