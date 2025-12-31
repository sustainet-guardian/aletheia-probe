# SPDX-License-Identifier: MIT
"""Centralized SQLite connection configuration utilities.

This module provides standardized connection configuration for all SQLite
database access throughout the application. It ensures consistent WAL mode,
timeout settings, and performance optimizations across all components.

The main function `get_configured_connection()` should be used instead of
direct `sqlite3.connect()` calls to ensure database lock conflicts are
minimized during concurrent operations.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..logging_config import get_detail_logger


detail_logger = get_detail_logger()


def configure_sqlite_connection(
    conn: sqlite3.Connection,
    enable_wal: bool = True,
) -> None:
    """Configure SQLite connection with performance optimizations and WAL mode.

    Applies consistent PRAGMA settings across all database connections:
    - WAL mode for concurrent read/write support
    - NORMAL synchronous mode for balanced safety/performance
    - Large cache size for reduced disk I/O
    - Memory temp storage for faster operations

    Args:
        conn: SQLite database connection to configure
        enable_wal: Whether to enable WAL mode (default: True)
    """
    detail_logger.debug("Configuring SQLite PRAGMA settings")

    if enable_wal:
        conn.execute("PRAGMA journal_mode = WAL")
        detail_logger.debug("Set PRAGMA journal_mode = WAL")

    conn.execute("PRAGMA synchronous = NORMAL")
    detail_logger.debug("Set PRAGMA synchronous = NORMAL")

    conn.execute("PRAGMA cache_size = 10000")
    detail_logger.debug("Set PRAGMA cache_size = 10000")

    conn.execute("PRAGMA temp_store = MEMORY")
    detail_logger.debug("Set PRAGMA temp_store = MEMORY")


@contextmanager
def get_configured_connection(
    db_path: str | Path,
    timeout: float = 30.0,
    enable_wal: bool = True,
) -> Iterator[sqlite3.Connection]:
    """Get a configured SQLite connection with proper timeout and settings.

    This is the standard way to access SQLite databases throughout the
    application. It provides:
    - 30-second timeout (handles large data chunks during sync)
    - WAL mode for concurrent read/write access
    - Performance optimizations (cache size, synchronous mode, etc.)
    - Automatic connection cleanup

    Args:
        db_path: Path to the SQLite database file
        timeout: Connection timeout in seconds (default: 30.0)
        enable_wal: Whether to enable WAL mode (default: True)

    Yields:
        Configured SQLite connection

    Example:
        ```python
        with get_configured_connection(cache.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table")
            results = cursor.fetchall()
        ```
    """
    detail_logger.debug(
        f"Opening SQLite connection to {db_path} with {timeout}s timeout"
    )

    # Convert Path to string for sqlite3.connect()
    db_path_str = str(db_path)

    # Create connection with timeout
    conn = sqlite3.connect(db_path_str, timeout=timeout)

    try:
        # Apply standard configuration
        configure_sqlite_connection(conn, enable_wal=enable_wal)
        yield conn
    finally:
        conn.close()
        detail_logger.debug(f"Closed SQLite connection to {db_path}")


@contextmanager
def get_connection_with_row_factory(
    db_path: str | Path,
    timeout: float = 30.0,
    enable_wal: bool = True,
) -> Iterator[sqlite3.Connection]:
    """Get a configured SQLite connection with Row factory for dict-like access.

    Same as get_configured_connection() but with sqlite3.Row factory
    enabled for dictionary-style access to query results.

    Args:
        db_path: Path to the SQLite database file
        timeout: Connection timeout in seconds (default: 30.0)
        enable_wal: Whether to enable WAL mode (default: True)

    Yields:
        Configured SQLite connection with Row factory
    """
    with get_configured_connection(db_path, timeout, enable_wal) as conn:
        conn.row_factory = sqlite3.Row
        yield conn
