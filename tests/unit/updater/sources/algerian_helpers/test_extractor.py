# SPDX-License-Identifier: MIT
"""Unit tests for ArchiveExtractor."""

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aletheia_probe.updater.sources.algerian_helpers.extractor import ArchiveExtractor


class TestArchiveExtractor:
    """Test suite for ArchiveExtractor class."""

    @pytest.mark.asyncio
    async def test_extract_zip_success(self, tmp_path: Path) -> None:
        """Test successful ZIP extraction."""
        # Create a test ZIP file
        zip_path = tmp_path / "test.zip"
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        extractor = ArchiveExtractor()
        result = await extractor.extract_zip(str(zip_path), str(temp_dir))

        assert result is not None
        extracted_dir = Path(result)
        assert extracted_dir.exists()
        assert (extracted_dir / "test.txt").exists()

    @pytest.mark.asyncio
    async def test_extract_zip_file_not_exists(self, tmp_path: Path) -> None:
        """Test extraction when ZIP file does not exist."""
        zip_path = tmp_path / "nonexistent.zip"
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        extractor = ArchiveExtractor()
        result = await extractor.extract_zip(str(zip_path), str(temp_dir))

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_zip_not_a_file(self, tmp_path: Path) -> None:
        """Test extraction when path points to a directory."""
        zip_path = tmp_path / "notafile"
        zip_path.mkdir()
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        extractor = ArchiveExtractor()
        result = await extractor.extract_zip(str(zip_path), str(temp_dir))

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_zip_invalid_extension(self, tmp_path: Path) -> None:
        """Test extraction with invalid file extension."""
        zip_path = tmp_path / "test.txt"
        zip_path.touch()
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        extractor = ArchiveExtractor()
        result = await extractor.extract_zip(str(zip_path), str(temp_dir))

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_zip_temp_dir_not_exists(self, tmp_path: Path) -> None:
        """Test extraction when temp directory does not exist."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        temp_dir = tmp_path / "nonexistent_temp"

        extractor = ArchiveExtractor()
        result = await extractor.extract_zip(str(zip_path), str(temp_dir))

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_zip_corrupted_file(self, tmp_path: Path) -> None:
        """Test extraction with corrupted ZIP file."""
        zip_path = tmp_path / "corrupted.zip"
        zip_path.write_text("not a valid zip file")
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        extractor = ArchiveExtractor()
        result = await extractor.extract_zip(str(zip_path), str(temp_dir))

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_zip_path_traversal(self, tmp_path: Path) -> None:
        """Test extraction prevents path traversal attacks."""
        zip_path = tmp_path / "malicious.zip"
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        # Create a ZIP with path traversal attempt
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Add a file with path traversal
            zf.writestr("../../../evil.txt", "malicious content")

        extractor = ArchiveExtractor()
        result = await extractor.extract_zip(str(zip_path), str(temp_dir))

        # Should fail due to security check
        assert result is None
