# SPDX-License-Identifier: MIT
"""Logging configuration for aletheia probe tool.

This module provides a dual-logger system:
1. Detail Logger: Captures all debug/info logs to file only (for troubleshooting)
2. Status Logger: Outputs user-facing progress/status to console (stderr) and file
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Logger names
DETAIL_LOGGER_NAME = "aletheia_probe.detail"
STATUS_LOGGER_NAME = "aletheia_probe.status"


def setup_logging(log_dir: Path | None = None) -> tuple[logging.Logger, logging.Logger]:
    """Configure dual logging system with detail and status loggers.

    Detail Logger:
        - Captures all DEBUG and above messages
        - Writes to file only
        - Used for verbose technical logs, API calls, data processing, etc.

    Status Logger:
        - Outputs user-facing progress and status information
        - Writes to both stderr (console) and file
        - Used for progress updates, status messages, warnings, and errors

    Args:
        log_dir: Directory for log file. If None, uses .aletheia-probe/ in current directory

    Returns:
        Tuple of (detail_logger, status_logger)
    """
    if log_dir is None:
        log_dir = Path.cwd() / ".aletheia-probe"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "aletheia-probe.log"

    # Configure root logger to capture everything
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    # Create shared file handler for both loggers
    # Mode 'w' overwrites the file each time
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # ===== Detail Logger Setup =====
    # This logger writes verbose technical details to file only
    detail_logger = logging.getLogger(DETAIL_LOGGER_NAME)
    detail_logger.setLevel(logging.DEBUG)
    detail_logger.handlers.clear()
    detail_logger.addHandler(file_handler)
    detail_logger.propagate = False  # Don't propagate to root logger

    # ===== Status Logger Setup =====
    # This logger writes user-facing status to both console and file
    status_logger = logging.getLogger(STATUS_LOGGER_NAME)
    status_logger.setLevel(logging.INFO)
    status_logger.handlers.clear()

    # Console handler for status logger - outputs to stderr
    # Ensure stderr is unbuffered for real-time output
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    console_handler.setFormatter(console_formatter)

    # Force immediate flush after each log message
    class FlushingStreamHandler(logging.StreamHandler):  # type: ignore[type-arg]
        def emit(self, record: logging.LogRecord) -> None:
            super().emit(record)
            # Only flush if the stream is not closed
            if self.stream and not self.stream.closed:
                self.flush()

    flushing_console_handler = FlushingStreamHandler(sys.stderr)
    flushing_console_handler.setLevel(logging.INFO)
    flushing_console_handler.setFormatter(console_formatter)

    status_logger.addHandler(flushing_console_handler)
    status_logger.addHandler(file_handler)
    status_logger.propagate = False  # Don't propagate to root logger

    # Log initialization
    detail_logger.info(f"Logging initialized. Log file: {log_file}")
    detail_logger.info(f"Detail logger: {DETAIL_LOGGER_NAME}")
    detail_logger.info(f"Status logger: {STATUS_LOGGER_NAME}")

    return detail_logger, status_logger


def get_detail_logger() -> logging.Logger:
    """Get the detail logger for verbose technical logging.

    Use this logger for:
    - Debug information
    - API calls and responses
    - Data processing details
    - Internal state changes
    - Technical diagnostics

    Returns:
        The detail logger instance
    """
    return logging.getLogger(DETAIL_LOGGER_NAME)


def get_status_logger() -> logging.Logger:
    """Get the status logger for user-facing progress and status.

    Use this logger for:
    - Progress updates
    - Status messages
    - User-facing warnings
    - Error messages
    - Summary information

    Returns:
        The status logger instance
    """
    return logging.getLogger(STATUS_LOGGER_NAME)
