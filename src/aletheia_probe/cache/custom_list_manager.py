# SPDX-License-Identifier: MIT
"""Custom journal list manager for persistent storage of user-provided lists.

This module provides the CustomListManager class to handle persistent storage
and management of custom journal lists. This solves the issue where custom list
registrations were lost between command invocations.

Key functionality:
- Store custom list metadata persistently in database
- Retrieve all registered custom lists
- Remove custom list registrations
- Auto-register custom lists on application startup
"""

import sqlite3
from pathlib import Path
from typing import Any

from ..enums import AssessmentType
from ..logging_config import get_detail_logger, get_status_logger
from .base import CacheBase


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class CustomListManager(CacheBase):
    """Manages persistent storage of custom journal lists."""

    def add_custom_list(
        self,
        list_name: str,
        file_path: str | Path,
        list_type: AssessmentType,
    ) -> None:
        """Add a custom list to persistent storage.

        Args:
            list_name: Unique name for the custom list
            file_path: Path to the CSV or JSON file containing journal data
            list_type: Assessment type for journals in this list

        Raises:
            ValueError: If list_name already exists or file_path doesn't exist
            sqlite3.Error: If database operation fails
        """
        file_path_obj = Path(file_path)

        # Validate file exists
        if not file_path_obj.exists():
            raise ValueError(f"File does not exist: {file_path_obj}")

        # Convert to absolute path for consistency
        absolute_path = str(file_path_obj.resolve())

        detail_logger.debug(
            f"Adding custom list '{list_name}' with file '{absolute_path}'"
        )

        with self.get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO custom_lists (list_name, file_path, list_type)
                    VALUES (?, ?, ?)
                    """,
                    (list_name, absolute_path, list_type.value),
                )
                detail_logger.info(
                    f"Successfully stored custom list '{list_name}' in database"
                )
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    raise ValueError(f"Custom list '{list_name}' already exists") from e
                raise

    def remove_custom_list(self, list_name: str) -> bool:
        """Remove a custom list from persistent storage.

        Args:
            list_name: Name of the custom list to remove

        Returns:
            True if list was removed, False if list didn't exist
        """
        detail_logger.debug(f"Removing custom list '{list_name}'")

        with self.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM custom_lists WHERE list_name = ?",
                (list_name,),
            )

            if cursor.rowcount > 0:
                detail_logger.info(f"Successfully removed custom list '{list_name}'")
                return True
            else:
                detail_logger.warning(f"Custom list '{list_name}' not found")
                return False

    def get_all_custom_lists(self) -> list[dict[str, Any]]:
        """Retrieve all registered custom lists.

        Returns:
            List of dictionaries containing custom list metadata:
            - list_name: str
            - file_path: str
            - list_type: str
            - enabled: bool
            - created_at: str
        """
        detail_logger.debug("Retrieving all custom lists from database")

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.execute(
                """
                SELECT list_name, file_path, list_type, enabled, created_at, updated_at
                FROM custom_lists
                ORDER BY created_at ASC
                """,
            )

            results = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                # Convert SQLite integer to boolean for enabled field
                row_dict["enabled"] = bool(row_dict["enabled"])
                results.append(row_dict)
            detail_logger.debug(f"Found {len(results)} custom lists")
            return results

    def get_enabled_custom_lists(self) -> list[dict[str, Any]]:
        """Retrieve only enabled custom lists.

        Returns:
            List of enabled custom lists with same format as get_all_custom_lists()
        """
        detail_logger.debug("Retrieving enabled custom lists from database")

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.execute(
                """
                SELECT list_name, file_path, list_type, enabled, created_at, updated_at
                FROM custom_lists
                WHERE enabled = TRUE
                ORDER BY created_at ASC
                """,
            )

            results = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                # Convert SQLite integer to boolean for enabled field
                row_dict["enabled"] = bool(row_dict["enabled"])
                results.append(row_dict)
            detail_logger.debug(f"Found {len(results)} enabled custom lists")
            return results

    def custom_list_exists(self, list_name: str) -> bool:
        """Check if a custom list with the given name exists.

        Args:
            list_name: Name of the custom list to check

        Returns:
            True if custom list exists, False otherwise
        """
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM custom_lists WHERE list_name = ?",
                (list_name,),
            )
            return cursor.fetchone() is not None


def auto_register_custom_lists() -> None:
    """Auto-register all enabled custom lists in the backend registry.

    This function should be called early in the application lifecycle to ensure
    custom lists are available for sync operations and assessments.

    Loads all enabled custom lists from the database and registers them
    with the backend registry so they can be used by the sync manager
    and assessment dispatcher.
    """
    from pathlib import Path

    from ..backends.base import get_backend_registry
    from ..backends.custom_list import CustomListBackend
    from ..enums import AssessmentType

    detail_logger.debug("Auto-registering custom lists from database")

    try:
        custom_list_manager = CustomListManager()
        custom_lists = custom_list_manager.get_enabled_custom_lists()

        if not custom_lists:
            detail_logger.debug("No enabled custom lists found for auto-registration")
            return

        backend_registry = get_backend_registry()
        registered_count = 0

        for custom_list in custom_lists:
            list_name = custom_list["list_name"]
            file_path = custom_list["file_path"]
            list_type_str = custom_list["list_type"]

            # Convert string back to enum
            try:
                list_type = AssessmentType(list_type_str)
            except ValueError:
                detail_logger.warning(
                    f"Invalid list_type '{list_type_str}' for custom list '{list_name}', skipping"
                )
                continue

            # Check if file still exists
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                detail_logger.warning(
                    f"File missing for custom list '{list_name}': {file_path}, skipping"
                )
                continue

            # Register the backend factory
            try:
                backend_registry.register_factory(
                    list_name,
                    lambda fp=file_path_obj,
                    lt=list_type,
                    ln=list_name: CustomListBackend(fp, lt, ln),
                    default_config={"enabled": True},
                )
                detail_logger.debug(
                    f"Auto-registered custom list '{list_name}' as backend"
                )
                registered_count += 1

            except Exception as e:
                detail_logger.warning(
                    f"Failed to register custom list '{list_name}': {e}"
                )
                continue

        if registered_count > 0:
            detail_logger.info(
                f"Auto-registered {registered_count} custom list(s) from database"
            )
        else:
            detail_logger.debug("No custom lists were auto-registered")

    except Exception as e:
        detail_logger.error(f"Failed to auto-register custom lists: {e}")
        # Don't raise - this shouldn't break the application
