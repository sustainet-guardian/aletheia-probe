# SPDX-License-Identifier: MIT
"""Database migration framework for schema version upgrades."""

import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ..logging_config import get_detail_logger, get_status_logger
from .connection_utils import get_configured_connection
from .schema import (
    SCHEMA_VERSION,
    get_schema_version,
    set_schema_version,
)


detail_logger = get_detail_logger()
status_logger = get_status_logger()


def migrate_v1_to_v2(db_path: Path) -> None:
    """Migrate database from version 1 to version 2.

    Changes:
    - Drop old venue_acronyms table
    - Create new venue_acronym_variants table (handled by init_database)
    - Create new learned_abbreviations table (handled by init_database)
    - Add schema_version table

    Args:
        db_path: Path to the SQLite database file
    """
    status_logger.info("Migrating from version 1 to version 2...")

    with get_configured_connection(db_path) as conn:
        cursor = conn.cursor()

        # Check if old venue_acronyms table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='venue_acronyms'"
        )
        if cursor.fetchone():
            status_logger.info("  Dropping old venue_acronyms table...")
            cursor.execute("DROP TABLE venue_acronyms")
            conn.commit()

        # Create schema_version table if it doesn't exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        if not cursor.fetchone():
            status_logger.info("  Creating schema_version table...")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    description TEXT NOT NULL
                )
                """
            )
            conn.commit()

    status_logger.info("  Migration to version 2 completed successfully")


def migrate_legacy_to_v2(db_path: Path) -> None:
    """Migrate legacy database (no version) to version 2.

    This handles databases created before schema versioning was introduced.

    Args:
        db_path: Path to the SQLite database file
    """
    status_logger.info("Migrating legacy database to version 2...")

    # Legacy databases are treated as version 1, then upgraded to version 2
    migrate_v1_to_v2(db_path)


# Migration registry: version -> migration function
MIGRATIONS: dict[int, Callable[[Path], None]] = {
    2: migrate_v1_to_v2,
}


def backup_database(db_path: Path) -> Path:
    """Create a backup of the database before migration.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        Path to the backup file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_backup_{timestamp}.db"

    status_logger.info(f"Creating backup: {backup_path}")
    shutil.copy2(db_path, backup_path)

    return backup_path


def migrate_database(db_path: Path, target_version: int | None = None) -> bool:
    """Migrate database to target version (or latest version).

    Args:
        db_path: Path to the SQLite database file
        target_version: Target version to migrate to (default: latest)

    Returns:
        True if migration was successful, False otherwise

    Raises:
        ValueError: If target version is invalid
        sqlite3.Error: If migration fails
    """
    if target_version is None:
        target_version = SCHEMA_VERSION

    if target_version > SCHEMA_VERSION:
        raise ValueError(
            f"Cannot migrate to version {target_version} "
            f"(maximum supported: {SCHEMA_VERSION})"
        )

    # Get current version
    current_version = get_schema_version(db_path)

    if current_version is None:
        status_logger.info("Detected legacy database (no version)")
        current_version = 1  # Treat legacy as version 1
    else:
        status_logger.info(f"Current database version: {current_version}")

    if current_version == target_version:
        status_logger.info(f"Database is already at version {target_version}")
        return True

    if current_version > target_version:
        raise ValueError(
            f"Cannot downgrade from version {current_version} to {target_version}. "
            f"Downgrades are not supported."
        )

    # Create backup before migration
    backup_path = backup_database(db_path)

    try:
        # Apply migrations sequentially
        for version in range(current_version + 1, target_version + 1):
            if version not in MIGRATIONS:
                raise ValueError(f"No migration path found for version {version}")

            status_logger.info(f"Applying migration to version {version}...")
            migration_func = MIGRATIONS[version]

            # Run migration
            migration_func(db_path)

            # Update version in database
            description = f"Migrated from v{version - 1} to v{version}"
            set_schema_version(db_path, version, description)

        status_logger.info(
            f"✅ Migration completed: v{current_version} → v{target_version}"
        )
        status_logger.info(f"Backup saved at: {backup_path}")
        return True

    except Exception as e:
        status_logger.error(f"❌ Migration failed: {e}")
        status_logger.error(f"Database backup available at: {backup_path}")
        detail_logger.exception("Migration error details:")
        raise


def reset_database(db_path: Path, confirm: bool = False) -> bool:
    """Reset database by deleting and reinitializing it.

    WARNING: This deletes all data!

    Args:
        db_path: Path to the SQLite database file
        confirm: Whether the user has confirmed the operation

    Returns:
        True if reset was successful, False otherwise
    """
    if not confirm:
        raise ValueError("Database reset requires explicit confirmation")

    # Create backup before reset
    backup_path = backup_database(db_path)

    try:
        status_logger.info("Resetting database...")

        # Close any existing connections and delete the database
        if db_path.exists():
            db_path.unlink()

        # Reinitialize with current schema
        from .schema import init_database

        init_database(db_path)

        status_logger.info(f"✅ Database reset to version {SCHEMA_VERSION}")
        status_logger.info(f"Backup of old database saved at: {backup_path}")
        return True

    except Exception as e:
        status_logger.error(f"❌ Database reset failed: {e}")
        status_logger.error(f"Backup available at: {backup_path}")
        detail_logger.exception("Reset error details:")
        raise
