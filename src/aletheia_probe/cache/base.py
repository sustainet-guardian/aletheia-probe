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
from typing import Any

from ..logging_config import get_detail_logger, get_status_logger
from ..utils.dead_code import code_is_used


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

    @code_is_used
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
            except OSError as e:
                error_msg = f"Failed to create database directory: {db_path.parent}"
                status_logger.error(error_msg)
                detail_logger.exception(f"{error_msg}: {e}")
                raise RuntimeError(error_msg) from e

            try:
                # Initialize database schema
                init_database(db_path)
            except (sqlite3.Error, OSError) as e:
                error_msg = f"Failed to initialize database at {db_path}"
                status_logger.error(error_msg)
                detail_logger.exception(f"{error_msg}: {e}")
                raise RuntimeError(error_msg) from e

        self.db_path = db_path

    def get_connection(self, timeout: float = 30.0, enable_wal: bool = True) -> Any:
        """Get a configured SQLite connection to this cache's database.

        This method provides the standard way to access the database with
        consistent configuration across all cache components. Uses the
        centralized connection configuration with proper timeout and WAL mode.

        Args:
            timeout: Connection timeout in seconds (default: 30.0)
            enable_wal: Whether to enable WAL mode (default: True)

        Returns:
            Context manager yielding a configured SQLite connection

        Example:
            ```python
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
                results = cursor.fetchall()
            ```
        """
        from .connection_utils import get_configured_connection

        return get_configured_connection(self.db_path, timeout, enable_wal)

    def get_connection_with_row_factory(
        self, timeout: float = 30.0, enable_wal: bool = True
    ) -> Any:
        """Get a configured SQLite connection with Row factory for dict-like access.

        Same as get_connection() but with sqlite3.Row factory enabled
        for dictionary-style access to query results.

        Args:
            timeout: Connection timeout in seconds (default: 30.0)
            enable_wal: Whether to enable WAL mode (default: True)

        Returns:
            Context manager yielding a configured SQLite connection with Row factory
        """
        from .connection_utils import get_connection_with_row_factory

        return get_connection_with_row_factory(self.db_path, timeout, enable_wal)
