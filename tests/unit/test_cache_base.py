# SPDX-License-Identifier: MIT
"""Tests for CacheBase error handling."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aletheia_probe.cache.base import CacheBase


class TestCacheBaseErrorHandling:
    """Test error handling in CacheBase initialization."""

    def test_init_with_explicit_db_path(self):
        """Test initialization with explicit database path succeeds."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            cache_base = CacheBase(db_path=db_path)
            assert cache_base.db_path == db_path
        finally:
            db_path.unlink(missing_ok=True)

    def test_init_with_invalid_config_structure(self):
        """Test that AttributeError from invalid config is properly handled."""
        # Mock config manager that returns invalid config structure
        with patch("aletheia_probe.config.get_config_manager") as mock_config:
            # Create mock that raises AttributeError when accessing cache.db_path
            mock_config.return_value.load_config.return_value = MagicMock(spec=[])
            del mock_config.return_value.load_config.return_value.cache

            with pytest.raises(
                RuntimeError,
                match="Invalid config structure: missing 'cache.db_path' configuration",
            ):
                CacheBase()

    def test_init_with_directory_creation_failure(self):
        """Test that OSError from directory creation failure is properly handled."""
        with patch("aletheia_probe.config.get_config_manager") as mock_config:
            # Mock config that returns valid path
            mock_config.return_value.load_config.return_value.cache.db_path = (
                "/invalid/path/cache.db"
            )

            # Mock Path.mkdir to raise OSError
            with patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied")):
                with pytest.raises(
                    RuntimeError, match="Failed to create database directory"
                ):
                    CacheBase()

    def test_init_with_database_init_failure(self):
        """Test that sqlite3.Error from database init is properly handled."""
        with (
            patch("aletheia_probe.config.get_config_manager") as mock_config,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            db_path = Path(tmpdir) / "test.db"
            mock_config.return_value.load_config.return_value.cache.db_path = str(
                db_path
            )

            # Mock init_database to raise sqlite3.Error
            with patch(
                "aletheia_probe.cache.schema.init_database",
                side_effect=sqlite3.Error("Database locked"),
            ):
                with pytest.raises(
                    RuntimeError, match="Failed to initialize database at"
                ):
                    CacheBase()

    def test_init_from_config_success(self):
        """Test successful initialization from config."""
        with (
            patch("aletheia_probe.config.get_config_manager") as mock_config,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            db_path = Path(tmpdir) / "test.db"
            mock_config.return_value.load_config.return_value.cache.db_path = str(
                db_path
            )

            # Mock init_database to do nothing (we're testing error handling, not schema)
            with patch("aletheia_probe.cache.schema.init_database"):
                cache_base = CacheBase()
                assert cache_base.db_path == db_path
