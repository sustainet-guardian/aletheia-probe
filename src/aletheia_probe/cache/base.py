# SPDX-License-Identifier: MIT
"""Base utilities for cache components.

This module provides the CacheBase class, which serves as the foundation for all
cache components in the system. It handles shared functionality including:

- Database initialization and path management
- Text normalization for robust name comparison (removing stop words, special chars)
- Common utility methods used across cache implementations
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..config import get_config_manager
from ..logging_config import get_detail_logger, get_status_logger
from ..utils.dead_code import code_is_used
from .connection_utils import configure_sqlite_connection
from .schema import init_database


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
        self._conn: sqlite3.Connection | None = None

    def _open_conn(self) -> sqlite3.Connection:
        """Open and configure the persistent connection (called once per instance)."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        configure_sqlite_connection(conn)
        return conn

    def _get_or_open_conn(self) -> sqlite3.Connection:
        """Return the persistent connection, creating it on first use."""
        if self._conn is None:
            self._conn = self._open_conn()
        return self._conn

    @contextmanager
    def get_connection(
        self, timeout: float = 30.0, enable_wal: bool = True
    ) -> Iterator[sqlite3.Connection]:
        """Get the persistent SQLite connection to this cache's database.

        Reuses a single long-lived connection per instance. Commits on success
        and rolls back on exception, but does not close the connection.

        Args:
            timeout: Ignored (kept for API compatibility; set at construction)
            enable_wal: Ignored (kept for API compatibility; set at construction)

        Yields:
            Configured SQLite connection
        """
        del timeout, enable_wal  # set once at connection creation
        conn = self._get_or_open_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    @contextmanager
    def get_connection_with_row_factory(
        self, timeout: float = 30.0, enable_wal: bool = True
    ) -> Iterator[sqlite3.Connection]:
        """Get the persistent connection with Row factory for dict-like access.

        Same as get_connection() but temporarily sets sqlite3.Row factory
        for the duration of the block.

        Args:
            timeout: Ignored (kept for API compatibility; set at construction)
            enable_wal: Ignored (kept for API compatibility; set at construction)

        Yields:
            Configured SQLite connection with Row factory
        """
        del timeout, enable_wal  # set once at connection creation
        conn = self._get_or_open_conn()
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.row_factory = None
