# SPDX-License-Identifier: MIT
"""Logging configuration for aletheia probe tool.

This module provides a dual-logger system:
1. Detail Logger: Captures all debug/info logs to file only (for troubleshooting)
2. Status Logger: Outputs user-facing progress/status to console (stderr) and file
"""

from __future__ import annotations

import atexit
import logging
import logging.handlers
import queue
import sys
import threading
from pathlib import Path


# Logger names
DETAIL_LOGGER_NAME = "aletheia_probe.detail"
STATUS_LOGGER_NAME = "aletheia_probe.status"

# The QueueListener owning the file handler, plus the lock guarding it.
# Kept at module level so it can be drained at exit and replaced on re-setup;
# a listener that is merely started and forgotten loses every record still
# queued when the process ends, because its monitor thread is a daemon.
_listener: logging.handlers.QueueListener | None = None
_listener_lock = threading.Lock()


def shutdown_logging() -> None:
    """Drain queued log records to the file and release the listener thread.

    Registered via atexit, and called again by setup_logging() so repeated
    setups do not leak a listener thread and an open file handle each time.
    Safe to call when no listener is active.
    """
    global _listener

    with _listener_lock:
        listener, _listener = _listener, None

    if listener is None:
        return

    # stop() drains the queue into the handlers, then joins the monitor thread.
    listener.stop()
    for handler in listener.handlers:
        handler.close()


# Runs before logging.shutdown() (atexit is LIFO and the logging module
# registers its own handler at import time, i.e. earlier than this one).
atexit.register(shutdown_logging)


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

    The file handler runs in a dedicated background thread via QueueHandler /
    QueueListener so that CephFS write latency never blocks the asyncio event
    loop.  Without this, a slow CephFS write (5–120 s is realistic under load)
    would freeze the event loop and cause asyncio.wait_for timeouts on backends
    that are otherwise healthy.

    Args:
        log_dir: Directory for log file. If None, uses .aletheia-probe/ in current directory

    Returns:
        Tuple of (detail_logger, status_logger)
    """
    global _listener

    if log_dir is None:
        log_dir = Path.cwd() / ".aletheia-probe"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "aletheia-probe.log"

    # Retire the listener from a previous setup_logging() call, flushing its
    # pending records, so neither its thread nor its file handle leaks.
    shutdown_logging()

    # Configure root logger to capture everything
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    for handler in root_logger.handlers[:]:
        handler.close()
    root_logger.handlers.clear()

    # ── Real file handler (runs in the QueueListener thread, not the event loop) ──
    # Mode 'w' overwrites the file each time
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # ── Queue-based non-blocking handler ──────────────────────────────────────
    # Loggers attach QueueHandler; a background QueueListener thread does the
    # actual file write.  The event loop thread never blocks on file I/O.
    log_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    queue_handler = logging.handlers.QueueHandler(log_queue)  # type: ignore[arg-type]

    listener = logging.handlers.QueueListener(
        log_queue,  # type: ignore[arg-type]
        file_handler,
        respect_handler_level=True,
    )
    listener.start()
    with _listener_lock:
        _listener = listener

    # ===== Detail Logger Setup =====
    # Verbose technical details, file only.
    detail_logger = logging.getLogger(DETAIL_LOGGER_NAME)
    detail_logger.setLevel(logging.DEBUG)
    for handler in detail_logger.handlers[:]:
        handler.close()
    detail_logger.handlers.clear()
    detail_logger.addHandler(queue_handler)
    detail_logger.propagate = False

    # ===== Status Logger Setup =====
    status_logger = logging.getLogger(STATUS_LOGGER_NAME)
    status_logger.setLevel(logging.INFO)
    for handler in status_logger.handlers[:]:
        handler.close()
    status_logger.handlers.clear()

    # Console formatter for status logger
    console_formatter = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")

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
    status_logger.addHandler(queue_handler)
    status_logger.propagate = False

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
