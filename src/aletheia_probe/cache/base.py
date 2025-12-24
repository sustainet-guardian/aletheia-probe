# SPDX-License-Identifier: MIT
"""Base utilities for cache components.

This module provides the CacheBase class, which serves as the foundation for all
cache components in the system. It handles shared functionality including:

- Database initialization and path management
- Text normalization for robust name comparison (removing stop words, special chars)
- Common utility methods used across cache implementations
"""

import sqlite3
from pathlib import Path

from ..logging_config import get_detail_logger, get_status_logger


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class CacheBase:
    """Base class for cache components with shared utilities.

    Provides foundational functionality for all cache implementations:

    - Automatic database initialization from config or explicit path
    - Shared database path management (self.db_path)

    Subclasses should call super().__init__(db_path) to initialize the database
    connection path and schema. The db_path parameter defaults to the value from
    the application configuration (config.cache.db_path).

    Attributes:
        db_path: Path to the SQLite database file used by this cache component.
    """

    def __init__(self, db_path: Path | None = None):
        """Initialize cache base with database path.

        Args:
            db_path: Path to the SQLite database file. If None, gets from config.

        Raises:
            RuntimeError: If config structure is invalid or database initialization fails.
        """
        if db_path is None:
            # Local import to avoid circular dependency (config -> backends -> cache)
            from ..config import get_config_manager
            from .schema import init_database

            try:
                db_path_str = get_config_manager().load_config().cache.db_path
                db_path = Path(db_path_str)
                detail_logger.debug(f"Using database path from config: {db_path}")
            except AttributeError as e:
                error_msg = (
                    "Invalid config structure: missing 'cache.db_path' configuration"
                )
                status_logger.error(error_msg)
                detail_logger.exception(f"{error_msg}: {e}")
                raise RuntimeError(error_msg) from e

            try:
                # Ensure parent directory exists
                db_path.parent.mkdir(parents=True, exist_ok=True)
                detail_logger.debug(
                    f"Ensured parent directory exists: {db_path.parent}"
                )
            except OSError as e:
                error_msg = f"Failed to create database directory: {db_path.parent}"
                status_logger.error(error_msg)
                detail_logger.exception(f"{error_msg}: {e}")
                raise RuntimeError(error_msg) from e

            try:
                # Initialize database schema
                init_database(db_path)
                detail_logger.debug(f"Database schema initialized: {db_path}")
            except (sqlite3.Error, OSError) as e:
                error_msg = f"Failed to initialize database at {db_path}"
                status_logger.error(error_msg)
                detail_logger.exception(f"{error_msg}: {e}")
                raise RuntimeError(error_msg) from e

        self.db_path = db_path
