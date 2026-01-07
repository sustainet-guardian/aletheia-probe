# SPDX-License-Identifier: MIT
"""Tests for CustomListSource data source."""

import csv
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.custom import CustomListSource


class TestCustomListSource:
    """Test cases for CustomListSource."""

    @pytest.fixture
    def source_json(self, tmp_path):
        """Fixture for JSON source."""
        file_path = tmp_path / "journals.json"
        return CustomListSource(file_path, AssessmentType.UNKNOWN, "custom_json")

    @pytest.fixture
    def source_csv(self, tmp_path):
        """Fixture for CSV source."""
        file_path = tmp_path / "journals.csv"
        return CustomListSource(file_path, AssessmentType.UNKNOWN, "custom_csv")

    def test_initialization(self, source_json):
        """Test initialization."""
        assert source_json.get_name() == "custom_json"
        assert source_json.get_list_type() == AssessmentType.UNKNOWN

    @patch("aletheia_probe.updater.sources.custom.DataSourceManager")
    def test_should_update_file_not_exists(self, mock_dsm_cls, source_json):
        """Test should_update when file does not exist."""
        # file_path is defined but file not created yet
        assert source_json.should_update() is False

    @patch("aletheia_probe.updater.sources.custom.DataSourceManager")
    def test_should_update_no_last_update(self, mock_dsm_cls, source_json):
        """Test should_update when no last update record exists."""
        source_json.file_path.touch()

        mock_dsm = mock_dsm_cls.return_value
        mock_dsm.get_source_last_updated.return_value = None

        assert source_json.should_update() is True

    @patch("aletheia_probe.updater.sources.custom.DataSourceManager")
    def test_should_update_file_newer(self, mock_dsm_cls, source_json):
        """Test should_update when file is newer than last update."""
        source_json.file_path.touch()

        mock_dsm = mock_dsm_cls.return_value
        # Set last update to past
        mock_dsm.get_source_last_updated.return_value = datetime.fromtimestamp(
            source_json.file_path.stat().st_mtime - 100
        )

        assert source_json.should_update() is True

    @patch("aletheia_probe.updater.sources.custom.DataSourceManager")
    def test_should_update_file_older(self, mock_dsm_cls, source_json):
        """Test should_update when file is older than last update."""
        source_json.file_path.touch()

        mock_dsm = mock_dsm_cls.return_value
        # Set last update to future (relative to file)
        mock_dsm.get_source_last_updated.return_value = datetime.fromtimestamp(
            source_json.file_path.stat().st_mtime + 100
        )

        assert source_json.should_update() is False

    @pytest.mark.asyncio
    async def test_fetch_data_json_success(self, source_json):
        """Test fetching data from JSON file."""
        data = [
            {"name": "Journal A", "issn": "1234-5678", "extra": "info"},
            {"journal_name": "Journal B", "publisher": "Pub B"},
        ]
        with open(source_json.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        journals = await source_json.fetch_data()

        assert len(journals) == 2
        assert journals[0]["journal_name"] == "Journal A"
        assert journals[0]["issn"] == "1234-5678"
        assert journals[0]["metadata"]["extra"] == "info"

        assert journals[1]["journal_name"] == "Journal B"
        assert journals[1]["publisher"] == "Pub B"

    @pytest.mark.asyncio
    async def test_fetch_data_csv_success(self, source_csv):
        """Test fetching data from CSV file."""
        with open(source_csv.file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "issn", "publisher", "extra"])
            writer.writerow(["Journal A", "1234-5678", "Pub A", "info"])
            # The code handles failures in rows gracefully, empty strings are valid but might be filtered?
            # Code: if journal_name: ...
            writer.writerow(["Journal B", "", "Pub B", ""])

        journals = await source_csv.fetch_data()

        assert len(journals) == 2
        assert journals[0]["journal_name"] == "Journal A"
        assert journals[0]["issn"] == "1234-5678"
        assert journals[0]["metadata"]["extra"] == "info"

        assert journals[1]["journal_name"] == "Journal B"

    @pytest.mark.asyncio
    async def test_fetch_data_unsupported_extension(self, tmp_path):
        """Test fetching data with unsupported extension."""
        file_path = tmp_path / "journals.txt"
        file_path.touch()
        source = CustomListSource(file_path, AssessmentType.UNKNOWN, "custom_txt")

        with patch(
            "aletheia_probe.updater.sources.custom.status_logger"
        ) as mock_logger:
            journals = await source.fetch_data()
            assert journals == []
            mock_logger.error.assert_called_with(
                "    custom_txt: Unsupported file format - .txt"
            )

    @pytest.mark.asyncio
    async def test_fetch_data_json_error(self, source_json):
        """Test error handling when JSON file is invalid."""
        with open(source_json.file_path, "w", encoding="utf-8") as f:
            f.write("{invalid json")

        with patch(
            "aletheia_probe.updater.sources.custom.status_logger"
        ) as mock_logger:
            journals = await source_json.fetch_data()
            assert journals == []
            assert mock_logger.error.called

    @pytest.mark.asyncio
    async def test_load_json_partial_data(self, source_json):
        """Test JSON with missing names."""
        data = [
            {"issn": "1234-5678"},  # No name
            {"name": "Journal A"},
        ]
        with open(source_json.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        journals = await source_json.fetch_data()
        assert len(journals) == 1
        assert journals[0]["journal_name"] == "Journal A"

    @pytest.mark.asyncio
    async def test_load_csv_partial_data(self, source_csv):
        """Test CSV with missing names."""
        with open(source_csv.file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "issn"])
            writer.writerow(["", "1234-5678"])  # No name
            writer.writerow(["Journal A", "9876-5432"])

        journals = await source_csv.fetch_data()
        assert len(journals) == 1
        assert journals[0]["journal_name"] == "Journal A"

    @pytest.mark.asyncio
    async def test_fetch_data_empty_json(self, source_json):
        """Test fetching data from empty JSON file."""
        with open(source_json.file_path, "w", encoding="utf-8") as f:
            f.write("[]")

        journals = await source_json.fetch_data()
        assert journals == []

    @pytest.mark.asyncio
    async def test_fetch_data_empty_csv(self, source_csv):
        """Test fetching data from empty CSV file."""
        with open(source_csv.file_path, "w", encoding="utf-8", newline="") as f:
            pass  # Create empty file

        # DictReader on empty file yields nothing
        journals = await source_csv.fetch_data()
        assert journals == []

    @pytest.mark.asyncio
    async def test_fetch_data_file_permission_error(self, source_json):
        """Test error handling when file processing fails."""
        source_json.file_path.touch()

        # Patch asyncio.to_thread to raise an exception
        with patch(
            "aletheia_probe.updater.sources.custom.asyncio.to_thread",
            side_effect=PermissionError("Access denied"),
        ):
            with patch(
                "aletheia_probe.updater.sources.custom.status_logger"
            ) as mock_logger:
                journals = await source_json.fetch_data()
                assert journals == []
                mock_logger.error.assert_called()
                args, _ = mock_logger.error.call_args
                assert "Permission denied" in args[0]
