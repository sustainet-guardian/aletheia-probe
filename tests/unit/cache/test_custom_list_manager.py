# SPDX-License-Identifier: MIT
"""Tests for the CustomListManager class."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from aletheia_probe.cache.custom_list_manager import (
    CustomListManager,
    auto_register_custom_lists,
)
from aletheia_probe.enums import AssessmentType


class TestCustomListManager:
    """Test cases for CustomListManager."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        # Initialize the database schema
        from aletheia_probe.cache.schema import init_database

        init_database(db_path)

        yield db_path

        # Cleanup
        db_path.unlink(missing_ok=True)

    @pytest.fixture
    def temp_csv_file(self):
        """Create a temporary CSV file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("journal_name\nTest Journal\nAnother Journal")
            csv_path = Path(f.name)

        yield csv_path

        # Cleanup
        csv_path.unlink(missing_ok=True)

    def test_add_custom_list_success(self, temp_db, temp_csv_file):
        """Test successful addition of custom list."""
        manager = CustomListManager(db_path=temp_db)

        manager.add_custom_list("test_list", temp_csv_file, AssessmentType.PREDATORY)

        # Verify it was added
        custom_lists = manager.get_all_custom_lists()
        assert len(custom_lists) == 1
        assert custom_lists[0]["list_name"] == "test_list"
        assert custom_lists[0]["list_type"] == "predatory"
        assert custom_lists[0]["enabled"] is True

    def test_add_custom_list_duplicate_name(self, temp_db, temp_csv_file):
        """Test adding custom list with duplicate name fails."""
        manager = CustomListManager(db_path=temp_db)

        # Add first list
        manager.add_custom_list("test_list", temp_csv_file, AssessmentType.PREDATORY)

        # Try to add duplicate
        with pytest.raises(ValueError, match="already exists"):
            manager.add_custom_list(
                "test_list", temp_csv_file, AssessmentType.LEGITIMATE
            )

    def test_add_custom_list_nonexistent_file(self, temp_db):
        """Test adding custom list with non-existent file fails."""
        manager = CustomListManager(db_path=temp_db)

        with pytest.raises(ValueError, match="File does not exist"):
            manager.add_custom_list(
                "test_list", "/nonexistent/file.csv", AssessmentType.PREDATORY
            )

    def test_remove_custom_list_success(self, temp_db, temp_csv_file):
        """Test successful removal of custom list."""
        manager = CustomListManager(db_path=temp_db)

        # Add list first
        manager.add_custom_list("test_list", temp_csv_file, AssessmentType.PREDATORY)

        # Remove it
        result = manager.remove_custom_list("test_list")
        assert result is True

        # Verify it's gone
        custom_lists = manager.get_all_custom_lists()
        assert len(custom_lists) == 0

    def test_remove_custom_list_not_found(self, temp_db):
        """Test removing non-existent custom list."""
        manager = CustomListManager(db_path=temp_db)

        result = manager.remove_custom_list("nonexistent")
        assert result is False

    def test_get_all_custom_lists_empty(self, temp_db):
        """Test getting custom lists when none exist."""
        manager = CustomListManager(db_path=temp_db)

        custom_lists = manager.get_all_custom_lists()
        assert custom_lists == []

    def test_get_enabled_custom_lists(self, temp_db, temp_csv_file):
        """Test getting only enabled custom lists."""
        manager = CustomListManager(db_path=temp_db)

        # Add list
        manager.add_custom_list("test_list", temp_csv_file, AssessmentType.PREDATORY)

        # Get enabled lists
        enabled_lists = manager.get_enabled_custom_lists()
        assert len(enabled_lists) == 1
        assert enabled_lists[0]["list_name"] == "test_list"
        assert enabled_lists[0]["enabled"] is True

    def test_custom_list_exists(self, temp_db, temp_csv_file):
        """Test checking if custom list exists."""
        manager = CustomListManager(db_path=temp_db)

        # Initially doesn't exist
        assert manager.custom_list_exists("test_list") is False

        # Add list
        manager.add_custom_list("test_list", temp_csv_file, AssessmentType.PREDATORY)

        # Now it exists
        assert manager.custom_list_exists("test_list") is True


class TestAutoRegisterCustomLists:
    """Test cases for auto_register_custom_lists function."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        # Initialize the database schema
        from aletheia_probe.cache.schema import init_database

        init_database(db_path)

        yield db_path

        # Cleanup
        db_path.unlink(missing_ok=True)

    @pytest.fixture
    def temp_csv_file(self):
        """Create a temporary CSV file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("journal_name\nTest Journal\nAnother Journal")
            csv_path = Path(f.name)

        yield csv_path

        # Cleanup
        csv_path.unlink(missing_ok=True)

    def test_auto_register_no_custom_lists(self, temp_db):
        """Test auto-registration with no custom lists."""
        with patch(
            "aletheia_probe.cache.custom_list_manager.CustomListManager"
        ) as mock_manager_class:
            mock_manager = mock_manager_class.return_value
            mock_manager.get_enabled_custom_lists.return_value = []

            # Should not raise any errors
            auto_register_custom_lists()

            mock_manager.get_enabled_custom_lists.assert_called_once()

    def test_auto_register_with_custom_lists(self, temp_db, temp_csv_file):
        """Test auto-registration with existing custom lists."""
        mock_custom_lists = [
            {
                "list_name": "test_list",
                "file_path": str(temp_csv_file),
                "list_type": "predatory",
                "enabled": True,
            }
        ]

        with (
            patch(
                "aletheia_probe.cache.custom_list_manager.CustomListManager"
            ) as mock_manager_class,
            patch(
                "aletheia_probe.backends.base.get_backend_registry"
            ) as mock_get_registry,
        ):
            mock_manager = mock_manager_class.return_value
            mock_manager.get_enabled_custom_lists.return_value = mock_custom_lists

            mock_registry = mock_get_registry.return_value

            auto_register_custom_lists()

            # Verify registration was called
            mock_registry.register_factory.assert_called_once()
            call_args = mock_registry.register_factory.call_args
            assert call_args[0][0] == "test_list"  # list_name
            assert call_args[1]["default_config"] == {"enabled": True}

    def test_auto_register_missing_file(self, temp_db):
        """Test auto-registration with missing file (should skip)."""
        mock_custom_lists = [
            {
                "list_name": "test_list",
                "file_path": "/nonexistent/file.csv",
                "list_type": "predatory",
                "enabled": True,
            }
        ]

        with (
            patch(
                "aletheia_probe.cache.custom_list_manager.CustomListManager"
            ) as mock_manager_class,
            patch(
                "aletheia_probe.backends.base.get_backend_registry"
            ) as mock_get_registry,
        ):
            mock_manager = mock_manager_class.return_value
            mock_manager.get_enabled_custom_lists.return_value = mock_custom_lists

            mock_registry = mock_get_registry.return_value

            auto_register_custom_lists()

            # Registration should not be called due to missing file
            mock_registry.register_factory.assert_not_called()

    def test_auto_register_invalid_list_type(self, temp_db, temp_csv_file):
        """Test auto-registration with invalid list type (should skip)."""
        mock_custom_lists = [
            {
                "list_name": "test_list",
                "file_path": str(temp_csv_file),
                "list_type": "invalid_type",
                "enabled": True,
            }
        ]

        with (
            patch(
                "aletheia_probe.cache.custom_list_manager.CustomListManager"
            ) as mock_manager_class,
            patch(
                "aletheia_probe.backends.base.get_backend_registry"
            ) as mock_get_registry,
        ):
            mock_manager = mock_manager_class.return_value
            mock_manager.get_enabled_custom_lists.return_value = mock_custom_lists

            mock_registry = mock_get_registry.return_value

            auto_register_custom_lists()

            # Registration should not be called due to invalid list_type
            mock_registry.register_factory.assert_not_called()

    def test_auto_register_exception_handling(self, temp_db):
        """Test auto-registration handles exceptions gracefully."""
        with patch(
            "aletheia_probe.cache.custom_list_manager.CustomListManager"
        ) as mock_manager_class:
            mock_manager = mock_manager_class.return_value
            mock_manager.get_enabled_custom_lists.side_effect = Exception(
                "Database error"
            )

            # Should not raise - exceptions are caught and logged
            auto_register_custom_lists()
