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
from aletheia_probe.fallback_chain import QueryFallbackChain
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
                fallback_chain=QueryFallbackChain([]),
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
            mock_async_assess.assert_called_once_with(
                "Test Journal", "journal", True, "text"
            )

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
            mock_async_assess.assert_called_once_with(
                "Test Journal", "journal", False, "json"
            )

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

    def test_sync_command_with_force(self, runner, mock_cache_sync_manager):
        """Test sync command with force flag."""

        # Wrap the sync method to verify calls
        original_sync = mock_cache_sync_manager.sync_cache_with_config
        mock_sync = Mock(side_effect=original_sync)
        mock_cache_sync_manager.sync_cache_with_config = mock_sync

        def run_coro(coro):
            """Run coroutine and return empty dict."""
            coro.close()  # Close without running
            return {}

        with patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro) as mock_run:
            result = runner.invoke(main, ["sync", "--force"])

            assert result.exit_code == 0
            # Verify force=True was passed to sync_cache_with_config
            mock_sync.assert_called_once_with(
                force=True, backend_filter=None, show_progress=True
            )

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


class TestCustomListCommand:
    """Test cases for the custom-list command."""

    def test_custom_list_add_success(self, runner):
        """Test custom-list add command successful execution."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("journal_name\nTest Journal\nAnother Journal")
            temp_file = f.name

        try:
            with patch(
                "aletheia_probe.cache.custom_list_manager.CustomListManager"
            ) as mock_manager_class:
                mock_manager = Mock()
                mock_manager_class.return_value = mock_manager

                result = runner.invoke(
                    main,
                    [
                        "custom-list",
                        "add",
                        temp_file,
                        "--list-type",
                        AssessmentType.PREDATORY,
                        "--list-name",
                        "test_list",
                    ],
                )

                assert result.exit_code == 0
                mock_manager.add_custom_list.assert_called_once_with(
                    "test_list", temp_file, AssessmentType.PREDATORY
                )

        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_custom_list_add_nonexistent_file(self, runner):
        """Test custom-list add command with non-existent file."""
        result = runner.invoke(
            main,
            [
                "custom-list",
                "add",
                "/nonexistent/file.csv",
                "--list-type",
                "predatory",
                "--list-name",
                "test_list",
            ],
        )

        assert result.exit_code != 0

    def test_custom_list_add_error(self, runner):
        """Test custom-list add command with error during processing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("journal_name\nTest Journal")
            temp_file = f.name

        try:
            with patch(
                "aletheia_probe.cache.custom_list_manager.CustomListManager"
            ) as mock_manager_class:
                mock_manager = Mock()
                mock_manager.add_custom_list.side_effect = ValueError("Duplicate name")
                mock_manager_class.return_value = mock_manager

                result = runner.invoke(
                    main,
                    [
                        "custom-list",
                        "add",
                        temp_file,
                        "--list-type",
                        AssessmentType.PREDATORY,
                        "--list-name",
                        "test_list",
                    ],
                )

                assert result.exit_code == 1
                assert "Duplicate name" in result.output

        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_custom_list_list_success(self, runner):
        """Test custom-list list command successful execution."""
        mock_lists = [
            {
                "list_name": "test_list",
                "file_path": "/path/to/test.csv",
                "list_type": "predatory",
                "enabled": True,
                "created_at": "2024-01-01 12:00:00",
            }
        ]

        with patch(
            "aletheia_probe.cache.custom_list_manager.CustomListManager"
        ) as mock_manager_class:
            mock_manager = Mock()
            mock_manager.get_all_custom_lists.return_value = mock_lists
            mock_manager_class.return_value = mock_manager

            with patch("pathlib.Path.exists", return_value=True):
                result = runner.invoke(main, ["custom-list", "list"])

                assert result.exit_code == 0
                assert "test_list" in result.output
                assert "predatory" in result.output
                mock_manager.get_all_custom_lists.assert_called_once()

    def test_custom_list_list_empty(self, runner):
        """Test custom-list list command with no lists."""
        with patch(
            "aletheia_probe.cache.custom_list_manager.CustomListManager"
        ) as mock_manager_class:
            mock_manager = Mock()
            mock_manager.get_all_custom_lists.return_value = []
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(main, ["custom-list", "list"])

            assert result.exit_code == 0
            assert "No custom lists found" in result.output

    def test_custom_list_remove_success(self, runner):
        """Test custom-list remove command successful execution."""
        with patch(
            "aletheia_probe.cache.custom_list_manager.CustomListManager"
        ) as mock_manager_class:
            mock_manager = Mock()
            mock_manager.custom_list_exists.return_value = True
            mock_manager.remove_custom_list.return_value = True
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(
                main, ["custom-list", "remove", "test_list", "--confirm"]
            )

            assert result.exit_code == 0
            mock_manager.remove_custom_list.assert_called_once_with("test_list")

    def test_custom_list_remove_not_found(self, runner):
        """Test custom-list remove command with non-existent list."""
        with patch(
            "aletheia_probe.cache.custom_list_manager.CustomListManager"
        ) as mock_manager_class:
            mock_manager = Mock()
            mock_manager.custom_list_exists.return_value = False
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(
                main, ["custom-list", "remove", "test_list", "--confirm"]
            )

            assert result.exit_code == 1
            assert "not found" in result.output


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
                identifiers={"issn": "1234-5679"},
                extracted_acronym_mappings={},
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
                raw_input="Test Journal",
                normalized_name="test journal",
                identifiers={},
                extracted_acronym_mappings={},
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
                identifiers={"issn": "1234-5679"},
                extracted_acronym_mappings={},
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


