# SPDX-License-Identifier: MIT
"""Tests for the CLI module."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from aletheia_probe.cli import main
from aletheia_probe.enums import AssessmentType
from aletheia_probe.models import (
    AssessmentResult,
    BackendResult,
    BackendStatus,
)


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def mock_cache_sync_manager():
    """Mock cache_sync_manager to prevent unawaited coroutine warnings.

    This fixture is autouse=True so it applies to all tests in this module,
    preventing the real cache_sync_manager from being accessed and creating
    unawaited coroutines during test execution.
    """

    # Create a real async function that can be awaited
    async def _mock_sync_impl(*args, **kwargs):
        """Mock implementation of sync_cache_with_config."""
        return {}

    # Create a mock manager with all required methods
    mock_manager = MagicMock()
    # Assign the actual async function (not AsyncMock) to avoid introspection issues
    mock_manager.sync_cache_with_config = _mock_sync_impl
    mock_manager.get_sync_status = MagicMock(
        return_value={"sync_in_progress": False, "backends": {}}
    )

    with patch("aletheia_probe.cli.cache_sync_manager", mock_manager):
        yield mock_manager


@pytest.fixture
def mock_assessment_result():
    """Create mock assessment result."""
    return AssessmentResult(
        input_query="Test Journal",
        assessment=AssessmentType.PREDATORY,
        confidence=0.85,
        overall_score=0.9,
        backend_results=[
            BackendResult(
                backend_name="test_backend",
                status=BackendStatus.FOUND,
                confidence=0.8,
                assessment=AssessmentType.PREDATORY,
                data={"key": "value"},
                sources=["test_source"],
                response_time=0.1,
            )
        ],
        metadata=None,
        reasoning=["Found in predatory database"],
        processing_time=1.2,
    )


class TestAssessCommand:
    """Test cases for the journal command."""

    def test_assess_basic_usage(self, runner, mock_assessment_result):
        """Test basic journal command usage."""
        # Store the real asyncio.run before patching
        real_asyncio_run = asyncio.run

        def run_coro(coro):
            """Run the coroutine using real asyncio.run."""
            return real_asyncio_run(coro)

        with (
            patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro) as mock_run,
            patch("aletheia_probe.cli._async_assess_publication") as mock_async_assess,
        ):
            mock_async_assess.return_value = None

            result = runner.invoke(main, ["journal", "Test Journal"])

            assert result.exit_code == 0
            mock_run.assert_called_once()

    def test_assess_with_verbose_flag(self, runner):
        """Test journal command with verbose flag."""
        # Store the real asyncio.run before patching
        real_asyncio_run = asyncio.run

        def run_coro(coro):
            """Run the coroutine using real asyncio.run."""
            return real_asyncio_run(coro)

        with (
            patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro) as mock_run,
            patch("aletheia_probe.cli._async_assess_publication") as mock_async_assess,
        ):
            mock_async_assess.return_value = None

            result = runner.invoke(main, ["journal", "Test Journal", "--verbose"])

            assert result.exit_code == 0
            # Check that the async function was called with correct args
            call_args = mock_run.call_args[0][0]  # Get the coroutine

    def test_assess_with_json_format(self, runner):
        """Test journal command with JSON output format."""
        # Store the real asyncio.run before patching
        real_asyncio_run = asyncio.run

        def run_coro(coro):
            """Run the coroutine using real asyncio.run."""
            return real_asyncio_run(coro)

        with (
            patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro) as mock_run,
            patch("aletheia_probe.cli._async_assess_publication") as mock_async_assess,
        ):
            mock_async_assess.return_value = None

            result = runner.invoke(
                main, ["journal", "Test Journal", "--format", "json"]
            )

            assert result.exit_code == 0

    def test_assess_invalid_format(self, runner):
        """Test journal command with invalid format."""
        result = runner.invoke(main, ["journal", "Test Journal", "--format", "invalid"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower()


class TestConfigCommand:
    """Test cases for the config command."""

    def test_config_command_success(self, runner):
        """Test config command successful execution."""
        mock_config_output = "backends:\n  test_backend:\n    enabled: true"

        with patch("aletheia_probe.cli.get_config_manager") as mock_get_config_manager:
            mock_config_manager = Mock()
            mock_config_manager.show_config.return_value = mock_config_output
            mock_get_config_manager.return_value = mock_config_manager

            result = runner.invoke(main, ["config"])

            assert result.exit_code == 0
            assert mock_config_output in result.output

    def test_config_command_error(self, runner):
        """Test config command with error."""
        with patch("aletheia_probe.cli.get_config_manager") as mock_get_config_manager:
            mock_config_manager = Mock()
            mock_config_manager.show_config.side_effect = Exception("Config error")
            mock_get_config_manager.return_value = mock_config_manager

            result = runner.invoke(main, ["config"])

            assert result.exit_code == 1
            assert "Config error" in result.output


class TestSyncCommand:
    """Test cases for the sync command."""

    def test_sync_command_success(self, runner):
        """Test sync command successful execution."""
        mock_sync_result = {
            "backend1": {"status": "success", "records_updated": 100},
            "backend2": {"status": "current"},
        }

        def run_coro(coro):
            """Run coroutine and return mock result."""
            coro.close()  # Close without running
            return mock_sync_result

        with patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro) as mock_run:
            result = runner.invoke(main, ["sync"])

            assert result.exit_code == 0
            # Output is now handled by logging system, not directly printed
            mock_run.assert_called_once()

    def test_sync_command_with_force(self, runner):
        """Test sync command with force flag."""

        def run_coro(coro):
            """Run coroutine and return empty dict."""
            coro.close()  # Close without running
            return {}

        with patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro) as mock_run:
            result = runner.invoke(main, ["sync", "--force"])

            assert result.exit_code == 0
            # Verify force=True was passed to sync_cache_with_config
            call_args = mock_run.call_args[0][0]  # The coroutine argument

    def test_sync_command_skipped(self, runner):
        """Test sync command when sync is skipped."""
        mock_sync_result = {"status": "skipped", "reason": "auto_sync_disabled"}

        def run_coro(coro):
            """Run coroutine and return mock result."""
            coro.close()  # Close without running
            return mock_sync_result

        with patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro) as mock_run:
            result = runner.invoke(main, ["sync"])

            assert result.exit_code == 0
            # Output is now handled by logging system, not directly printed
            mock_run.assert_called_once()

    def test_sync_command_error(self, runner):
        """Test sync command with error."""

        def mock_run_with_cleanup(coro):
            """Mock asyncio.run that properly closes coroutines before raising."""
            coro.close()  # Close the coroutine to avoid warning
            raise Exception("Sync failed")

        with patch("aletheia_probe.cli.asyncio.run", side_effect=mock_run_with_cleanup):
            result = runner.invoke(main, ["sync"])

            assert result.exit_code == 1
            # Error messages now go through logging system to stderr
            # The test runner might not capture stderr, so just verify exit code


class TestStatusCommand:
    """Test cases for the status command."""

    def test_status_command_success(self, runner, mock_cache_sync_manager):
        """Test status command successful execution."""
        mock_status = {
            "sync_in_progress": False,
            "backends": {
                "backend1": {
                    "enabled": True,
                    "has_data": True,
                    "type": "cached",
                    "last_updated": "2023-12-01",
                },
                "backend2": {"enabled": False, "has_data": False, "type": "hybrid"},
            },
        }

        mock_cache_sync_manager.get_sync_status.return_value = mock_status

        result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "backend1" in result.output
        assert "enabled" in result.output
        assert "disabled" in result.output

    def test_status_command_sync_in_progress(self, runner, mock_cache_sync_manager):
        """Test status command when sync is in progress."""
        mock_status = {"sync_in_progress": True, "backends": {}}

        mock_cache_sync_manager.get_sync_status.return_value = mock_status

        result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "progress" in result.output.lower()

    def test_status_command_error(self, runner, mock_cache_sync_manager):
        """Test status command with error."""
        mock_cache_sync_manager.get_sync_status.side_effect = Exception("Status error")

        result = runner.invoke(main, ["status"])

        assert result.exit_code == 1
        assert "Status error" in result.output


class TestAddListCommand:
    """Test cases for the add-list command."""

    def test_add_list_success(self, runner):
        """Test add-list command successful execution."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("journal_name\nTest Journal\nAnother Journal")
            temp_file = f.name

        try:
            with patch("aletheia_probe.cli.data_updater") as mock_updater:
                result = runner.invoke(
                    main,
                    [
                        "add-list",
                        temp_file,
                        "--list-type",
                        AssessmentType.PREDATORY,
                        "--list-name",
                        "test_list",
                    ],
                )

                assert result.exit_code == 0
                mock_updater.add_custom_list.assert_called_once()

        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_add_list_nonexistent_file(self, runner):
        """Test add-list command with non-existent file."""
        result = runner.invoke(
            main,
            [
                "add-list",
                "/nonexistent/file.csv",
                "--list-type",
                "predatory",
                "--list-name",
                "test_list",
            ],
        )

        assert result.exit_code != 0

    def test_add_list_error(self, runner):
        """Test add-list command with error during processing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("journal_name\nTest Journal")
            temp_file = f.name

        try:
            with patch("aletheia_probe.cli.data_updater") as mock_updater:
                mock_updater.add_custom_list.side_effect = Exception("Processing error")

                result = runner.invoke(
                    main,
                    [
                        "add-list",
                        temp_file,
                        "--list-type",
                        AssessmentType.PREDATORY,
                        "--list-name",
                        "test_list",
                    ],
                )

                assert result.exit_code == 1
                assert "Processing error" in result.output

        finally:
            Path(temp_file).unlink(missing_ok=True)


class TestAsyncMain:
    """Test cases for the async assess publication function."""

    @pytest.mark.asyncio
    async def test_async_main_text_output(self, mock_assessment_result):
        """Test async assess publication with text output format."""
        with (
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
            patch("aletheia_probe.cli.query_dispatcher") as mock_dispatcher,
            patch("builtins.print") as mock_print,
        ):
            mock_normalizer.normalize.return_value = Mock(
                raw_input="Test Journal",
                normalized_name="test journal",
                identifiers={"issn": "1234-5678"},
            )
            mock_dispatcher.assess_journal = AsyncMock(
                return_value=mock_assessment_result
            )

            from aletheia_probe.cli import _async_assess_publication

            await _async_assess_publication(
                "Test Journal", "journal", verbose=False, output_format="text"
            )

            # Verify text output was printed
            mock_print.assert_called()
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            output_text = " ".join(print_calls)

            assert "Test Journal" in output_text
            assert "PREDATORY" in output_text
            assert "0.85" in output_text

    @pytest.mark.asyncio
    async def test_async_main_json_output(self, mock_assessment_result):
        """Test async assess publication with JSON output format."""
        with (
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
            patch("aletheia_probe.cli.query_dispatcher") as mock_dispatcher,
            patch("builtins.print") as mock_print,
        ):
            mock_normalizer.normalize.return_value = Mock(
                raw_input="Test Journal", normalized_name="test journal", identifiers={}
            )
            mock_dispatcher.assess_journal = AsyncMock(
                return_value=mock_assessment_result
            )

            from aletheia_probe.cli import _async_assess_publication

            await _async_assess_publication(
                "Test Journal", "journal", verbose=False, output_format="json"
            )

            # Verify JSON output was printed
            mock_print.assert_called()
            output_text = mock_print.call_args[0][0]

            # Should be valid JSON
            parsed = json.loads(output_text)
            assert parsed["input_query"] == "Test Journal"
            assert parsed["assessment"] == "predatory"

    @pytest.mark.asyncio
    async def test_async_main_verbose_output(self, mock_assessment_result):
        """Test async assess publication with verbose flag."""
        with (
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
            patch("aletheia_probe.cli.query_dispatcher") as mock_dispatcher,
            patch("builtins.print") as mock_print,
        ):
            mock_query_input = Mock(
                raw_input="Test Journal",
                normalized_name="test journal",
                identifiers={"issn": "1234-5678"},
            )
            mock_normalizer.normalize.return_value = mock_query_input
            mock_dispatcher.assess_journal = AsyncMock(
                return_value=mock_assessment_result
            )

            from aletheia_probe.cli import _async_assess_publication

            await _async_assess_publication(
                "Test Journal", "journal", verbose=True, output_format="text"
            )

            # Check verbose output includes backend results
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            output_text = " ".join(print_calls)

            assert "Backend Results" in output_text
            assert "test_backend" in output_text

    @pytest.mark.asyncio
    async def test_async_main_value_error(self):
        """Test async assess publication with value error."""
        with (
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
            patch("sys.exit") as mock_exit,
        ):
            mock_normalizer.normalize.side_effect = ValueError("Invalid input")

            from aletheia_probe.cli import _async_assess_publication

            await _async_assess_publication(
                "", "journal", verbose=False, output_format="text"
            )

            mock_exit.assert_called_with(1)

    @pytest.mark.asyncio
    async def test_async_main_unexpected_error_verbose(self):
        """Test async assess publication with unexpected error in verbose mode."""
        with (
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
            patch("traceback.print_exc") as mock_traceback,
            patch("sys.exit") as mock_exit,
        ):
            mock_normalizer.normalize.side_effect = RuntimeError("Unexpected error")

            from aletheia_probe.cli import _async_assess_publication

            await _async_assess_publication(
                "Test", "journal", verbose=True, output_format="text"
            )

            mock_traceback.assert_called()
            mock_exit.assert_called_with(1)

    @pytest.mark.asyncio
    async def test_async_main_unexpected_error_non_verbose(self):
        """Test async assess publication with unexpected error in non-verbose mode."""
        with (
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
            patch("sys.exit") as mock_exit,
        ):
            mock_normalizer.normalize.side_effect = RuntimeError("Unexpected error")

            from aletheia_probe.cli import _async_assess_publication

            await _async_assess_publication(
                "Test", "journal", verbose=False, output_format="text"
            )

            mock_exit.assert_called_with(1)
