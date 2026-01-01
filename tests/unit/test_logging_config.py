# SPDX-License-Identifier: MIT
"""Tests for the logging configuration module."""

import logging
import re
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from aletheia_probe.logging_config import (
    DETAIL_LOGGER_NAME,
    STATUS_LOGGER_NAME,
    get_detail_logger,
    get_status_logger,
    setup_logging,
)


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create a temporary directory for log files."""
    log_dir = tmp_path / "test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging state before and after each test.

    Only clears the detail and status loggers, which are the only loggers
    the application should use.
    """
    # Clear all existing handlers before test
    detail_logger = logging.getLogger(DETAIL_LOGGER_NAME)
    for handler in detail_logger.handlers[:]:
        handler.close()
    detail_logger.handlers.clear()

    status_logger = logging.getLogger(STATUS_LOGGER_NAME)
    for handler in status_logger.handlers[:]:
        handler.close()
    status_logger.handlers.clear()

    yield

    # Cleanup after test
    for handler in detail_logger.handlers[:]:
        handler.close()
    detail_logger.handlers.clear()
    for handler in status_logger.handlers[:]:
        handler.close()
    status_logger.handlers.clear()


class TestSetupLogging:
    """Test cases for setup_logging function."""

    def test_setup_logging_creates_log_file(self, temp_log_dir) -> None:
        """Test that setup_logging creates a log file in the specified directory."""
        detail_logger, status_logger = setup_logging(temp_log_dir)

        log_file = temp_log_dir / "aletheia-probe.log"
        assert log_file.exists()
        assert log_file.is_file()

    def test_setup_logging_uses_default_directory_when_none(self, tmp_path) -> None:
        """Test that setup_logging uses .aletheia-probe in cwd when log_dir is None."""
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            detail_logger, status_logger = setup_logging(log_dir=None)

            expected_dir = tmp_path / ".aletheia-probe"
            expected_log_file = expected_dir / "aletheia-probe.log"

            assert expected_dir.exists()
            assert expected_log_file.exists()

    def test_setup_logging_returns_correct_loggers(self, temp_log_dir) -> None:
        """Test that setup_logging returns detail and status logger instances."""
        detail_logger, status_logger = setup_logging(temp_log_dir)

        assert isinstance(detail_logger, logging.Logger)
        assert isinstance(status_logger, logging.Logger)
        assert detail_logger.name == DETAIL_LOGGER_NAME
        assert status_logger.name == STATUS_LOGGER_NAME

    def test_detail_logger_configuration(self, temp_log_dir) -> None:
        """Test that detail logger is configured correctly."""
        detail_logger, _ = setup_logging(temp_log_dir)

        # Verify logger level
        assert detail_logger.level == logging.DEBUG

        # Verify propagate is disabled
        assert detail_logger.propagate is False

        # Verify handlers (should have 1 file handler)
        assert len(detail_logger.handlers) == 1
        handler = detail_logger.handlers[0]
        assert isinstance(handler, logging.FileHandler)
        assert handler.level == logging.DEBUG

    def test_status_logger_configuration(self, temp_log_dir) -> None:
        """Test that status logger is configured correctly."""
        _, status_logger = setup_logging(temp_log_dir)

        # Verify logger level
        assert status_logger.level == logging.INFO

        # Verify propagate is disabled
        assert status_logger.propagate is False

        # Verify handlers (should have 2: console + file)
        assert len(status_logger.handlers) == 2

        # Check handler types
        handler_types = {type(h).__name__ for h in status_logger.handlers}
        assert "FlushingStreamHandler" in handler_types
        assert "FileHandler" in handler_types

    def test_detail_logger_writes_to_file_only(self, temp_log_dir) -> None:
        """Test that detail logger writes to file but not to console."""
        detail_logger, _ = setup_logging(temp_log_dir)

        # Detail logger should only have file handler
        # FileHandler is a subclass of StreamHandler, so we need to check specifically
        assert len(detail_logger.handlers) == 1
        handler = detail_logger.handlers[0]
        assert isinstance(handler, logging.FileHandler)
        # Ensure it's not writing to stderr/stdout
        assert handler.stream.name != "<stderr>"
        assert handler.stream.name != "<stdout>"

    def test_status_logger_writes_to_console_and_file(self, temp_log_dir) -> None:
        """Test that status logger writes to both console and file."""
        _, status_logger = setup_logging(temp_log_dir)

        # Status logger should have both stream and file handlers
        # Note: FileHandler is a subclass of StreamHandler, so we need to filter it out
        stream_handlers = [
            h
            for h in status_logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        file_handlers = [
            h for h in status_logger.handlers if isinstance(h, logging.FileHandler)
        ]

        assert len(stream_handlers) == 1  # FlushingStreamHandler (console output)
        assert len(file_handlers) == 1

    def test_log_file_format(self, temp_log_dir) -> None:
        """Test that log file uses correct format."""
        detail_logger, status_logger = setup_logging(temp_log_dir)

        test_message = "Test message for format verification"
        detail_logger.info(test_message)

        log_file = temp_log_dir / "aletheia-probe.log"
        log_content = log_file.read_text()

        # Verify format: timestamp - logger_name - level - message
        assert DETAIL_LOGGER_NAME in log_content
        assert "INFO" in log_content
        assert test_message in log_content
        # Check for timestamp format (YYYY-MM-DD HH:MM:SS)
        timestamp_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
        assert re.search(timestamp_pattern, log_content), (
            "Log file missing proper timestamp format"
        )

    def test_console_format_for_status_logger(self, temp_log_dir) -> None:
        """Test that status logger console output uses simplified format."""
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            _, status_logger = setup_logging(temp_log_dir)

            test_message = "Test status message"
            status_logger.info(test_message)

            console_output = mock_stderr.getvalue()

            # Console format should be: "HH:MM:SS message" (no logger name, no full date)
            assert test_message in console_output
            # Should NOT contain full logger name in console output
            assert DETAIL_LOGGER_NAME not in console_output

    def test_log_file_overwrite_mode(self, temp_log_dir) -> None:
        """Test that log file is overwritten on each setup (mode='w')."""
        log_file = temp_log_dir / "aletheia-probe.log"

        # First setup and write
        detail_logger1, _ = setup_logging(temp_log_dir)
        detail_logger1.info("First message")
        first_content = log_file.read_text()

        # Reset logging
        for handler in detail_logger1.handlers[:]:
            handler.close()
        detail_logger1.handlers.clear()

        # Second setup and write
        detail_logger2, _ = setup_logging(temp_log_dir)
        detail_logger2.info("Second message")
        second_content = log_file.read_text()

        # First message should not be in second content (file was overwritten)
        assert "First message" not in second_content
        assert "Second message" in second_content

    def test_setup_logging_creates_directory_if_not_exists(self, tmp_path) -> None:
        """Test that setup_logging creates log directory if it doesn't exist."""
        non_existent_dir = tmp_path / "new_logs" / "nested"

        assert not non_existent_dir.exists()

        setup_logging(non_existent_dir)

        assert non_existent_dir.exists()
        assert non_existent_dir.is_dir()
        assert (non_existent_dir / "aletheia-probe.log").exists()

    def test_setup_logging_writes_initialization_messages(self, temp_log_dir) -> None:
        """Test that setup_logging writes initialization messages to detail logger."""
        setup_logging(temp_log_dir)

        log_file = temp_log_dir / "aletheia-probe.log"
        log_content = log_file.read_text()

        assert "Logging initialized" in log_content
        assert "Detail logger:" in log_content
        assert "Status logger:" in log_content
        assert str(log_file) in log_content

    def test_detail_logger_handles_debug_level(self, temp_log_dir) -> None:
        """Test that detail logger captures DEBUG level messages."""
        detail_logger, _ = setup_logging(temp_log_dir)

        debug_message = "Debug level message"
        detail_logger.debug(debug_message)

        log_file = temp_log_dir / "aletheia-probe.log"
        log_content = log_file.read_text()

        assert debug_message in log_content
        assert "DEBUG" in log_content

    def test_status_logger_ignores_debug_level(self, temp_log_dir) -> None:
        """Test that status logger does not output DEBUG level messages to console."""
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            _, status_logger = setup_logging(temp_log_dir)

            debug_message = "Debug message from status logger"
            status_logger.debug(debug_message)

            console_output = mock_stderr.getvalue()

            # Debug message should not appear in console output
            assert debug_message not in console_output

    def test_status_logger_handles_info_level(self, temp_log_dir) -> None:
        """Test that status logger captures INFO level messages."""
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            _, status_logger = setup_logging(temp_log_dir)

            info_message = "Info level message"
            status_logger.info(info_message)

            console_output = mock_stderr.getvalue()
            log_file = temp_log_dir / "aletheia-probe.log"
            file_content = log_file.read_text()

            # Should be in both console and file
            assert info_message in console_output
            assert info_message in file_content

    def test_file_handler_uses_utf8_encoding(self, temp_log_dir) -> None:
        """Test that file handler uses UTF-8 encoding."""
        detail_logger, _ = setup_logging(temp_log_dir)

        # Log message with non-ASCII characters
        unicode_message = "Test message with Unicode: 日本語 français €"
        detail_logger.info(unicode_message)

        log_file = temp_log_dir / "aletheia-probe.log"
        log_content = log_file.read_text(encoding="utf-8")

        assert unicode_message in log_content


class TestFlushingStreamHandler:
    """Test cases for FlushingStreamHandler class."""

    def test_flushing_stream_handler_flushes_after_emit(self, temp_log_dir) -> None:
        """Test that FlushingStreamHandler flushes after each log message."""
        mock_stream = Mock()
        mock_stream.closed = False

        with patch("sys.stderr", mock_stream):
            _, status_logger = setup_logging(temp_log_dir)

            status_logger.info("Test message")

            # Verify flush was called
            assert mock_stream.flush.called

    def test_flushing_stream_handler_handles_closed_stream(self, temp_log_dir) -> None:
        """Test that FlushingStreamHandler doesn't call flush when stream is None."""
        _, status_logger = setup_logging(temp_log_dir)

        # Get the FlushingStreamHandler
        flushing_handler = None
        for handler in status_logger.handlers:
            if type(handler).__name__ == "FlushingStreamHandler":
                flushing_handler = handler
                break

        assert flushing_handler is not None

        # Test that it handles None stream gracefully
        original_stream = flushing_handler.stream
        try:
            flushing_handler.stream = None
            # Should not raise an error
            status_logger.info("Test message with None stream")
        finally:
            flushing_handler.stream = original_stream

    def test_flushing_stream_handler_uses_stderr(self, temp_log_dir) -> None:
        """Test that FlushingStreamHandler writes to stderr."""
        original_stderr = sys.stderr

        try:
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                _, status_logger = setup_logging(temp_log_dir)

                test_message = "Test stderr message"
                status_logger.info(test_message)

                # Message should be in stderr
                assert test_message in mock_stderr.getvalue()
        finally:
            sys.stderr = original_stderr


class TestGetDetailLogger:
    """Test cases for get_detail_logger function."""

    def test_get_detail_logger_returns_logger_instance(self) -> None:
        """Test that get_detail_logger returns a Logger instance."""
        logger = get_detail_logger()

        assert isinstance(logger, logging.Logger)
        assert logger.name == DETAIL_LOGGER_NAME

    def test_get_detail_logger_returns_same_instance(self) -> None:
        """Test that get_detail_logger returns the same instance on multiple calls."""
        logger1 = get_detail_logger()
        logger2 = get_detail_logger()

        assert logger1 is logger2

    def test_get_detail_logger_after_setup(self, temp_log_dir) -> None:
        """Test that get_detail_logger returns configured logger after setup."""
        detail_logger_from_setup, _ = setup_logging(temp_log_dir)
        detail_logger_from_getter = get_detail_logger()

        # Should return the same instance
        assert detail_logger_from_setup is detail_logger_from_getter


class TestGetStatusLogger:
    """Test cases for get_status_logger function."""

    def test_get_status_logger_returns_logger_instance(self) -> None:
        """Test that get_status_logger returns a Logger instance."""
        logger = get_status_logger()

        assert isinstance(logger, logging.Logger)
        assert logger.name == STATUS_LOGGER_NAME

    def test_get_status_logger_returns_same_instance(self) -> None:
        """Test that get_status_logger returns the same instance on multiple calls."""
        logger1 = get_status_logger()
        logger2 = get_status_logger()

        assert logger1 is logger2

    def test_get_status_logger_after_setup(self, temp_log_dir) -> None:
        """Test that get_status_logger returns configured logger after setup."""
        _, status_logger_from_setup = setup_logging(temp_log_dir)
        status_logger_from_getter = get_status_logger()

        # Should return the same instance
        assert status_logger_from_setup is status_logger_from_getter


class TestLoggerIntegration:
    """Integration tests for the dual-logger system."""

    def test_both_loggers_write_to_same_file(self, temp_log_dir) -> None:
        """Test that both loggers write to the same log file."""
        detail_logger, status_logger = setup_logging(temp_log_dir)

        detail_message = "Detail logger message"
        status_message = "Status logger message"

        detail_logger.info(detail_message)
        status_logger.info(status_message)

        log_file = temp_log_dir / "aletheia-probe.log"
        log_content = log_file.read_text()

        assert detail_message in log_content
        assert status_message in log_content

    def test_logger_names_are_correct(self) -> None:
        """Test that logger name constants are correct."""
        assert DETAIL_LOGGER_NAME == "aletheia_probe.detail"
        assert STATUS_LOGGER_NAME == "aletheia_probe.status"

    def test_loggers_do_not_propagate_to_root(self, temp_log_dir) -> None:
        """Test that loggers have propagate=False to avoid duplicate logs."""
        detail_logger, status_logger = setup_logging(temp_log_dir)

        assert detail_logger.propagate is False
        assert status_logger.propagate is False