class TestConferenceAcronymCommands:
    """Tests for acronym command group."""

    def test_acronym_status_empty(self, runner):
        """Test acronym status command with empty database."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.get_acronym_stats.return_value = {"total_count": 0}
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(main, ["acronym", "status"])

            assert result.exit_code == 0
            assert "empty" in result.output.lower()

    def test_acronym_status_with_data(self, runner):
        """Test acronym status command with data."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.get_acronym_stats.return_value = {"total_count": 2}
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(main, ["acronym", "status"])

            assert result.exit_code == 0
            assert "2" in result.output

    def test_acronym_stats(self, runner):
        """Test acronym stats command."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.get_acronym_stats.return_value = {
                "total_count": 5,
            }
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(main, ["acronym", "stats"])

            assert result.exit_code == 0
            assert "5" in result.output

    def test_acronym_stats_empty(self, runner):
        """Test acronym stats command with empty database."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.get_acronym_stats.return_value = {"total_count": 0}
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(main, ["acronym", "stats"])

            assert result.exit_code == 0
            assert "empty" in result.output.lower()

    def test_acronym_list(self, runner):
        """Test acronym list command."""
        with (
            patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache,
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
        ):
            mock_cache = MagicMock()
            mock_cache.list_all_acronyms.return_value = [
                {
                    "acronym": "ICML",
                    "normalized_name": "international conference on machine learning",
                    "entity_type": "conference",
                    "usage_count": 5,
                },
                {
                    "acronym": "CVPR",
                    "normalized_name": "computer vision and pattern recognition",
                    "entity_type": "conference",
                    "usage_count": 3,
                },
            ]
            mock_cache.get_acronym_stats.return_value = {"total_count": 2}
            mock_acronym_cache.return_value = mock_cache

            # Mock the normalize_case function to return title-cased names for display
            with patch(
                "aletheia_probe.cli.normalize_case",
                side_effect=lambda text: text.title(),
            ):
                result = runner.invoke(main, ["acronym", "list"])

                assert result.exit_code == 0
                assert "ICML" in result.output
                assert "CVPR" in result.output
                assert "count:" in result.output

    def test_acronym_list_empty(self, runner):
        """Test acronym list command with empty database."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.list_all_acronyms.return_value = []
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(main, ["acronym", "list"])

            assert result.exit_code == 0
            assert "No acronyms found" in result.output

    def test_acronym_list_with_limit(self, runner):
        """Test acronym list command with limit option."""
        with (
            patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache,
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
        ):
            mock_cache = MagicMock()
            mock_cache.list_all_acronyms.return_value = [
                {
                    "acronym": "ICML",
                    "normalized_name": "international conference on machine learning",
                    "entity_type": "conference",
                    "usage_count": 5,
                }
            ]
            mock_cache.get_acronym_stats.return_value = {"total_count": 10}
            mock_acronym_cache.return_value = mock_cache

            # Mock the normalize_case function to return title-cased names for display
            with patch(
                "aletheia_probe.cli.normalize_case",
                side_effect=lambda text: text.title(),
            ):
                result = runner.invoke(main, ["acronym", "list", "--limit", "1"])

                assert result.exit_code == 0
                assert "Showing 1 of 10" in result.output

    def test_acronym_clear_with_confirm(self, runner):
        """Test acronym clear command with --confirm flag."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.clear_acronym_database.return_value = 5
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(main, ["acronym", "clear", "--confirm"])

            assert result.exit_code == 0
            assert "5" in result.output
            mock_cache.clear_acronym_database.assert_called_once()

    def test_acronym_clear_without_confirm_abort(self, runner):
        """Test acronym clear command without confirm - user aborts."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_acronym_cache.return_value = mock_cache

            # Simulate user selecting 'n' for no
            result = runner.invoke(main, ["acronym", "clear"], input="n\n")

            assert result.exit_code == 1
            # Should not have called clear if user aborted
            mock_cache.clear_acronym_database.assert_not_called()

    def test_acronym_clear_without_confirm_proceed(self, runner):
        """Test acronym clear command without confirm - user proceeds."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.clear_acronym_database.return_value = 3
            mock_acronym_cache.return_value = mock_cache

            # Simulate user selecting 'y' for yes
            result = runner.invoke(main, ["acronym", "clear"], input="y\n")

            assert result.exit_code == 0
            assert "3" in result.output
            mock_cache.clear_acronym_database.assert_called_once()

    def test_acronym_clear_already_empty(self, runner):
        """Test acronym clear command when database is already empty."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.clear_acronym_database.return_value = 0
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(main, ["acronym", "clear", "--confirm"])

            assert result.exit_code == 0
            assert "already empty" in result.output.lower()

    def test_acronym_add(self, runner):
        """Test acronym add command."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(
                main,
                [
                    "acronym",
                    "add",
                    "ICML",
                    "International Conference on Machine Learning",
                    "--entity-type",
                    "conference",
                ],
            )

            assert result.exit_code == 0
            assert "ICML" in result.output
            assert "International Conference on Machine Learning" in result.output
            mock_cache.store_acronym_mapping.assert_called_once_with(
                "ICML",
                "International Conference on Machine Learning",
                "conference",
                "manual",
            )

    def test_acronym_add_with_source(self, runner):
        """Test acronym add command with custom source."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(
                main,
                [
                    "acronym",
                    "add",
                    "CVPR",
                    "Computer Vision and Pattern Recognition",
                    "--entity-type",
                    "conference",
                    "--source",
                    "external_database",
                ],
            )

            assert result.exit_code == 0
            assert "external_database" in result.output
            mock_cache.store_acronym_mapping.assert_called_once_with(
                "CVPR",
                "Computer Vision and Pattern Recognition",
                "conference",
                "external_database",
            )

    def test_acronym_add_error(self, runner):
        """Test acronym add command with error."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.store_acronym_mapping.side_effect = Exception("Database error")
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(
                main,
                [
                    "acronym",
                    "add",
                    "TEST",
                    "Test Conference",
                    "--entity-type",
                    "conference",
                ],
            )

            assert result.exit_code == 1
            assert "Error" in result.output
