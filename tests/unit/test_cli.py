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
    QueryInput,
    VenueType,
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
                "Test Journal",
                "journal",
                True,
                "text",
                use_acronyms=True,
                confidence_min=0.8,
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
                "Test Journal",
                "journal",
                False,
                "json",
                use_acronyms=True,
                confidence_min=0.8,
            )

    def test_assess_with_no_acronyms_flag(self, runner):
        """Test journal command with --no-acronyms flag."""
        real_asyncio_run = asyncio.run

        def run_coro(coro):
            return real_asyncio_run(coro)

        with (
            patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro),
            patch("aletheia_probe.cli._async_assess_publication") as mock_async_assess,
        ):
            mock_async_assess.return_value = None

            result = runner.invoke(main, ["journal", "Test Journal", "--no-acronyms"])

            assert result.exit_code == 0
            mock_async_assess.assert_called_once_with(
                "Test Journal",
                "journal",
                False,
                "text",
                use_acronyms=False,
                confidence_min=0.8,
            )

    def test_assess_with_confidence_min(self, runner):
        """Test journal command with --confidence-min override."""
        real_asyncio_run = asyncio.run

        def run_coro(coro):
            return real_asyncio_run(coro)

        with (
            patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro),
            patch("aletheia_probe.cli._async_assess_publication") as mock_async_assess,
        ):
            mock_async_assess.return_value = None

            result = runner.invoke(
                main,
                ["journal", "Test Journal", "--confidence-min", "0.9"],
            )

            assert result.exit_code == 0
            mock_async_assess.assert_called_once_with(
                "Test Journal",
                "journal",
                False,
                "text",
                use_acronyms=True,
                confidence_min=0.9,
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

        mock_registry = Mock()
        mock_registry.get_backend_names.return_value = [
            "bealls",
            "dblp_venues",
            "doaj",
            "ror_snapshot",
        ]

        with (
            patch(
                "aletheia_probe.backends.base.get_backend_registry",
                return_value=mock_registry,
            ),
            patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro) as mock_run,
        ):
            result = runner.invoke(main, ["sync", "--force"])

            assert result.exit_code == 0
            # Verify force=True was passed to sync_cache_with_config
            mock_sync.assert_called_once_with(
                force=True,
                backend_filter=["bealls", "doaj"],
                show_progress=True,
            )

    def test_sync_command_include_large_datasets(self, runner, mock_cache_sync_manager):
        """Test sync command with include-large-datasets flag."""
        original_sync = mock_cache_sync_manager.sync_cache_with_config
        mock_sync = Mock(side_effect=original_sync)
        mock_cache_sync_manager.sync_cache_with_config = mock_sync

        def run_coro(coro):
            """Run coroutine and return empty dict."""
            coro.close()
            return {}

        with patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro):
            result = runner.invoke(main, ["sync", "--include-large-datasets"])

            assert result.exit_code == 0
            mock_sync.assert_called_once_with(
                force=False, backend_filter=None, show_progress=True
            )

    def test_sync_command_explicit_backend_names(self, runner, mock_cache_sync_manager):
        """Test sync command with explicit backend names."""
        original_sync = mock_cache_sync_manager.sync_cache_with_config
        mock_sync = Mock(side_effect=original_sync)
        mock_cache_sync_manager.sync_cache_with_config = mock_sync

        def run_coro(coro):
            """Run coroutine and return empty dict."""
            coro.close()
            return {}

        with patch("aletheia_probe.cli.asyncio.run", side_effect=run_coro):
            result = runner.invoke(main, ["sync", "dblp_venues"])

            assert result.exit_code == 0
            mock_sync.assert_called_once_with(
                force=False, backend_filter=["dblp_venues"], show_progress=True
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

    @pytest.mark.asyncio
    async def test_async_main_conference_uses_conference_acronym_lookup(
        self, mock_assessment_result
    ):
        """Conference command should normalize with conference-scoped acronym lookup."""
        with (
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
            patch("aletheia_probe.cli.query_dispatcher") as mock_dispatcher,
            patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache,
            patch("builtins.print"),
        ):
            mock_query_input = Mock(
                raw_input="AGENTS",
                normalized_name="agents",
                identifiers={},
                extracted_acronym_mappings={},
                venue_type=VenueType.UNKNOWN,
            )
            mock_normalizer.normalize.return_value = mock_query_input
            mock_dispatcher.assess_journal = AsyncMock(
                return_value=mock_assessment_result
            )

            mock_cache = MagicMock()
            mock_cache.get_full_name_for_acronym.return_value = (
                "proceedings of the international conference on autonomous agents"
            )
            mock_acronym_cache.return_value = mock_cache

            from aletheia_probe.cli import _async_assess_publication

            await _async_assess_publication(
                "AGENTS", "conference", verbose=False, output_format="text"
            )

            normalize_kwargs = mock_normalizer.normalize.call_args.kwargs
            lookup = normalize_kwargs["acronym_lookup"]
            lookup("AGENTS")
            mock_cache.get_full_name_for_acronym.assert_called_with(
                "AGENTS", "conference", min_confidence=0.8
            )
            assert mock_query_input.venue_type == VenueType.CONFERENCE

    @pytest.mark.asyncio
    async def test_async_main_selects_best_acronym_candidate(self):
        """Choose strongest result among acronym workflow candidates."""
        with (
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
            patch("aletheia_probe.cli.query_dispatcher") as mock_dispatcher,
            patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache,
            patch("builtins.print") as mock_print,
        ):

            def normalize_side_effect(
                raw_text: str, acronym_lookup: object = None
            ) -> QueryInput:
                return QueryInput(
                    raw_input=raw_text,
                    normalized_name=raw_text.lower(),
                    identifiers={},
                    aliases=[],
                    extracted_acronym_mappings={},
                    venue_type=VenueType.UNKNOWN,
                )

            mock_normalizer.normalize.side_effect = normalize_side_effect
            mock_normalizer._is_standalone_acronym.return_value = False

            mock_cache = MagicMock()
            mock_cache.get_variant_match.return_value = {
                "canonical": (
                    "proceedings of the international conference on autonomous agents"
                ),
                "acronym": "AGENTS",
            }
            mock_cache.get_issns.return_value = []
            mock_cache.get_full_name_for_acronym.return_value = None
            mock_cache.get_issn_match.return_value = None
            mock_acronym_cache.return_value = mock_cache

            unknown_result = AssessmentResult(
                input_query="q1",
                assessment=AssessmentType.UNKNOWN,
                confidence=0.2,
                overall_score=0.0,
                backend_results=[],
                metadata=None,
                reasoning=[],
                processing_time=0.1,
            )
            legit_result = AssessmentResult(
                input_query="q2",
                assessment=AssessmentType.LEGITIMATE,
                confidence=0.85,
                overall_score=0.8,
                backend_results=[],
                metadata=None,
                reasoning=[],
                processing_time=0.1,
            )

            async def assess_side_effect(query_input: QueryInput) -> AssessmentResult:
                if query_input.raw_input == "AGENTS":
                    return legit_result
                return unknown_result

            mock_dispatcher.assess_journal = AsyncMock(side_effect=assess_side_effect)

            from aletheia_probe.cli import _async_assess_publication

            await _async_assess_publication(
                "proceedings of the international conference on autonomous agents",
                "conference",
                verbose=False,
                output_format="text",
            )

            output_text = " ".join(call[0][0] for call in mock_print.call_args_list)
            assert "Assessment: LEGITIMATE" in output_text
            assert "Acronym workflow: tried" in output_text
            assert "Tried Candidates:" in output_text
            assert "[✓] variant->acronym: AGENTS" in output_text

    @pytest.mark.asyncio
    async def test_async_main_skips_issn_candidate_on_title_mismatch(self):
        """Skip ISSN candidate when resolved title does not match expected venue."""
        with (
            patch("aletheia_probe.cli.input_normalizer") as mock_normalizer,
            patch("aletheia_probe.cli.query_dispatcher") as mock_dispatcher,
            patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache,
            patch(
                "aletheia_probe.cli._resolve_issn_title",
                new=AsyncMock(return_value="Lecture Notes in Computer Science"),
            ),
            patch("builtins.print"),
        ):

            def normalize_side_effect(
                raw_text: str, acronym_lookup: object = None
            ) -> QueryInput:
                return QueryInput(
                    raw_input=raw_text,
                    normalized_name=raw_text.lower(),
                    identifiers={},
                    aliases=[],
                    extracted_acronym_mappings={},
                    venue_type=VenueType.UNKNOWN,
                )

            mock_normalizer.normalize.side_effect = normalize_side_effect
            mock_normalizer._is_standalone_acronym.return_value = False

            mock_cache = MagicMock()
            mock_cache.get_variant_match.return_value = {
                "canonical": (
                    "proceedings of the international conference on "
                    "artificial intelligence in education"
                ),
                "acronym": "AIED",
            }
            mock_cache.get_issns.return_value = ["0302-9743"]
            mock_cache.get_full_name_for_acronym.return_value = None
            mock_cache.get_issn_match.return_value = None
            mock_acronym_cache.return_value = mock_cache

            unknown_result = AssessmentResult(
                input_query="q",
                assessment=AssessmentType.UNKNOWN,
                confidence=0.2,
                overall_score=0.0,
                backend_results=[],
                metadata=None,
                reasoning=[],
                processing_time=0.1,
            )
            mock_dispatcher.assess_journal = AsyncMock(return_value=unknown_result)

            from aletheia_probe.cli import _async_assess_publication

            await _async_assess_publication(
                "AIED",
                "conference",
                verbose=False,
                output_format="text",
                confidence_min=0.5,
            )

            # input + variant/full; variant/acronym is duplicate of input and ISSN is skipped
            assert mock_dispatcher.assess_journal.await_count == 2


class TestConferenceAcronymCommands:
    """Tests for acronym command group."""

    def test_acronym_status_empty(self, runner):
        """Test acronym status command with empty database."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.get_full_stats.return_value = {
                "total_acronyms": 0,
                "total_variants": 0,
                "total_issns": 0,
                "by_entity_type": [],
            }
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(main, ["acronym", "status"])

            assert result.exit_code == 0
            assert "empty" in result.output.lower()

    def test_acronym_status_with_data(self, runner):
        """Test acronym status command with data."""
        with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
            mock_cache = MagicMock()
            mock_cache.get_full_stats.return_value = {
                "total_acronyms": 2,
                "total_variants": 10,
                "total_issns": 3,
                "by_entity_type": [
                    {
                        "entity_type": "conference",
                        "acronyms": 1,
                        "variants": 7,
                        "issns": 0,
                    },
                    {
                        "entity_type": "journal",
                        "acronyms": 1,
                        "variants": 3,
                        "issns": 3,
                    },
                ],
            }
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(main, ["acronym", "status"])

            assert result.exit_code == 0
            assert "2" in result.output

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

    def test_acronym_import_uses_source_override(self, runner):
        """Test acronym import stores explicit --source label."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "acronyms": [
                        {
                            "acronym": "ICML",
                            "entity_type": "conference",
                            "canonical": "international conference on machine learning",
                        }
                    ]
                },
                f,
            )
            temp_file = f.name

        try:
            with patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache:
                mock_cache = MagicMock()
                mock_cache.import_acronyms.return_value = 1
                mock_acronym_cache.return_value = mock_cache

                result = runner.invoke(
                    main,
                    [
                        "acronym",
                        "import",
                        temp_file,
                        "--source",
                        "manual-curation",
                    ],
                )

                assert result.exit_code == 0
                mock_cache.import_acronyms.assert_called_once()
                assert (
                    mock_cache.import_acronyms.call_args.kwargs["source_file"]
                    == "manual-curation"
                )
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_acronym_sync_downloads_and_imports(self, runner):
        """Test acronym sync downloads latest release dataset and imports it."""
        release_payload = {
            "assets": [
                {
                    "name": "venue-acronyms-2025-curated.json",
                    "browser_download_url": "https://example.org/dataset.json",
                }
            ]
        }
        dataset_payload = {
            "acronyms": [
                {
                    "acronym": "AAAI",
                    "entity_type": "conference",
                    "canonical": "aaai conference on artificial intelligence",
                }
            ]
        }

        with (
            patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache,
            patch(
                "aletheia_probe.cli._fetch_https_json",
                new=AsyncMock(side_effect=[release_payload, dataset_payload]),
            ) as mock_fetch_json,
        ):
            mock_cache = MagicMock()
            mock_cache.import_acronyms.return_value = 1
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(main, ["acronym", "sync"])

            assert result.exit_code == 0
            mock_cache.import_acronyms.assert_called_once()
            assert (
                mock_cache.import_acronyms.call_args.kwargs["source_file"]
                == "venue-acronyms-2025-curated.json"
            )

    def test_acronym_sync_uses_source_override(self, runner):
        """Test acronym sync stores explicit --source label."""
        release_payload = {
            "assets": [
                {
                    "name": "venue-acronyms-2025-curated.json",
                    "browser_download_url": "https://example.org/dataset.json",
                }
            ]
        }
        dataset_payload = {
            "acronyms": [
                {
                    "acronym": "ICLR",
                    "entity_type": "conference",
                    "canonical": "international conference on learning representations",
                }
            ]
        }

        with (
            patch("aletheia_probe.cli.AcronymCache") as mock_acronym_cache,
            patch(
                "aletheia_probe.cli._fetch_https_json",
                new=AsyncMock(side_effect=[release_payload, dataset_payload]),
            ) as mock_fetch_json,
        ):
            mock_cache = MagicMock()
            mock_cache.import_acronyms.return_value = 1
            mock_acronym_cache.return_value = mock_cache

            result = runner.invoke(
                main, ["acronym", "sync", "--source", "github-release-v1"]
            )

            assert result.exit_code == 0
            mock_cache.import_acronyms.assert_called_once()
            assert (
                mock_cache.import_acronyms.call_args.kwargs["source_file"]
                == "github-release-v1"
            )
